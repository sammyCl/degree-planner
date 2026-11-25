"""Plan validator (docs/plan-format.md): rules code, no LLM.

Checks prerequisite order, credit totals, program requirements, double-counted
credits, and claimed exceptions. Returns a new Plan with `prerequisite_edges`,
`flags`, and `summary` filled in. Used by the frontend's drag-and-drop check and
by the agent's `check_plan` tool.
"""

from __future__ import annotations

import re
import sqlite3

from degree_planner_backend.lookups import NotFoundError, get_course, get_program
from degree_planner_backend.models import Program, Requirement, RequirementGroup
from degree_planner_backend.plan_models import CountsToward, Edge, Flag, FlagSeverity, FlagType, Plan, Semester, Summary

_GRADUATE_LEVELS = ("master", "phd")


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
    if requirement is None or requirement.type == "course":
        return []
    if requirement.type == "exception":
        return [requirement.label]
    return [label for sub in requirement.of for label in _exception_labels(sub)]


_ADD_ON_LEVELS = ("minor", "asi")
# 2026-2027 undergraduate catalog (forms-policies.json, policy-minor-requirements and
# policy-asi-requirements): at least 9 credits of a minor or ASI not used for any other part of
# the degree except free electives.
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

    def record(code: str, program: Program, group: RequirementGroup) -> None:
        entry = CountsToward(program_id=program.program_id, group_id=group.group_id, label=group.label)
        if entry not in counts.setdefault(code, []):
            counts[code].append(entry)

    equivalent: dict[str, list[str]] = {}

    def with_equivalents(codes: set[str]) -> set[str]:
        """codes plus their equivalent courses: an equivalent course satisfies a prerequisite (BUG-041)."""
        out = set(codes)
        for code in codes:
            if code not in equivalent:
                equivalent[code] = _equivalents(connection, code, catalog_year)
            out.update(equivalent[code])
        return out

    satisfied_before = with_equivalents({completed.code for completed in student.completed_courses})
    for semester in semesters:
        for course in semester.courses:
            try:
                requirement = get_course(connection, course.code, catalog_year).prerequisites
            except NotFoundError:
                requirement = None

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

    # A minor or ASI adds no credit total of its own on top of a degree (BUG-037): its groups make
    # sure its courses are planned, and its courses may also be the degree's free electives. Its
    # total counts only when the student has no degree program.
    loaded = []
    for program_id in student.programs:
        try:
            loaded.append(get_program(connection, program_id, catalog_year))
        except NotFoundError:
            continue
    has_degree = any(p.degree_level not in _ADD_ON_LEVELS for p in loaded)
    total_credits_required = 0.0
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
            if bachelor_part is not None and grad_part is not None:
                bachelor_codes = {c for g in bachelor_part.requirement_groups for c in (g.courses or [])}
                bachelor_semesters = [
                    index
                    for code in bachelor_codes
                    if code in plan_codes
                    for index, _ in code_to_course_ids.get(code, [])
                ]
                if bachelor_semesters:
                    last_bachelor_semester = max(bachelor_semesters)
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
                available -= set(listed) | {stand_in[code] for code in listed if code in stand_in}

            for group in requirement_groups_kind:
                assert group.requirement is not None  # enforced by the model
                satisfied_codes = plan_codes | set(stand_in.keys())
                branch = _satisfied_branch(group.requirement, satisfied_codes)
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
                for listed_code in candidates:
                    code = listed_code if listed_code in available else stand_in.get(listed_code, "")
                    if code not in available or code in claimed:
                        continue
                    if earned >= credits_required:
                        break
                    earned += code_credits.get(code, 0.0)
                    claimed.add(code)
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
        for add_on in (p for p in loaded if p.degree_level in _ADD_ON_LEVELS):
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
        counts_toward={
            course.course_id: counts[course.code]
            for semester in semesters
            for course in semester.courses
            if course.code in counts
        },
    )
