"""Tests for prereq_parser.py using real catalog text. Run from backend/: uv run pytest ../data/tools"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from prereq_parser import parse_corequisites, parse_prerequisites  # noqa: E402


def c(code):
    return {"type": "course", "code": code}


def AND(*of):
    return {"type": "AND", "of": list(of)}


def OR(*of):
    return {"type": "OR", "of": list(of)}


def exc(label):
    return {"type": "exception", "label": label}


def req(text):
    return parse_prerequisites(text).requirement


def test_none_variants():
    for t in ["", "None", "none", "none.", "N/A", None]:
        assert req(t) is None


def test_single_and_trailing_period_and_space_in_code():
    assert req("MATH111") == c("MATH111")
    assert req("MTGN334.") == c("MTGN334")
    assert req("CBEN 110") == c("CBEN110")


def test_comma_list_is_and():
    assert req("MATH111, EBGN509") == AND(c("MATH111"), c("EBGN509"))
    assert req("CBEN 110, CBEN 120") == AND(c("CBEN110"), c("CBEN120"))


def test_or_list_and_oxford_list():
    assert req("CEEN470 or CEEN478 or CEEN570 or CEEN572") == OR(c("CEEN470"), c("CEEN478"), c("CEEN570"), c("CEEN572"))
    assert req("MATH112, MATH122, or PHGN100") == OR(c("MATH112"), c("MATH122"), c("PHGN100"))


def test_or_binds_tighter_than_and():
    assert req("MATH225 or MATH235 and MATH332 or MATH342") == AND(OR(c("MATH225"), c("MATH235")), OR(c("MATH332"), c("MATH342")))
    assert req("PEGN419, PEGN316 and MATH 225 or MATH235") == AND(c("PEGN419"), c("PEGN316"), OR(c("MATH225"), c("MATH235")))


def test_bare_number_inherits_subject():
    assert req("MATH 201 or 530 and MATH 324 or 531") == AND(OR(c("MATH201"), c("MATH530")), OR(c("MATH324"), c("MATH531")))


def test_consent_and_equivalent_become_exceptions():
    assert req("EENG470 or instructor consent.") == OR(c("EENG470"), exc("instructor consent"))
    assert req("PHGN350 or equivalent") == OR(c("PHGN350"), exc("equivalent course"))
    assert req("EENG310, EENG 311, EENG 391; or consent of instructor.") == OR(
        AND(c("EENG310"), c("EENG311"), c("EENG391")), exc("instructor consent")
    )


def test_semicolon_is_and():
    assert req("CSCI128; MATH112, MATH122, or PHGN100") == AND(c("CSCI128"), OR(c("MATH112"), c("MATH122"), c("PHGN100")))


def test_grade_minimums_dropped_and_counted():
    r = parse_prerequisites("CSCI200 with a C- or better, CSCI358 or MATH334")
    assert r.requirement == AND(c("CSCI200"), OR(c("CSCI358"), c("MATH334")))
    assert r.grade_dropped
    r = parse_prerequisites("Grade of C- or better in MATH112 or MATH122")
    assert r.requirement == OR(c("MATH112"), c("MATH122"))
    r = parse_prerequisites("CSCI220 with a grade of C- or higher or CSCI262 with a grade of C- or higher")
    assert r.requirement == OR(c("CSCI220"), c("CSCI262"))


def test_parentheses():
    got = req("(CSCI220 with a grade of C- or higher or CSCI262 with a grade of C- or higher) and (MATH201 or MATH334)")
    assert got == AND(OR(c("CSCI220"), c("CSCI262")), OR(c("MATH201"), c("MATH334")))


def test_free_text_is_kept_whole_as_exception():
    r = parse_prerequisites("Enrollment in Chemistry M.S. or Ph.D. degree program")
    assert r.fallback and r.requirement == exc("Enrollment in Chemistry M.S. or Ph.D. degree program")


def test_mixed_clauses_keep_the_course_logic():
    r = parse_prerequisites("GEGN467 or equivalent; Math through Differential Equations")
    assert r.requirement == AND(OR(c("GEGN467"), exc("equivalent course")), exc("Math through Differential Equations"))
    assert r.fallback
    assert req("PHGN320, PHGN341,") == AND(c("PHGN320"), c("PHGN341"))
    assert req("GEGN468, EGGN361, MNGN321, (or equivalents)") == OR(c("GEGN468"), c("EGGN361"), c("MNGN321"), exc("equivalent course"))


def test_credit_notes_are_dropped_not_parsed():
    r = parse_prerequisites("none. Variable credit: 0 to 6 credit hours. Repeatable for credit under different titles.")
    assert r.requirement is None and r.notes_dropped
    r = parse_prerequisites("CSCI200. Repeatable for credit under different topics.")
    assert r.requirement == c("CSCI200") and r.notes_dropped


def test_corequisites():
    assert parse_corequisites("MTGN464") == (["MTGN464"], True)
    assert parse_corequisites("CBEN404, CBEN210") == (["CBEN404", "CBEN210"], True)
    assert parse_corequisites("None") == ([], True)
    assert parse_corequisites("PHGN300 or PHGN310") == ([], False)
