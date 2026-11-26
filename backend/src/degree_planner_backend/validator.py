"""Plan validator (docs/plan-format.md): rules code, no LLM.

Checks prerequisite order, credit totals, program requirements, double-counted
credits, and claimed exceptions. Returns a new Plan with `prerequisite_edges`,
`flags`, and `summary` filled in. Used by the frontend's drag-and-drop check and
by the agent's `check_plan` tool.
"""

from __future__ import annotations

import re
import sqlite3

from degree_planner_backend.lookups import NotFoundError, get_course, get_program, program_years
from degree_planner_backend.models import Program, Requirement, RequirementGroup
from degree_planner_backend.plan_models import (
    CountsToward,
    Edge,
    Flag,
    FlagSeverity,
    FlagType,
    Plan,
    RequirementStatus,
    Semester,
    Summary,
)

# A transcript's placeholder credit, as the transcript reader numbers it: "HASS2XX-1" (subject, level digit).
_PLACEHOLDER_CODE = re.compile(r"^([A-Z]{2,5})(\d)XX(?:-?\d+)?$")  # the agent drops the hyphen: "HASS2XX1"
_SUBJECT_LEVEL = re.compile(r"^([A-Z]{2,5})(\d)\d{2}[A-Z]?$")
_GRADUATE_LEVELS = ("master", "phd")
# 2026-2027 Graduate Catalog: up to 15 credits a semester without extra approval for a graduate
# student; 18 for an undergraduate (BUG-026a). The same numbers the agent's planner.md already
# tells the model to count for itself, since check_plan didn't check this until now.
_SEMESTER_CREDIT_LIMIT_GRADUATE = 15.0
_SEMESTER_CREDIT_LIMIT_UNDERGRAD = 18.0


def _course_number(code: str) -> int | None:
    """The numeric part of a course code (e.g. 562 for "CSCI562"), or None if it has none."""
    match = re.search(r"\d+", code)
    return int(match.group()) if match else None


def _resolve(requirement: Requirement | None, satisfied_codes: set[str]) -> bool:
    if requirement is None:
        return True
    if requirement.type == "course":
        return requirement.code in satisfied_codes
    if requirement.type == "exception":
        return True
    if requirement.type == "AND":
        return all(_resolve(sub, satisfied_codes) for sub in requirement.of)
    return any(_resolve(sub, satisfied_codes) for sub in requirement.of)  # OR


def _describe(requirement: Requirement) -> str:
    if requirement.type == "course":
        return requirement.code
    if requirement.type == "exception":
        return f"an exception ({requirement.label})"
    if requirement.type == "AND":
        return " and ".join(_describe(sub) for sub in requirement.of)
    return "(" + " or ".join(_describe(sub) for sub in requirement.of) + ")"


def _course_codes(requirement: Requirement | None) -> list[str]:
    if requirement is None or requirement.type == "exception":
        return []
    if requirement.type == "course":
        return [requirement.code]
    return [code for sub in requirement.of for code in _course_codes(sub)]


def _satisfied_branch(requirement: Requirement, satisfied_codes: set[str]) -> list[str] | None:
    """The course codes of one combination requirement describes that satisfied_codes meets (the
    first OR branch that works, every course of an AND), or None if no combination does (BUG-038:
    a "requirement" group, e.g. the Thorson swap, is met by one specific pair, never a mix)."""
    if requirement.type == "course":
        return [requirement.code] if requirement.code in satisfied_codes else None
    if requirement.type == "exception":
        return []
    if requirement.type == "AND":
        codes: list[str] = []
        for sub in requirement.of:
            sub_codes = _satisfied_branch(sub, satisfied_codes)
            if sub_codes is None:
                return None
            codes.extend(sub_codes)
        return codes
    for sub in requirement.of:  # OR
        sub_codes = _satisfied_branch(sub, satisfied_codes)
        if sub_codes is not None:
            return sub_codes
    return None


def _exception_labels(requirement: Requirement | None) -> list[str]:
    # BUG-026(d) (held back): an earlier version of this only returned labels for branches "needed"
    # to satisfy an OR (e.g. not OR(CSCI100, exception) once CSCI100 is satisfied). Reverted: the
    # chatbot's whole Exception handling feature (chat_tools.py's open_exceptions/accept_exception,
    # test_chat_tools.py, test_chat_loop.py) is built on this unconditionally surfacing every
    # exception a course's prerequisites could rely on, regardless of whether another branch is
    # already satisfied — e.g. test_accept_an_exception_the_student_was_granted plans TEST101 (which
    # would satisfy OR(TEST101, exception)) in an earlier semester and still expects TEST201 to show
    # as an open exception. Needs Samantha's call, same shape as the other held-back bugs.
    if requirement is None or requirement.type == "course":
        return []
    if requirement.type == "exception":
        return [requirement.label]
    return [label for sub in requirement.of for label in _exception_labels(sub)]


_ADD_ON_LEVELS = ("minor", "asi", "certificate")
# The 9-credit-unshared rule below (policy-minor-requirements and policy-asi-requirements) is
# stated only for minors and ASIs; no certificate policy is loaded yet, so it stays narrower than
# _ADD_ON_LEVELS rather than guessing the same rule applies.
_UNSHARED_MIN_LEVELS = ("minor", "asi")
# Minor and ASI share the same rule: at least 9 credits not used for any other part of the
# degree except free electives (18 total for a minor, 12 for an ASI). Confirmed 2026-11-25
# (BUG-052) against the 2025-2026 Undergraduate Catalog (p. 24, "Minimum Hours Outside of Degree
# Requirements - 9.0", stated identically for Minors and for Areas of Special Interest), the
# newest catalog PDF Mines has published, plus the live CASA advising FAQ (casa.mines.edu/faqs,
# current as of Spring 2027 registration), which independently states the same 9-credit minor
# rule; catalog.mines.edu itself (which may already show 2026-2027) was unreachable to check
# directly. The rule has held unchanged across at least the 2019-2020 through 2025-2026 catalogs.
ADD_ON_UNSHARED_MIN = 9.0


def _unshared_credits(
    add_on: Program, degree_parts: list[Program], have: set[str], credits: dict[str, float]
) -> tuple[float, list[str]]:
    """Credits filling the minor or ASI that the degree does not also need, read in the student's
    favor because a plan does not say which course fills which group:
    - a course is shared when a degree part needs it: it is in an "all" group, or in a listed
      choose group the plan's other courses do not already fill (a group with no list is free
      electives, which may be shared);
    - the add-on is filled group by group, unshared courses first, whole courses, up to each
      group's credits; a group with no list takes any course not already counted for it.
    Returns the unshared credits and the shared courses used."""
    degree_all = {c for part in degree_parts for g in part.requirement_groups if g.kind == "all" for c in g.courses or []}

    def is_shared(code: str) -> bool:
        if code in degree_all:
            return True
        for part in degree_parts:
            for g in part.requirement_groups:
                if g.kind != "all" and g.courses and code in g.courses:
                    others = sum(credits.get(c, 0.0) for c in g.courses if c in have and c != code and c not in degree_all)
                    if others < (g.credits_required or 0.0):
                        return True
        return False

    used: dict[str, bool] = {}
    for group in add_on.requirement_groups:
        if group.kind == "all":
            for code in group.courses or []:
                if code in have:
                    used.setdefault(code, is_shared(code))
            continue
        pool = sorted(c for c in (group.courses or sorted(have)) if c in have and c not in used)
        pool.sort(key=is_shared)  # unshared first; sort is stable, so code order otherwise
        earned = 0.0
        for code in pool:
            if earned >= (group.credits_required or 0.0):
                break
            used[code] = is_shared(code)
            earned += credits.get(code, 0.0)
    unshared = sum(credits.get(c, 0.0) for c, shared in used.items() if not shared)
    return unshared, sorted(c for c, shared in used.items() if shared)


def _equivalents(connection: sqlite3.Connection, code: str, catalog_year: str) -> list[str]:
    """Courses the catalog calls equivalent to code (BUG-041); [] for a code not in the catalog."""
    try:
        return list(get_course(connection, code, catalog_year).equivalent_with)
    except NotFoundError:
        return []


def _inferred_equivalents(connection: sqlite3.Connection, code: str, catalog_year: str) -> list[str]:
    """The subset of _equivalents(code, ...) the catalog text never actually states, only inferred
    by the team's rule (BUG-055); [] for a code not in the catalog."""
    try:
        return list(get_course(connection, code, catalog_year).equivalent_with_inferred)
    except NotFoundError:
        return []


def _add_on_with_fallback(connection: sqlite3.Connection, program_id: str, requested_year: str) -> tuple[Program, str] | None:
    """A minor, ASI or certificate not re-collected for the student's own catalog year falls back
    to its own newest stored year no later than requested_year, unlike the student's actual degree
    (bachelor's/master's/combined), which never falls back: using a stale year for an add-on is a
    much smaller risk than for the degree itself. None if nothing usable is stored at or before
    requested_year, or the fallback year's program turns out not to be an add-on level either."""
    years = [year for year in program_years(connection, program_id) if year <= requested_year]
    if not years:
        return None
    fallback_year = max(years)
    try:
        program = get_program(connection, program_id, fallback_year)
    except NotFoundError:
        return None
    return (program, fallback_year) if program.degree_level in _ADD_ON_LEVELS else None


def check_plan(connection: sqlite3.Connection, plan: Plan) -> Plan:
    student = plan.student
    catalog_year = student.catalog_year

    previously_overridden = {(flag.type, flag.course_id) for flag in plan.flags if flag.overridden}

    semesters = [
        Semester(
            semester_id=semester.semester_id,
            label=semester.label,
            courses=semester.courses,
            total_credits=sum(course.credits for course in semester.courses),
        )
        for semester in plan.semesters
    ]

    code_to_course_ids: dict[str, list[tuple[int, str]]] = {}
    for index, semester in enumerate(semesters):
        for course in semester.courses:
            code_to_course_ids.setdefault(course.code, []).append((index, course.course_id))

    flags: list[Flag] = []
    edges: list[Edge] = []
    flag_count = 0

    def add_flag(flag_type: FlagType, severity: FlagSeverity, course_id: str | None, message: str, overridable: bool) -> None:
        nonlocal flag_count
        flag_count += 1
        flags.append(
            Flag(
                flag_id=f"flag-{flag_count}",
                type=flag_type,
                severity=severity,
                course_id=course_id,
                message=message,
                overridable=overridable,
                overridden=overridable and (flag_type, course_id) in previously_overridden,
            )
        )

    # Which requirement groups each planned course fills (code -> groups), for Plan.counts_toward.
    counts: dict[str, list[CountsToward]] = {}

    # Whether each requirement group is met, in the programs' own order, for Plan.requirement_status.
    statuses: list[tuple[int, int, RequirementStatus]] = []
    program_rank = 0

    def report(group: RequirementGroup, program: Program, met: bool, **fields: float | int | None) -> None:
        order = [g.group_id for g in program.requirement_groups]
        statuses.append(
            (
                program_rank,
                order.index(group.group_id),
                RequirementStatus(
                    program_id=program.program_id, group_id=group.group_id, label=group.label, kind=group.kind, met=met, **fields
                ),
            )
        )

    def record(code: str, program: Program, group: RequirementGroup) -> None:
        entry = CountsToward(program_id=program.program_id, group_id=group.group_id, label=group.label)
        if entry not in counts.setdefault(code, []):
            counts[code].append(entry)

    equivalent: dict[str, list[str]] = {}
    inferred_equivalent: dict[str, list[str]] = {}

    def with_equivalents(codes: set[str]) -> set[str]:
        """codes plus their equivalent courses: an equivalent course satisfies a prerequisite (BUG-041)."""
        out = set(codes)
        for code in codes:
            if code not in equivalent:
                equivalent[code] = _equivalents(connection, code, catalog_year)
                inferred_equivalent[code] = _inferred_equivalents(connection, code, catalog_year)
            out.update(equivalent[code])
        return out

    satisfied_before = with_equivalents({completed.code for completed in student.completed_courses})
    for semester in semesters:
        # BUG-049: a corequisite, unlike a prerequisite, is met by the same semester as well as an
        # earlier one.
        satisfied_with_semester = satisfied_before | with_equivalents({c.code for c in semester.courses})
        for course in semester.courses:
            try:
                fetched = get_course(connection, course.code, catalog_year)
                requirement = fetched.prerequisites
                coreq = fetched.corequisites
            except NotFoundError:
                requirement = None
                coreq = None

            for code in _course_codes(requirement):
                candidates = [(i, cid) for i, cid in code_to_course_ids.get(code, []) if cid != course.course_id]
                if candidates:
                    _, from_id = min(candidates, key=lambda pair: pair[0])
                    edges.append(Edge(**{"from": from_id, "to": course.course_id}))

            for label in _exception_labels(requirement):
                add_flag(
                    "exception_claimed",
                    "warning",
                    course.course_id,
                    f"{course.code} relies on a claimed exception ({label}); confirm it still applies.",
                    True,
                )

            if course.status == "planned" and not _resolve(requirement, satisfied_before):
                assert requirement is not None  # _resolve(None, ...) is always True
                add_flag(
                    "broken_prerequisite",
                    "error",
                    course.course_id,
                    f"{course.code} requires {_describe(requirement)} to be completed in an earlier semester.",
                    False,
                )

            if course.status == "planned" and not _resolve(coreq, satisfied_with_semester):
                assert coreq is not None  # _resolve(None, ...) is always True
                add_flag(
                    "broken_prerequisite",
                    "error",
                    course.course_id,
                    f"{course.code} needs {_describe(coreq)} as a corequisite, in the same semester "
                    "or an earlier one.",
                    False,
                )

        satisfied_before |= with_equivalents({course.code for course in semester.courses})

    code_credits: dict[str, float] = {completed.code: completed.credits for completed in student.completed_courses}
    for semester in semesters:
        for course in semester.courses:
            code_credits.setdefault(course.code, course.credits)

    # Of a set of equivalent courses only the first (completed, then by semester) counts toward the
    # degree; the others still satisfy prerequisites above but add no credits and fill no group
    # (BUG-041). stand_in lets a group that lists one course be filled by its counted equivalent.
    taken_in_order = [completed.code for completed in student.completed_courses] + [
        course.code for semester in semesters for course in semester.courses
    ]
    plan_codes: set[str] = set()
    duplicate_of: dict[str, str] = {}
    for code in dict.fromkeys(taken_in_order):
        twin = next((other for other in equivalent.get(code, []) if other in plan_codes), None)
        if twin is None:
            plan_codes.add(code)
        else:
            duplicate_of[code] = twin
    stand_in: dict[str, str] = {}
    for code in sorted(plan_codes):
        for other in equivalent.get(code, []):
            if other not in plan_codes:
                stand_in.setdefault(other, code)
    for code, twin in duplicate_of.items():
        add_flag(
            "requirement_unmet",
            "warning",
            next((cid for _, cid in code_to_course_ids.get(code, [])), None),
            f"{code} is equivalent to {twin}, so only {twin} counts toward the degree; {code} adds no credits.",
            False,
        )

    # BUG-055: flag a stand-in only once per (listed, actual) pair, and only when the catalog
    # never actually states the equivalence (it's the team's own inference, worth confirming),
    # unlike an equivalence the catalog states as fact.
    flagged_assumed: set[tuple[str, str]] = set()

    def flag_if_assumed(listed_code: str, actual_code: str) -> None:
        if actual_code == listed_code or (listed_code, actual_code) in flagged_assumed:
            return
        if listed_code not in inferred_equivalent.get(actual_code, []):
            return
        flagged_assumed.add((listed_code, actual_code))
        add_flag(
            "assumed_equivalent",
            "warning",
            next((cid for _, cid in code_to_course_ids.get(actual_code, [])), None),
            f"{actual_code} stands in for {listed_code} here, but the catalog never states they are "
            "equivalent; this is the team's own inference. Confirm with your advisor.",
            False,
        )

    # A minor or ASI adds no credit total of its own on top of a degree (BUG-037): its groups make
    # sure its courses are planned, and its courses may also be the degree's free electives. Its
    # total counts only when the student has no degree program.
    loaded = []
    for program_id in student.programs:
        try:
            loaded.append(get_program(connection, program_id, catalog_year))
        except NotFoundError:
            fallback = _add_on_with_fallback(connection, program_id, catalog_year)
            if fallback is None:
                continue
            program, fallback_year = fallback
            loaded.append(program)
            add_flag(
                "stale_program_year",
                "warning",
                None,
                f"{program.name} is not in the {catalog_year} catalog data; using the newest version "
                f"on record ({fallback_year}) instead. Confirm its requirements with your advisor.",
                False,
            )
    has_degree = any(p.degree_level not in _ADD_ON_LEVELS for p in loaded)
    total_credits_required = 0.0
    # The first semester after a combined program's bachelor's part is done (BUG-026a: that's also
    # when the per-semester credit limit switches from undergraduate to graduate), or None if the
    # student isn't in a combined program or hasn't planned any of the bachelor's required courses.
    # KEEP IN SYNC: agent/chat_tools.py (_combined_boundary_semester, semester_credit_limits)
    # copies this rule to show the chatbot each semester's limit and room. If you change how this
    # boundary is found, change it there too (test_chat_limits_match_the_validator checks it).
    combined_boundary_semester: int | None = None
    for program in loaded:
        if not (has_degree and program.degree_level in _ADD_ON_LEVELS):
            total_credits_required += program.total_credits_required

        requirement_programs: list[Program]
        if program.combines:
            requirement_programs = []
            for component_id in program.combines:
                try:
                    requirement_programs.append(get_program(connection, component_id, catalog_year))
                except NotFoundError:
                    continue
        else:
            requirement_programs = [program]

        if program.combines:
            # A combined-program student is still an undergraduate until the bachelor's part is
            # done, and may take 700-level credits before then only in a thesis-based master's/PhD
            # (BUG-044). thesis_based is None (unknown) for most programs on purpose, so this only
            # fires where the data says the master's/PhD part is known non-thesis.
            bachelor_part = next((p for p in requirement_programs if p.degree_level == "bachelor"), None)
            grad_part = next(
                (p for p in requirement_programs if p.degree_level in _GRADUATE_LEVELS and p.thesis_based is False),
                None,
            )
            if bachelor_part is not None:
                bachelor_codes = {c for g in bachelor_part.requirement_groups for c in (g.courses or [])}
                bachelor_semesters = [
                    index
                    for code in bachelor_codes
                    if code in plan_codes
                    for index, _ in code_to_course_ids.get(code, [])
                ]
                if bachelor_semesters:
                    last_bachelor_semester = max(bachelor_semesters)
                    combined_boundary_semester = last_bachelor_semester
                    if grad_part is not None:
                        grad_codes = {c for g in grad_part.requirement_groups for c in (g.courses or [])}
                        for code in grad_codes:
                            if code not in plan_codes or (_course_number(code) or 0) < 700:
                                continue
                            for index, course_id in code_to_course_ids.get(code, []):
                                if index <= last_bachelor_semester:
                                    add_flag(
                                        "ineligible_course",
                                        "error",
                                        course_id,
                                        f"{code} is a 700-level course in {grad_part.name}, a non-thesis "
                                        f"program; {bachelor_part.name} still has work planned through "
                                        f"{semesters[last_bachelor_semester].label}. Combined-program "
                                        "undergraduates may take 700-level credits only in a thesis-based "
                                        "program.",
                                        False,
                                    )

        for req_program in requirement_programs:
            program_rank += 1
            for double_count in req_program.double_counts_with:
                shared_used = sum(
                    code_credits.get(code, 0.0) for code in double_count.shared_courses if code in plan_codes
                )
                if shared_used > double_count.shared_credit_limit:
                    add_flag(
                        "double_count_exceeded",
                        "error",
                        None,
                        f"{req_program.name} and {double_count.program_id} share {shared_used} credits, "
                        f"over the {double_count.shared_credit_limit}-credit cap.",
                        False,
                    )

            # A course counts toward at most one group of this program (BUG-025): "all" groups and
            # "requirement" groups (BUG-038) claim their courses first, then choose_credits groups
            # with an explicit list, in the order they're declared, then choose_credits groups with
            # no list (free electives) take whatever is left. Cross-program double counting is
            # unaffected; that's double_counts_with's job, above.
            available = set(plan_codes)
            all_groups = [g for g in req_program.requirement_groups if g.kind == "all"]
            requirement_groups_kind = [g for g in req_program.requirement_groups if g.kind == "requirement"]
            choose_with_list = [g for g in req_program.requirement_groups if g.kind == "choose_credits" and g.courses]
            choose_without_list = [
                g for g in req_program.requirement_groups if g.kind == "choose_credits" and not g.courses
            ]

            for group in all_groups:
                listed = group.courses or []
                missing = [code for code in listed if code not in plan_codes and code not in stand_in]
                if missing:
                    add_flag(
                        "requirement_unmet",
                        "error",
                        None,
                        f"{req_program.name}: {group.label} is missing {', '.join(missing)}.",
                        False,
                    )
                report(
                    group,
                    req_program,
                    not missing,
                    credits_earned=sum(code_credits.get(code, 0.0) for code in listed if code in plan_codes),
                    missing_count=len(missing),
                )
                if group.every_semester:
                    # BUG-042: a 0-credit graduate seminar required every fall and spring
                    # semester isn't met by appearing once anywhere, unlike a normal "all" group.
                    for semester in semesters:
                        if not semester.label.startswith(("Fall", "Spring")):
                            continue
                        semester_codes = {course.code for course in semester.courses}
                        still_missing = [code for code in listed if code not in semester_codes]
                        if still_missing:
                            add_flag(
                                "requirement_unmet",
                                "error",
                                None,
                                f"{req_program.name}: {group.label} needs {', '.join(still_missing)} "
                                f"in every fall and spring semester; missing in {semester.label}.",
                                False,
                            )
                for code in listed:
                    actual = code if code in plan_codes else stand_in.get(code, "")
                    if actual in plan_codes:
                        record(actual, req_program, group)
                        flag_if_assumed(code, actual)
                available -= set(listed) | {stand_in[code] for code in listed if code in stand_in}

            for group in requirement_groups_kind:
                assert group.requirement is not None  # enforced by the model
                satisfied_codes = plan_codes | set(stand_in.keys())
                branch = _satisfied_branch(group.requirement, satisfied_codes)
                report(group, req_program, branch is not None, credits_required=group.credits_required)
                if branch is None:
                    add_flag(
                        "requirement_unmet",
                        "error",
                        None,
                        f"{req_program.name}: {group.label} needs {_describe(group.requirement)}.",
                        False,
                    )
                else:
                    for code in branch:
                        actual = code if code in plan_codes else stand_in.get(code, "")
                        if actual in plan_codes:
                            record(actual, req_program, group)
                            flag_if_assumed(code, actual)
                    available -= set(branch) | {stand_in[code] for code in branch if code in stand_in}

            for group in choose_with_list + choose_without_list:
                candidates = group.courses if group.courses else sorted(available)
                # A graduate-degree elective group with no fixed course list still can't be filled
                # by an undergraduate-level course (BUG-043): the Graduate Catalog says
                # undergraduate courses don't count toward a graduate degree's requirements. A
                # group that does list its courses is trusted as-is (e.g. a combined program's
                # project group may deliberately list a 700-level course for a master's student).
                if not group.courses and req_program.degree_level in _GRADUATE_LEVELS:
                    candidates = [code for code in candidates if (_course_number(code) or 0) >= 500]
                credits_required = group.credits_required or 0.0
                earned = 0.0
                claimed: set[str] = set()
                # Placeholder credit from a transcript ("HASS2XX-1": a 200-level HASS elective Mines granted
                # without naming the course) fills a listed group when the group lists a course of the same
                # subject and level. It counts before planned courses: credit already earned fills the group
                # first, so a planned course it makes unnecessary shows as extra. "FREE1XX" matches no list,
                # so it stays a free elective.
                if group.courses:
                    levels = {(m.group(1), m.group(2)) for c in group.courses if (m := _SUBJECT_LEVEL.match(c))}
                    for code in sorted(available):
                        placeholder = _PLACEHOLDER_CODE.match(code)
                        if not placeholder or (placeholder.group(1), placeholder.group(2)) not in levels:
                            continue
                        if earned >= credits_required:
                            break
                        earned += code_credits.get(code, 0.0)
                        claimed.add(code)
                for listed_code in candidates:
                    code = listed_code if listed_code in available else stand_in.get(listed_code, "")
                    if code not in available or code in claimed:
                        continue
                    if earned >= credits_required:
                        break
                    earned += code_credits.get(code, 0.0)
                    claimed.add(code)
                    flag_if_assumed(listed_code, code)
                report(group, req_program, earned >= credits_required, credits_required=credits_required, credits_earned=earned)
                if earned < credits_required:
                    add_flag(
                        "credit_shortfall",
                        "error",
                        None,
                        f"{req_program.name}: {group.label} needs {credits_required} credits, "
                        f"only {earned} completed or planned.",
                        False,
                    )
                for code in claimed:
                    record(code, req_program, group)
                available -= claimed

    # No semester over the Mines per-term credit limit (BUG-026a): graduate throughout for a
    # master's/PhD student, graduate only after the bachelor's part is done for a combined student,
    # undergraduate otherwise.
    # KEEP IN SYNC: agent/chat_tools.py (semester_credit_limits, CREDIT_LIMIT_UNDERGRADUATE/GRADUATE)
    # copies these limits and this rule. If you change them, change it there too.
    for index, semester in enumerate(semesters):
        if student.degree_level in _GRADUATE_LEVELS or (
            combined_boundary_semester is not None and index > combined_boundary_semester
        ):
            limit = _SEMESTER_CREDIT_LIMIT_GRADUATE
        else:
            limit = _SEMESTER_CREDIT_LIMIT_UNDERGRAD
        if semester.total_credits > limit:
            add_flag(
                "semester_overload",
                "error",
                None,
                f"{semester.label} has {semester.total_credits:g} credits, over the {limit:g}-credit "
                f"limit for {'a graduate' if limit == _SEMESTER_CREDIT_LIMIT_GRADUATE else 'an undergraduate'} "
                "semester.",
                False,
            )

    # Every minor and ASI: at least 9 of its credits not used for any other part of the degree
    # except free electives (BUG-036; policy-minor-requirements and policy-asi-requirements).
    if has_degree:
        degree_parts: list[Program] = []
        for program in loaded:
            if program.degree_level in _ADD_ON_LEVELS:
                continue
            if program.combines:
                for component_id in program.combines:
                    try:
                        degree_parts.append(get_program(connection, component_id, catalog_year))
                    except NotFoundError:
                        continue
            else:
                degree_parts.append(program)
        for add_on in (p for p in loaded if p.degree_level in _UNSHARED_MIN_LEVELS):
            unshared, shared = _unshared_credits(add_on, degree_parts, plan_codes, code_credits)
            if unshared < ADD_ON_UNSHARED_MIN:
                add_flag(
                    "requirement_unmet",
                    "error",
                    None,
                    f"{add_on.name}: only {unshared:g} of its credits are not also used for the degree "
                    f"(shared: {', '.join(shared) or 'none'}); at least {ADD_ON_UNSHARED_MIN:g} must not be, "
                    "except free electives.",
                    False,
                )

    total_credits = sum(semester.total_credits for semester in semesters) + sum(
        completed.credits for completed in student.completed_courses
    ) - sum(code_credits.get(code, 0.0) for code in duplicate_of)
    if total_credits < total_credits_required:
        add_flag(
            "credit_shortfall",
            "error",
            None,
            f"Plan has {total_credits} credits; needs {total_credits_required}.",
            False,
        )

    requirements_met = not any(flag.severity == "error" and not flag.overridden for flag in flags)

    return Plan(
        plan_id=plan.plan_id,
        student=student,
        semesters=semesters,
        prerequisite_edges=edges,
        flags=flags,
        summary=Summary(
            total_credits=total_credits,
            total_credits_required=total_credits_required,
            requirements_met=requirements_met,
        ),
        requirement_status=[status for _, _, status in sorted(statuses, key=lambda s: (s[0], s[1]))],
        counts_toward={
            course.course_id: counts[course.code]
            for semester in semesters
            for course in semester.courses
            if course.code in counts
        },
    )
