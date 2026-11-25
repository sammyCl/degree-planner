"""Build frontend/src/setup/programOptions.json: the programs the setup page lets a student pick.

    python3 data/tools/build_frontend_options.py

The backend has no endpoint that lists programs yet, so the setup page reads this file. It is built from the
program files in data/json/ (bachelor's, master's, combined, minors, ASIs). Re-run it after program data changes.
PhD programs are left out on purpose: the proposal covers bachelor's, master's, combined BS+MS, minors and ASIs.
Only programs in the student's catalog year are offered: the backend looks a program up by exactly that year, so a program
from another year (today all 18 ASIs, collected from the 2025-2026 catalog) cannot be checked and would fail with "not
in the loaded 2026-2027 program data". They come back once confirmed and stored for 2026-2027 (data/CONFLICT-LOG.md).
Standard library only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["bachelors.json", "graduate-programs.json", "minors.json", "asis.json"]
KEEP = {"bachelor", "master", "combined", "minor", "asi"}
CATALOG_YEAR = "2026-2027"  # the student's catalog year (the setup page sends this one)


def main() -> None:
    programs = []
    left_out: dict[str, int] = {}
    for name in SOURCES:
        for p in json.loads((ROOT / "data" / "json" / name).read_text())["programs"]:
            if p["degree_level"] not in KEEP:
                continue
            if p["catalog_year"] != CATALOG_YEAR:
                left_out[p["degree_level"]] = left_out.get(p["degree_level"], 0) + 1
                continue
            programs.append({"id": p["program_id"], "name": p["name"], "level": p["degree_level"]})
    order = {level: i for i, level in enumerate(["bachelor", "master", "combined", "minor", "asi"])}
    programs.sort(key=lambda p: (order[p["level"]], p["name"].lower()))
    out = ROOT / "frontend" / "src" / "setup" / "programOptions.json"
    out.write_text(json.dumps({"catalog_year": CATALOG_YEAR, "programs": programs}, indent=1, ensure_ascii=False) + "\n")
    counts = {lvl: sum(1 for p in programs if p["level"] == lvl) for lvl in order}
    print(f"wrote {out.relative_to(ROOT)}: {counts}")
    if left_out:
        print(f"left out, not in catalog year {CATALOG_YEAR}: {left_out}")


if __name__ == "__main__":
    main()
