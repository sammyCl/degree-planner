import json
import logging
import sqlite3
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from degree_planner_backend.agent.chat_loop import run_chat
from degree_planner_backend.agent.chat_models import ChatRequest, ChatResponse
from degree_planner_backend.agent.loop import ClaudeCodeError, run_agent
from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse
from degree_planner_backend.agent.transcript_matcher import CatalogCourse, OutsideCourse
from degree_planner_backend.agent.transcript_matcher import suggest as suggest_equivalents
from degree_planner_backend.agent.transcript_reader import read_redacted
from degree_planner_backend.db import get_db
from degree_planner_backend.lookups import get_course
from degree_planner_backend.plan_models import CompletedCourse, Plan
from degree_planner_backend.plan_store import PlanNotFoundError, load_plan, save_plan
from degree_planner_backend.transcript_parser import (
    TranscriptParseError,
    parse_transcript_csv,
    parse_transcript_pdf,
    pdf_lines,
)
from degree_planner_backend.transfer_credit import TranscriptReading, load_equivalencies, read_transcript
from degree_planner_backend.validator import check_plan

logger = logging.getLogger(__name__)

app = FastAPI(title="Degree Planner API")


@app.exception_handler(RequestValidationError)
async def _on_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's default handler echoes each error's "input" back in the response; a lone
    surrogate in the request body (valid JSON, not valid text, e.g. "\\ud800") can't then be
    encoded as UTF-8, turning an ordinary 422 into a 500 (BUG-046). Drop "input" instead."""
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))


@app.exception_handler(Exception)
async def _on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Trial-ready API: an HTTPException or RequestValidationError is handled above or by FastAPI
    itself and never reaches this; this is only for a genuine bug or server problem we did not
    anticipate (e.g. a locked database). The real exception and traceback go to the server log
    (same principle as BUG-006: internals are never a student's problem or an attacker's map of
    this server); the response stays a plain, fixed message so the frontend has something to show
    and retry, instead of the connection just failing."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our end. Please try again in a moment."},
    )


@app.get("/health")
def health(connection: sqlite3.Connection = Depends(get_db)) -> dict[str, str]:
    connection.execute("SELECT 1")
    return {"status": "ok", "database": "ok"}


@app.post("/plans/check", response_model=Plan)
def check(plan: Plan, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    """Re-run the validator on a plan (e.g. after drag-and-drop moves a course)."""
    return check_plan(connection, plan)


@app.post("/plans", response_model=Plan)
def create_plan(plan: Plan, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    """Re-validate before saving: flags and summary.requirements_met are never trusted from the client."""
    return save_plan(connection, check_plan(connection, plan))


@app.put("/plans/{plan_id}", response_model=Plan)
def update_plan(plan_id: str, plan: Plan, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    checked = check_plan(connection, plan.model_copy(update={"plan_id": plan_id}))
    return save_plan(connection, checked)


@app.get("/plans/{plan_id}", response_model=Plan)
def get_plan(plan_id: str, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    try:
        return load_plan(connection, plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/plans/submit-setup", response_model=AgentResponse)
def submit_setup(request: AgentRequest, connection: sqlite3.Connection = Depends(get_db)) -> AgentResponse:
    """Setup form submitted: call the agent loop and return the plan it builds (or why it couldn't)."""
    try:
        return run_agent(connection, request)
    except ClaudeCodeError as exc:
        # The agent itself could not run (not installed, not signed in) - a server problem, not
        # something wrong with the student's setup, so 503 rather than 400.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Note for Midhat (from Samantha, agent/chat branch): this endpoint is new in your file. It only
# calls the chat loop (agent/chat_loop.py); nothing else in main.py changed. The format is
# docs/chat-format.md. The proposal is not saved here: the page saves it with POST /plans or
# PUT /plans/{plan_id} when the student clicks Apply, so the plan store is untouched.
@app.post("/plans/chat", response_model=ChatResponse)
def chat(request: ChatRequest, connection: sqlite3.Connection = Depends(get_db)) -> ChatResponse:
    """One chat message from the planner page: the chatbot's reply and any proposed plan change."""
    try:
        return run_chat(connection, request)
    except ClaudeCodeError as exc:
        # Same as submit_setup: the agent could not run at all, a server problem.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/transcripts/parse", response_model=list[CompletedCourse])
def parse_transcript(file: UploadFile = File(...)) -> list[CompletedCourse]:
    """Turn an uploaded transcript (CSV or PDF) into completed courses the student can review."""
    suffix = Path(file.filename or "").suffix.lower()
    contents = file.file.read()

    try:
        if suffix == ".csv":
            return parse_transcript_csv(contents.decode("utf-8"))
        if suffix == ".pdf":
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp.flush()
                return parse_transcript_pdf(Path(tmp.name))
        raise HTTPException(status_code=400, detail="Transcript must be a .csv or .pdf file")
    except TranscriptParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/transcripts/read", response_model=TranscriptReading)
def read_transcript_file(
    file: UploadFile = File(...),
    school: str | None = Form(None),
    connection: sqlite3.Connection = Depends(get_db),
) -> TranscriptReading:
    """Read a transcript for the setup page: the school it is from, its courses as Mines courses, and the courses
    from another school that still need a Mines equivalent (transfer_credit.py). `school` names the school when the
    student corrects it. The file is read from a temporary file and not kept."""
    suffix = Path(file.filename or "").suffix.lower()
    contents = file.file.read()

    def credits_of(code: str) -> float | None:
        try:
            return get_course(connection, code).credits
        except LookupError:  # NotFoundError or AmbiguousLookupError
            return None

    try:
        if suffix == ".csv":
            # our own CSV already uses Mines course codes
            return TranscriptReading(
                school=None, from_mines=True, courses=parse_transcript_csv(contents.decode("utf-8")), tes_url=load_equivalencies()["tes_url"]
            )
        if suffix == ".pdf":
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(contents)
                tmp.flush()
                # a layout the rules do not know is read by Claude, after personal details are removed; courses with
                # no saved match get a suggested Mines course (only codes, titles and credits are sent)
                return read_transcript(
                    pdf_lines(Path(tmp.name)), school=school, credits_of=credits_of, claude=read_redacted,
                    suggest=lambda courses, from_school: suggest_equivalents(
                        [OutsideCourse(c.code, c.title, c.credits) for c in courses], from_school, _catalog(connection)
                    ),
                )
        raise HTTPException(status_code=400, detail="Transcript must be a .csv or .pdf file")
    except TranscriptParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _catalog(connection: sqlite3.Connection) -> list[CatalogCourse]:
    """Every catalog course's code, title and credits, for suggesting transfer equivalents."""
    out: list[CatalogCourse] = []
    for code, data in connection.execute("SELECT code, data FROM courses"):
        course = json.loads(data)
        out.append(CatalogCourse(code, course.get("title", ""), float(course.get("credits") or 0)))
    return out
