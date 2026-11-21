import pytest
from fastapi.testclient import TestClient

from degree_planner_backend import transcript_parser
from degree_planner_backend.main import app

client = TestClient(app)


def test_parse_transcript_endpoint_reads_csv() -> None:
    csv_text = (
        "code,credits,term,transfer_from\n"
        "MATH111,4.0,transfer,Front Range Community College\n"
        "CSCI200,4.0,Fall 2024,\n"
    )

    response = client.post(
        "/transcripts/parse",
        files={"file": ("transcript.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 200
    courses = response.json()
    assert [c["code"] for c in courses] == ["MATH111", "CSCI200"]
    assert courses[0]["transfer_from"] == "Front Range Community College"


def test_parse_transcript_endpoint_rejects_malformed_csv() -> None:
    response = client.post(
        "/transcripts/parse",
        files={"file": ("transcript.csv", "code,credits\nMATH111,4.0\n", "text/csv")},
    )

    assert response.status_code == 400


def test_parse_transcript_endpoint_rejects_unknown_extension() -> None:
    response = client.post(
        "/transcripts/parse",
        files={"file": ("transcript.txt", "whatever", "text/plain")},
    )

    assert response.status_code == 400
    assert ".csv or .pdf" in response.json()["detail"]


def test_parse_transcript_endpoint_reads_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdfReader:
        def __init__(self, _path: str) -> None:
            self.pages = [FakePage("Fall 2024\nCSCI200 Computer Science I A 4.00")]

    monkeypatch.setattr(transcript_parser, "PdfReader", FakePdfReader)

    response = client.post(
        "/transcripts/parse",
        files={"file": ("transcript.pdf", b"%PDF-fake-bytes", "application/pdf")},
    )

    assert response.status_code == 200
    courses = response.json()
    assert [(c["code"], c["term"], c["credits"]) for c in courses] == [("CSCI200", "Fall 2024", 4.0)]
