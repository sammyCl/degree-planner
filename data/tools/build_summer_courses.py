"""Build the summer-course data: data/json/summer-courses.json and frontend/src/setup/summerPrograms.json.

    python3 data/tools/build_summer_courses.py

The course data does not say which terms a course is offered (bugs.txt BUG-045), so the planner placed summer field
sessions in fall or spring. SUMMER_COURSES is hand-listed from the "Summer" term of each program's plan of study in
data/Undergraduate Programs/ (2026-2027). The validator warns when one is planned in another term, and the setup page
switches summer terms on for a degree that requires one. Optional summer courses (MNGN205) are left out.
Standard library only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# course -> the program PDF that lists it in a summer term
SUMMER_COURSES = {
    "BIOL415": "Quantitative Biosciences and Engineering",
    "CBEN312": "Chemical Engineering",
    "CBEN313": "Chemical Engineering",
    "CEEN330": "Environmental Engineering",
    "CEEN331": "Civil Engineering",
    "CHGN490": "Chemistry",
    "CSCI370": "Computer Science",
    "GEGN316": "Geological Engineering",
    "GPGN486": "Geophysical Engineering",
    "MNGN203": "Mining Engineering",
    "MNGN301": "Mining Engineering",
    "MNGN308": "Mining Engineering",
    "MTGN272": "Metallurgical and Materials Engineering",
    "PEGN315": "Petroleum Engineering",
    "PEGN316": "Petroleum Engineering",
    "PHGN384": "Engineering Physics",
}


def required_summer_courses(program: dict) -> list[str]:
    """The summer courses a degree cannot do without: in an "all" group, or a group whose only choice is that course."""
    found: set[str] = set()
    for group in program["requirement_groups"]:
        courses = group.get("courses") or []
        if group["kind"] == "all" or (group["kind"] == "choose_credits" and len(courses) == 1):
            found.update(code for code in courses if code in SUMMER_COURSES)
    return sorted(found)


def main() -> None:
    programs: dict[str, dict] = {}
    for name in ("bachelors.json", "graduate-programs.json"):
        for p in json.loads((ROOT / "data" / "json" / name).read_text())["programs"]:
            if p["catalog_year"] == "2026-2027":
                programs[p["program_id"]] = p
    needs: dict[str, list[str]] = {}
    for program_id, p in sorted(programs.items()):
        if p["degree_level"] not in ("bachelor", "combined"):
            continue
        parts = [programs[c] for c in p.get("combines") or [] if c in programs] if p["degree_level"] == "combined" else []
        found = sorted({code for part in [p, *parts] for code in required_summer_courses(part)})
        if found:
            needs[program_id] = found
    (ROOT / "data" / "json" / "summer-courses.json").write_text(
        json.dumps({"about": "Courses taken in a summer term. Built by data/tools/build_summer_courses.py.",
                    "summer_courses": SUMMER_COURSES}, indent=1) + "\n"
    )
    out = ROOT / "frontend" / "src" / "setup" / "summerPrograms.json"
    out.write_text(json.dumps(needs, indent=1) + "\n")
    print(f"{len(SUMMER_COURSES)} summer courses; {len(needs)} degrees require one: {', '.join(needs)}")


if __name__ == "__main__":
    main()
