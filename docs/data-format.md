# Data format

The common schema for everything the data layer stores: courses, program requirements, and forms/policies.
Everyone's data collection (bachelor's, graduate, minors/ASIs) is written into this shape before it goes into the database.
A full example of every type is in [data-format.sample.json](data-format.sample.json).

Field names use `snake_case`. Credits are numbers (not strings), since `0.5`/`1.5`-credit courses exist in the catalog CSVs already collected.

## Course

| Field | Type | Required | Notes |
|---|---|---|---|
| `code` | string | yes | e.g. `"CSCI400"`, no space. Primary key within a catalog year. |
| `subject` | string | yes | e.g. `"CSCI"` |
| `number` | string | yes | e.g. `"400"` |
| `title` | string | yes | |
| `credits` | number | yes | |
| `description` | string | yes | catalog text, may be empty string |
| `prerequisites` | Requirement \| null | no | see **Requirement expressions** below; `null` means no prerequisites |
| `corequisites` | array of course codes | no | default `[]` |
| `catalog_year` | string | yes | e.g. `"2026-2027"`; requirements change by year, so the same code can have one row per year |
| `source` | object | no | `{"url": string, "page": number}`, for the spot-check task |

### Requirement expressions

Prerequisites need real AND/OR logic, not a flat string (the raw CSVs collected so far store prerequisites as plain text like `"MATH301, MATH332."`, which this format replaces). A requirement is one of:

- A single course: `{"type": "course", "code": "MATH301"}`
- All of a list: `{"type": "AND", "of": [Requirement, ...]}`
- Any of a list: `{"type": "OR", "of": [Requirement, ...]}`
- An exception the student says they were granted (placement, instructor approval): `{"type": "exception", "label": "instructor approval"}`. The validator does not silently pass this; per DECISIONS.md it shows a warning and lets the student override.

Nest `AND`/`OR` to express real catalog text, e.g. "CSCI306 and (MATH201 or MATH223)":
```json
{"type": "AND", "of": [
  {"type": "course", "code": "CSCI306"},
  {"type": "OR", "of": [
    {"type": "course", "code": "MATH201"},
    {"type": "course", "code": "MATH223"}
  ]}
]}
```

## Program

A bachelor's, master's, PhD, minor, or ASI. A combined BS+MS is its own program entry that names its component programs (see **Combined and double-counted credits**).

| Field | Type | Required | Notes |
|---|---|---|---|
| `program_id` | string | yes | stable slug, e.g. `"cs-bs-general-track"` |
| `name` | string | yes | |
| `degree_level` | string | yes | one of `bachelor`, `master`, `phd`, `combined`, `minor`, `asi` |
| `catalog_year` | string | yes | |
| `total_credits_required` | number | yes | |
| `requirement_groups` | array of RequirementGroup | yes | see below |
| `combines` | array of program_id | no | only on a `combined` program, e.g. `["mining-bs", "mining-ms"]` |

### Requirement group

One row of the requirements table: either a fixed list a student must all take, or an elective choice.

| Field | Type | Required | Notes |
|---|---|---|---|
| `group_id` | string | yes | unique within the program |
| `label` | string | yes | e.g. `"Math and Science"` |
| `kind` | string | yes | `all` (take every course listed) or `choose_credits` (take enough of the listed courses, or any course if `courses` is omitted, to reach `credits_required`) |
| `courses` | array of course codes | no | omit for "any course counts" electives |
| `credits_required` | number | required if `kind` is `choose_credits` | |

### Combined and double-counted credits

Examples 3, 4, and 5 need credits that count toward two programs at once (a combined BS+MS, or a bachelor's plus a minor). Rather than guessing at the cap in the schema, each program names the cap explicitly:

```json
"double_counts_with": [
  {"program_id": "mining-ms", "shared_courses": ["MNGN501", "MNGN502"], "shared_credit_limit": 12}
]
```

This says: these specific courses, up to this many credits, count toward both this program's total and the named program's total. The validator reads this to avoid flagging the overlap as an error and to enforce the cap.

## Form or policy

| Field | Type | Required | Notes |
|---|---|---|---|
| `form_id` | string | yes | e.g. `"independent-study-credit"` |
| `name` | string | yes | |
| `applies_to` | array of program_id, or `["any"]` | yes | |
| `max_credits` | number | no | e.g. Independent Study's cap |
| `requires` | string | no | e.g. `"instructor approval"` |
| `url` | string | no | |
| `notes` | string | no | |

## What this format does not cover

- **Transfer credits and completed courses** are a student's data, not catalog data; they live in the Plan format (a list of completed/transferred courses with the Mines course they map to, if any), not here.
- **Catalog scraping mechanics** (how a PDF or page becomes this JSON) are the data-collection tasks' problem; this doc only fixes the shape they must produce.
