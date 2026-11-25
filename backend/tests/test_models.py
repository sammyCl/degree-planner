from degree_planner_backend.models import Course, CourseRequirement, Program

BASE_COURSE = {
    "code": "MNGN598",
    "subject": "MNGN",
    "number": "598",
    "title": "Independent Study",
    "credits": 6.0,
    "description": "",
    "catalog_year": "2026-2027",
}

BASE_PROGRAM = {
    "program_id": "test-minor",
    "name": "Test Minor",
    "degree_level": "minor",
    "catalog_year": "2026-2027",
    "total_credits_required": 18,
    "requirement_groups": [],
}


def test_program_notes_default_to_empty() -> None:
    program = Program.model_validate(BASE_PROGRAM)

    assert program.notes == []


def test_program_accepts_certificate_degree_level() -> None:
    program = Program.model_validate({**BASE_PROGRAM, "degree_level": "certificate"})

    assert program.degree_level == "certificate"


def test_program_notes_can_be_set() -> None:
    program = Program.model_validate({**BASE_PROGRAM, "notes": ["Not open to QBE majors."]})

    assert program.notes == ["Not open to QBE majors."]


def test_course_credits_min_max_are_optional() -> None:
    course = Course.model_validate(BASE_COURSE)

    assert course.credits_min is None
    assert course.credits_max is None


def test_course_credits_min_max_can_express_a_range() -> None:
    course = Course.model_validate({**BASE_COURSE, "credits_min": 1.0, "credits_max": 6.0})

    assert course.credits_min == 1.0
    assert course.credits_max == 6.0


def test_course_requirement_min_grade_is_optional() -> None:
    requirement = CourseRequirement.model_validate({"type": "course", "code": "CSCI200"})

    assert requirement.min_grade is None


def test_course_requirement_min_grade_can_be_set() -> None:
    requirement = CourseRequirement.model_validate({"type": "course", "code": "CSCI200", "min_grade": "C-"})

    assert requirement.min_grade == "C-"


def test_course_corequisites_can_be_an_or_of_courses() -> None:
    course = Course.model_validate(
        {
            **BASE_COURSE,
            "corequisites": {
                "type": "OR",
                "of": [
                    {"type": "course", "code": "PHGN300"},
                    {"type": "course", "code": "PHGN310"},
                ],
            },
        }
    )

    assert course.corequisites is not None
    assert course.corequisites.type == "OR"


def test_course_corequisites_default_to_none() -> None:
    course = Course.model_validate(BASE_COURSE)

    assert course.corequisites is None
