"""Tests for the course title capitalisation in build_courses_json.py. Run from backend/: uv run pytest ../data/tools"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from build_courses_json import title_case  # noqa: E402


@pytest.mark.parametrize(
    ("catalog", "expected"),
    [
        # a Roman numeral joined to a hyphen was the bug: "Physics Ii-Electromagnetism"
        ("PHYSICS II-ELECTROMAGNETISM AND OPTICS", "Physics II-Electromagnetism and Optics"),
        ("PHYSICS III-MODERN PHYSICS I", "Physics III-Modern Physics I"),
        ("HONORS PHYSICS III-MODERN PHYSICS", "Honors Physics III-Modern Physics"),
        ("PRINCIPLES OF CHEMISTRY II (SC1)", "Principles of Chemistry II (SC1)"),
        ("COMPUTER SCIENCE FOR STEM", "Computer Science for STEM"),
        ("CSM CONCERT/MARCH BAND-FRESHMAN", "CSM Concert/March Band-Freshman"),
        ("LA-ICP-MS/MS TRACE ELEMENT ANALYSIS AND DATING", "LA-ICP-MS/MS Trace Element Analysis and Dating"),
        ("GIS-BASED REAL WORLD LEARNING PROJECT I - FUNDAMENTALS", "GIS-Based Real World Learning Project I - Fundamentals"),
        ("HIGH VOLTAGE DC (HVDC) SYSTEMS", "High Voltage DC (HVDC) Systems"),
        ("IOT SECURITY AND PRIVACY", "IoT Security and Privacy"),
        ("CS@MINES BRIDGE SEMINAR COURSE", "CS@Mines Bridge Seminar Course"),
        ("COMPUTING BEYOND CPU'S", "Computing Beyond CPU's"),
        ("WOMEN'S STUDIES", "Women's Studies"),
        ("SPECIAL TOPCS", "Special Topics"),  # a misspelling in the catalog itself
        ("TEAM AND LEADERSHIP FUNDAMENTA", "Team and Leadership Fundamentals"),
        ("WOMEN'S RAQUETBALL", "Women's Racquetball"),
        ("GRADUATE ENGINEERING REPORTMASTER OF ENGINEERING", "Graduate Engineering Report - Master of Engineering"),
        ("AUTOCAD BASICS", "AutoCAD Basics"),
        ("SOLIDWORKS BASICS (FOR CERTIFICATION)", "SolidWorks Basics (for Certification)"),
        ("MCBRIDE PRACTICUM", "McBride Practicum"),
        ("csm CONCERT CHOIR - SOPHOMORE", "CSM Concert Choir - Sophomore"),
        ("ENGINEERING FIELD SESSION, CIVIL", "Engineering Field Session, Civil"),
        ("DATA STRUCTURES AND ALGORITHMS", "Data Structures and Algorithms"),
    ],
)
def test_all_caps_titles(catalog: str, expected: str) -> None:
    assert title_case(catalog) == expected


def test_a_title_that_already_has_lowercase_is_left_alone() -> None:
    assert title_case("Already Mixed Case") == "Already Mixed Case"
