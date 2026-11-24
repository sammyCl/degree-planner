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
| `credits` | number | yes | for a variable- or range-credit course (e.g. independent study), the upper bound |
| `credits_min` | number \| null | no | set together with `credits_max` when the catalog gives a range (e.g. "1-6 credits"); omit for a fixed-credit course |
| `credits_max` | number \| null | no | equal to `credits` when set; see `credits_min` |
| `equivalent_with` | array of course codes | no | courses the catalog calls equivalent ("Equivalent with ..." in the description), listed on both courses; one satisfies a prerequisite on the other, and only one counts toward a degree. Default `[]` |
| `description` | string | yes | catalog text, may be empty string |
| `prerequisites` | Requirement \| null | no | see **Requirement expressions** below; `null` means no prerequisites |
| `corequisites` | Requirement \| null | no | same shape as `prerequisites` (a flat `AND` of courses covers the common case); `null` means no corequisites |
| `catalog_year` | string | yes | e.g. `"2026-2027"`; requirements change by year, so the same code can have one row per year |
| `source` | object | no | `{"url": string, "page": number}`, for the spot-check task |

### Requirement expressions

Prerequisites need real AND/OR logic, not a flat string (the raw CSVs collected so far store prerequisites as plain text like `"MATH301, MATH332."`, which this format replaces). A requirement is one of:

- A single course: `{"type": "course", "code": "MATH301"}`, optionally with a minimum grade: `{"type": "course", "code": "MATH301", "min_grade": "C-"}`. Omit `min_grade` when the catalog states no minimum beyond a passing grade. The validator does not yet check it (BUG-026); the field exists so the requirement isn't silently lost.
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
| `thesis_based` | boolean \| null | no | only meaningful when `degree_level` is `master` or `phd`; whether the program is thesis-based. `null`/omitted means unknown. A combined program's non-thesis master's/PhD part limits when its student may take 700-level credits (see below) |

### Requirement group

One row of the requirements table: either a fixed list a student must all take, an elective choice,
or a logical rule over courses.

| Field | Type | Required | Notes |
|---|---|---|---|
| `group_id` | string | yes | unique within the program |
| `label` | string | yes | e.g. `"Math and Science"` |
| `kind` | string | yes | `all` (take every course listed), `choose_credits` (take enough of the listed courses, or any course if `courses` is omitted, to reach `credits_required`), or `requirement` (the group is met only when `requirement` resolves true; for a rule a flat list or credit count can't express, such as "this pair of courses, or that pair, never a mix") |
| `courses` | array of course codes | no | for `all`, should be non-empty — an empty list is malformed data, not a requirement that's trivially met (BUG-026, held back: not yet enforced at load, see bugs.txt) — omit for "any course counts" electives; for `requirement`, may still list every course the expression mentions (for display and catalog checks), but the validator decides whether the group is met from `requirement`, not this list |
| `credits_required` | number | required if `kind` is `choose_credits` or `requirement` | for `requirement`, a nominal credit count for bookkeeping only (e.g. so a printed program total adds up), not what the validator checks |
| `requirement` | Requirement | required if `kind` is `requirement` | same shape as a course's `prerequisites`/`corequisites` (see **Requirement expressions**), e.g. `{"type": "OR", "of": [{"type": "AND", "of": [course A, course B]}, {"type": "AND", "of": [course C, course D]}]}` for "A and B, or C and D" |
| `every_semester` | boolean | no | only meaningful when `kind` is `all`; the listed course(s) must be planned in every fall and spring semester of the plan, not just once anywhere (e.g. a 0-credit graduate seminar required each term). Default `false` |

### Combined and double-counted credits

Examples 3, 4, and 5 need credits that count toward two programs at once (a combined BS+MS, or a bachelor's plus a minor). Rather than guessing at the cap in the schema, each program names the cap explicitly:

```json
"double_counts_with": [
  {"program_id": "mining-ms", "shared_courses": ["MNGN501", "MNGN502"], "shared_credit_limit": 12}
]
```

This says: these specific courses, up to this many credits, count toward both this program's total and the named program's total. The validator reads this to avoid flagging the overlap as an error and to enforce the cap.

A combined program's undergraduate may take 700-level credits before finishing the bachelor's part only if the master's/PhD part is thesis-based (Graduate Programs catalog, Combined Undergraduate-Graduate Degree Programs). The validator flags a 700-level course from the master's/PhD part's `requirement_groups` planned no later than the bachelor's part's last planned required course, when that part's `thesis_based` is explicitly `false`.

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
