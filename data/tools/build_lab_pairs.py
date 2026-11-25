"""Build frontend/src/planner/labPairs.json: which lab course belongs to which lecture course.

    python3 data/tools/build_lab_pairs.py

The planner draws a lab attached to its lecture and moves the two together. The plan format carries no corequisite
information and the backend has no course endpoint yet, so the pairs are read from data/json/courses.json here. A lab
is paired only when the match is certain, in this order:
  1. the lab's corequisite is exactly one course (the lecture);
  2. the lab's code is the lecture's code plus "L" (CEEN312L and CEEN312);
  3. the lab's title is the lecture's title plus "Lab" or "Laboratory", in the same subject, and only one course has it.
Special topics, independent study and leadership labs are never paired. Labs that match none of these stay ordinary courses.
Standard library only.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IS_LAB_TITLE = re.compile(r"\blab(oratory)?\b", re.I)
SKIP_TITLE = re.compile(r"special topics|independent study|leadership|research", re.I)
LAB_WORD = re.compile(r"\s*[-–:]?\s*\(?\blab(oratory)?\b\)?\s*", re.I)


def main() -> None:
    courses = json.loads((ROOT / "data" / "json" / "courses.json").read_text())["courses"]
    by_code = {c["code"]: c for c in courses}
    is_lab = lambda c: bool(IS_LAB_TITLE.search(c["title"]) or re.fullmatch(r"[A-Z]{4}\d{3}L", c["code"]))
    pairs: dict[str, str] = {}
    for lab in courses:
        if not is_lab(lab) or SKIP_TITLE.search(lab["title"]) or re.search(r"\d{3}L[A-Z]$", lab["code"]):
            continue
        coreq = lab.get("corequisites")
        lecture = None
        if coreq and coreq.get("type") == "course" and coreq["code"] in by_code and not is_lab(by_code[coreq["code"]]):
            lecture = coreq["code"]
        elif re.fullmatch(r"[A-Z]{4}\d{3}L", lab["code"]) and lab["code"][:-1] in by_code:
            lecture = lab["code"][:-1]
        else:
            base = LAB_WORD.sub(" ", lab["title"]).strip().lower()
            same = [
                c["code"]
                for c in courses
                if c["subject"] == lab["subject"] and c["code"] != lab["code"] and not is_lab(c) and c["title"].strip().lower() == base
            ]
            if len(same) == 1:
                lecture = same[0]
        if lecture:
            pairs[lab["code"]] = lecture
    out = ROOT / "frontend" / "src" / "planner" / "labPairs.json"
    out.write_text(json.dumps(dict(sorted(pairs.items())), indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)}: {len(pairs)} labs paired with a lecture")


if __name__ == "__main__":
    main()
