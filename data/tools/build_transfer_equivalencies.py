"""Build data/json/transfer-equivalencies.json: which outside courses Mines has already approved, and as what.

    python3 data/tools/build_transfer_equivalencies.py

Source: the Mines registrar's preapproved Colorado Community College System (CCCS) lists, copied as text into
data/Transfer Credit/ (core and general courses, computer science and engineering, CAS/HASS mid-level electives).
Every CCCS college shares one course numbering, so one table covers all 15 of them. Courses from other schools are
not here: the student looks those up in Mines' Transfer Evaluation System (TES) and picks the Mines course by hand.

The transcript reader (backend transcript_parser.py) uses this file for a transcript from another school. Mines'
own transcripts already show the Mines course each transfer course became, so they never need it.

Shape of the output, one entry per outside course (or group of them):
  {"system": "cccs", "subjects": ["MAT"], "numbers": ["201", "2410"], "any_number": false, "title": "Calculus I",
   "mines": ["MATH111"], "note": null, "only_at": null, "pair": null}
- numbers: the old (before summer 2022) and new CCCS numbers; any_number: every course of the subject counts.
- mines: the Mines course codes it becomes. Placeholders: HASS2XX (a CAS/HASS mid-level elective), CSM2XX (a Success
  and Wellness elective), PAGN1XX (a physical activity course), FREE1XX (a free elective).
- only_at: the colleges it applies at, when the registrar limits it (EGG 1040 as EDNS151).
- pair: "HASS100" for the two courses that together make HASS100 (PHI 2018 with ENG 1022 or 1031); one alone is a
  free elective.
Standard library only.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "Transfer Credit"
OUT = ROOT / "data" / "json" / "transfer-equivalencies.json"

# From https://www.mines.edu/registrar/cccs-preapproved-transfer/ (retrieved 2026-11-26).
CCCS_SCHOOLS = [
    "Red Rocks Community College",
    "Front Range Community College",
    "Arapahoe Community College",
    "Pikes Peak State College",
    "Community College of Denver",
    "Community College of Aurora",
    "Colorado Mountain College",
    "Aims Community College",
    "Pueblo Community College",
    "Lamar Community College",
    "Morgan Community College",
    "Northeastern Community College",
    "Colorado Northwestern Community College",
    "Otero Junior College",
    "Trinidad State Junior College",
]
# Short or older names each CCCS college goes by on transcripts.
CCCS_ALIASES = {
    "Red Rocks Community College": ["RRCC", "Red Rocks CC"],
    "Front Range Community College": ["FRCC", "Front Range CC"],
    "Arapahoe Community College": ["Arapahoe CC"],
    "Pikes Peak State College": ["Pikes Peak Community College", "PPSC", "PPCC"],
    "Community College of Denver": ["CC of Denver"],
    "Community College of Aurora": ["CC Aurora", "CC of Aurora"],
    "Colorado Mountain College": [],
    "Aims Community College": ["Aims CC"],
    "Pueblo Community College": ["Pueblo CC"],
    "Lamar Community College": [],
    "Morgan Community College": [],
    "Northeastern Community College": ["Northeastern Junior College"],
    "Colorado Northwestern Community College": [],
    "Otero Junior College": ["Otero College"],
    "Trinidad State Junior College": ["Trinidad State College"],
}
# Colorado's four-year colleges and universities. Mines has no published preapproved list for them, so their courses
# are looked up in TES; listing them lets the page recognise and name the school. Compiled by hand (2026-11-26) from
# the schools' own names; aliases are the short and older names that appear on transcripts. Check before relying on it.
COLORADO_UNIVERSITIES = {
    "University of Colorado Boulder": ["CU Boulder", "University of Colorado at Boulder"],
    "University of Colorado Denver": ["CU Denver", "University of Colorado at Denver", "University of Colorado Denver Anschutz Medical Campus", "UC Denver"],
    "University of Colorado Colorado Springs": ["UCCS", "CU Colorado Springs", "University of Colorado at Colorado Springs"],
    "University of Denver": [],
    "Colorado State University": ["Colorado State University Fort Collins", "CSU Fort Collins"],
    "Colorado State University Pueblo": ["CSU Pueblo"],
    "Colorado State University Global": ["CSU Global"],
    "Metropolitan State University of Denver": ["MSU Denver", "Metropolitan State College of Denver", "Metro State"],
    "University of Northern Colorado": [],
    "Colorado Mesa University": ["Mesa State College"],
    "Fort Lewis College": [],
    "Western Colorado University": ["Western State Colorado University", "Western State College"],
    "Adams State University": ["Adams State College"],
    "Colorado College": [],
    "Regis University": [],
    "Colorado Christian University": [],
    "Naropa University": [],
    "Rocky Mountain College of Art and Design": ["RMCAD", "Rocky Mountain College of Art + Design"],
    "United States Air Force Academy": ["USAFA", "U.S. Air Force Academy"],
    "Colorado Technical University": [],
}

# The colleges the registrar names for EGG 1040 as EDNS151 ("CC Aurora, Front Range CC, Pikes Peak, Arapahoe CC &
# Red Rocks CC"), with their full names.
EDNS151_ONLY_AT = [
    "Community College of Aurora",
    "Front Range Community College",
    "Pikes Peak State College",
    "Arapahoe Community College",
    "Red Rocks Community College",
]


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")[1:]]


def numbers(raw: str) -> tuple[list[str], bool]:
    """'201 or 202' -> ['201', '202']; 'N/A' -> []; 'Any Number' -> [] and any_number."""
    if re.match(r"any num", raw, re.IGNORECASE):
        return [], True
    return re.findall(r"\b\d{3,4}\b", raw), False


def mines_codes(subject: str, number: str) -> tuple[list[str], str | None]:
    """'CHGN', '221 & 223' -> ['CHGN221', 'CHGN223']; 'CSM', '2XX' -> ['CSM2XX']; 'PAGN', '101+' -> ['PAGN1XX']."""
    note = None
    if "*" in number:
        number, note = number.split("*", 1)
        note = note.strip()
    if re.fullmatch(r"\s*\dXX\s*", number):
        return [f"{subject}{number.strip()}"], note
    if number.strip().endswith("+"):
        return [f"{subject}{number.strip()[0]}XX"], note
    return [f"{subject}{n}" for n in re.findall(r"\d{3}", number)], note


def read_mines_table(name: str) -> list[dict]:
    """A table with Mines columns: Mines subject, number, title, (and/or), CCCS subject, old number, new number, title."""
    entries: list[dict] = []
    current: tuple[list[str], str | None] | None = None
    for line in (SOURCE / name).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if not line.lstrip().startswith("|"):
            if entries and entries[-1]["note"]:  # a note that wrapped onto the next line
                entries[-1]["note"] += " " + line.strip()
            continue
        c = cells(line)
        if c[0] == "Mines Subject":
            continue
        if len(c) >= 8 and not any(c[:7]) and c[7].startswith("*"):  # a note row for the course above
            if entries:
                entries[-1]["note"] = c[7].lstrip("* ")
            continue
        if c[0]:
            current = mines_codes(c[0], c[1])
        if current is None or len(c) < 8 or "No CCCS" in c[4]:
            continue
        old, any_old = numbers(c[5])
        new, any_new = numbers(c[6])
        subjects = [s.lstrip("*") for s in c[4].split("/")]
        codes, note = current
        entries.append(
            {
                "system": "cccs",
                "subjects": subjects,
                "numbers": old + new,
                "any_number": any_old or any_new,
                "title": c[7].rstrip("*").strip(),
                "mines": codes,
                "note": note,
                "only_at": None,
                "pair": None,
            }
        )
    return entries


def read_hass_table(name: str) -> list[dict]:
    """The CAS/HASS list has no Mines columns: every course on it is a CAS/HASS mid-level elective (HASS2XX)."""
    entries: list[dict] = []
    for line in (SOURCE / name).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith("*"):
            if entries:
                note = line.lstrip("* ").strip()
                entries[-1]["note"] = note if not entries[-1]["note"] else f"{entries[-1]['note']} {note}"
            continue
        c = cells(line)
        if len(c) < 4 or not c[0] or c[0] == "CCCS Subject":
            continue
        old, any_old = numbers(c[1])
        new, any_new = numbers(c[2])
        entries.append(
            {
                "system": "cccs",
                "subjects": c[0].split("/"),
                "numbers": old + new,
                "any_number": any_old or any_new,
                "title": c[3],
                "mines": ["HASS2XX"],
                "note": None,
                "only_at": None,
                "pair": None,
            }
        )
    return entries


def main() -> None:
    entries = (
        read_mines_table("cccs-core-general.txt")
        + read_mines_table("cccs-compsci-engr.txt")
        + read_hass_table("cccs-hass-courses.txt")
    )
    for e in entries:
        if e["mines"] == ["EDNS151"]:
            e["only_at"] = EDNS151_ONLY_AT
        if e["mines"] == ["HASS100"]:
            e["pair"] = "HASS100"
            e["note"] = "Two courses make HASS100 (PHI 2018 with ENG 1022 or 1031); the other's hours are a free elective."
    OUT.write_text(
        json.dumps(
            {
                "about": "Outside courses Mines has preapproved, and the Mines course each becomes. "
                "Built by data/tools/build_transfer_equivalencies.py from data/Transfer Credit/. Not a guarantee: "
                "the registrar decides when official transcripts arrive.",
                "retrieved": "2026-11-26",
                "sources": [
                    "https://www.mines.edu/registrar/cccs-preapproved-transfer/",
                    "https://www.mines.edu/registrar/cccs-core-general/",
                    "https://www.mines.edu/registrar/cccs-compsci-engr/",
                    "https://www.mines.edu/registrar/cccs-hass-courses/",
                ],
                "tes_url": "https://tes.collegesource.com/publicview/TES_publicview01.aspx?rid=2827e8b2-59b1-46b1-8274-ad33fdab2135&aid=72fb7eaa-493b-439c-93bb-6419eeb87a48",
                "systems": {
                    "cccs": {
                        "name": "Colorado Community College System",
                        "schools": CCCS_SCHOOLS,
                        "min_grade": "C",
                        "unlisted": "Academic courses not on the lists transfer as free electives (FREE1XX), up to the "
                        "hours the degree needs. No credit for vocational or developmental courses (pre-calculus, "
                        "introductory chemistry).",
                    }
                },
                # every school the transcript reader recognises: name, other names, and its saved list (or none)
                "schools": [
                    {"name": "Colorado School of Mines", "aliases": [], "system": None, "kind": "mines"}
                ]
                + [{"name": n, "aliases": CCCS_ALIASES[n], "system": "cccs", "kind": "community college"} for n in CCCS_SCHOOLS]
                + [{"name": n, "aliases": a, "system": None, "kind": "university"} for n, a in COLORADO_UNIVERSITIES.items()],
                "equivalencies": entries,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    assert set(CCCS_ALIASES) == set(CCCS_SCHOOLS)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(entries)} equivalencies for {len(CCCS_SCHOOLS)} CCCS colleges; "
          f"{len(COLORADO_UNIVERSITIES)} Colorado universities recognised (TES)")


if __name__ == "__main__":
    main()
