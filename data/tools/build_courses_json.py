"""Build data/json/courses.json (and courses.REVIEW.md) from the two course catalog CSVs.

    python3 data/tools/build_courses_json.py

Inputs:  data/Academic Catalog/mines-courses.csv (undergraduate, with catalog URLs)
         data/Academic Catalog/mines-graduate-courses.csv (graduate)
Output:  data/json/courses.json in the common data format (docs/data-format.md), one entry per course code.
Rules are written up in data/CONFLICT-LOG.md ("Course catalog"). Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prereq_parser import parse_corequisites, parse_prerequisites  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CSV_DIR = ROOT / "data" / "Academic Catalog"
OUT = ROOT / "data" / "json" / "courses.json"
REVIEW = ROOT / "data" / "json" / "courses.REVIEW.md"
CATALOG_YEAR = "2026-2027"

SMALL = {"and", "or", "of", "the", "in", "for", "to", "a", "an", "on", "at", "by", "with", "from", "as"}
ACRONYMS = {
    "CAD", "CAM", "CNC", "GIS", "GPS", "FEA", "CFD", "MEMS", "VLSI", "RF", "DC", "AC", "IC", "IT", "AI", "ML", "LED",
    "PLC", "HVAC", "NMR", "XRD", "SEM", "TEM", "ISS", "ICE", "PES", "STEM", "HASS", "EBGN", "MATLAB", "SQL", "CS",
    "EE", "ME", "BME", "CPR", "UAS", "UAV", "3D", "2D", "LNG", "CO2", "CCUS", "PV", "FPGA", "ASIC", "SC1", "SC2", "SC3",
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "I", "TCP", "IP", "OS", "VR", "AR", "R&D", "PhD", "MS",
}


def title_case(s: str) -> str:
    s = " ".join(s.split())
    if any(ch.islower() for ch in s):
        return s  # already mixed case in the catalog

    def word(w: str, first: bool) -> str:
        core = re.sub(r"[^\w&]", "", w)
        if core in ACRONYMS or re.search(r"\d", core):
            return w
        low = w.lower()
        if not first and low in SMALL:
            return low
        # capitalize each hyphen/slash/paren-separated piece
        return re.sub(r"(^|[-/(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), low)

    words = s.split(" ")
    return " ".join(word(w, i == 0) for i, w in enumerate(words))


def norm(s: str) -> str:
    return re.sub(r"[\s.;,]+$", "", " ".join((s or "").split())).lower()


def credits(raw: str) -> tuple[float, bool]:
    raw = raw.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?", raw)
    if not m:
        raise ValueError(f"bad credits {raw!r}")
    return (float(m.group(2) or m.group(1)), m.group(2) is not None)  # a range uses its upper bound


def load_rows() -> list[dict]:
    rows = []
    for name, grad in [("mines-courses.csv", False), ("mines-graduate-courses.csv", True)]:
        with open(CSV_DIR / name, newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                r["_grad"] = grad
                r["_line"] = f"{name}:{i}"
                rows.append(r)
    return rows


def merge(rows: list[dict], notes: dict[str, list[str]]) -> list[dict]:
    """One row per code: the undergraduate row wins (it has a catalog URL); gaps are filled from the others."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["course_number"].strip()].append(r)
    merged = []
    for code, group in by.items():
        group.sort(key=lambda r: r["_grad"])  # undergraduate first, then graduate in file order
        base = dict(group[0])
        for field in ("course_name", "credits", "description", "prerequisites", "corequisites"):
            vals = [r[field] for r in group if r[field].strip() and r[field].strip().lower() not in ("none", "n/a")]
            if not base[field].strip() or base[field].strip().lower() in ("none", "n/a"):
                if vals:
                    base[field] = vals[0]
            if field == "description":  # a truncated copy is a strict prefix of the full one
                longest = max(vals, key=len, default=base[field])
                if norm(longest).startswith(norm(base[field])):
                    base[field] = longest
            distinct = {norm(v) for v in vals}
            if len(distinct) > 1 and field != "description":
                notes["conflicts"].append(
                    f"{code} {field}: kept `{norm(base[field])[:70]}`; other: "
                    + "; ".join(f"`{d[:70]}`" for d in sorted(distinct - {norm(base[field])}))
                )
        base["_in_both"] = len({r["_grad"] for r in group}) == 2
        merged.append(base)
    merged.sort(key=lambda r: (r["subject"], r["course_number"]))
    return merged


def build() -> tuple[list[dict], dict[str, list[str]], Counter]:
    notes: dict[str, list[str]] = defaultdict(list)
    stats: Counter = Counter()
    rows = load_rows()
    stats["csv rows"] = len(rows)
    merged = merge(rows, notes)
    known = {r["course_number"].strip() for r in merged}
    courses = []
    for r in merged:
        code = r["course_number"].strip()
        subject = r["subject"].strip()
        cr, ranged = credits(r["credits"])
        if ranged:
            stats["credit ranges (upper bound used)"] += 1
            notes["credit ranges"].append(f"{code}: {r['credits']} -> {cr:g}")
        pre = parse_prerequisites(r["prerequisites"])
        if pre.fallback:
            whole = pre.requirement["type"] == "exception"
            stats["prerequisites kept as one exception (free text)" if whole else "prerequisites partly free text (mixed)"] += 1
            notes["free-text prerequisites"].append(f"{code}{'' if whole else ' (mixed)'}: {' '.join(r['prerequisites'].split())[:140]}")
        if pre.grade_dropped:
            stats["prerequisites with a grade minimum (grade dropped)"] += 1
        if pre.notes_dropped:
            stats["credit/repeat notes dropped from prerequisites"] += 1
        if pre.requirement is None and r["prerequisites"].strip().lower() not in ("", "none", "none.", "n/a"):
            if not pre.notes_dropped:
                notes["empty prerequisites"].append(f"{code}: {r['prerequisites'][:100]}")
        coreq, ok = parse_corequisites(r["corequisites"])
        if not ok:
            stats["corequisites not expressible (OR/free text; left empty)"] += 1
            notes["corequisites"].append(f"{code}: {r['corequisites'][:120]}")
        course = {
            "code": code,
            "subject": subject,
            "number": code[len(subject):],
            "title": title_case(r["course_name"]),
            "credits": cr,
            "description": " ".join(r["description"].split()),
            "prerequisites": pre.requirement,
            "corequisites": coreq,
            "catalog_year": CATALOG_YEAR,
        }
        if not r["_grad"] and r["source_page"].startswith("http"):
            course["source"] = {"url": r["source_page"]}
        else:
            stats["graduate-only courses without a source URL"] += 1
        if not course["description"]:
            stats["courses with no description"] += 1
        courses.append(course)

        def refs(req):
            if req is None:
                return
            if req["type"] == "course":
                yield req["code"]
            elif req["type"] in ("AND", "OR"):
                for x in req["of"]:
                    yield from refs(x)

        for ref in list(refs(course["prerequisites"])) + coreq:
            if ref not in known:
                stats["references to codes not in the catalog"] += 1
                notes["unknown references"].append(f"{code} -> {ref}")
    stats["courses written"] = len(courses)
    stats["codes in both CSVs (merged)"] = sum(1 for r in merged if r["_in_both"])
    return courses, notes, stats


def write_review(notes: dict[str, list[str]], stats: Counter) -> None:
    out = ["# Course data review (generated by data/tools/build_courses_json.py)\n"]
    out.append("Regenerated every run; do not edit by hand. Rules: `data/CONFLICT-LOG.md`, section Course catalog.\n")
    out.append("## Counts\n")
    out += [f"- {k}: {v}" for k, v in sorted(stats.items())]
    caps = {
        "free-text prerequisites": "Prerequisites that are free text, whole or in part (free text becomes an exception the student can override)",
        "corequisites": "Corequisites not expressible as a plain list (OR or free text), left empty",
        "unknown references": "Prerequisite/corequisite codes that are not courses in the catalog CSVs (typos or retired courses)",
        "conflicts": "Duplicate codes whose CSV rows disagree (undergraduate row kept)",
        "empty prerequisites": "Prerequisite text that produced no requirement",
        "credit ranges": "Variable-credit courses (upper bound used)",
    }
    for key, title in caps.items():
        items = notes.get(key, [])
        out.append(f"\n## {title} ({len(items)})\n")
        shown = items if key != "credit ranges" else items[:15]
        out += [f"- {x}" for x in shown]
        if len(shown) < len(items):
            out.append(f"- ... and {len(items) - len(shown)} more (same pattern)")
    REVIEW.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    courses, notes, stats = build()
    OUT.write_text(json.dumps({"courses": courses}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_review(notes, stats)
    for k, v in sorted(stats.items()):
        print(f"{k}: {v}")
    print(f"wrote {OUT.relative_to(ROOT)} and {REVIEW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
