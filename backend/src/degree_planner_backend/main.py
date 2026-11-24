import sqlite3
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

from degree_planner_backend.agent.chat_loop import run_chat
from degree_planner_backend.agent.chat_models import ChatRequest, ChatResponse
from degree_planner_backend.agent.loop import ClaudeCodeError, run_agent
from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse
from degree_planner_backend.db import get_db
from degree_planner_backend.plan_models import CompletedCourse, Plan
from degree_planner_backend.plan_store import PlanNotFoundError, load_plan, save_plan
from degree_planner_backend.transcript_parser import (
    TranscriptParseError,
    parse_transcript_csv,
    parse_transcript_pdf,
)
from degree_planner_backend.validator import check_plan

app = FastAPI(title="Degree Planner API")


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
