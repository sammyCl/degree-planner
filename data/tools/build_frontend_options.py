"""Build frontend/src/setup/programOptions.json: the programs the setup page lets a student pick.

    python3 data/tools/build_frontend_options.py

The backend has no endpoint that lists programs yet, so the setup page reads this file. It is built from the
program files in data/json/ (bachelor's, master's, combined, minors, ASIs). Re-run it after program data changes.
PhD programs are left out on purpose: the proposal covers bachelor's, master's, combined BS+MS, minors and ASIs.
Degrees are offered only for the student's catalog year. Minors, ASIs and certificates are offered from the newest
catalog year stored for them, even when that is older (today all 18 ASIs are from 2025-2026): each option carries its own
"catalog_year" and the setup page warns that those must be checked against the current catalog. Certificates have no
program data yet, so none appear until a data file with degree_level "certificate" exists.
Standard library only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["bachelors.json", "graduate-programs.json", "minors.json", "asis.json"]
KEEP = {"bachelor", "master", "combined", "minor", "asi", "certificate"}
ADD_ONS = {"minor", "asi", "certificate"}  # offered from their newest stored year, not only the student's
CATALOG_YEAR = "2026-2027"  # the student's catalog year (the setup page sends this one)


def main() -> None:
    found: dict[str, dict] = {}
    left_out: dict[str, int] = {}
    for name in SOURCES:
        for p in json.loads((ROOT / "data" / "json" / name).read_text())["programs"]:
            level = p["degree_level"]
            if level not in KEEP:
                continue
            if level not in ADD_ONS and p["catalog_year"] != CATALOG_YEAR:
                left_out[level] = left_out.get(level, 0) + 1
                continue
            option = {"id": p["program_id"], "name": p["name"], "level": level, "catalog_year": p["catalog_year"]}
            if p["program_id"] not in found or option["catalog_year"] > found[p["program_id"]]["catalog_year"]:
                found[p["program_id"]] = option  # the newest year wins
    programs = list(found.values())
    order = {level: i for i, level in enumerate(["bachelor", "master", "combined", "minor", "asi", "certificate"])}
    programs.sort(key=lambda p: (order[p["level"]], p["name"].lower()))
    out = ROOT / "frontend" / "src" / "setup" / "programOptions.json"
    out.write_text(json.dumps({"catalog_year": CATALOG_YEAR, "programs": programs}, indent=1, ensure_ascii=False) + "\n")
    counts = {lvl: sum(1 for p in programs if p["level"] == lvl) for lvl in order}
    print(f"wrote {out.relative_to(ROOT)}: {counts}")
    older = {lvl: sorted({p["catalog_year"] for p in programs if p["level"] == lvl}) for lvl in ADD_ONS}
    older = {lvl: years for lvl, years in older.items() if years and years != [CATALOG_YEAR]}
    if older:
        print(f"add-ons not from {CATALOG_YEAR}: {older}")
    if left_out:
        print(f"left out, not in catalog year {CATALOG_YEAR}: {left_out}")


if __name__ == "__main__":
    main()
