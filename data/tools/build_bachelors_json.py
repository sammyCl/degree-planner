"""Turn the bachelor's PDFs in data/Undergraduate Programs into data/json/bachelors.json (format: docs/data-format.md).

Usage:  python -I data/tools/build_bachelors_json.py      (needs pypdf; from backend/: uv run python -I ../data/tools/build_bachelors_json.py)

Same approach as build_minors_json.py (Abdallah): each program's requirement groups are written by hand in SPECS
below, from reading the PDF's degree-requirements table. Typed-in course lists go through X(), which refuses a code
that is not in the PDF text; pools like "any CSCI 400-level course" come from the course CSV (pool()).

Checks, written to data/json/bachelors.REVIEW.md:
  - codes the course CSV does not have
  - PDF course title vs CSV course title
  - requirement credits that do not add up to the program total
  - rules in the PDF text that the format cannot express (notes)

Slice owner: Samantha (bachelor's data). Only the programs the five examples need are built so far.
"""
import csv, json, os, re
import pypdf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDFS = os.path.join(ROOT, "data", "Undergraduate Programs")
CSV = os.path.join(ROOT, "data", "Academic Catalog", "mines-courses.csv")
OUT = os.path.join(ROOT, "data", "json")
YEAR = "2026-2027"
CODE = re.compile(r"^(or\s+)?([A-Z]{3,4})\s?(\d{3}[A-Z]?)\b\s*(.*)$")
CREDITS = re.compile(r"(\d{1,2}\.\d)\s*$")


def load_courses():
    with open(CSV, newline="", encoding="utf-8") as f:
        return {r["course_number"]: r for r in csv.DictReader(f)}


def cr(courses, code):
    """Credits from the CSV; for a range like '0-3' the upper bound (PDFs quote the usual amount)."""
    try:
        return float(re.split(r"[-–]", courses[code]["credits"])[-1])
    except (KeyError, ValueError):
        return None


class Ctx:
    """Everything a spec needs for one PDF."""

    def __init__(self, name, courses):
        self.name, self.c = name, courses
        r = pypdf.PdfReader(os.path.join(PDFS, name, name + ".pdf"))
        self.text = "\n".join((p.extract_text() or "") for p in r.pages)
        self.lines = [l.strip() for l in self.text.splitlines() if l.strip()]
        self.flat = re.sub(r"\s+", "", self.text).upper()
        self.pdf_titles = {}
        self.notes = []
        # Titles as printed in the requirements tables, for the title check. The tables end at "Major GPA"; after
        # that come the course descriptions, whose prerequisite prose would give false title mismatches.
        end = next((k for k, l in enumerate(self.lines) if l.startswith("Major GPA")), len(self.lines))
        for e in self.entries(self.lines[:end]):
            if not e["text"][:1].isalpha():
                continue  # a footnote fragment like "CSCI474, or CSCI478", not a title
            self.pdf_titles.setdefault(e["code"], re.sub(r"\s*\d{1,2}\.\d\s*$|\s*\d-\d\s*$", "", e["text"]).strip())

    def entries(self, lines):
        out, cur = [], None
        for l in lines:
            m = CODE.match(l)
            if m and m.group(2) != "ANY":
                cur = {"code": m.group(2) + m.group(3), "alt": bool(m.group(1)), "text": m.group(4)}
                out.append(cur)
                if CREDITS.search(m.group(4)):
                    cur = None
            elif cur is not None and not CREDITS.fullmatch(l) and len(l) < 70 and l.upper() == l:
                cur["text"] += " " + l
            else:
                cur = None
        return out

    def X(self, codes):
        """Typed-in list; every code must appear in the PDF text."""
        for c in codes:
            assert c in self.flat, "%s: %s not in the PDF text" % (self.name, c)
        return codes

    def pool(self, prefix, lo=0, hi=999, exclude=()):
        return sorted(
            c for c in self.c
            if re.fullmatch(prefix + r"\d{3}", c) and lo <= int(c[-3:]) <= hi and c not in exclude
        )

    def note(self, s):
        self.notes.append(s)


def g(gid, label, kind, courses=None, credits=None):
    d = {"group_id": gid, "label": label, "kind": kind}
    if courses is not None:
        d["courses"] = courses
    if credits is not None:
        d["credits_required"] = credits
    return d


def ALL(gid, label, courses):
    return g(gid, label, "all", courses)


def PICK(gid, label, credits, courses=None):
    return g(gid, label, "choose_credits", courses, credits)


def P(program_id, name, total, groups):
    return {"program_id": program_id, "name": name, "total": total, "groups": groups}


# ---------------------------------------------------------------- shared core pieces

def cas_groups(x, mid_credits=6, upper_credits=3):
    """Culture and Society (CAS) restricted electives.

    No collected source lists the restricted CAS courses. The Transfer Course Approval form defines a mid-level
    HASS elective as HASS 2XX (sophomore/junior level), so mid-level is modelled as HASS200-399 and the 400-level
    elective as HASS400-499. HASS100 and HASS215 are core courses, not CAS electives, so they are left out.
    """
    x.note("CAS restricted electives modelled as HASS200-399 (mid-level) and HASS400-499 (400-level), going by the "
           "slot names in the degree tables.")
    x.note("To look into later (data unchanged): the registrar's core-curriculum page (%s, read 2026-11-20 via a "
           "summary, not quoted) also lists non-HASS courses as CAS-eligible: LIFL courses (mid-level), HNRS courses "
           "(with advisor approval), and approved EBGN, EDNS, MNGN and PEGN courses (for example EBGN201, EDNS315, "
           "MNGN335, PEGN430). It does not say which of these fill the mid-level slot and which fill the 400-level "
           "slot, so none are added yet." % SW_SOURCE)
    core = {"HASS100", "HASS215"}
    return [
        PICK("cas-mid", "Culture and Society (CAS) Mid-Level Restricted Electives", mid_credits,
             x.pool("HASS", 200, 399, exclude=core)),
        PICK("cas-400", "Culture and Society (CAS) 400-Level Restricted Elective", upper_credits,
             x.pool("HASS", 400, 499)),
    ]


SW_SOURCE = "https://registrar.mines.edu/core-curriculum/"


def success_wellness(x):
    """Success and Wellness (S&W) elective, from the registrar's 'Success & Wellness Electives' table.

    The table lists CSM202, CSM250, CSM275, CSM350 and 'Any 1.0 credit PAGN 2xx Course'. The program PDFs show the
    slot only as 'S&W SUCCESS AND WELLNESS 1.0', so these codes are not in the PDF text and are checked against the
    course CSV instead of X(). CSM202 is left out because every program already requires it.
    """
    pagn = [c for c in x.pool("PAGN", 200, 299) if x.c[c]["credits"].strip() == "1.0"]
    listed = ["CSM250", "CSM275", "CSM350"]
    for c in listed:
        assert c in x.c, "S&W course %s not in the course CSV" % c
    x.note("S&W elective list from the registrar's 'Success & Wellness Electives' table (%s, read 2026-11-20): "
           "CSM250, CSM275, CSM350, or any 1.0-credit PAGN 2xx course (PAGN298/PAGN299 are variable-credit, so left "
           "out). CSM202 is also on that table but is already required. The registrar says more courses may be "
           "approved later; the table is for the revised core from the 2023-2024 catalog on." % SW_SOURCE)
    return PICK("success-wellness", "Success and Wellness (S&W) elective", 1, listed + pagn)


# ---------------------------------------------------------------- specs

def s_cs(x):
    required = [
        "MATH111", "MATH112", "MATH213", "MATH225", "MATH332", "MATH334",
        "CHGN121", "PHGN100", "PHGN200",
        "HASS100", "HASS215", "EDNS151", "EBGN321", "CSM101", "CSM202",
        "CSCI128", "CSCI200", "CSCI210", "CSCI220", "CSCI306", "CSCI341", "CSCI358",
        "CSCI370", "CSCI400", "CSCI406", "CSCI442",
    ]
    x.note("General track = the 'Computer Science' focus area (5 CS electives + 3 free electives), plus the CS elective "
           "and 3 free electives in the main table: 18 CS elective credits and 18 free elective credits in all.")
    x.note("CS electives: any CSCI400-level or CSCI500-level course (500-level needs advisor approval), CSED435, EENG383, "
           "MATH307; EDNS491 and EDNS492 count only when both are taken. Required courses are left out of the list "
           "(the PDF says a required course cannot also count as a CS elective). Advisor approval and the EDNS pair rule "
           "are not enforceable in this format.")
    x.note("EBGN321 has a prerequisite of 60 credit hours (PDF footnote).")
    cs_elect = x.pool("CSCI", 400, 599, exclude=set(required)) + x.X(["CSED435", "EENG383", "MATH307", "EDNS491", "EDNS492"])
    return [P("cs-bs-general-track", "Bachelor of Science in Computer Science (General Track)", 128, [
        ALL("required", "Required core and Computer Science courses", x.X(required)),
        success_wellness(x),
        *cas_groups(x),
        PICK("cs-electives", "Computer Science Electives (6 courses)", 18, cs_elect),
        PICK("free-electives", "Free Electives", 18),
    ])]


def s_mining(x):
    required = [
        "MATH111", "MATH112", "MATH213", "MATH225",
        "CHGN121", "CHGN122", "PHGN100", "GEGN101",
        "HASS100", "HASS215", "EDNS151", "EBGN321", "CSM101", "CSM202", "CSCI128",
        "CEEN241", "CEEN311",
        "MNGN203", "MNGN209", "MNGN210", "MNGN301", "MNGN308", "MNGN309", "MNGN310", "MNGN311", "MNGN312",
        "MNGN314", "MNGN317", "MNGN321", "MNGN322", "MNGN412", "MNGN414", "MNGN425", "MNGN427", "MNGN428",
        "MNGN429", "MNGN433", "MNGN438", "MNGN482",
    ]
    x.note("'MNGN2XX New Special Topics' (3 credits, sophomore spring) has no single code; modelled as 3 credits from the "
           "MNGN 200-level courses in the CSV that are not already required (MNGN205, MNGN298, MNGN299). Confirm with "
           "the department which course is meant.")
    x.note("MNGN205 Mining Engineering Field Experience is marked optional, so it is not required. The PDF lists it as "
           "2.0 credits; the CSV says 1.0.")
    x.note("Junior fall lists 'CAS ELECTIVE' with no level; read as a mid-level CAS elective (the table also has one "
           "'CAS Mid Level' and one '400-Level' CAS elective), giving 6 mid-level and 3 400-level CAS credits.")
    x.note("EBGN321 has a prerequisite of 60 credit hours.")
    mngn2xx = x.pool("MNGN", 200, 299, exclude=set(required))
    return [P("mining-bs", "Bachelor of Science in Mining Engineering", 131, [
        ALL("required", "Required core and Mining Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("fluid-mechanics", "MEGN351 Fluid Mechanics or PEGN251 Fluid Mechanics", 3, x.X(["MEGN351", "PEGN251"])),
        PICK("mngn-2xx", "MNGN2XX New Special Topics", 3, mngn2xx),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 9),
    ])]


def s_ams(x):
    """Three emphases, one program each (CONFLICT-LOG rule 8). They share 90 credits; each adds 30 of its own."""
    common = [
        "MATH111", "MATH112", "MATH201", "MATH213", "MATH225", "MATH300", "MATH301", "MATH307", "MATH310",
        "MATH324", "MATH334",
        "CHGN121", "PHGN100", "PHGN200",
        "HASS100", "HASS215", "EDNS151", "EBGN321", "CSM101", "CSM202", "CSCI128", "CSCI200",
    ]
    x.note("The PDF writes 'MATH332 LINEAR ALGEBRA or 342'; read as MATH332 or MATH342 (the honors version).")
    x.note("AMS electives: any 3-credit 300-, 400- or 500-level MATH course other than MATH530 that the emphasis does "
           "not already require, plus CSCI403, CSCI406, DSCI403, DSCI560, DSCI561 ('up to 4 electives from this list'). "
           "Courses on the emphasis elective list are also on the AMS list; the format cannot stop one course from "
           "counting toward both groups. 'Department approval required for courses not on this list' is not enforceable.")
    x.note("Computing elective (footnote 1): CAM and STATS list CSCI220, CSCI303, CSCI403, CSCI441, CSCI470, CSCI474, "
           "CSCI478; DS lists the same without CSCI303 and CSCI470 (DS requires CSCI470).")

    def three_credit(code):
        try:
            return float(x.c[code]["credits"]) == 3.0
        except (KeyError, ValueError):
            return False

    def program(suffix, name, own_required, computing, own_elect_label, own_elect, ams_elect_credits):
        required = common + own_required
        ams_list = [c for c in x.pool("MATH", 300, 599, exclude=set(required) | {"MATH530"}) if three_credit(c)]
        ams_list += [c for c in x.X(["CSCI403", "CSCI406", "DSCI403", "DSCI560", "DSCI561"]) if c not in required]
        return P("ams-bs-" + suffix, "Bachelor of Science in Applied Mathematics and Statistics (%s)" % name, 120, [
            ALL("required", "Required core, mathematics and %s emphasis courses" % name, x.X(required)),
            success_wellness(x),
            PICK("linear-algebra", "MATH332 Linear Algebra or MATH342 (honors)", 3, x.X(["MATH332"]) + ["MATH342"]),
            PICK("computing-elective", "Computing Elective", 3, x.X(computing)),
            PICK("ams-electives", "Mathematics-AMS Electives", ams_elect_credits, ams_list),
            PICK("emphasis-electives", own_elect_label, 6, [c for c in x.X(own_elect) if c not in required]),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ])

    computing = ["CSCI220", "CSCI303", "CSCI403", "CSCI441", "CSCI470", "CSCI474", "CSCI478"]
    return [
        program("cam", "Computational and Applied Mathematics", ["MATH408", "MATH431", "MATH455", "MATH484"], computing,
                "Mathematics-CAM Electives (at least 2)",
                ["MATH440", "MATH454", "MATH457", "MATH458", "MATH459", "MATH472", "MATH500", "MATH501", "MATH514",
                 "MATH515", "MATH550", "MATH551", "MATH552"], 12),
        program("stats", "Statistics", ["MATH335", "MATH436", "MATH437", "MATH482"], computing,
                "Mathematics-STAT Electives (at least 2)",
                ["MATH432", "MATH433", "MATH438", "MATH443", "MATH531", "MATH534", "MATH535", "MATH560", "MATH561",
                 "CSCI403", "DSCI560", "DSCI561"], 12),
        program("ds", "Data Science", ["DSCI403", "MATH335", "MATH436", "MATH482", "CSCI470"],
                ["CSCI220", "CSCI403", "CSCI441", "CSCI474", "CSCI478"],
                "Mathematics-DS Electives (at least 2)",
                ["MATH432", "MATH433", "MATH436", "MATH437", "MATH438", "MATH440", "MATH443", "MATH560", "MATH561",
                 "CSCI403", "CSCI404", "CSCI406", "CSCI423", "CSCI475", "DSCI560", "DSCI561"], 9),
    ]


SPECS = [
    ("Computer Science", s_cs),
    ("Mining Engineering", s_mining),
    ("Applied Mathematics and Statistics", s_ams),
]


# ---------------------------------------------------------------- build

def group_credits(courses, grp):
    if grp["kind"] == "choose_credits":
        return grp["credits_required"], []
    total, unknown = 0.0, []
    for code in grp.get("courses", []):
        c = cr(courses, code)
        if c is None:
            unknown.append(code)
        else:
            total += c
    return total, unknown


def main():
    courses = load_courses()
    programs, review = [], []
    for pdf_name, spec in SPECS:
        x = Ctx(pdf_name, courses)
        for p in spec(x):
            programs.append({
                "program_id": p["program_id"],
                "name": p["name"],
                "degree_level": "bachelor",
                "catalog_year": YEAR,
                "total_credits_required": p["total"],
                "requirement_groups": p["groups"],
            })
            total = 0.0
            for grp in p["groups"]:
                credits, unknown = group_credits(courses, grp)
                total += credits
                missing = [c for c in grp.get("courses", []) if c not in courses]
                if missing:
                    review.append("- **%s**, group `%s`: not in the course CSV: %s" % (p["name"], grp["group_id"], ", ".join(missing)))
                if unknown and not missing:
                    review.append("- **%s**, group `%s`: no credits in the CSV for %s" % (p["name"], grp["group_id"], ", ".join(unknown)))
            if abs(total - p["total"]) > 0.01:
                review.append("- **%s**: requirement credits add up to %g but the total is %g." % (p["name"], total, p["total"]))
        for code, pdf_title in sorted(x.pdf_titles.items()):
            if code in courses and pdf_title:
                csv_title = courses[code]["course_name"]
                a, b = re.sub(r"[^A-Z0-9]", "", pdf_title.upper()), re.sub(r"[^A-Z0-9]", "", csv_title.upper())
                if not (a.startswith(b) or b.startswith(a)):
                    review.append("- **%s**, title differs: %s: PDF '%s' vs CSV '%s'" % (pdf_name, code, pdf_title, csv_title))
        for n in x.notes:
            review.append("- **%s**, note: %s" % (pdf_name, n))

    with open(os.path.join(OUT, "bachelors.json"), "w", encoding="utf-8") as fh:
        json.dump({"programs": programs}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(OUT, "bachelors.REVIEW.md"), "w", encoding="utf-8") as fh:
        fh.write("# Bachelor's programs: conflicts, gaps and notes\n\n")
        fh.write("Generated by data/tools/build_bachelors_json.py. Items here are things in the program PDFs that disagree "
                 "with the course CSV, or rules the data format cannot express. How a conflict was resolved goes in "
                 "data/CONFLICT-LOG.md.\n\n")
        fh.write("\n".join(review) + "\n")
    print("%d program(s), %d review item(s)" % (len(programs), len(review)))


if __name__ == "__main__":
    main()
