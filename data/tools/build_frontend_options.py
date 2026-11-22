"""Build frontend/src/setup/programOptions.json: the programs the setup page lets a student pick.

    python3 data/tools/build_frontend_options.py

The backend has no endpoint that lists programs yet, so the setup page reads this file. It is built from the
program files in data/json/ (bachelor's, master's, combined, minors, ASIs). Re-run it after program data changes.
PhD programs are left out on purpose: the proposal covers bachelor's, master's, combined BS+MS, minors and ASIs.
Standard library only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["bachelors.json", "graduate-programs.json", "minors.json", "asis.json"]
KEEP = {"bachelor", "master", "combined", "minor", "asi"}
CATALOG_YEAR = "2026-2027"  # the student's catalog year; ASI data is 2025-2026 and the backend resolves that


def main() -> None:
    programs = []
    for name in SOURCES:
        for p in json.loads((ROOT / "data" / "json" / name).read_text())["programs"]:
            if p["degree_level"] in KEEP:
                programs.append({"id": p["program_id"], "name": p["name"], "level": p["degree_level"]})
    order = {level: i for i, level in enumerate(["bachelor", "master", "combined", "minor", "asi"])}
    programs.sort(key=lambda p: (order[p["level"]], p["name"].lower()))
    out = ROOT / "frontend" / "src" / "setup" / "programOptions.json"
    out.write_text(json.dumps({"catalog_year": CATALOG_YEAR, "programs": programs}, indent=1, ensure_ascii=False) + "\n")
    counts = {lvl: sum(1 for p in programs if p["level"] == lvl) for lvl in order}
    print(f"wrote {out.relative_to(ROOT)}: {counts}")


if __name__ == "__main__":
    main()
