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
DROPPED = ROOT / "data" / "json" / "courses.dropped-info.csv"  # CSV, not JSON: the loader reads every .json under data/
REVIEW = ROOT / "data" / "json" / "courses.REVIEW.md"
CATALOG_YEAR = "2026-2027"
# Credits for every course titled "Independent Study" (variable 0.5-6 or 1-6 in the catalog); see build().
INDEPENDENT_STUDY_CREDITS = 3.0

# "Equivalent with MATH223, This is ..." at the start of a description (BUG-041).
EQUIVALENT = re.compile(r"^\s*Equivalent with ((?:[A-Z]{3,4}\s?\d{3}[A-Z]{0,2}\s*,\s*)*[A-Z]{3,4}\s?\d{3}[A-Z]{0,2})\b")

SMALL = {"and", "or", "of", "the", "in", "for", "to", "a", "an", "on", "at", "by", "with", "from", "as"}
ROMAN = {"I", "II", "III", "IV", "V", "VI"}
# Words the catalog prints in capitals that must stay capitals (or a fixed mix) in a title.
ACRONYMS = {
    "CAD", "CAM", "CNC", "GIS", "GPS", "FEA", "CFD", "MEMS", "VLSI", "RF", "DC", "AC", "IC", "IT", "AI", "ML", "LED",
    "PLC", "HVAC", "NMR", "XRD", "SEM", "TEM", "ISS", "ICE", "PES", "STEM", "HASS", "EBGN", "MATLAB", "SQL", "CS",
    "EE", "ME", "BME", "CPR", "UAS", "UAV", "3D", "2D", "LNG", "CO2", "CCUS", "PV", "FPGA", "ASIC", "SC1", "SC2", "SC3",
    "TCP", "IP", "OS", "VR", "AR", "R&D", "PhD", "MS",
    # found by scanning every title against the catalog (2026-11-24)
    "CSM", "QBE", "MCAT", "CPU", "CPT", "REU", "HVDC", "SWIR", "ICP", "AAPG", "SRC", "MME", "MN", "CASA", "LA", "IoT",
    # product and proper names written with an inner capital
    "AutoCAD", "SolidWorks", "McBride",
}
FORMS = {a.upper(): a for a in ACRONYMS} | {r: r for r in ROMAN}
# Misspellings in the catalog itself, fixed in the title (the CSV is not changed). FUNDAMENTA is cut off (its sibling
# AFGN202 reads "Fundamentals II"); REPORTMASTER is "Report" and "Master" run together (MNGN700, the Master of
# Engineering report), written here as "Report - Master", the best reading of the description.
TYPOS = {"TOPCS": "Topics", "FUNDAMENTA": "Fundamentals", "RAQUETBALL": "Racquetball", "REPORTMASTER": "Report - Master"}
TOKEN = re.compile(r"[A-Za-z0-9&]+")


def title_case(s: str) -> str:
    """ALL CAPS catalog titles become Title Case, word by word so a Roman numeral or acronym joined to a hyphen,
    slash or parenthesis ("PHYSICS II-ELECTROMAGNETISM", "(HVDC)") is still recognised."""
    s = " ".join(s.split())
    s = re.sub(r"^csm\b", "CSM", s)  # LIMU211 is printed "csm CONCERT CHOIR - SOPHOMORE"
    if any(ch.islower() for ch in s):
        return s  # already mixed case in the catalog

    def fix(m: re.Match) -> str:
        w = m.group(0)
        up = w.upper()
        if up in TYPOS:
            return TYPOS[up]
        if up in FORMS:
            return FORMS[up]
        if re.search(r"\d", w):
            return up  # SC1, 4XX, ...
        if up == "S" and m.start() > 0 and s[m.start() - 1] == "'":
            return "s"  # WOMEN'S, CPU'S
        if m.start() > 0 and up.lower() in SMALL:
            return up.lower()
        return up.capitalize()

    return TOKEN.sub(fix, s)


def norm(s: str) -> str:
    return re.sub(r"[\s.;,]+$", "", " ".join((s or "").split())).lower()


def credits(raw: str) -> tuple[float, bool]:
    raw = raw.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?", raw)
    if not m:
        raise ValueError(f"bad credits {raw!r}")
    return (float(m.group(2) or m.group(1)), m.group(2) is not None)  # a range uses its upper bound


def equivalents(description: str) -> list[str]:
    """Course codes named in a leading "Equivalent with ..." (placeholders like LAIS1XX do not match)."""
    m = EQUIVALENT.match(description or "")
    return [re.sub(r"\s+", "", c) for c in m.group(1).split(",")] if m else []


def link_equivalents(courses: list[dict], notes: dict[str, list[str]], stats: Counter) -> None:
    """Set equivalent_with on both courses of every pair, keeping only codes that are in the catalog."""
    by_code = {c["code"]: c for c in courses}
    pairs: set[tuple[str, str]] = set()
    for c in courses:
        for other in c.pop("_equivalent", []):
            if other == c["code"]:
                continue
            if other not in by_code:
                notes["equivalent not in catalog"].append(f"{c['code']} -> {other}")
                continue
            pairs.add(tuple(sorted((c["code"], other))))
    for a, b in pairs:
        by_code[a].setdefault("equivalent_with", []).append(b)
        by_code[b].setdefault("equivalent_with", []).append(a)
    for c in courses:
        if "equivalent_with" in c:
            c["equivalent_with"] = sorted(set(c["equivalent_with"]))
            stats["courses with an equivalent"] += 1


SKIP_INFERENCE = re.compile(r"special topics|independent study|research|thesis|seminar", re.I)
INFERRED_JSON = ROOT / "frontend" / "src" / "planner" / "inferredEquivalents.json"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _codes_in(req: dict | None) -> set[str]:
    if req is None:
        return set()
    if req["type"] == "course":
        return {req["code"]}
    if req["type"] in ("AND", "OR"):
        return set().union(*[_codes_in(x) for x in req["of"]]) if req["of"] else set()
    return set()


def infer_equivalents(courses: list[dict], notes: dict[str, list[str]], stats: Counter) -> list[dict]:
    """Treat courses as equivalent when the catalog never says so but the data strongly suggests it (the team's rule).

    Only courses with the same title, the same description and the same credits are considered. Then:
      1. Both are named in the prerequisites or corequisites of the same other course (for example MNGN311 asks
         for "GEOL310 or MNGN310"): the catalog treats them as interchangeable.
      2. Same number, different subject, the same prerequisites once rule 1's equivalents are treated as one, and
         the same two subjects as a pair rule 1 already found (GEOL and MNGN): the twin of a pair found by rule 1.
    Courses that only differ by level (a 400 and a 500 version of the same text) are never matched.
    The planner shows each of these as something to confirm. Returns [{"codes": [...], "reason": "..."}].
    """
    by_code = {c["code"]: c for c in courses}
    groups: dict[tuple, list[str]] = defaultdict(list)
    for c in courses:
        if SKIP_INFERENCE.search(c["title"]) or "XX" in c["code"]:
            continue
        groups[(_norm(c["title"]), _norm(c["description"]), c["credits"])].append(c["code"])
    identical = [sorted(v) for v in groups.values() if len(v) > 1]
    found: list[dict] = []

    def link(codes: list[str], reason: str) -> None:
        new = [(a, b) for i, a in enumerate(codes) for b in codes[i + 1 :] if b not in by_code[a].get("equivalent_with", [])]
        if not new:
            return  # the catalog already says so
        for a, b in new:
            by_code[a].setdefault("equivalent_with", []).append(b)
            by_code[b].setdefault("equivalent_with", []).append(a)
        found.append({"codes": codes, "reason": reason})

    linked_subjects: set[frozenset[str]] = set()
    for group in identical:  # rule 1
        for c in courses:
            named = (_codes_in(c.get("prerequisites")) | _codes_in(c.get("corequisites"))) & set(group)
            if len(named) >= 2:
                link(sorted(named), f"same title and description, and {c['code']} names both as prerequisites")
                linked_subjects.add(frozenset(by_code[x]["subject"] for x in named))
    canon = {}
    for entry in found:
        for code in entry["codes"]:
            canon[code] = entry["codes"][0]

    def shape(req):
        if isinstance(req, dict):
            return {k: (canon.get(v, v) if k == "code" else shape(v)) for k, v in req.items()}
        if isinstance(req, list):
            return sorted((shape(v) for v in req), key=json.dumps)
        return req

    for group in identical:  # rule 2
        numbers = {by_code[x]["number"] for x in group}
        subjects = frozenset(by_code[x]["subject"] for x in group)
        same_prereqs = len({json.dumps(shape(by_code[x].get("prerequisites")), sort_keys=True) for x in group}) == 1
        if len(numbers) == 1 and subjects in linked_subjects and same_prereqs:
            link(group, "same title, description, number and prerequisites as an equivalent pair of the same two subjects")
    for entry in found:
        notes["inferred equivalents"].append(f"{', '.join(entry['codes'])}: {entry['reason']}")
    for c in courses:
        if "equivalent_with" in c:
            c["equivalent_with"] = sorted(set(c["equivalent_with"]))
    stats["equivalent groups inferred (not in the catalog text)"] = len(found)
    return found


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


def _resolve_unknown_refs(req: dict | None, known: set[str]) -> tuple[dict | None, bool]:
    """A course reference to a code not in the catalog (typo or retired course) is a dead
    requirement that can never be satisfied. Left alone, it is either harmless (an OR with another,
    real branch already covers it) or a trap (an AND, or an OR where every branch is unknown, that
    the validator will flag forever with no way for the student to move past it).

    Returns the rewritten requirement and whether it has at least one real, satisfiable path.
    A course node is valid when its code is known; exception and None are always valid (the
    validator already lets the student override those). An AND is valid only once every branch is;
    any bare unknown-code branch it still has becomes an exception, so the AND can still be met by
    override instead of being permanently broken. An OR is valid as soon as one branch is: when
    another branch already works, its unknown-code siblings are left exactly as they are (a dead
    but harmless branch) rather than turned into exceptions too, because the validator surfaces
    every exception label regardless of whether another OR branch is satisfied (BUG-026(d), held
    back); turning a harmless branch into an exception would raise a false exception_claimed on an
    otherwise-clean plan. Only once no OR branch is real does it fall back to the AND treatment.
    """
    if req is None:
        return None, True
    if req["type"] == "course":
        return req, req["code"] in known
    if req["type"] == "exception":
        return req, True
    children = [_resolve_unknown_refs(sub, known) for sub in req["of"]]
    if req["type"] == "OR" and any(valid for _, valid in children):
        return {"type": "OR", "of": [child for child, _ in children]}, True
    # AND, or an OR with no real branch at all: every still-bare unknown-code child becomes an
    # exception (a child that is itself an AND/OR already resolved itself by this point).
    fixed = [
        child if child["type"] != "course" or valid else
        {"type": "exception", "label": f'the catalog names "{child["code"]}" here, which is not a course in our data; confirm with your advisor'}
        for child, valid in children
    ]
    return {"type": req["type"], "of": fixed}, True


def build() -> tuple[list[dict], dict[str, list[str]], Counter]:
    notes: dict[str, list[str]] = defaultdict(list)
    stats: Counter = Counter()
    dropped: list[dict] = []
    notes["_dropped"] = dropped  # type: ignore[assignment]
    rows = load_rows()
    stats["csv rows"] = len(rows)
    merged = merge(rows, notes)
    known = {r["course_number"].strip() for r in merged}
    courses = []
    for r in merged:
        code = r["course_number"].strip()
        subject = r["subject"].strip()
        cr, ranged = credits(r["credits"])
        if "INDEPENDENT STUDY" in r["course_name"].upper():
            # Team decision (Samantha, 2026-11-22): plan Independent Study at a typical 3 credits rather than the
            # range's upper bound (6), until a plan can choose the credits (BUG-039).
            cr = INDEPENDENT_STUDY_CREDITS
            stats["independent study (set to 3 credits)"] += 1
            notes["independent study"].append(f"{code}: {r['credits']} -> {cr:g}")
        elif ranged:
            stats["credit ranges (upper bound used)"] += 1
            notes["credit ranges"].append(f"{code}: {r['credits']} -> {cr:g}")
        pre = parse_prerequisites(r["prerequisites"])
        if pre.fallback:
            whole = pre.requirement["type"] == "exception"
            stats["prerequisites kept as one exception (free text)" if whole else "prerequisites partly free text (mixed)"] += 1
            notes["free-text prerequisites"].append(f"{code}{'' if whole else ' (mixed)'}: {original}")
        original = " ".join(r["prerequisites"].split())
        if pre.grade_dropped:
            stats["prerequisites with a grade minimum (grade dropped)"] += 1
            dropped.append({"code": code, "kind": "grade minimum", "detail": "; ".join(pre.grade_texts), "original_prerequisites": original})
        if pre.placement_dropped:
            stats["placement-level prerequisites left out (not a course)"] += 1
            dropped.append({"code": code, "kind": "placement assumption", "detail": pre.placement_dropped, "original_prerequisites": original})
        if pre.notes_dropped:
            stats["credit/repeat notes dropped from prerequisites"] += 1
            dropped.append({"code": code, "kind": "credit/repeat note", "detail": " | ".join(pre.notes_dropped), "original_prerequisites": original})
        if pre.requirement is None and r["prerequisites"].strip().lower() not in ("", "none", "none.", "n/a"):
            if not pre.notes_dropped:
                notes["empty prerequisites"].append(f"{code}: {r['prerequisites'][:100]}")
        coreq_res = parse_corequisites(r["corequisites"])
        coreq = coreq_res.requirement
        if coreq_res.fallback:
            stats["corequisites kept as one exception (free text)"] += 1
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
        found = equivalents(r["description"])
        if found:
            course["_equivalent"] = found
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

        for ref in list(refs(course["prerequisites"])) + list(refs(course["corequisites"])):
            if ref not in known:
                stats["references to codes not in the catalog"] += 1
                notes["unknown references"].append(f"{code} -> {ref}")

        # Rewrite only the branches that would otherwise be a dead end (see
        # _resolve_unknown_refs): a harmless unknown-code sibling in an already-satisfiable OR is
        # left exactly as it was, so this does not touch the review file's counts above.
        for field in ("prerequisites", "corequisites"):
            resolved, _ = _resolve_unknown_refs(course[field], known)
            if resolved != course[field]:
                stats["unknown references turned into an overridable exception"] += 1
            course[field] = resolved
    link_equivalents(courses, notes, stats)
    inferred = infer_equivalents(courses, notes, stats)
    INFERRED_JSON.write_text(json.dumps(inferred, indent=1) + "\n", encoding="utf-8")
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
        "corequisites": "Corequisites that are free text, kept whole as one exception (same as free-text prerequisites)",
        "unknown references": "Prerequisite/corequisite codes that are not courses in the catalog CSVs (typos or retired courses)",
        "conflicts": "Duplicate codes whose CSV rows disagree (undergraduate row kept)",
        "empty prerequisites": "Prerequisite text that produced no requirement",
        "credit ranges": "Variable-credit courses (upper bound used)",
        "independent study": "Independent Study courses (set to 3 credits, not the upper bound)",
        "inferred equivalents": "Equivalent courses the catalog does not state, inferred by the team's rule (shown to students as to confirm)",
        "equivalent not in catalog": "Equivalent courses named in a description but not in the catalog CSVs (left out)",
    }
    for key, title in caps.items():
        items = notes.get(key, [])
        out.append(f"\n## {title} ({len(items)})\n")
        out += [f"- {x}" for x in items]
    dropped = notes.get("_dropped", [])
    for kind, title in [
        ("grade minimum", "Grade minimums dropped from prerequisites (the data format has no grade field)"),
        ("credit/repeat note", "Credit/repeat notes dropped from prerequisites (not course requirements)"),
        ("placement assumption", "Placement-level prerequisites left out (a level of preparation, not a course)"),
    ]:
        items = [d for d in dropped if d["kind"] == kind]
        out.append(f"\n## {title} ({len(items)})\n")
        out += [f"- {d['code']}: `{d['detail']}` (full text: {d['original_prerequisites']})" for d in items]
    REVIEW.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    courses, notes, stats = build()
    OUT.write_text(json.dumps({"courses": courses}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_review(notes, stats)
    with open(DROPPED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "kind", "detail", "original_prerequisites"])
        w.writeheader()
        w.writerows(notes["_dropped"])  # type: ignore[arg-type]
    for k, v in sorted(stats.items()):
        print(f"{k}: {v}")
    print(f"wrote {OUT.relative_to(ROOT)}, {REVIEW.relative_to(ROOT)} and {DROPPED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
