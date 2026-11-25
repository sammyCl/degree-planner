// Facts shown while a plan is being built. Every one comes from the catalog data we collected (data/ and the
// program PDFs), not from memory; the source is noted next to each. Add new ones the same way.

export interface Fact {
  topic: string
  text: string
}

export const FACTS: Fact[] = [
  {
    // data/json/bachelors.json: all 44 bachelor's programs include these in their requirements
    topic: 'What HASS means',
    text: 'HASS stands for Humanities, Arts, and Social Sciences. Every bachelor\'s degree includes HASS215 Futures, and starts with HASS100 Nature and Human Values (honors students take HNRS105 and HNRS115 instead).',
  },
  {
    // degree tables for Geological, Chemistry, Geophysical and Civil Engineering list these in the Summer rows
    topic: 'Field sessions',
    text: 'Field sessions are usually taken in the summer. Geological Engineering has Field Geology (5 credits), Chemistry has a 6-credit Field Session, Geophysics has Field Camp, and Civil Engineering has a 3-credit Engineering Field Session.',
  },
  {
    // Geophysical Engineering PDF, footnote 2; the other programs' CAS slots follow the same 6 mid-level + 3 upper split
    topic: 'Culture and Society',
    text: 'CAS means Culture and Society. These restricted electives add up to 9 credits in most degrees, and at least 3 of them have to be 400-level courses.',
  },
  {
    // PDF footnote in every bachelor's table; all 44 programs require EBGN321
    topic: 'Engineering Economics',
    text: 'EBGN321 Engineering Economics is in all 44 bachelor\'s programs, but it needs 60 completed credit hours first, so it usually waits until junior year.',
  },
  {
    // Registrar core-curriculum page, read for the bachelor's data; CSM101 and CSM202 are in all 44 programs
    topic: 'Success and Wellness',
    text: 'Every bachelor\'s degree includes the 1-credit Freshman Success Seminar (CSM101), a 1-credit well-being course (CSM202), and one more Success and Wellness credit. That one can be CSM250, CSM275, CSM350, or any 1-credit PAGN 2xx course.',
  },
  {
    // Electrical, Civil, Construction, Environmental, Mechanical, Design and Quantum Systems degree tables
    topic: 'Senior capstone',
    text: 'Many engineering degrees end with a two-semester capstone: EDNS491 Capstone Design I and EDNS492 Capstone Design II, 3 credits each.',
  },
  {
    // data/json/forms-policies.json, the minor and ASI policies from the 2026-2027 catalog
    topic: 'Minors and ASIs',
    text: 'A minor needs at least 18 credits and an Area of Special Interest (ASI) at least 12. In both, at least 9 credits cannot be used for any other part of your degree, except free electives.',
  },
  {
    // data/json/forms-policies.json: the Independent Study credit form
    topic: 'Independent Study',
    text: 'Independent Study credit needs a form turned in to the Registrar, and the deadline is Census Day.',
  },
  {
    // planner.md: the credit limits the planning assistant follows
    topic: 'Credit limits',
    text: 'The planning assistant keeps each undergraduate semester at 18 credits or fewer, and each graduate semester at 15 or fewer.',
  },
  {
    // data/json/courses.json and the program files
    topic: 'The catalog',
    text: 'The planner reads 2,137 courses and 44 bachelor\'s programs from the 2026-2027 catalog, and checks every plan with rules code, not guesses.',
  },
]
