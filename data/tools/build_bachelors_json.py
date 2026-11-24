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

Slice owner: Samantha (bachelor's data). She built the five example programs; Abdallah added the rest of the majors on
2026-11-22 (all 21 PDFs, 44 programs). Decisions and open questions are in data/CONFLICT-LOG.md.
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


def course_req(code):
    return {"type": "course", "code": code}


def and_req(codes):
    return {"type": "AND", "of": [course_req(c) for c in codes]}


def REQUIRE(gid, label, credits, requirement, courses=None):
    d = g(gid, label, "requirement", courses, credits)
    d["requirement"] = requirement
    return d


def P(program_id, name, total, groups):
    return {"program_id": program_id, "name": name, "total": total, "groups": groups}


# Thorson First-Year Honors: HNRS105 + HNRS115 replace HASS100 + EDNS151 for all majors (policy-thorson-first-year-
# honors in forms-policies.json). The two core courses move out of the required list into a "requirement" group
# (BUG-038) that holds the real either/or rule, so a mix such as HASS100 + HNRS105 is correctly rejected.
# credits_required here is nominal (the base pair's total, 3+3), for the printed program total to add up; the
# honors pair is 7 credits (HNRS105 3 + HNRS115 4), a one-credit difference the catalog text doesn't explain
# (policy-thorson-first-year-honors's own note says to confirm with the Honors office).
THORSON_PAIR = ("HASS100", "EDNS151")
THORSON_HNRS_PAIR = ("HNRS105", "HNRS115")


def thorson(groups):
    """Move HASS100 and EDNS151 out of the "all" group that lists both into a "requirement" group that holds the
    Thorson swap's real rule. Returns the new groups, or None when no group lists both."""
    for k, grp in enumerate(groups):
        if grp["kind"] == "all" and all(c in grp.get("courses", []) for c in THORSON_PAIR):
            kept = dict(grp, courses=[c for c in grp["courses"] if c not in THORSON_PAIR])
            swap = REQUIRE(
                "first-year-core",
                "HASS100 and EDNS151, or HNRS105 and HNRS115 (Thorson First-Year Honors)",
                6,
                {"type": "OR", "of": [and_req(THORSON_PAIR), and_req(THORSON_HNRS_PAIR)]},
                courses=sorted(THORSON_PAIR + THORSON_HNRS_PAIR),
            )
            return groups[:k] + [kept, swap] + groups[k + 1:]
    return None


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
    groups = []
    if mid_credits:  # a program with no slot of one kind (for example no 400-level CAS) passes 0 for it
        groups.append(PICK("cas-mid", "Culture and Society (CAS) Mid-Level Restricted Electives", mid_credits,
                           x.pool("HASS", 200, 399, exclude=core)))
    if upper_credits:
        groups.append(PICK("cas-400", "Culture and Society (CAS) 400-Level Restricted Elective", upper_credits,
                           x.pool("HASS", 400, 499)))
    return groups


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

CS_REQUIRED = [  # shared by every Computer Science focus area
    "MATH111", "MATH112", "MATH213", "MATH225", "MATH332", "MATH334",
    "CHGN121", "PHGN100", "PHGN200",
    "HASS100", "HASS215", "EDNS151", "EBGN321", "CSM101", "CSM202",
    "CSCI128", "CSCI200", "CSCI210", "CSCI220", "CSCI306", "CSCI341", "CSCI358",
    "CSCI370", "CSCI400", "CSCI406", "CSCI442",
]


def s_cs(x):
    required = CS_REQUIRED
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


# ---- programs added by Abdallah on 2026-11-22 (the remaining bachelor's majors; Samantha built the first five)

def either(x, a, b):
    """A 'X or Y' slot printed in the degree table: one of two courses."""
    return x.X([a, b])


def subject_pool(x, prefix, lo, hi, required, label_note=None):
    """Courses for a slot that names only a subject ('MTGN Elective'): that subject, a level range, not already required."""
    return x.pool(prefix, lo, hi, exclude=set(required))


def s_ee(x):
    required = [
        "CHGN121", "MATH111", "HASS100", "CSM101", "MATH112", "EDNS151", "PHGN100", "CSM202", "CSCI128",
        "HASS215", "MATH213", "PHGN200", "CSCI200", "MATH225", "EENG284", "EENG281", "EENG282", "MATH332",
        "EENG307", "EBGN321", "EENG310", "EENG383", "EENG391", "EENG386", "EENG385", "EENG311", "EENG389", "EENG350",
        "EDNS491", "EDNS492",
    ]
    x.note("The 'Science Elective' slot (4 credits) is one of CBEN110, GEGN101, CHGN122 or CHGN125.")
    x.note("Senior-fall field session is EENG393 (Printed Circuit Board Design) or EENG394 (1 credit).")
    x.note("EE electives: 15 credits from the approved list, at least 9 of them 400-level or higher EENG courses. The "
           "9-credit minimum is not enforceable in this format. Graduate EE courses and other 400-level courses taught "
           "by EE faculty may count with instructor approval or a course exception request; not modelled.")
    ee_list = x.X(["EENG411", "EENG415", "EENG417", "EENG421", "EENG423", "EENG425", "EENG427", "EENG428", "EENG430",
                   "EENG433", "EENG437", "EENG470", "EENG475", "EENG480", "EENG484", "CSCI341", "CSCI410", "CSCI440",
                   "CSCI442", "CEEN405", "MEGN441", "MATH335", "MATH455", "MEGN330", "MEGN465", "PHGN300", "PHGN320",
                   "PHGN435", "PHGN440", "PHGN441", "PHGN462"])
    return [P("ee-bs", "Bachelor of Science in Electrical Engineering", 128, [
        ALL("required", "Required core and Electrical Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("science-elective", "Science Elective", 4, x.X(["CBEN110", "GEGN101", "CHGN122", "CHGN125"])),
        PICK("field-session", "Field session (EENG393 or EENG394)", 1, either(x, "EENG393", "EENG394")),
        PICK("ee-electives", "Electrical Engineering Electives (5 courses)", 15, ee_list),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_engphys(x):
    required = [
        "MATH111", "CHGN121", "HASS100", "CSCI128", "CSM101", "MATH112", "CHGN122", "PHGN100", "EDNS151",
        "MATH213", "PHGN200", "HASS215", "EDNS251", "CSM202", "PHGN215",
        "PHGN384", "PHGN311", "PHGN315", "PHGN317", "PHGN350", "EBGN321",
        "PHGN320", "PHGN326", "PHGN341", "PHGN361", "PHGN471", "PHGN481", "PHGN462", "PHGN472", "PHGN482",
    ]
    x.note("HNRS105 and HNRS115 replace HASS100 and EDNS151 for honors students (PDF note); see the Thorson policy in "
           "forms-policies.json.")
    x.note("'Engineering Science Elective' (3 credits) has no list in the PDF; left open (any course). Confirm with the "
           "Physics department.")
    x.note("PHGN310 (honors) or PHGN300 fills Modern Physics; the Physics department recommends PHGN310. Honors PHGN491 "
           "and PHGN492 may replace PHGN481 and PHGN482 with instructor consent (not modelled).")
    return [P("engineering-physics-bs", "Bachelor of Science in Engineering Physics", 127, [
        ALL("required", "Required core and Engineering Physics courses", x.X(required)),
        success_wellness(x),
        PICK("differential-equations", "MATH225 Differential Equations or MATH235", 3, x.X(["MATH225"]) + ["MATH235"]),
        PICK("linear-algebra", "MATH332 Linear Algebra or MATH342", 3, x.X(["MATH332"]) + ["MATH342"]),
        PICK("modern-physics", "PHGN310 Honors Modern Physics or PHGN300", 3, x.X(["PHGN310", "PHGN300"])),
        PICK("engineering-science", "Engineering Science Elective", 3),
        *cas_groups(x, mid_credits=3, upper_credits=6),
        PICK("free-electives", "Free Electives (4 courses)", 12),
    ])]


def mme_core(x):
    """Courses the Ceramic and Metallurgical and Materials programs share."""
    return ["CHGN121", "CSM101", "MATH111", "HASS100", "CSCI128", "CHGN125", "PHGN100", "CSM202", "MATH112", "EDNS151",
            "MTGN272", "MATH213", "PHGN200", "MTGN202", "MTGN251", "HASS215", "MATH225", "CEEN241", "MTGN211",
            "MTGN281", "EBGN321", "MTGN352", "MTGN310", "MTGN310L", "MTGN350", "MTGN315", "MTGN467", "MTGN468"]


def s_ceramic(x):
    required = mme_core(x) + ["MTGN319", "MTGN319L", "MTGN345", "MTGN345L", "MTGN410", "MTGN465", "MTGN465L"]
    x.note("'MTGN Elective' (4 courses, 12 credits) names only the subject; modelled as MTGN300-499 courses that are not "
           "already required. The level is assumed; confirm the approved list with the department.")
    x.note("MTGN100-MTGN599 count toward the major GPA (PDF).")
    return [P("ceramic-engineering-bs", "Bachelor of Science in Ceramic Engineering", 127, [
        ALL("required", "Required core and Ceramic Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("mechanics-of-materials", "CEEN311 Mechanics of Materials or MEGN212", 3, either(x, "CEEN311", "MEGN212")),
        *cas_groups(x, mid_credits=9, upper_credits=0),
        PICK("mtgn-electives", "MTGN Electives (4 courses)", 12, subject_pool(x, "MTGN", 300, 499, required)),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_mme(x):
    required = mme_core(x) + ["MTGN334", "MTGN334L", "MTGN348", "MTGN348L", "MTGN445", "MTGN445L", "MTGN461"]
    x.note("'MTGN Elective' (4 courses, 12 credits) names only the subject; modelled as MTGN300-499 courses that are not "
           "already required. The level is assumed; confirm the approved list with the department.")
    return [P("mme-bs", "Bachelor of Science in Metallurgical and Materials Engineering", 127, [
        ALL("required", "Required core and Metallurgical and Materials Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("mechanics-of-materials", "CEEN311 Mechanics of Materials or MEGN212", 3, either(x, "CEEN311", "MEGN212")),
        *cas_groups(x),
        PICK("mtgn-electives", "MTGN Electives (4 courses)", 12, subject_pool(x, "MTGN", 300, 499, required)),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_geophysics(x):
    required = [
        "MATH111", "CHGN121", "HASS100", "CSM101", "GEGN101", "MATH112", "PHGN100", "EDNS151", "CSCI128",
        "MATH213", "GPGN228", "HASS215", "CSM202", "GEGN212", "PHGN200", "MATH225", "GPGN229", "GPGN268",
        "MATH332", "GPGN328", "GPGN318", "EBGN321", "GPGN404", "GPGN329", "DSCI403", "GPGN319", "GPGN486",
        "GPGN436", "GPGN409", "GPGN438",
    ]
    methods = x.X(["GPGN411", "GPGN420", "GPGN461", "GPGN470"])
    x.note("Earth Elective (3 credits): at least 3 credits of GEGN or GEOL (PDF footnote 1); modelled as GEGN or GEOL "
           "courses at the 200-499 level. The level range is an assumption.")
    x.note("Advanced GPGN electives: 12 credits at the 400 or 500 level, at least 6 of them from the geophysical methods "
           "courses GPGN411, GPGN420, GPGN461, GPGN470 (footnote 3). Modelled as 6 credits from the methods courses plus "
           "6 from other GPGN400-599 courses.")
    earth = x.pool("GEGN", 200, 499, exclude=set(required)) + x.pool("GEOL", 200, 499, exclude=set(required))
    return [P("geophysical-engineering-bs", "Bachelor of Science in Geophysical Engineering", 126, [
        ALL("required", "Required core and Geophysical Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("earth-elective", "Earth Elective (GEGN or GEOL)", 3, earth),
        *cas_groups(x),
        PICK("gpgn-methods", "Advanced GPGN electives: geophysical methods", 6, methods),
        PICK("gpgn-advanced", "Advanced GPGN electives (400 or 500 level)", 6,
             [c for c in x.pool("GPGN", 400, 599, exclude=set(required) | set(methods))]),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_petroleum(x):
    required = [
        "CSM101", "GEGN101", "MATH111", "CHGN121", "HASS100", "PHGN100", "MATH112", "CHGN122", "CSCI128", "CSM202",
        "CEEN241", "MATH213", "PHGN200", "PEGN201", "EDNS151", "PEGN251", "PEGN308", "PEGN282", "CHGN209", "HASS215",
        "EBGN321", "PEGN315", "PEGN311", "PEGN312", "PEGN382", "GEOL315", "CEEN311", "MATH225",
        "PEGN361", "PEGN411", "PEGN419", "PEGN438", "PEGN482", "GEOL308", "PEGN316",
        "PEGN423", "PEGN422", "PEGN424", "PEGN426", "PEGN439",
    ]
    return [P("petroleum-engineering-bs", "Bachelor of Science in Petroleum Engineering", 131, [
        ALL("required", "Required core and Petroleum Engineering courses", x.X(required)),
        success_wellness(x),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_civil(x):
    required = [
        "MATH111", "CHGN121", "HASS100", "CSM101", "CSCI128", "MATH112", "PHGN100", "CHGN122", "EDNS151",
        "CEEN210", "MATH213", "PHGN200", "CEEN241", "CSM202", "HASS215",
        "MATH201", "CEEN310", "CEEN311", "CEEN315", "CEEN317", "CEEN331",
        "MATH225", "CEEN312", "CEEN312L", "CEEN314", "CEEN350", "CEEN415", "EBGN321", "EDNS491", "EDNS492",
    ]
    breadth = x.X(["CEEN301", "CEEN381", "CEEN320"])
    structural = x.X(["CEEN443", "CEEN445"])
    technical = x.X([
        "CEEN302", "CEEN303", "CEEN321", "CEEN322", "CEEN324", "CEEN401", "CEEN402", "CEEN405", "CEEN406", "CEEN410",
        "CEEN411", "CEEN421", "CEEN422", "CEEN424", "CEEN425", "CEEN426", "CEEN429", "CEEN430", "CEEN433", "CEEN439",
        "CEEN442", "CEEN448", "CEEN449", "CEEN460", "CEEN461", "CEEN470", "CEEN472", "CEEN473", "CEEN475", "CEEN478",
        "CEEN479", "CEEN480", "CEEN482", "CEEN492", "GEGN466", "GEGN468", "GEGN473", "GEGN475", "MEGN416", "MNGN321",
        "MNGN404", "MNGN405", "MNGN406"])
    x.note("Breadth, structural and technical electives: a course on one list that is not needed to meet that list's "
           "minimum may also count as a technical or free elective (PDF). The format cannot express the overlap, so each "
           "list is its own group. At least 2 of the 4 technical electives must have a CEEN prefix; not enforceable.")
    return [P("civil-engineering-bs", "Bachelor of Science in Civil Engineering", 126, [
        ALL("required", "Required core and Civil Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("design-ii", "CEEN267 Design II: Civil Engineering or EDNS251", 3, x.X(["CEEN267", "EDNS251"])),
        PICK("ce-breadth", "Civil Engineering Breadth Electives (minimum two courses)", 6, breadth),
        PICK("structural-design", "Structural Design Elective", 3, structural),
        PICK("ce-technical", "Civil Engineering Technical Electives (minimum four courses)", 12, technical),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 6),
    ])]


def s_construction(x):
    required = [
        "MATH111", "CHGN121", "CSM101", "HASS100", "EDNS151", "MATH112", "PHGN100", "CSCI128", "MATH201",
        "MATH213", "CEEN241", "CEEN210", "CEEN320", "HASS215", "CSM202",
        "CEEN267", "CEEN310", "CEEN311", "CEEN322", "CEEN331",
        "MATH225", "CEEN312", "CEEN312L", "CEEN314", "CEEN321",
        "CEEN315", "CEEN324", "CEEN350", "CEEN415", "EBGN321",
        "CEEN424", "CEEN427", "EDNS491", "CEEN422", "EDNS492",
    ]
    technical = x.X([
        "CEEN381", "CEEN401", "CEEN405", "CEEN406", "CEEN410", "CEEN411", "CEEN419", "CEEN421", "CEEN425", "CEEN426",
        "CEEN429", "CEEN430", "CEEN442", "CEEN443", "CEEN445", "CEEN448", "CEEN449", "CEEN470", "CEEN473", "CEEN475",
        "CEEN493", "GEGN466", "GEGN468", "GEGN473", "MNGN321"])
    x.note("Distributed Science Selection (4 credits): one of CHGN122, PHGN200, GEGN101, CBEN110. The PDF suggests CHGN122 "
           "for the Material/Environmental track, GEGN101 for Underground and PHGN200 for Robotics; the tracks are not "
           "modelled as separate programs because only this one choice differs.")
    x.note("Construction Engineering Technical Electives: at least 3 courses from the list, 2 of them with a CEEN prefix "
           "(not enforceable). Unused ones may count as free electives.")
    return [P("construction-engineering-bs", "Bachelor of Science in Construction Engineering", 127, [
        ALL("required", "Required core and Construction Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("distributed-science", "Distributed Science Selection", 4, x.X(["CHGN122", "PHGN200", "GEGN101", "CBEN110"])),
        PICK("con-technical", "Construction Engineering Technical Electives (3 courses)", 9, technical),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 3),
    ])]


def s_environmental(x):
    required = [
        "MATH111", "CHGN121", "GEGN101", "HASS100", "CSM101", "MATH112", "CHGN122", "PHGN100", "EDNS151",
        "MATH213", "CEEN241", "CSM202", "MATH225", "CEEN310", "HASS215", "CSCI128",
        "CEEN381", "MATH201", "CEEN301", "EBGN321", "CEEN302", "CEEN303", "CEEN330",
        "EDNS491", "CEEN470", "CEEN482", "EDNS492", "CEEN480",
    ]
    bio = x.X(["CBEN110", "CEEN460", "CEEN461", "CHGN462"])
    eve = x.X([
        "CEEN311", "CEEN312", "CEEN405", "CEEN401", "CEEN402", "CEEN410", "CEEN425", "CEEN426", "CEEN460", "CEEN461",
        "CEEN472", "CEEN473", "CEEN475", "CEEN478", "CEEN479", "CEEN492", "CEEN493", "CEEN555", "CEEN581", "CHGN403",
        "CHGN462", "ENGY320", "GEGN466", "GEGN468", "GEGN473", "GEGN475", "MEGN467", "PEGN430"])
    x.note("Bio-science elective: if met with BIOL110, then CEEN460, CEEN461 and CHGN462 may count as Environmental "
           "Engineering Electives or Free Electives; BIOL110 cannot count as an Environmental Engineering Elective "
           "(PDF footnote). BIOL110 is not in the course CSV, so it is not in the list; CBEN110 is.")
    x.note("Environmental Engineering Electives: a minimum of four courses from the list; unused ones may count as free "
           "electives. The PDF lists CEEN311 and CEEN312 with them.")
    return [P("environmental-engineering-bs", "Bachelor of Science in Environmental Engineering", 127, [
        ALL("required", "Required core and Environmental Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("design-ii", "EDNS251 Cornerstone Design II or CEEN267", 3, x.X(["EDNS251", "CEEN267"])),
        PICK("thermodynamics", "CHGN209, CBEN210 or MEGN261 (thermodynamics)", 3, x.X(["CHGN209", "CBEN210", "MEGN261"])),
        PICK("bioscience", "Bio-Science Elective", 3, bio),
        PICK("eve-electives", "Environmental Engineering Electives (4 courses)", 12, eve),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 9),
    ])]


def s_biochemistry(x):
    required = [
        "MATH111", "CBEN110", "CHGN121", "CSM101", "CSCI128", "MATH112", "PHGN100", "CHGN122", "HASS100", "CSM202",
        "MATH213", "PHGN200", "CHGN209", "CHGN221", "CHGN223", "MATH225", "CHGN335", "CHGN222", "CHGN224", "EDNS151",
        "HASS215", "CHGN341", "CHGN351", "CHGN395", "CHGN336", "CHGN337",
        "CHGN428", "CHGN323", "CHGN431", "CBEN120", "CHGN490", "CHGN429", "EBGN321",
    ]
    chgn = x.X(["CHGN311", "CHGN403", "CHGN409", "CHGN441", "CHGN445", "CHGN462", "CHGN495"])
    x.note("Technical Electives (7 credits: 4 in junior fall, 3 in senior spring) are 'courses in any technical field'; "
           "HASS, PAGN, Military Science, ROTC, McBride and most EBGN courses are not accepted. Left open (any course). "
           "The PDF lists examples (CBEN304, CBEN305, CBEN311, CBEN320, CBEN321, CBEN322, CBEN411, CBEN431, ...), not "
           "a closed list. CHGN495 Undergraduate Research is 1-5 credits.")
    return [P("biochemistry-bs", "Bachelor of Science in Biochemistry", 133, [
        ALL("required", "Required core and Biochemistry courses", x.X(required)),
        success_wellness(x),
        PICK("chgn-electives", "Chemistry Electives (3 courses)", 9, chgn),
        PICK("technical-electives", "Technical Electives (any technical field)", 7),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 9),
    ])]


def s_quantum(x):
    required = [
        "MATH111", "CHGN121", "HASS100", "CSCI128", "CSM101", "MATH112", "CSCI200", "HASS215", "PHGN100", "EDNS151",
        "MATH213", "MATH225", "CEEN241", "PHGN200", "CSM202", "MATH332", "CSCI210", "PHGN215", "MEGN261",
        "CSCI341", "EENG284", "EENG307", "PHGN315", "EDNS220", "EENG383", "EBGN321", "PHGN320",
        "EDNS491", "EENG421", "PHGN417", "EDNS492", "CSCI581",
    ]
    tech = x.X(["CSCI404", "CSCI410", "CSCI470", "EENG385", "EENG433", "EENG484", "MEGN351", "MEGN461", "MEGN423",
                "PHGN435", "PHGN440", "PHGN466", "PHGN480"])
    x.note("'PHGNXXX Quantum Devices Laboratory (NEW)' has no course code yet; modelled as an open 3-credit slot. Replace "
           "it with the real course when it appears in the catalog.")
    x.note("EDNS220 takes the place of one CAS mid-level elective (PDF). CSCI581 is marked 'Reformat at 4xx-level'; code "
           "as printed.")
    x.note("PHGN384 Field Session Techniques in Physics is 3.0 credits here ('new version specifically redesigned for this "
           "program') but 6.0 in the course CSV (and in the Engineering Physics PDF). It is a 3-credit group, not a required "
           "course, so the credits add up to the PDF's 129.")
    x.note("EDNS311 Systems Engineering ('New, similar to EDNS310') is not in the course CSV yet, so it is an open 3-credit "
           "slot, not a required course code. Make it required once the catalog has it.")
    x.note("The PDF says the 3 technical credits and the 6 free-elective credits 'can be selected from' the technical list; "
           "the free electives are left open and only the technical elective uses the list.")
    return [P("quantum-systems-engineering-bs", "Bachelor of Science in Quantum Systems Engineering", 129, [
        ALL("required", "Required core and Quantum Systems Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("modern-physics", "PHGN300 Modern Physics I or PHGN310 (honors)", 3, x.X(["PHGN300", "PHGN310"])),
        PICK("field-session", "PHGN384 Field Session Techniques in Physics (3-credit version for this program)", 3,
             x.X(["PHGN384"])),
        PICK("quantum-devices-lab", "Quantum Devices Laboratory (new course, no code yet)", 3),
        PICK("systems-engineering", "EDNS311 Systems Engineering (new course, not in the catalog yet)", 3),
        PICK("technical-elective", "Technical Elective", 3, tech),
        *cas_groups(x, mid_credits=3, upper_credits=3),
        PICK("free-electives", "Free Electives", 6),
    ])]


def listed(x, header, stop, exclude=()):
    """Course codes printed in the PDF between `header` and `stop` (whitespace-normalised, first occurrence of each),
    keeping only codes the course CSV has. Used for long approved-elective lists so they are not retyped by hand."""
    text = re.sub(r"\s+", " ", x.text)
    start = text.index(header) + len(header)
    end = text.index(stop, start) if stop else len(text)
    out = []
    for m in re.finditer(r"\b([A-Z]{3,4}) ?(\d{3}[A-Z]?)\b", text[start:end]):
        c = m.group(1) + m.group(2)
        if c in x.c and c not in out and c not in exclude:
            out.append(c)
    assert out, "%s: no course codes between %r and %r" % (x.name, header, stop)
    return out


def merge_lists(*lists):
    out = []
    for lst in lists:
        for c in lst:
            if c not in out:
                out.append(c)
    return out


def s_mechanical(x):
    required = [
        "CHGN121", "CSM101", "EDNS151", "HASS100", "MATH111", "HASS215", "CSCI128", "MATH112", "PHGN100", "CSM202",
        "CEEN241", "MTGN202", "MATH213", "MEGN200", "PHGN200", "EENG281", "MATH225", "MEGN212", "MEGN261", "MEGN201",
        "MATH307", "MEGN300", "MEGN315", "MEGN324", "EBGN321", "MEGN301", "MEGN351", "MEGN381", "MEGN481",
        "EDNS491", "MEGN471", "EDNS492",
    ]
    adv = listed(x, "Advanced Engineering Sciences:", "Mechanical Engineering Electives:")
    me_list = listed(x, "Mechanical Engineering Electives:", "Major GPA", exclude=set(required))
    placeholder_pools = []
    for prefix in ["AMFG", "CSCI", "EENG", "ENGY", "FEGN", "MATH"]:
        placeholder_pools += x.pool(prefix, 500, 597)
    megn_tech = x.pool("MEGN", 400, 498, exclude=set(required) | {"MEGN471", "MEGN481"})
    megn_500 = x.pool("MEGN", 500, 599)
    me_all = merge_lists(adv, me_list, megn_tech, megn_500, placeholder_pools)
    x.note("MEGN200 appears in the sophomore-fall slot ('MEGN200 or MEGN201') and MEGN201 again in sophomore spring, so "
           "both are required; students take one in each semester.")
    x.note("Mechanical Engineering electives: four courses (12 credits), at least one from Advanced Engineering "
           "Sciences (MEGN412, MEGN416, MEGN451, MEGN461); the other three from that list or the Mechanical Engineering "
           "Electives list. That list is read from the PDF by code. Its placeholder lines are modelled as pools: "
           "'MEGN4XX Mechanical Tech Elective (not including 499 & required 400-level courses)' as MEGN400-498 not "
           "required, 'MEGN5XX any 500-level MEGN course' as MEGN500-599, and 'AMFG5XX, CSCI5XX, EENG5XX, ENGY5XX, "
           "FEGN5XX, MATH5XX non-seminar/non-project and research credit' as 500-597 courses in those subjects "
           "(the exclusion of seminar and research credit is approximate). MEGN391 is for Automotive-track students only "
           "(PDF); the Automotive track is not a separate table, so it is left in the list. HNRS VIPER credit (up to 3 "
           "credits) is not modelled.")
    return [P("mechanical-engineering-bs", "Bachelor of Science in Mechanical Engineering", 126, [
        ALL("required", "Required core and Mechanical Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("advanced-engineering-sciences", "Advanced Engineering Sciences Elective", 3, adv),
        PICK("me-electives", "Mechanical Engineering Electives (3 courses)", 9, me_all),
        *cas_groups(x),
        PICK("free-electives", "Free Electives", 6),
    ])]


CBE_COMMON = [
    "CBEN110", "CHGN121", "CSM101", "HASS100", "MATH111", "CHGN122", "CSCI128", "MATH112", "PHGN100", "CBEN210",
    "CHGN221", "CHGN223", "MATH213", "PHGN200", "CSM202", "CBEN200", "CBEN201", "CHGN222", "EDNS151", "MATH225",
    "CBEN307", "CBEN357", "CBEN358", "CHGN351", "HASS215", "CBEN314", "CBEN375", "CBEN403", "CBEN312", "CBEN313",
    "CBEN402", "CBEN414", "CBEN418", "EBGN321",
]


def s_chemical(x):
    base = "Bachelor of Science in Chemical Engineering"
    x.note("Four programs: the base degree and three tracks (Biological Engineering, Process Engineering, Honors "
           "Research), each its own program (CONFLICT-LOG rule 8). They share the same 34 core courses.")
    x.note("'Technical Electives' are any upper-division (300-level or higher) course in any engineering or science "
           "designation; Humanities and Economics do not count. Left as open groups (any course), since no closed list "
           "exists.")
    x.note("The Honors Research track is by application only and also needs public dissemination of the research, an "
           "accepted written thesis and an overall GPA of 3.5 or higher; those are not course requirements.")
    cbe_general = listed(x, "CBEN Electives", "Degree Requirements (Biological", exclude=set(CBE_COMMON))
    cbe_400 = listed(x, "400-Level CBEN Electives", "Degree Requirements (Process", exclude=set(CBE_COMMON))
    cbe_400 = [c for c in cbe_400 if c.startswith("CBEN4")]
    bio_tech = listed(x, "Biological Tech Electives", "400-Level CBEN Electives")
    process = listed(x, "Process Electives", "Degree Requirements (Chemical Engineering Honors", exclude=set(CBE_COMMON))
    process_400 = [c for c in process if c.startswith("CBEN4")]
    def chgn_cben_300(extra=()):
        skip = set(CBE_COMMON) | set(extra)
        return x.pool("CBEN", 300, 599, exclude=skip) + x.pool("CHGN", 300, 599, exclude=skip)

    research = ["CBEN350", "CBEN351", "CBEN450", "CBEN451"]
    for c in research:
        assert c in x.c, "%s not in the course CSV" % c
    return [
        P("chemical-engineering-bs", base, 133, [
            ALL("required", "Required core and Chemical Engineering courses", x.X(CBE_COMMON)),
            success_wellness(x),
            PICK("technical-electives", "Technical Electives (2 courses, 300-level or higher)", 6),
            PICK("cbe-elective", "CBEN Elective (from the CBEN electives list)", 3, cbe_general),
            PICK("cbe-400", "400-Level Chemical Engineering Elective", 3, cbe_400),
            PICK("chgn-cben-300", "CHGN or CBEN Elective (300-level or higher)", 3, chgn_cben_300()),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("chemical-engineering-bs-biological", base + " (Biological Engineering Track)", 133, [
            ALL("required", "Required core, Chemical Engineering and Biological Engineering courses",
                x.X(CBE_COMMON + ["CHGN428", "CBEN360"])),
            success_wellness(x),
            PICK("bio-tech-electives", "Biological Tech Electives (2 courses)", 6, bio_tech),
            PICK("cbe-400", "400-Level Chemical Engineering Elective", 3, cbe_400),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("chemical-engineering-bs-process", base + " (Process Engineering Track)", 133, [
            ALL("required", "Required core, Chemical Engineering and Process Engineering courses",
                x.X(CBE_COMMON + ["CBEN365"])),
            success_wellness(x),
            PICK("process-electives", "Process Electives (2 courses)", 6, process),
            PICK("process-400", "400-Level Process Elective (a 400-level CBEN course)", 3, process_400),
            PICK("chgn-cben-300", "CHGN or CBEN Elective (300-level or higher)", 3, chgn_cben_300(["CBEN365"])),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("chemical-engineering-bs-honors-research", base + " (Honors Research Track)", 133, [
            ALL("required", "Required core, Chemical Engineering and Honors Research courses",
                x.X(CBE_COMMON + ["CBEN368", "CBEN430"])),
            success_wellness(x),
            PICK("honors-research", "Honors Undergraduate Research (CBEN350, 351, 450 or 451; 5 credits)", 5, research),
            PICK("cbe-elective-400-500", "400- or 500-Level Chemical Engineering Elective", 3,
                 x.pool("CBEN", 400, 599, exclude=set(CBE_COMMON) | {"CBEN430"})),
            PICK("technical-electives", "Technical Elective (300-level or higher)", 3),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
    ]


def s_design(x):
    required = [
        "EDNS151", "EDNS200", "MATH111", "CHGN121", "CSM101", "MATH112", "PHGN100", "CSCI128", "HASS100",
        "EDNS210", "MATH213", "PHGN200", "MATH201", "HASS215", "CSM202",
        "EDNS220", "MATH225", "CEEN241", "EDNS310", "EBGN321", "EDNS479", "EDNS320", "EDNS445",
        "EDNS491", "EDNS492", "EDNS450",
    ]
    eng = listed(x, "Chemical Engineering CBEN310", "Major GPA", exclude=set(required))
    x.note("EDNS220 serves as one of the three mid-level CAS electives (PDF), so only 2 CAS slots remain: one mid-level "
           "and one 400-level.")
    x.note("Engineering Fundamentals (footnote #): one thermodynamics course (MEGN261, CHGN209 or CBEN210), CEEN241, one "
           "circuits course (EENG281 or EENG282), one materials course (MTGN202, CEEN311 or MEGN212) and one fluid "
           "mechanics course (CEEN310 or MEGN351; the printed row also lists CBEN307).")
    x.note("Thematic Electives (4 courses, 12 credits): a custom set of 300-level-or-higher courses approved by the "
           "advisor and the Design Engineering Program Director; left open (any course). Engineering Electives (3 courses, "
           "9 credits) come from the approved list in the PDF or other 300+ engineering courses approved by the advisor "
           "(the list is read from the PDF; the advisor-approval route is not enforceable). Also required by the PDF: "
           "9 credits at or above 300-level with one course prefix, and 9 credits of engineering content at the 400 level "
           "or above across the thematic and engineering electives; neither is enforceable here.")
    return [P("design-engineering-bs", "Bachelor of Science in Design Engineering", 126, [
        ALL("required", "Required core and Design Engineering courses", x.X(required)),
        success_wellness(x),
        PICK("thermodynamics", "Thermodynamics: MEGN261, CHGN209 or CBEN210", 3, x.X(["MEGN261", "CHGN209", "CBEN210"])),
        PICK("circuits", "Circuits: EENG281 or EENG282", 3, either(x, "EENG281", "EENG282")),
        PICK("materials", "Materials: MEGN212, CEEN311 or MTGN202", 3, x.X(["MEGN212", "CEEN311"]) + ["MTGN202"]),
        PICK("fluids", "Fluid mechanics: MEGN351, CBEN307 or CEEN310", 3, x.X(["MEGN351", "CBEN307", "CEEN310"])),
        PICK("thematic-electives", "Thematic Electives (4 courses)", 12),
        PICK("engineering-electives", "Engineering Electives (3 courses)", 9, eng),
        *cas_groups(x, mid_credits=3, upper_credits=3),
        PICK("free-electives", "Free Electives", 6),
    ])]


CHEM_COMMON = [
    "CHGN121", "CSM101", "EDNS151", "CSCI128", "MATH111", "CHGN122", "MATH112", "HASS100", "PHGN100", "CSM202",
    "MATH213", "PHGN200", "CHGN209", "CHGN221", "CHGN223", "HASS215", "CHGN222", "CHGN224", "MATH225", "CHGN335",
    "CHGN336", "CHGN337", "CHGN341", "CHGN351", "CHGN395", "CHGN353", "CHGN323", "CHGN428", "CHGN490", "EBGN321",
]


def s_chemistry(x):
    x.note("Three tracks (Chemistry, Environmental Chemistry, Biochemistry), each its own program (CONFLICT-LOG rule 8). "
           "The Chemistry degree is ACS-certified.")
    x.note("Technical electives are 'courses in any technical field'; HASS, PAGN, Military Science, ROTC, McBride and "
           "most EBGN courses are not accepted. Left open (any course); the PDF lists examples only.")
    x.note("Chemistry electives are non-required courses taught in the Chemistry Department, plus graduate-level "
           "Chemistry and Geochemistry courses taught there; modelled as CHGN300-599 and CHGC500-599 (the level range is "
           "an assumption). Two slots: 3 credits (senior fall) and 2 credits (senior spring).")
    chem_pool = lambda req: [c for c in x.pool("CHGN", 300, 599, exclude=set(req)) + x.pool("CHGC", 500, 599)]
    env_list = listed(x, "Environmental electives are courses that are directly or indirectly related to Environmental "
                         "Chemistry. Examples of possible electives that are acceptable are:",
                      "Degree Requirements (Biochemistry Track)")
    chgn_bio = listed(x, "CHGN Electives:", "Tech Electives:")
    chem_req = CHEM_COMMON + ["CHGN401"]
    env_req = [c for c in CHEM_COMMON if c not in ("EDNS151",)] + ["EDNS151", "GEGN101", "CHGN406", "CHGN403"]
    bio_req = CHEM_COMMON + ["CBEN110", "CBEN120", "CHGN429", "CHGN401"]
    env_list = [c for c in env_list if c not in env_req]  # CHGN406 and CHGN403 are required in this track
    chgn_bio = [c for c in chgn_bio if c not in bio_req]
    return [
        P("chemistry-bs-chemistry", "Bachelor of Science in Chemistry (Chemistry Track)", 131, [
            ALL("required", "Required core and Chemistry courses", x.X(chem_req)),
            success_wellness(x),
            PICK("technical-electives", "Technical Electives (5 courses)", 15),
            PICK("chemistry-electives", "Chemistry Electives (3 + 2 credits)", 5, chem_pool(chem_req)),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 9),
        ]),
        P("chemistry-bs-environmental", "Bachelor of Science in Chemistry (Environmental Chemistry Track)", 135, [
            ALL("required", "Required core and Environmental Chemistry courses", x.X(env_req)),
            success_wellness(x),
            PICK("environmental-electives", "Environmental Electives (4 courses)", 12, env_list),
            PICK("technical-electives", "Technical Elective", 3),
            PICK("chemistry-electives", "Chemistry Electives (3 + 2 credits)", 5, chem_pool(env_req)),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("chemistry-bs-biochemistry", "Bachelor of Science in Chemistry (Biochemistry Track)", 134, [
            ALL("required", "Required core and Biochemistry courses", x.X(bio_req)),
            success_wellness(x),
            PICK("technical-electives", "Technical Electives (4 + 3 credits)", 7),
            PICK("chemistry-electives", "Chemistry Electives (3 + 2 credits)", 5, merge_lists(chgn_bio, chem_pool(bio_req))),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 9),
        ]),
    ]


GEO_COMMON = [
    "GEGN101", "MATH111", "CHGN121", "EDNS151", "CSM101", "PHGN100", "MATH112", "CSCI128", "HASS100",
    "GEGN203", "CHGN122", "CEEN241", "MATH213", "HASS215", "PHGN200", "CEEN311", "GEGN212", "GEGN217", "CSM202",
    "GEOL309", "EBGN321", "MATH225", "GEGN432", "GEOL314", "GEGN317", "GEGN316", "GEGN475",
]


def s_geological(x):
    base = "Bachelor of Science in Geological Engineering"
    x.note("Three tracks chosen after the sophomore year (Environmental Geosciences, Engineering Geology and "
           "Geotechnics, Mineral and Energy Resources Exploration), each its own program (CONFLICT-LOG rule 8). Each "
           "has 130 credits.")
    x.note("Environmental Geosciences: 'GEGN4XX Environmental Geosciences Design' (3 credits) and the 1-credit "
           "geochemistry lab (printed 'CHGN499L - Lab will be added in CIM as CHGN406L') have no catalog code yet, and "
           "'Restricted Elective 1' must be GEGN473, 'GEOL 4XX Paleoclimate' or 'GEGN 4XX Surface Water Hydrology' (the "
           "last two have no code yet). These are open slots (any course); replace them when the codes exist.")
    x.note("Environmental Geosciences 'Restricted Elective 2' is a 400- or 500-level GEGN, GEOL or GPGN course.")
    x.note("Mineral and Energy Resources: the senior-spring 'Restricted Elective, choose from list below' has no list in "
           "the PDF text; left open (any course).")
    x.note("Engineering Geology and Geotechnics students may use their free electives for an informal emphasis area; "
           "it is not on the transcript and is not modelled.")
    geo_400 = lambda req: (x.pool("GEGN", 400, 599, exclude=set(req)) + x.pool("GEOL", 400, 599, exclude=set(req))
                           + x.pool("GPGN", 400, 599, exclude=set(req)))
    env_req = GEO_COMMON + ["CEEN312", "CEEN312L", "GEGN351", "CHGN406", "GEGN466", "GEGN466L", "GEGN470"]
    eng_req = GEO_COMMON + ["MNGN321", "CEEN312", "CEEN312L", "GEGN351", "GEGN468", "GEGN466", "GEGN466L", "GEGN473",
                            "GEGN469", "GEGN470"]
    min_req = [c for c in GEO_COMMON if c != "GEGN475"] + [
        "GEGN475", "GEOL321", "GEGN307", "GEGN401", "GEGN438", "GEGN403", "GEGN439"]
    return [
        P("geological-engineering-bs-environmental-geosciences", base + " (Environmental Geosciences Track)", 130, [
            ALL("required", "Required core and Environmental Geosciences courses", x.X(env_req)),
            success_wellness(x),
            PICK("geochemistry-lab", "Geochemistry lab (code pending: CHGN406L)", 1),
            PICK("env-geosciences-design", "Environmental Geosciences Design (code pending)", 3),
            PICK("restricted-1", "Restricted Elective 1 (GEGN473, Paleoclimate or Surface Water Hydrology)", 3),
            PICK("restricted-2", "Restricted Elective 2 (400- or 500-level GEGN, GEOL or GPGN)", 3, geo_400(env_req)),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("geological-engineering-bs-engineering-geology", base + " (Engineering Geology and Geotechnics Track)", 130, [
            ALL("required", "Required core and Engineering Geology and Geotechnics courses", x.X(eng_req)),
            success_wellness(x),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
        P("geological-engineering-bs-mineral-energy", base + " (Mineral and Energy Resources Exploration Track)", 130, [
            ALL("required", "Required core and Mineral and Energy Resources courses", x.X(min_req)),
            success_wellness(x),
            PICK("soil-or-rock-mechanics", "CEEN312 Soil Mechanics or MNGN321 Introduction to Rock Mechanics", 3,
                 x.X(["CEEN312", "MNGN321"])),
            PICK("restricted-elective", "Restricted Elective (list not in the PDF text)", 3),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 6),
        ]),
    ]


BEMS_COMMON = [
    "CSCI128", "MATH111", "CHGN121", "HASS100", "CSM101", "PHGN100", "MATH112", "EDNS151", "EBGN201", "CSM202",
    "MATH213", "MATH201", "HASS215", "EBGN305", "EBGN307", "EBGN280", "EBGN345", "EBGN308", "EBGN309", "EBGN321",
    "EBGN381", "EBGN303", "EBGN382", "EBGN453", "EBGN485", "EBGN490",
]


def s_bems(x):
    base = "Bachelor of Science in Business Engineering and Management Science"
    x.note("The base degree and seven tracks, each its own program (CONFLICT-LOG rule 8). The tracks differ only in how "
           "the 18 credits of technical electives (six courses) are filled. Other courses may count with advisor "
           "approval; not modelled.")
    x.note("Engineering track: at least 15 credits from the engineering list (with the 'or' alternatives printed there "
           "as separate courses), and the remaining 3 credits from that list or the approved business electives that "
           "all BEMS students may take; modelled as 15 credits from the list plus 3 from the list or any EBGN 300-499 "
           "course. The business-elective list itself is not in the PDF text.")
    ebgn = x.pool("EBGN", 300, 499, exclude=set(BEMS_COMMON))

    def prog(suffix, label, extra_groups):
        name = base if label is None else "%s (%s Track)" % (base, label)
        return P("bems-bs" + ("" if suffix is None else "-" + suffix), name, 122, [
            ALL("required", "Required core and Business Engineering courses", x.X(BEMS_COMMON)),
            success_wellness(x),
            PICK("data-science", "DSCI403 Introduction to Data Science or CSCI303", 3, either(x, "DSCI403", "CSCI303")),
            *cas_groups(x),
            *extra_groups,
            PICK("free-electives", "Free Electives", 12),
        ])

    corp = listed(x, "Corporate Management Take 18 credit hours from the following list:", "Financial Economics")
    fin_a = listed(x, "Financial Economics Take at least 9CH from the following list:", "The remaining 9CH")
    fin_b = listed(x, "The remaining 9CH may come from a combination of the courses listed above or the following courses:",
                   "Energy and Natural Resources Management")
    enr_a = listed(x, "Energy and Natural Resources Management Take at least 9CH from the following list:", "The remaining 9CH")
    # the second "remaining 9CH" list belongs to the energy track: it sits between that track's first list and Computing
    txt = re.sub(r"\s+", " ", x.text)
    k = txt.index("Energy and Natural Resources Management Take at least 9CH")
    k2 = txt.index("The remaining 9CH may come from a combination of the courses listed above or the following courses:", k)
    k3 = txt.index("Computing Required Course", k2)
    enr_b = [m.group(1) + m.group(2) for m in re.finditer(r"\b([A-Z]{3,4}) ?(\d{3}[A-Z]?)\b", txt[k2:k3])
             if m.group(1) + m.group(2) in x.c]
    comp = listed(x, "The remaining 15 CH may from a combination of the following courses:", "Operations Research")
    opr = listed(x, "Operations Research Take 18 CH from the following list:", "Actuarial Science")
    act = listed(x, "The remaining 12 CH may come from a combination of the following courses:", "Engineering BEMS students")
    eng = listed(x, "BEMS students pursuing the Engineering track are required to take at least 15 credit hours of "
                    "engineering courses from the following list:", "The remaining 3 credit hours")
    return [
        prog(None, None, [PICK("technical-electives", "Technical Electives (6 courses, EBGN 300 or 400 level)", 18, ebgn)]),
        prog("corporate-management", "Corporate Management",
             [PICK("technical-electives", "Corporate Management technical electives (18 credits)", 18, corp)]),
        prog("financial-economics", "Financial Economics", [
            PICK("track-core", "Financial Economics list (at least 9 credits)", 9, fin_a),
            PICK("track-more", "Financial Economics list or additional courses (9 credits)", 9, merge_lists(fin_a, fin_b))]),
        prog("energy-natural-resources", "Energy and Natural Resources Management", [
            PICK("track-core", "Energy and Natural Resources list (at least 9 credits)", 9, enr_a),
            PICK("track-more", "Energy and Natural Resources list or additional courses (9 credits)", 9,
                 merge_lists(enr_a, enr_b))]),
        prog("computing", "Computing", [
            ALL("track-required", "Computing track required course", x.X(["CSCI200"])),
            PICK("track-electives", "Computing track electives (15 credits)", 15, comp)]),
        prog("operations-research", "Operations Research",
             [PICK("technical-electives", "Operations Research technical electives (18 credits)", 18, opr)]),
        prog("actuarial-science", "Actuarial Science", [
            ALL("track-required", "Actuarial Science track required courses", x.X(["MATH334", "MATH335"])),
            PICK("track-electives", "Actuarial Science track electives (12 credits)", 12, act)]),
        prog("engineering", "Engineering", [
            PICK("track-engineering", "Engineering track: engineering list (at least 15 credits)", 15, eng),
            PICK("track-engineering-more", "Engineering track: list or business electives (3 credits)", 3,
                 merge_lists(eng, ebgn))]),
    ]


def s_qbe(x):
    base = "Bachelor of Science in Quantitative Biosciences and Engineering"
    x.note("Two programs: the General Track and the Honors Track (CONFLICT-LOG rule 8). The PDF marks some courses as "
           "'new course needed for the major'; codes are as printed.")
    x.note("CAS Restricted Electives I to III (9 credits) have no level given; modelled as 6 mid-level and 3 400-level "
           "credits like the other programs.")
    x.note("CBEN321 Genetics is 4.0 credits in the QBE PDF but 3.0 in the course CSV (the CSV is used), so the General "
           "Track adds up to 129 against the printed 130. The PDF's 4.0 probably means Genetics plus its 1-credit lab "
           "(CBEN331); code kept as printed, nothing added. Honors: HNRS398 and HNRS498 are variable-credit (1-6) in the "
           "CSV but 1.0 in the PDF, so they are explicit 1-credit groups.")
    tech = listed(x, "Technical electives with emphasis on biology-related courses, chosen from the following:",
                  "Free Technical Elective totals")
    common = [
        "CBEN110", "MATH111", "CHGN121", "EDNS151", "CSM101", "MATH112", "CHGN122", "HASS100", "CBEN120",
        "CHGN221", "CHGN223", "MATH213", "CSCI128", "PHGN100", "CSM202", "CHGN222", "MATH225", "BIOL300", "PHGN200",
        "MATH201", "CHGN428", "CHGN431", "HASS215", "BIOL301", "CBEN320", "CBEN321", "BIOL415", "EBGN321", "CSCI478",
    ]
    mid = [success_wellness(x), PICK("microbiology", "CHGN462 Microbiology or CEEN460", 3, either(x, "CHGN462", "CEEN460")),
           PICK("entrepreneurship", "BIOL412 Entrepreneurship in the Biological Sciences or BIOL491", 3,
                either(x, "BIOL412", "BIOL491"))]
    return [
        P("qbe-bs-general", base + " (General Track)", 130, [
            ALL("required", "Required core and QBE courses", x.X(common)), *mid,
            PICK("technical-electives", "Interdisciplinary Bio Technical Electives (5 courses)", 15, tech),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 9),
        ]),
        P("qbe-bs-honors", base + " (Honors Track)", 130, [
            ALL("required", "Required core, QBE and Honors courses", x.X(common + ["BIOL490"])),
            PICK("honors-research-methods", "HNRS398 Special Topics (Research Methods, 1 credit)", 1, x.X(["HNRS398"])),
            PICK("honors-research-communications", "HNRS498 Special Topics (Research Communications, 1 credit)", 1,
                 x.X(["HNRS498"])),
            *mid,
            PICK("honors-research", "BIOL499 Independent Study (Honors Research, 6 credits over two semesters)", 6,
                 x.X(["BIOL499"])),
            PICK("technical-electives", "Interdisciplinary Bio Technical Electives (2 courses)", 6, tech),
            *cas_groups(x),
            PICK("free-electives", "Free Electives", 9),
        ]),
    ]


def s_cs_focus(x):
    """The six other Computer Science focus areas. Samantha built the first ('Computer Science', the General track).
    Each focus area replaces the 8 'Focus Area Course' slots (24 credits) of the main table; the rest is the same core."""
    x.note("Six more programs, one per focus area (CONFLICT-LOG rule 8): CS + Business, + Computer Engineering, + Data "
           "Science, + Entrepreneurship & Innovation, + Robotics & Intelligent Systems, + Space. Each is the CS core, the "
           "CS and free electives of the main table, and the focus area's own 24 credits.")
    x.note("In a focus area, a course it requires cannot also count as a CS elective (PDF); only the fixed required "
           "courses are removed from the CS elective list, since which 'or' alternative a student takes is not known.")
    x.note("Several 'or' slots mix courses with different credits (for example PHGN215 is 4.0, EENG281 is 3.0) and "
           "CSCI423, CSCI437 are listed as 0-3. Each slot is modelled with the credits of the first course printed (3 "
           "unless the PDF says 4 or 1), which makes each focus area 24 credits, matching the PDF's total.")
    x.note("CS + Entrepreneurship: CSCI460 is both required (Design) and printed among the Prototyping alternatives; since "
           "it is already required, it is left out of the Prototyping list.")
    cs_pool = x.pool("CSCI", 400, 599) + x.X(["CSED435", "EENG383", "MATH307", "EDNS491", "EDNS492"])

    def slot(gid, label, codes, credits=3):
        return PICK(gid, label, credits, x.X(codes))

    def prog(suffix, name, groups):
        fixed = {c for g in groups if g["kind"] == "all" for c in g["courses"]}
        elect = [c for c in cs_pool if c not in set(CS_REQUIRED) | fixed]
        return P("cs-bs-" + suffix, "Bachelor of Science in Computer Science (%s)" % name, 128, [
            ALL("required", "Required core and Computer Science courses", x.X(CS_REQUIRED)),
            success_wellness(x),
            *cas_groups(x),
            PICK("cs-elective", "Computer Science Elective", 3, elect),
            PICK("free-electives", "Free Electives", 9),
            *groups,
        ])

    ebgn_mix = ["EBGN301", "EBGN201", "EBGN280", "EBGN302", "EBGN305", "EBGN308", "EBGN309", "EBGN315", "EBGN320",
                "EBGN345", "EBGN346", "EBGN360", "EBGN381", "EBGN382", "EBGN453", "EBGN459", "EBGN461"]
    circuits = ["EENG281", "EENG282", "PHGN215"]
    return [
        prog("business", "CS + Business", [
            ALL("focus-data", "Required data courses", x.X(["CSCI403", "CSCI413", "CSCI475"])),
            slot("focus-front-end", "Front end application", ["CSCI448", "CSCI445", "CSCI446"]),
            slot("focus-business-core", "Business core", ["EBGN201", "EBGN280", "EBGN305", "EBGN308", "EBGN309"]),
            slot("focus-business-application", "Business application", ["EBGN320", "EBGN315", "EBGN360"]),
            slot("focus-business-additional", "Two additional business core or application courses", ebgn_mix, 6),
        ]),
        prog("computer-engineering", "CS + Computer Engineering", [
            slot("focus-circuits", "Circuits", circuits),
            slot("focus-digital-logic", "Digital logic", ["EENG284", "PHGN317"], 4),
            ALL("focus-embedded", "Embedded systems", x.X(["EENG383"])),
            slot("focus-info-security", "Information processing and security",
                 ["CSCI471", "CSCI474", "CSCI475", "CSCI560", "CSCI574", "CSCI585", "EENG411", "EENG427"]),
            slot("focus-software", "Software for systems", ["CSCI403", "CSCI423", "CSCI425", "CSCI440", "CSCI581"]),
            slot("focus-hardware", "Hardware for systems",
                 ["CSCI410", "CSCI564", "CSCI565", "CSCI580", "CSCI582", "EENG350", "EENG423", "PHGN435"]),
            slot("focus-compe-elective", "Computer engineering elective",
                 ["CSCI423", "CSCI403", "CSCI410", "CSCI425", "CSCI437", "CSCI440", "CSCI507", "CSCI564", "CSCI565",
                  "CSCI572", "CSCI580", "CSCI581", "CSCI582", "EENG350", "EENG423", "EENG484", "MEGN441", "PHGN435"]),
            PICK("focus-free", "Additional free elective (1 credit)", 1),
        ]),
        prog("data-science", "CS + Data Science", [
            ALL("focus-data", "Required data and statistics courses",
                x.X(["CSCI403", "CSCI413", "CSCI470", "MATH201", "MATH324", "MATH335"])),
            slot("focus-advanced-statistics", "Advanced statistics",
                 ["MATH432", "MATH433", "MATH436", "MATH437", "MATH438", "MATH560"]),
            slot("focus-application", "Application or advanced data science",
                 ["CSCI404", "CSCI423", "CSCI474", "CSCI478", "CSCI575"]),
        ]),
        prog("entrepreneurship", "CS + Entrepreneurship and Innovation", [
            ALL("focus-entrepreneur", "Required entrepreneur and design courses", x.X(["EBGN320", "EBGN360", "CSCI460"])),
            slot("focus-business", "Business", ["EBGN201", "EBGN280", "EBGN305", "EBGN308", "EBGN453", "EBGN460"]),
            slot("focus-social", "Social and ethical impact",
                 ["EDNS315", "EDNS301", "EDNS401", "EDNS430", "EDNS450", "EDNS478", "EDNS515"]),
            slot("focus-front-end", "Front end application", ["CSCI422", "CSCI445", "CSCI446", "CSCI448"]),
            slot("focus-prototyping", "Prototyping", ["CSCI421", "EDNS301", "EDNS401", "EDNS445"]),  # CSCI460 is required here
            PICK("focus-cs-elective", "Additional CS elective", 3, [c for c in cs_pool if c not in set(CS_REQUIRED) | {"CSCI460"}]),
        ]),
        prog("robotics", "CS + Robotics and Intelligent Systems", [
            ALL("focus-robotics", "Required robotics courses", x.X(["CSCI404", "EENG307", "MEGN441"])),
            slot("focus-circuits", "Electrical circuits", circuits),
            slot("focus-perception", "Perception", ["CSCI437", "CSCI507", "EENG519"]),
            slot("focus-cognition", "Cognition", ["CSCI470", "CSCI534"]),
            slot("focus-interaction", "Interaction and society", ["CSCI432", "CSCI421", "CSCI436"]),
            slot("focus-additional", "Additional perception, cognition, interaction and society course",
                 ["CSCI421", "CSCI432", "CSCI436", "CSCI437", "CSCI507", "CSCI534", "EENG519", "MEGN544"]),
        ]),
        prog("space", "CS + Space", [
            slot("focus-circuits", "Electrical circuits", circuits),
            ALL("focus-space", "Required space courses", x.X(["MEGN452", "MEGN455", "MEGN456"])),
            slot("focus-logic", "Logic", ["CSCI410", "EENG284"]),
            slot("focus-control", "Control", ["EENG307", "EENG383"]),
            slot("focus-data", "Data", ["CSCI404", "CSCI413", "CSCI475"]),
            slot("focus-simulation", "Simulation", ["CSCI423", "CSCI440", "CSCI471"]),
        ]),
    ]


SPECS = [
    ("Computer Science", s_cs),
    ("Computer Science", s_cs_focus),
    ("Mining Engineering", s_mining),
    ("Applied Mathematics and Statistics", s_ams),
    ("Electrical Engineering", s_ee),
    ("Engineering Physics", s_engphys),
    ("Ceramic Engineering", s_ceramic),
    ("Metallurgical and Materials Engineering", s_mme),
    ("Geophysical Engineering", s_geophysics),
    ("Petroleum Engineering", s_petroleum),
    ("Civil Engineering", s_civil),
    ("Construction Engineering", s_construction),
    ("Environmental Engineering", s_environmental),
    ("Biochemistry", s_biochemistry),
    ("Quantum Systems Engineering", s_quantum),
    ("Mechanical Engineering", s_mechanical),
    ("Chemical Engineering", s_chemical),
    ("Design Engineering", s_design),
    ("Chemistry", s_chemistry),
    ("Geological Engineering", s_geological),
    ("Business Engineering and Management Science", s_bems),
    ("Quantitative Biosciences and Engineering", s_qbe),
]


# ---------------------------------------------------------------- build

def group_credits(courses, grp):
    if grp["kind"] in ("choose_credits", "requirement"):
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
            swapped = thorson(p["groups"])
            if swapped is None:
                review.append("- **%s**: no required group lists both HASS100 and EDNS151, so the Thorson substitution "
                              "was not applied." % p["name"])
            else:
                p = dict(p, groups=swapped)
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
