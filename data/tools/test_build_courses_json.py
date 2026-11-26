"""Tests for build_courses_json.py's _resolve_unknown_refs. Run from backend/: uv run pytest ../data/tools"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_courses_json import _resolve_unknown_refs  # noqa: E402

KNOWN = {"CSCI128", "CSCI102", "HASS100", "HASS327"}


def c(code):
    return {"type": "course", "code": code}


def AND(*of):
    return {"type": "AND", "of": list(of)}


def OR(*of):
    return {"type": "OR", "of": list(of)}


def exc(label):
    return {"type": "exception", "label": label}


def test_known_code_is_untouched():
    req = c("CSCI128")
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert resolved == req
    assert valid is True


def test_none_is_untouched():
    assert _resolve_unknown_refs(None, KNOWN) == (None, True)


def test_unknown_code_with_a_known_or_sibling_is_left_as_a_literal():
    # MATH225's real shape: OR(CSC128, CSCI102). CSC128 is harmless here because CSCI102 already
    # satisfies the OR, so it stays a dead-but-harmless course reference rather than becoming an
    # exception (which would make the validator raise exception_claimed even though the OR is met).
    req = OR(c("CSC128"), c("CSCI102"))
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert resolved == req
    assert valid is True


def test_unknown_code_alone_in_an_and_becomes_an_exception():
    # HASS330's real shape for one of its branches: a bare, required reference with no fallback.
    req = AND(c("HASS100"), c("CSM192"))
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert valid is True
    assert resolved["of"][0] == c("HASS100")
    assert resolved["of"][1]["type"] == "exception"
    assert "CSM192" in resolved["of"][1]["label"]


def test_or_with_no_known_branch_turns_every_branch_into_an_exception():
    req = OR(c("CSM191"), c("CSM192"))
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert valid is True
    assert all(child["type"] == "exception" for child in resolved["of"])


def test_existing_exception_is_already_valid_and_untouched():
    req = AND(c("HASS100"), exc("instructor consent"))
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert resolved == req
    assert valid is True


def test_nested_or_inside_and_resolves_independently():
    # AND( OR(unknown, known), bare unknown ): the inner OR is safe on its own and stays a
    # literal; the bare unknown sibling has no fallback and becomes an exception.
    req = AND(OR(c("CSC128"), c("CSCI102")), c("CSM192"))
    resolved, valid = _resolve_unknown_refs(req, KNOWN)
    assert valid is True
    assert resolved["of"][0] == OR(c("CSC128"), c("CSCI102"))
    assert resolved["of"][1]["type"] == "exception"
