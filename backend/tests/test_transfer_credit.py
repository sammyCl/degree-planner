"""Reading real-layout transcripts: Mines' own unofficial transcript, a CCCS college's, and an unknown school's.

Every transcript here is synthetic (made-up student, made-up rows in the real layouts). Never commit a real one.
"""

import pytest
from fastapi.testclient import TestClient

from degree_planner_backend import transfer_credit
from degree_planner_backend.main import app
from degree_planner_backend.transcript_parser import _parse_transcript_lines
from degree_planner_backend.transfer_credit import MINES, load_equivalencies, read_transcript

# The Mines unofficial transcript's text as pypdf extracts it, including rows that wrap over lines.
MINES_TRANSCRIPT = """Colorado School of Mines
Unofficial Academic Transcript
STUDENT INFORMATION
Name
Test Student
TRANSFER CREDIT ACCEPTED BY INSTITUTION
SP20: IB Credit
Subject Course Title Grade Credit Hours Quality Points R
MATH 111 CALC FOR SCI & ENGRS I T 4.000
FREE 1XX Free Elective-Art History T 3.000
Attempt Hours Passed Hours Earned Hours GPA Hours Quality Points GPA
Current Term 7.000 7.000 7.000 0.000 0.000
FA19-SP21: Example State University
Subject Course Title Grade Credit Hours Quality Points R
CSCI 101 Intro to Computer Science T 3.000
FREE 1XX Free Elective: Example Course T 3.000
HASS 2XX HASS ELECTIVE: Example Topic T 3.000
EDNS 151 Design Proﬁciency T 3.000
201980: AP Credit
Subject Course Title Grade Credit Hours Quality Points R
FREE 1XX Free Elective: Example AP Course T 3.000
INSTITUTION CREDIT
Term: Spring 2024
Student Type
Continuing
Subject Course Campus Level Title Grade Credit
Hours
Quality
Points
R
CHGN 122 Main
Campus
UG PRINCIPLES OF CHEMISTRY II C 4.000 8.000
PHGN 200 Main
Campus
UG PHYSICS II F 4.000 0.000
Term Totals
(Undergraduate)
Term: Summer 2024
EBGN 321 Main
Campus
UG ENGINEERING
ECONOMICS
A 3.000 12.000
TRANSCRIPT TOTALS
Total Institution 7.000 7.000 7.000 7.000 20.000 2.857
COURSE(S) IN PROGRESS
Term: Fall 2024
Subject Course Campus Level Title Credit Hours
CSCI 261 Main Campus UG PROGRAMMING CONCEPTS 3.000
CSM 101 Main Campus UG FRESHMAN SUCCESS
SEMINAR
1.000
""".splitlines()

DATA = load_equivalencies()


def test_reads_every_kind_of_row_on_a_mines_transcript() -> None:
    reading = read_transcript(MINES_TRANSCRIPT)
    assert reading.school == MINES and reading.from_mines
    got = [(c.code, c.credits, c.term, c.transfer_from, c.in_progress) for c in reading.courses]
    assert got == [
        ("MATH111", 4.0, "transfer", "IB credit", False),
        ("FREE1XX-1", 3.0, "transfer", "IB credit", False),
        ("CSCI101", 3.0, "transfer", "Example State University", False),
        ("FREE1XX-2", 3.0, "transfer", "Example State University", False),
        ("HASS2XX-1", 3.0, "transfer", "Example State University", False),
        ("EDNS151", 3.0, "transfer", "Example State University", False),
        ("FREE1XX-3", 3.0, "aplcredit", None, False),
        ("CHGN122", 4.0, "Spring 2024", None, False),  # credits, not the 8.000 quality points
        ("EBGN321", 3.0, "Summer 2024", None, False),  # a row wrapped over five lines
        ("CSCI261", 3.0, "Fall 2024", None, True),
        ("CSM101", 1.0, "Fall 2024", None, True),
    ]
    assert reading.skipped == ["PHGN 200 PHYSICS II: grade F, no credit"]
    assert reading.unmatched == []


def test_keeps_the_transcript_s_title_and_fixes_ligatures() -> None:
    courses = {c.code: c for c in read_transcript(MINES_TRANSCRIPT).courses}
    assert courses["FREE1XX-2"].title == "Free Elective: Example Course"
    assert courses["EDNS151"].title == "Design Proficiency"
    assert courses["CSM101"].title == "FRESHMAN SUCCESS SEMINAR"


def test_the_old_parse_endpoint_function_reads_the_mines_layout_too() -> None:
    assert [c.code for c in _parse_transcript_lines(MINES_TRANSCRIPT)][:3] == ["MATH111", "FREE1XX-1", "CSCI101"]


CCCS_TRANSCRIPT = """Front Range Community College
Unofficial Transcript
Fall 2023
MAT 2410 Calculus I A 5.000
CHE 2111 Organic Chemistry I B 5.000
ENG 1021 English Composition I B 3.000
PHI 2018 Environmental Ethics A 3.000
ENG 1022 English Composition II B 3.000
Spring 2024
ECO 2001 Prin Macroeconomics B 3.000
ECO 2002 Prin Microeconomics A 3.000
EGG 1040 Engineering Projects A 3.000
PED 1004 Fitness Walking A 1.000
MAT 1340 College Algebra C- 4.000
""".splitlines()


def test_matches_a_cccs_transcript_to_the_preapproved_list() -> None:
    reading = read_transcript(CCCS_TRANSCRIPT, credits_of={"CHGN221": 3.0, "CHGN223": 2.0}.get)
    assert reading.school == "Front Range Community College"
    assert not reading.from_mines
    assert reading.system == "Colorado Community College System"
    got = [(c.code, c.credits) for c in reading.courses]
    assert got == [
        ("MATH111", 5.0),
        ("CHGN221", 3.0),  # one outside course, two Mines courses: split by Mines catalog credits
        ("CHGN223", 2.0),
        ("HASS100", 3.0),  # PHI 2018 with ENG 1022 makes HASS100 ...
        ("FREE1XX-1", 3.0),  # ... and the other's hours are a free elective
        ("EBGN201", 3.0),
        ("HASS2XX-1", 3.0),  # the second economics course is a CAS/HASS elective, not a second EBGN201
        ("EDNS151", 3.0),  # Front Range is one of the colleges where EGG 1040 counts as EDNS151
        ("PAGN1XX-1", 1.0),
    ]
    assert all(c.transfer_from == "Front Range Community College" and c.term == "transfer" for c in reading.courses)
    assert [(u.code, u.suggestion) for u in reading.unmatched] == [("ENG 1021", "FREE1XX")]
    assert reading.skipped == ["MAT 1340 College Algebra: grade C-; Mines needs a C or better to transfer"]


def test_egg1040_is_not_edns151_at_a_college_the_registrar_does_not_name() -> None:
    lines = ["Aims Community College", "Fall 2023", "EGG 1040 Engineering Projects A 3.000"]
    reading = read_transcript(lines)
    assert reading.courses == []
    assert [u.code for u in reading.unmatched] == ["EGG 1040"]


def test_a_school_with_no_saved_list_leaves_every_course_for_the_student_to_look_up_in_tes() -> None:
    lines = ["Example State University", "Official Transcript", "Fall 2022", "MATH 1401 Calculus I A 4.000", "CSCI 1300 Intro to Programming B+ 4.000"]
    reading = read_transcript(lines)
    assert reading.school == "Example State University"
    assert not reading.from_mines and reading.system is None
    assert reading.courses == []
    assert [(u.code, u.credits, u.suggestion) for u in reading.unmatched] == [("MATH 1401", 4.0, None), ("CSCI 1300", 4.0, None)]
    assert all("TES" in u.reason for u in reading.unmatched)
    assert reading.tes_url.startswith("https://tes.collegesource.com/")


def test_the_student_can_name_the_school_when_it_is_not_recognised() -> None:
    lines = ["Transcript", "Fall 2023", "MAT 2410 Calculus I A 5.000"]
    assert read_transcript(lines).school is None
    reading = read_transcript(lines, school="Red Rocks Community College")
    assert [c.code for c in reading.courses] == ["MATH111"]


def test_every_cccs_college_and_tes_link_are_in_the_saved_file() -> None:
    schools = DATA["systems"]["cccs"]["schools"]
    assert len(schools) == 15 and "Red Rocks Community College" in schools
    assert all(e["mines"] for e in DATA["equivalencies"])
    assert transfer_credit.EQUIVALENCIES_PATH.exists()


def test_read_endpoint_returns_the_reading(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("degree_planner_backend.main.pdf_lines", lambda _path: MINES_TRANSCRIPT)
    client = TestClient(app)
    response = client.post("/transcripts/read", files={"file": ("transcript.pdf", b"%PDF-1.4 synthetic", "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    assert body["school"] == MINES and body["from_mines"] is True
    assert body["courses"][0] == {
        "code": "MATH111", "credits": 4.0, "term": "transfer", "transfer_from": "IB credit",
        "title": "CALC FOR SCI & ENGRS I", "in_progress": False,
    }


def test_read_endpoint_takes_the_school_the_student_names(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("degree_planner_backend.main.pdf_lines", lambda _path: ["Transcript", "Fall 2023", "MAT 2410 Calculus I A 5.000"])
    def no_claude(_lines):  # type: ignore[no-untyped-def]
        raise RuntimeError("not in tests")
    monkeypatch.setattr("degree_planner_backend.main.read_redacted", no_claude)
    client = TestClient(app)
    response = client.post(
        "/transcripts/read",
        files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")},
        data={"school": "Red Rocks Community College"},
    )
    assert response.status_code == 200
    assert [c["code"] for c in response.json()["courses"]] == ["MATH111"]


def test_read_endpoint_reads_our_csv_and_rejects_other_files() -> None:
    client = TestClient(app)
    ok = client.post("/transcripts/read", files={"file": ("t.csv", b"code,credits,term\nMATH111,4,Fall 2025\n", "text/csv")})
    assert ok.status_code == 200 and ok.json()["courses"][0]["code"] == "MATH111"
    bad = client.post("/transcripts/read", files={"file": ("t.docx", b"x", "application/octet-stream")})
    assert bad.status_code == 400


def test_the_reading_lists_the_schools_the_student_can_pick() -> None:
    schools = read_transcript(["Transcript"]).known_schools
    assert schools[0] == MINES and len(schools) == 36  # Mines, 15 CCCS colleges, 20 other Colorado schools
    assert {"Front Range Community College", "University of Colorado Boulder", "University of Colorado Denver", "University of Denver"} <= set(schools)


def test_a_colorado_university_is_recognised_and_its_courses_go_to_tes() -> None:
    reading = read_transcript(["UNIVERSITY OF COLORADO BOULDER", "Unofficial Transcript", "Fall 2022", "MATH 1300 Calculus 1 A 5.000"])
    assert reading.school == "University of Colorado Boulder" and reading.system is None
    assert [(u.code, u.suggestion) for u in reading.unmatched] == [("MATH 1300", None)]


@pytest.mark.parametrize(
    "written, school",
    [
        ("University Of Colorado-Denver", "University of Colorado Denver"),
        ("CU Denver | Anschutz", "University of Colorado Denver"),
        ("Colorado State University-Pueblo", "Colorado State University Pueblo"),  # the longer name wins
        ("Colorado State University", "Colorado State University"),
        ("Pikes Peak Community College", "Pikes Peak State College"),  # its older name
        ("MSU Denver Office of the Registrar", "Metropolitan State University of Denver"),
        ("Rocky Mountain College of Art + Design", "Rocky Mountain College of Art and Design"),
        ("Some Other College", None),
    ],
)
def test_school_names_are_matched_however_a_transcript_writes_them(written: str, school: str | None) -> None:
    assert transfer_credit._known_name(written, DATA) == school


def test_a_mines_transcript_names_its_transfer_schools_properly() -> None:
    lines = [line.replace("Example State University", "University Of Colorado-Denver") for line in MINES_TRANSCRIPT]
    sources = {c.transfer_from for c in read_transcript(lines).courses}
    assert "University of Colorado Denver" in sources


def test_a_community_college_transcript_naming_a_university_lower_down_is_still_the_college() -> None:
    lines = ["Red Rocks Community College", "Official Transcript", "Transfer credit from University of Colorado Denver", "Fall 2023", "MAT 2410 Calculus I A 5.000"]
    assert read_transcript(lines).school == "Red Rocks Community College"
