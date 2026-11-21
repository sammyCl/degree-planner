import sqlite3
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

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
    return save_plan(connection, plan)


@app.put("/plans/{plan_id}", response_model=Plan)
def update_plan(plan_id: str, plan: Plan, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    return save_plan(connection, plan.model_copy(update={"plan_id": plan_id}))


@app.get("/plans/{plan_id}", response_model=Plan)
def get_plan(plan_id: str, connection: sqlite3.Connection = Depends(get_db)) -> Plan:
    try:
        return load_plan(connection, plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
