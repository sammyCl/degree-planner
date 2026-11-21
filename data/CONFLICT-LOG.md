# Conflict log for collected data

When two sources disagree, or a source is unclear, the choice made is written here so the same call can be made again later (and so a teammate can disagree with it).
The generated list of what the build script found is `data/json/minors.REVIEW.md`; this file is the human decisions about it.
Slice: minors, ASIs, forms, policies (Abdallah). Add a row here whenever a new conflict is resolved, by anyone.

## Rules used to resolve conflicts

1. **Requirement structure comes from the program PDF, course facts come from the course CSV.** Which courses a minor needs, and how many credits, follow the minor's PDF. A course's title, credits, prerequisites follow `data/Academic Catalog/mines-courses.csv`.
2. **A typo-like count error is resolved in favor of the list actually printed.** If the text says "select two of six" and lists five, the list is the evidence; use "two of the five". Record it here.
3. **Keep the code the PDF names, even if the CSV lacks it.** Do not silently swap codes, because the PDF is what the student reads. Report the missing code to the course-data owner (Samantha for bachelor's courses) and list it in `minors.REVIEW.md`.
4. **When the PDF and CSV disagree about a renamed or renumbered course, keep the PDF code and note both.** If a student-portal check or the department settles it, record who checked and when.
5. **A total that fails the university minimum is read in the way that reaches the minimum** (minor 18 credits, ASI 12), and the reading is written down.
6. **Rules the data format cannot express stay as text.** They go in the group `label` or a `note` in the REVIEW file; never invent a schema field. Propose new fields to Midhat (data format owner) instead.
7. **Anything that is a department's decision stays open** (see "Department approval" below). Do not guess a course list.
8. **Track or option choices become separate programs** (for example Electrical Engineering has four tracks), named `Minor in X (track name)`.
9. **Catalog year is stored on every program.** Do not mix years inside one program.

## Resolved

| # | Where | Conflict | Resolution | Rule | Status |
|---|---|---|---|---|---|
| 1 | Independent Study form | Registrar calls it "Independent Study Registration Form"; the proposal and plan say "Independent Study Credit form". Registrar form and graduate catalog say the deadline is Census Day; a registrar web page says add/drop. | Name kept as "Independent Study Credit Form"; deadline is Census Day (last day of registration). | Team decision, 2026-11-17 | Decided by Abdallah |
| 2 | Music minor, `LAIS422` | PDF lists LAIS422 "Real World Recording Seminar". The CSV has no LAIS422; HASS429 "Real World Recording/Research" is "Equivalent with LAIS429"; HASS422 is "Art and Environmentalism". All LAIS codes were renamed HASS. | Use **HASS429**. Abdallah checked the student registration portal and found only one course called Real World Recording (offered in spring). The PDF's "422" is treated as a typo for "429". | 4 | Resolved (portal check) |
| 3 | Water Sustainability | "Select two of the following six courses" but five are listed (CEEN472, 475, 478, 480, 482). | Two of the five. | 2 | Resolved by rule |
| 4 | Petroleum Data Analytics | "Seven courses (18 credits)" but six courses are listed (five required + one technical elective). | Six courses, 18 credits. | 2 | Resolved by rule |
| 5 | Biomechanical Engineering | "At least 11.0 credits" but also 7 required credits and "three more courses"; the university minimum is 18. | 7 required + at least 11 elective credits = 18. | 5 | Resolved by rule |
| 6 | Physics and Engineering Physics PDFs | Both PDFs contain the same page (an Engineering Physics block, then a Physics block). The Physics PDF's first block is also titled "Minor in Engineering Physics". | Engineering Physics minor built from the first block, Physics minor from the second. | 1 | Resolved by rule |
| 7 | Quantum Engineering | PDF lists CSCI481 and EENG432 (with CSCI581 and EENG532). The CSV has only the 500-level versions. | PDF codes kept. Ask Samantha whether the CSV is missing them. | 3 | Open for course data |
| 8 | Space Mining, `SPRS401` | Required course not in the CSV; the CSV has SPRS501 "Space Resources Fundamentals" (same title). | PDF code kept; probably the undergraduate number of SPRS501. | 3 | Open for course data |
| 9 | Teaching minor | PDF titles SCED464 and CSED465 "Capstone Curriculum Design"; the CSV titles them as student-teaching courses. Credits differ (CSV 1-3 for SCED262 and 6-12 for SCED465, PDF says 3 and 6). | PDF structure and credits used. | 1 | Resolved by rule |
| 10 | Course titles | CBEN412 ("Introduction to Pharmacology" vs "Pharmacokinetics"), BIOL499 ("Research Project or Internship" vs "Independent Study"), MNGN498 ("Data Analytics for Resources Engineering" vs "Special Topics"), HASS491 in GPS ("Energy Politics" vs "Energy Transition: Politics and Policy"). | Codes kept; CSV titles are the course facts. | 1, 4 | Resolved by rule |
| 11 | Electrical Engineering | Credit totals given as "18 or 20" and "19 or 21" depending on EENG282 vs MEGN300 and EENG421 vs EENG423. | The minimum is stored (18, 18, 18, 19). | 5 | Resolved by rule |
| 12 | `max_credits` for Independent Study | Midhat's sample file says 6; the form does not state a cap. | 6 is the per-course maximum: every independent study (x99) course in both course CSVs is 0.5-6 or 1-6 credits, and the registrar's hours table stops at 6. No degree-wide cap on independent study credits appears in the catalog text, so none is recorded; a department may have one. | 1 | Resolved (per course) |
| 13 | Tracks and options | EE (4 tracks), Mechanical Engineering (3 tracks), Data Science (2 options), Teaching (with and without licensure). | One program each. | 8 | Decision for Midhat to confirm |

## ASIs

- The ASI list in `data/json/asis.json` comes from the **2025-2026** catalog (extracted pages: `data/Minors and ASIs/ASIs (2025-2026 catalog, extracted pages).pdf`; general rules: `data/Policies/Minor and ASI Rules (2025-2026 catalog, pp. 23-25).pdf`).
- The catalog site was unreachable when this was collected, so the 2026-2027 pages could not be read. The 2026-2027 minors list has no ASIs and no longer lists some 2025-2026 programs (Additive Manufacturing, and the Business minor is now "Business" not "Business and Entrepreneurship"). **ASIs may have been dropped or moved in 2026-2027. Confirm in the live catalog before showing them to students.**
- Several 2025-2026 codes are not in the 2026-2027 CSV (for example CEEN360 appears to be CEEN320 "Introduction to Construction Engineering" in 2026-2027; AMFG401, AMFG421, AMFG498, EDNS480 are absent). They are kept as printed and listed in `minors.REVIEW.md`.
- 18 ASIs: Civil, Environmental, Economics, Entrepreneurship, Humanitarian Engineering, Electrical, Aerospace, Mechanical, Additive Manufacturing, Energy, Space and Planetary Science and Engineering, Underground Construction and Tunneling, Geological Engineering, Chemistry, Polymer Chemistry, Environmental Chemistry, Biochemistry, Music Technology.

## Department approval (kept open on purpose)

Some requirements say only "approved by the department". These groups have no `courses` list (the format reads that as "any course counts") and their `label` says who approves:
Chemistry minor and ASIs, Geological Engineering minor and ASI, the Geophysics minor's last 3 credits, the Individualized HASS minor, the Metallurgical and Materials Engineering minor (a sequence approved by the department head), Petroleum Engineering minor (PEGN courses approved by the department), Music Technology ASI, the Space and Planetary ASI (advisor may approve others).

- The validator must not treat these groups as satisfied by any course without telling the student.
- **For the UI:** show a notice on any group whose label says "approved" or whose `courses` is missing: "Confirm this choice with the department."
- **Proposal for Midhat:** an optional boolean on a requirement group, for example `needs_approval: true` plus `approver: "Geophysics department"`, so the UI does not have to read the label text. Not added to the schema; it is her decision.

## Course catalog (`json/courses.json`)

Built from the two course CSVs by `tools/build_courses_json.py`. Counts and every flagged item are regenerated, in full, into `json/courses.REVIEW.md`; everything the format could not hold (dropped grade minimums and notes) is also in `json/courses.dropped-info.csv`.

- **Same code in both CSVs:** about 950 codes (the 400-level cross-listed courses) appear in both files, some more than once in the graduate file. One entry per code. The undergraduate row wins (it carries the catalog URL); an empty field is filled from the other rows; a shorter description that is a prefix of a longer one is replaced by the longer. Real disagreements (title, credits, prerequisites) keep the undergraduate value and are listed in the review file.
- **Credit ranges** ("1-6", "0.5-6"; 471 courses, mostly independent study, thesis, special topics): the format has one number, so the upper bound is used, as for minors. Open question for Midhat: does the format need a minimum and maximum?
- **Prerequisite text becomes AND/OR logic** (`tools/prereq_parser.py`, tested in `tools/test_prereq_parser.py`):
  - A comma or "and" means AND; "or" binds tighter, so "MATH225 or MATH235 and MATH332 or MATH342" is (225 or 235) AND (332 or 342); a list that is only commas ending in ", or" is one OR.
  - A bare number after a code inherits its subject ("MATH 201 or 530").
  - "Instructor consent", "permission of instructor" and "or equivalent" become `exception` requirements (the validator warns and the student can override).
  - **Grade minimums** ("with a C- or better") are dropped because the format has no grade field. Open question for Midhat. **Every course affected (67) is listed with the exact wording in `json/courses.REVIEW.md` and in `json/courses.dropped-info.csv`**, so a grade field can be added later and filled from that list. Grade wording inside free-text prerequisites is not dropped: it stays in the exception's label.
  - Notes about credit or repetition ("Variable credit...", "Repeatable for credit...", "Independent Study form must be completed...") are dropped from prerequisites; each one is listed in the same two files (kind `credit/repeat note`).
  - **Free text** that is not course logic ("Graduate standing", "Enrollment in Chemistry M.S. program") is kept whole as one `exception` with the original text as its label, so nothing is lost and nothing is silently passed. If a `;`-separated clause has course codes, those clauses are kept as real requirements and only the free-text clauses become exceptions ("mixed").
- **Corequisites** are a plain list in the format, so an OR ("PHGN300 or PHGN310") or free text cannot be expressed and is left empty and reported. Open question for Midhat.
- **Codes the catalog does not have:** prerequisite codes that match no course (typos like `CSC128`, retired courses) are kept as written and listed in the review file, not corrected.
- **Placeholder and special codes** (`CHGN1XX`, `HASS2XX`, `CEEN599AB`, lab sections such as `MTGN348L`) are real catalog entries and are kept.
- **Titles** are in capitals in the catalog and are converted to title case (small words lower, Roman numerals and common acronyms kept); a few unusual acronyms may be off. Titles that already have lower-case letters are untouched.
- **Source:** undergraduate rows carry their catalog URL. The graduate CSV has a PDF page number and no URL, so the six courses only it has carry no `source`.
- **Catalog year:** 2026-2027 for all courses, matching the minors.
- **Programs that reference codes missing from the catalog:** `CSCI481`, `EENG432`, `SPRS401` (Quantum Engineering, Space Mining minors) and `CEEN360`, `EDNS480`, `AMFG401`, `AMFG421`, `AMFG498` (ASIs). The program PDFs list them, so the programs keep them; Samantha is checking the CSV.

## Catalog years

- Minors and forms/policies: 2026-2027. ASIs: 2025-2026 (see above).
- The catalog changes every year and mid-year; the student registration portal (Trailhead) is the most current source but is private to students. Student-only data cannot be collected into this public repo (it is private, and the repo is public).
