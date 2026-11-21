"""Turn catalog prerequisite text into the data format's Requirement expressions (docs/data-format.md).

Pure standard library. Rules (also written up in data/CONFLICT-LOG.md):

- Course codes ("MATH201", "MATH 201", "CSCI200") become {"type": "course", "code": ...}. A bare 3-digit
  number right after a code inherits its subject ("MATH 201 or 530" -> MATH201 or MATH530).
- "or" binds tighter than "and", a comma, or a semicolon: "MATH225 or MATH235 and MATH332 or MATH342" is
  (225 or 235) AND (332 or 342). A list that is only commas and ends in ", or" ("A, B, or C") is one OR.
- "; or consent of instructor" ORs the exception with everything before it.
- "instructor consent", "permission of instructor", "or equivalent" and similar become
  {"type": "exception", "label": ...}: the validator warns and lets the student override.
- Grade minimums ("with a C- or better") are dropped: the data format has no grade field. They are counted.
- Anything else (free text such as "Enrollment in Chemistry M.S. program") is kept whole as one exception
  whose label is the original text, and reported, so no requirement is silently lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CODE = r"[A-Z]{2,5}\s?\d{3}[A-Z]?"
GRADE = re.compile(
    r"\s*\(\s*(?:with\s+)?(?:a\s+)?(?:minimum\s+)?(?:grade\s+of\s+)?[A-D][+-]?(?:\s+or\s+(?:better|higher))?\s*\)"
    r"|\s*\b(?:with\s+)?(?:a\s+)?(?:minimum\s+)?(?:grade\s+of\s+)?[A-D][+-]?\s+or\s+(?:better|higher)(?:\s+in)?\b"
    r"|\s*\bwith\s+(?:a\s+)?(?:minimum\s+)?grade\s+of\s+[A-D][+-]?\b",
    re.IGNORECASE,
)
EXCEPTIONS = [
    (re.compile(r"(?:consent|permission|approval)\s+of\s+(?:the\s+)?(?:course\s+)?(?:instructor|department|program|advisor|professor)s?", re.I), "instructor consent"),
    (re.compile(r"(?:instructor|department|advisor|professor)(?:'s)?\s+(?:consent|permission|approval)", re.I), "instructor consent"),
    (re.compile(r"equivalents?(?:\s+(?:courses?|project\s+classes?|knowledge|experience))?", re.I), "equivalent course"),
]
NOISE_SENTENCE = re.compile(r"^(?:variable credit|repeatable|offered|may be repeated|this course)", re.I)
NONE = re.compile(r"^(?:none|n/a|na|no prerequisites?)\.?$", re.I)


@dataclass
class ParseResult:
    requirement: dict | None
    fallback: bool = False  # whole text kept as one exception
    grade_dropped: bool = False
    notes_dropped: list[str] = field(default_factory=list)


def _course(code: str) -> dict:
    return {"type": "course", "code": re.sub(r"\s", "", code)}


def _wrap(kind: str, items: list[dict]) -> dict:
    flat: list[dict] = []
    for item in items:
        flat.extend(item["of"] if item["type"] == kind else [item])
    return flat[0] if len(flat) == 1 else {"type": kind, "of": flat}


_TOKEN = re.compile(
    r"(?P<open>\()|(?P<close>\))"
    r"|(?P<code>(?-i:" + CODE + r"))"
    r"|(?P<num>\b\d{3}[A-Z]?\b)"
    r"|(?P<orc>,\s*or\b)|(?P<andc>,\s*and\b)|(?P<comma>,)|(?P<semi>;)"
    r"|(?P<and>\band\b|&)|(?P<or>\bor\b|/)"
    r"|(?P<ws>\s+)",
    re.I,
)


def _tokens(text: str) -> list[tuple[str, str]] | None:
    """Split text into tokens; None if anything unrecognized is left over."""
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        for pattern, _label in EXCEPTIONS:
            m = pattern.match(text, pos)
            if m:
                out.append(("exc", _label))
                pos = m.end()
                break
        else:
            m = _TOKEN.match(text, pos)
            if not m:
                return None
            kind = m.lastgroup
            piece = m.group()
            if kind == "code" and not piece[:2].isupper():
                return None
            if kind == "num" and not any(k == "code" for k, _ in out):
                return None
            if kind != "ws":
                out.append((kind, piece))
            pos = m.end()
    return out


class _Fail(Exception):
    pass


def _parse_group(toks: list[tuple[str, str]]) -> dict:
    """Parse a token list with no ';' at the top level."""
    atoms: list[dict] = []
    conns: list[str] = []
    i = 0
    last_subject = ""
    expect_atom = True
    while i < len(toks):
        kind, val = toks[i]
        if expect_atom:
            if kind == "open":
                depth, j = 1, i + 1
                while j < len(toks) and depth:
                    depth += (toks[j][0] == "open") - (toks[j][0] == "close")
                    j += 1
                if depth:
                    raise _Fail
                atoms.append(_parse_all(toks[i + 1 : j - 1]))
                i = j
            elif kind == "code":
                c = _course(val)
                last_subject = re.match(r"[A-Z]+", c["code"]).group()
                atoms.append(c)
                i += 1
            elif kind == "num":
                atoms.append(_course(last_subject + val))
                i += 1
            elif kind == "exc":
                atoms.append({"type": "exception", "label": val})
                i += 1
            else:
                raise _Fail
            expect_atom = False
        else:
            if kind in ("orc", "or"):
                conns.append("orc" if kind == "orc" else "or")
            elif kind in ("comma", "and", "andc"):
                conns.append("comma" if kind == "comma" else "and")
            else:
                raise _Fail
            i += 1
            expect_atom = True
    if expect_atom or not atoms:
        raise _Fail
    if len(atoms) == 1:
        return atoms[0]
    if conns[-1] == "orc" and all(c == "comma" for c in conns[:-1]):
        return _wrap("OR", atoms)
    groups: list[list[dict]] = [[atoms[0]]]
    for conn, atom in zip(conns, atoms[1:]):
        if conn in ("or", "orc"):
            groups[-1].append(atom)
        else:
            groups.append([atom])
    return _wrap("AND", [_wrap("OR", g) for g in groups])


def _parse_all(toks: list[tuple[str, str]]) -> dict:
    parts: list[list[tuple[str, str]]] = [[]]
    for t in toks:
        if t[0] == "semi":
            parts.append([])
        else:
            parts[-1].append(t)
    parsed: list[dict] = []
    or_with_prev: list[dict] = []
    for part in parts:
        if not part:
            continue
        if part[0][0] == "or":  # "; or consent of instructor"
            or_with_prev.append(_parse_group(part[1:]))
        else:
            parsed.append(_parse_group(part))
    if not parsed:
        raise _Fail
    result = _wrap("AND", parsed)
    return _wrap("OR", [result, *or_with_prev]) if or_with_prev else result


def parse_prerequisites(text: str) -> ParseResult:
    original = " ".join((text or "").replace("“", '"').replace("”", '"').replace("’", "'").split())
    if not original or NONE.match(original):
        return ParseResult(None)

    # Keep the prerequisite sentence(s); drop notes about credit or repetition.
    sentences = [s.strip() for s in re.split(r"(?<=[a-z0-9)])\.\s+(?=[A-Z\"])", original) if s.strip()]
    kept, dropped = [], []
    for s in sentences:
        s = s.rstrip(".").strip()
        if NONE.match(s):
            continue
        (dropped if NOISE_SENTENCE.match(s) or "form must be completed" in s else kept).append(s)
    if not kept:
        return ParseResult(None, notes_dropped=dropped)
    body = "; ".join(kept) if len(kept) > 1 and all(re.match(CODE, k) for k in kept) else kept[0]
    if len(kept) > 1 and body == kept[0]:
        # several sentences that are not plain code lists: keep them all as free text
        body = ". ".join(kept)

    stripped, n_grade = GRADE.subn("", body)
    stripped = re.sub(r"\(\s*or\s+(equivalents?)\s*\)", r"or \1", stripped, flags=re.I)
    stripped = re.sub(r"\s+", " ", stripped).strip(" .,;")
    toks = _tokens(stripped)
    if toks is not None and any(k in ("code", "num", "exc") for k, _ in toks):
        try:
            return ParseResult(_parse_all(toks), grade_dropped=bool(n_grade), notes_dropped=dropped)
        except _Fail:
            pass
    # Mixed text: parse each ";" clause on its own; a clause that cannot be parsed becomes an exception.
    clauses = [c.strip(" .,") for c in re.split(r";", stripped) if c.strip(" .,")]
    if len(clauses) > 1:
        atoms, any_course = [], False
        for clause in clauses:
            ct = _tokens(clause)
            try:
                if ct is None or not any(k in ("code", "num") for k, _ in ct):
                    raise _Fail
                atoms.append(_parse_all(ct))
                any_course = True
            except _Fail:
                atoms.append({"type": "exception", "label": clause[:300]})
        if any_course:
            return ParseResult(_wrap("AND", atoms), fallback=True, grade_dropped=bool(n_grade), notes_dropped=dropped)
    return ParseResult(
        {"type": "exception", "label": body.rstrip(".")[:300]},
        fallback=True,
        notes_dropped=dropped,
    )


def parse_corequisites(text: str) -> tuple[list[str], bool]:
    """Return (codes, expressible). OR/free text cannot be a plain list, so it is reported, not guessed."""
    t = " ".join((text or "").split()).rstrip(". ")
    if not t or NONE.match(t):
        return [], True
    res = parse_prerequisites(t)
    req = res.requirement
    if req is None or res.fallback:
        return [], False
    if req["type"] == "course":
        return [req["code"]], True
    if req["type"] == "AND" and all(x["type"] == "course" for x in req["of"]):
        return [x["code"] for x in req["of"]], True
    return [], False
