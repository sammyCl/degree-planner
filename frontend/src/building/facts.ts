// Facts shown while a plan is being built. Every one comes from the catalog data we collected (data/ and the
// program PDFs), not from memory; the source is noted next to each. Add new ones the same way.

/** How long each fact stays on screen, in milliseconds (the cross-fade itself is in BuildingScreen.css). */
export const FACT_INTERVAL_MS = 7500

export interface Fact {
  topic: string
  text: string
}

export const FACTS: Fact[] = [
  {
    // data/json/bachelors.json: all 44 bachelor's programs include HASS215
    topic: 'What HASS means',
    text: 'HASS stands for Humanities, Arts, and Social Sciences. Every bachelor\'s degree includes HASS215 Futures.',
  },
  {
    // degree tables for Geological, Chemistry, Geophysical and Civil Engineering list field sessions in the Summer rows
    topic: 'Field sessions',
    text: 'Field sessions, like Field Geology (5 credits), are usually taken in the summer.',
  },
  {
    // Geophysical Engineering PDF, footnote 2; the other programs use the same 6 mid-level + 3 upper-level split
    topic: 'Culture and Society',
    text: 'CAS means Culture and Society: 9 elective credits in most degrees, at least 3 at the 400 level.',
  },
  {
    // PDF footnote in every bachelor's table; all 44 programs require EBGN321
    topic: 'Engineering Economics',
    text: 'EBGN321 needs 60 credit hours first, so it usually waits until junior year.',
  },
  {
    // Registrar core-curriculum page; every program has a success-wellness group
    topic: 'Success and Wellness',
    text: 'Every bachelor\'s degree includes a 1-credit Success and Wellness elective.',
  },
  {
    // Electrical, Civil, Construction, Environmental, Mechanical, Design and Quantum Systems degree tables
    topic: 'Senior capstone',
    text: 'Many engineering degrees end with a two-semester capstone: EDNS491 and EDNS492.',
  },
  {
    // data/json/forms-policies.json, the minor and ASI policies from the 2026-2027 catalog
    topic: 'Minors and ASIs',
    text: 'A minor needs at least 18 credits, and an Area of Special Interest (ASI) at least 12.',
  },
  {
    // data/json/forms-policies.json: the Independent Study credit form
    topic: 'Independent Study',
    text: 'Independent Study credit needs a form, due by Census Day.',
  },
  {
    // planner.md: the credit limits the planning assistant follows
    topic: 'Credit limits',
    text: 'The planning assistant keeps undergraduate semesters at 18 credits or fewer.',
  },
  {
    // data/json/courses.json and the program files
    topic: 'The catalog',
    text: 'The planner reads 2,137 courses and 44 bachelor\'s programs from the 2026-2027 catalog.',
  },
]
