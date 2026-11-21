# data/

Everything the team collected for the planner. Nothing here is private.

| Folder | What | Owner of the slice |
|---|---|---|
| `Academic Catalog/` | Full 2026-2027 catalog PDFs and the course CSVs | Samantha / Midhat |
| `Undergraduate Programs/` | One PDF per bachelor's program | Samantha |
| `Graduate Programs/` | One PDF per graduate program | Midhat |
| `Certifications/` | Graduate certificate PDFs | Midhat |
| `Minors and ASIs/` | One PDF per undergraduate minor, plus the general list | Abdallah |
| `Forms/` | Registrar forms (Independent Study, double degree, transfer approval, ...) | Abdallah |
| `Policies/` | Catalog policy pages (honors programs, academic regulations, degree requirements) | Abdallah |
| `json/` | The PDFs turned into the format in [docs/data-format.md](../docs/data-format.md): `minors.json` (2026-2027), `asis.json` (2025-2026), `forms-policies.json` (Abdallah); `courses.json` (all 2,137 catalog courses with prerequisite logic, 2026-2027); `bachelors.json` (CS General Track, Mining, and the three AMS emphases, 2026-2027; Samantha) | Abdallah (courses: built for Samantha/Midhat's slices); Samantha (bachelor's) |
| `CONFLICT-LOG.md` | Every place two sources disagreed, how it was resolved, and the rules used. Add a row for each new conflict | Everyone |
| `tools/` | Scripts that rebuild `json/` from the PDFs | Abdallah; `build_bachelors_json.py`: Samantha |

`json/minors.REVIEW.md` lists conflicts between the catalog PDFs and the course CSV, and rules the format cannot express.
Rebuild minors/ASIs/forms: `python -I data/tools/build_minors_json.py` (needs `pypdf`).
Rebuild bachelor's programs: from `backend/`, `uv run python -I ../data/tools/build_bachelors_json.py` (needs `pypdf`, already in the backend environment); `json/bachelors.REVIEW.md` lists the same kinds of conflicts and gaps for the bachelor's PDFs. Tests: from `backend/`, `uv run pytest tests/test_bachelors_data.py`.
Rebuild courses: `python3 data/tools/build_courses_json.py` (standard library only); `json/courses.REVIEW.md` lists everything it could not convert cleanly, and `json/courses.dropped-info.csv` lists each grade minimum and note the format could not hold. Tests for the prerequisite parser: from `backend/`, `uv run pytest ../data/tools`.
Load everything into the database (each person builds their own; the `.db` file is not in git): from `backend/`, `uv run load-data ../data`.
