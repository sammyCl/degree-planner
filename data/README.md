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
| `json/` | The PDFs turned into the format in [docs/data-format.md](../docs/data-format.md): `minors.json` (2026-2027), `asis.json` (2025-2026), `forms-policies.json` | Abdallah |
| `CONFLICT-LOG.md` | Every place two sources disagreed, how it was resolved, and the rules used. Add a row for each new conflict | Everyone |
| `tools/` | Scripts that rebuild `json/` from the PDFs | Abdallah |

`json/minors.REVIEW.md` lists conflicts between the catalog PDFs and the course CSV, and rules the format cannot express.
Rebuild: `python -I data/tools/build_minors_json.py` (needs `pypdf`).
