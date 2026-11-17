"""Turn the minors PDFs in data/Minors and ASIs into data/json/minors.json (format: docs/data-format.md).

Usage:  python -I data/tools/build_minors_json.py      (needs `pip install pypdf`)

Every minor's requirement groups are written by hand in SPECS below, from reading the PDF text.
Course lists are pulled from the PDF text (region()) or typed in (X()); X() refuses a code that is not in the PDF.
Pools like "any MNGN course" come from the course CSV (pool()).

Checks, written to data/json/minors.REVIEW.md:
  - codes the course CSV does not have
  - PDF course title vs CSV course title (stale or renamed courses)
  - requirement credits that do not add up to the program total
  - rules in the PDF text that the format cannot express (notes)
"""
import csv, glob, json, os, re
import pypdf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDFS = os.path.join(ROOT, "data", "Minors and ASIs")
CSV = os.path.join(ROOT, "data", "Academic Catalog", "mines-courses.csv")
OUT = os.path.join(ROOT, "data", "json")
YEAR = "2026-2027"
CODE = re.compile(r"^(or\s+)?([A-Z]{3,4})\s?(\d{3}[A-Z]?)\b\s*(.*)$")
CREDITS = re.compile(r"(\d{1,2}\.\d)\s*$")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_courses():
    with open(CSV, newline="", encoding="utf-8") as f:
        return {r["course_number"]: r for r in csv.DictReader(f)}


def cr(courses, code):
    """Credits from the CSV; for a range like '0-3' or '6-12' the upper bound (PDFs quote the usual amount)."""
    try:
        return float(re.split(r"[-\u2013]", courses[code]["credits"])[-1])
    except (KeyError, ValueError):
        return None


class Ctx:
    """Everything a spec needs for one PDF."""

    def __init__(self, name, courses, path=None):
        self.name, self.c = name, courses
        r = pypdf.PdfReader(path or os.path.join(PDFS, name + ".pdf"))
        self.text = "\n".join((p.extract_text() or "") for p in r.pages)
        self.lines = [l.strip() for l in self.text.splitlines() if l.strip()]
        self.flat = re.sub(r"\s+", "", self.text).upper()
        self.pdf_titles = {}
        self.notes = []

    def entries(self, lines):
        out, cur = [], None
        for l in lines:
            m = CODE.match(l)
            if m and m.group(2) != "ANY" and not l.upper().startswith("OR ELECT"):
                cur = {"code": m.group(2) + m.group(3), "alt": bool(m.group(1)), "text": m.group(4)}
                out.append(cur)
                if CREDITS.search(m.group(4)):
                    cur = None
            elif cur is not None and not CREDITS.fullmatch(l) and len(l) < 70 and l.upper() == l:
                cur["text"] += " " + l
            else:
                cur = None
        return out

    def region(self, start, end=None):
        """Codes listed between the first line matching `start` and the next line matching `end`."""
        i = next(k for k, l in enumerate(self.lines) if re.search(start, l, re.I))
        j = len(self.lines)
        if end:
            j = next((k for k in range(i + 1, len(self.lines)) if re.search(end, self.lines[k], re.I)), len(self.lines))
        out = []
        for e in self.entries(self.lines[i:j]):
            self.pdf_titles.setdefault(e["code"], re.sub(r"\s*\d{1,2}\.\d\s*$|\s*\d-\d\s*$", "", e["text"]))
            if e["code"] not in out:
                out.append(e["code"])
        return out

    def X(self, codes):
        """Typed-in list; every code must appear in the PDF text."""
        for c in codes:
            assert c in self.flat, "%s: %s not in the PDF text" % (self.name, c)
        return codes

    def pool(self, prefix, lo=0, hi=999):
        return sorted(c for c in self.c if re.fullmatch(prefix + r"\d{3}", c) and lo <= int(c[-3:]) <= hi)

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


def V(suffix, total, groups, label=None):
    return {"suffix": suffix, "label": label, "total": total, "groups": groups}


# ---------------------------------------------------------------- specs
def s_aerospace(x):
    return [V("", 18, [PICK("choose-six", "Choose 6 of the listed courses (not for Mechanical Engineering Aerospace Track students)", 18,
        x.X(["MEGN412", "MEGN416", "MEGN451", "MEGN461", "MEGN414", "MEGN423", "MEGN523", "MEGN452", "MEGN453",
             "MEGN454", "MEGN554", "MEGN455", "MEGN456", "MEGN553", "FEGN525"]))])]


def s_ams(x):
    extra = x.X(["CSCI303", "CSCI406", "CSCI441", "CSCI444", "CSCI470", "CSCI474"])
    return [V("", 18, [
        ALL("stats", "MATH201", ["MATH201"]),
        PICK("diff-eq", "MATH225 or MATH235 (honors)", 3, ["MATH225", "MATH235"]),
        PICK("lin-alg", "MATH332 or MATH342 (honors)", 3, ["MATH332", "MATH342"]),
        PICK("math-400", "At least 3 credits in a MATH course at the 400 level or above", 3, x.pool("MATH", 400)),
        PICK("math-300", "6 more credits: MATH courses at the 300 level or above, or the listed CSCI courses",
             6, x.pool("MATH", 300) + extra)])]


def s_biology(x):
    x.note("At least 9 credits must not double count with the major, other than free electives. Not open to QBE majors.")
    x.note("'BIOL 499 Research Project or Internship' is a variable-credit course.")
    return [V("", 18, [
        ALL("required", "CBEN110, CBEN120", x.X(["CBEN110", "CBEN120"])),
        PICK("electives", "10 credits of biology electives (special topics may be approved case by case)", 10,
             x.region(r"^ELECTIVE COURSES", None))])]


def s_biomech(x):
    x.note("Text says 'at least 11.0 credits' but also lists 7 required credits and 'three more courses'. Read as 7 required + at least 11 elective credits = 18, the university minimum. Confirm with the department.")
    x.note("MEGNX98/X99 special topics count if noted as relevant to the minor; not enumerable.")
    return [V("", 18, [
        ALL("required", "CBEN110, MEGN330", x.X(["CBEN110", "MEGN330"])),
        PICK("electives", "Electives from the list (at least 11 credits)", 11, x.region(r"^MEGN430", r"^\*\s*As the content"))])]


def s_bme(x):
    x.note("CBEN35X/45X/X98/X99 (undergraduate research, special topics, independent study) can count if noted as relevant; not enumerable.")
    eng = x.region(r"^BIOL300", r"^Plus at least 4 more")
    add = x.region(r"^CBEN304", r"^\*\s*As the content")
    return [V("", 18, [
        ALL("required", "CBEN110, CBEN120, CBEN310", x.X(["CBEN110", "CBEN120", "CBEN310"])),
        PICK("engineering-elective", "At least 3 credits of engineering electives related to BME", 3, eng),
        PICK("more-electives", "At least 4 more credits from the engineering and additional lists", 4, sorted(set(eng + add)))])]


def s_business(x):
    return [V("", 18, [
        ALL("required", "EBGN321", ["EBGN321"]),
        PICK("choose-five", "Select 5 of the listed EBGN courses", 15, x.region(r"^EBGN201", r"^At least 9 of"))])]


def s_chemistry(x):
    x.note("No fixed courses: students design the 18 credits with the Chemistry department. The Organic Chemistry sequence may exceed the 100-200-level limit. Modelled as any 18 credits.")
    return [V("", 18, [PICK("approved-sequence", "18 credits designed with and approved by the Chemistry department", 18)])]


def s_compeng(x):
    x.note("PHGN215 may replace EENG281/EENG282 and PHGN317 may replace EENG284, with program director pre-approval. At most 6 credits may count toward another minor. At least 9 credits at 300 level or above.")
    return [V("", 18, [PICK("choose-18", "At least 18 credits from the list", 18,
        x.X(["CSCI200", "CSCI210", "CSCI220", "CSCI341", "CSCI442", "EENG281", "EENG282", "EENG284", "EENG383"]))])]


def s_ccc(x):
    four = x.region(r"^400-level courses", r"^PRIMARY CONTACT")
    mid = x.region(r"^Midlevel courses", r"^400-level courses")
    return [V("", 18, [
        PICK("upper", "At least two 400-level courses", 6, four),
        PICK("rest", "12 more credits from the midlevel and 400-level lists, with an advisor", 12, mid + four)])]


def s_datascience(x):
    return [
        V("-option-1", 18, [
            ALL("core", "CSCI200, CSCI220, CSCI413, MATH201", x.X(["CSCI200", "CSCI220", "CSCI413", "MATH201"])),
            PICK("choose-two", "Choose 2 of CSCI403, CSCI404, CSCI470, CSCI478", 6, x.X(["CSCI403", "CSCI404", "CSCI470", "CSCI478"]))],
            "option 1"),
        V("-option-2", 18, [
            ALL("core", "CSCI200, CSCI220, CSCI413, MATH201, MATH334, MATH335",
                x.X(["CSCI200", "CSCI220", "CSCI413", "MATH201", "MATH334", "MATH335"]))], "option 2")]


def s_economics(x):
    return [V("", 18, [
        ALL("principles", "EBGN201", ["EBGN201"]),
        PICK("intermediate", "EBGN301 or EBGN302", 3, ["EBGN301", "EBGN302"]),
        PICK("electives", "Four more EBGN courses", 12, x.pool("EBGN", 100, 499))])]


def s_ee(x):
    pe = ["EENG281", "EENG282", "EENG307"]
    x.note("The PDF gives credit totals of 18 or 20 (ICE) and 19 or 21 (General) depending on EENG282 vs MEGN300 and EENG421 vs EENG423; the minimum is used. 'EENG281 & EENG282' is a single 4-credit unit in the catalog (3 + 1).")
    return [
        V("-iss-track", 18, [ALL("core", "Information Systems and Science track", x.X(pe + ["EENG284", "EENG310", "EENG311", "EENG391"]))],
          "Information Systems and Science (ISS) track"),
        V("-pes-track", 18, [ALL("core", "Power and Energy Systems track", x.X(pe + ["EENG385", "EENG386", "EENG389"]))],
          "Power and Energy Systems (PES) track"),
        V("-ice-track", 18, [
            ALL("core", "Integrated Circuits and Electronics track", x.X(["EENG281", "EENG307", "EENG284", "EENG383"])),
            PICK("lab", "EENG282, or MEGN300", 1, x.X(["EENG282", "MEGN300"])),
            PICK("device", "EENG421 or EENG423", 3, x.X(["EENG421", "EENG423"]))],
          "Integrated Circuits and Electronics (ICE) track"),
        V("-general-track", 19, [
            ALL("core", "General Electrical Engineering track", x.X(["EENG281", "EENG307", "EENG284", "EENG310", "EENG385", "EENG391"])),
            PICK("lab", "EENG282, or MEGN300", 1, x.X(["EENG282", "MEGN300"]))],
          "General Electrical Engineering track")]


def s_energy(x):
    x.note("The Director may approve other energy-related courses. ENGY497/ENGY498 are 1-6 credits; PEGN201 has no credit in the PDF.")
    return [V("", 18, [
        ALL("required", "EBGN330", ["EBGN330"]),
        PICK("policy", "At least one policy course: HASS490 or HASS491", 3, x.X(["HASS490", "HASS491"])),
        PICK("electives", "Remaining electives from the energy lists", 12,
             x.region(r"^Social Sciences and Law", r"^ENGY200\. INTRODUCTION"))])]


def s_engphys(x):
    x.note("This PDF contains both the Engineering Physics minor and the Physics minor (same page as the Physics PDF). Only the Engineering Physics block is built here.")
    return [V("", 18, [
        ALL("required", "PHGN200", ["PHGN200"]),
        PICK("modern-physics", "PHGN300 or PHGN310 (honors)", 3, x.X(["PHGN300", "PHGN310"])),
        PICK("electives", "Select at least 11 credits from the list", 11, x.region(r"^PHGN215", r"^Minor in Physics"))])]


def s_physics(x):
    x.note("The first block of this PDF is titled 'Minor in Engineering Physics'; it repeats the Engineering Physics minor. Only the second block (titled 'Minor in Physics') is built here.")
    return [V("", 18, [
        ALL("required", "PHGN200, MATH332, PHGN311", x.X(["PHGN200", "MATH332", "PHGN311"])),
        PICK("modern-physics", "PHGN300 or PHGN310 (honors)", 3, x.X(["PHGN300", "PHGN310"])),
        PICK("electives", "Select at least 5 credits from the list", 5, x.region(r"^PHGN320", r"^Primary Contact"))])]


def s_ess(x):
    hass = x.region(r"^HASS Courses", r"^Economics and Business Courses")
    other = x.region(r"^Economics and Business Courses", r"^Restricted environmental")
    stem = x.region(r"^Restricted environmental", r"^PRIMARY CONTACT")
    x.note("Five CAS courses: at least three must be HASS and at least one HASS course must be 400 level; up to two may be EBGN, EDNS, GEOC or PEGN. Modelled as 3 HASS courses plus 2 from any list; the 400-level rule is not enforceable here. Up to 3 credits of independent study with director approval.")
    return [V("", 18, [
        PICK("hass", "At least three HASS courses (one at 400 level)", 9, hass),
        PICK("cas-more", "Two more CAS courses from the HASS, EBGN, EDNS, GEOC and PEGN lists", 6, hass + other),
        PICK("stem", "One restricted environmental science and engineering elective", 3, stem)])]


def s_explosive(x):
    return [V("", 18, [
        ALL("required", "MNGN333, MNGN407, MNGN444", x.X(["MNGN333", "MNGN407", "MNGN444"])),
        PICK("electives", "At least three courses from the list", 9, x.region(r"^MNGN210", r"^Total Semester"))])]


def s_geoleng(x):
    x.note("No fixed courses: 18 credits in a logical sequence approved by the department before starting; may include GEGN101 (4 credits) and up to 4 credits at the 200 level. Modelled as any 18 credits.")
    return [V("", 18, [PICK("approved-sequence", "18 credits in a sequence approved by the Geology and Geological Engineering department", 18)])]


def s_gps(x):
    x.note("At least one elective must be 400 level. Foreign language (LIFL1XX) up to 6 hours: modelled with the numbered LIFL courses in the CSV.")
    elect = x.region(r"^HASS339", r"^PRIMARY CONTACT")
    lifl = [c for c in x.pool("LIFL", 100, 299) if not c.endswith(("98", "99"))]
    return [V("", 18, [
        PICK("required", "HASS460 or HASS344", 3, x.X(["HASS460", "HASS344"])),
        PICK("electives", "Remaining 15 credits from the elective lists", 15, elect + lifl)])]


def s_mcbride(x):
    x.note("21-credit minor (the university minimum is 18). Admission to the program is by application; GPA minimums 2.9 overall and 3.0 in Honors courses. HNRS405 is 1-3 credits (3 required).")
    return [V("", 21, [
        ALL("core", "HNRS305, HNRS315", x.X(["HNRS305", "HNRS315"])),
        PICK("practicum", "HNRS405 McBride Practicum (3 credits)", 3, ["HNRS405"]),
        PICK("electives", "12 credits of honors electives", 12,
             x.X(["HNRS425", "HNRS430", "HNRS435", "HNRS440", "HNRS445", "HNRS450", "HNRS398", "HNRS498", "HNRS499"]))])]


def s_humanitarian(x):
    x.note("The CAS elective list also allows any 400+ HNRS course (taken from the CSV) or a CAS course approved by the minor director; the elective list also allows a course approved by the director.")
    return [V("", 18, [
        ALL("introductory", "EDNS315, EDNS430, EDNS477, EDNS479", x.X(["EDNS315", "EDNS430", "EDNS477", "EDNS479"])),
        PICK("cas", "One CAS elective", 3, x.X(["HASS419", "HASS425", "HASS427", "HASS468", "HASS490"]) + x.pool("HNRS", 400)),
        PICK("elective", "One elective from the list", 3, x.region(r"^EDNS401", r"^OR A COURSE APPROVED"))])]


def s_hass(x):
    x.note("Individualized minor: 18 HASS credits chosen with a HASS faculty member who approves a coherent rationale. Modelled as any 18 credits from numbered HASS courses.")
    return [V("", 18, [PICK("approved-rationale", "18 restricted-elective HASS credits approved by a HASS faculty advisor", 18, x.pool("HASS", 100, 499))])]


def s_megn(x):
    base = PICK("required", "Choose three of MEGN212, MEGN261, MEGN315, MEGN351", 9, x.X(["MEGN212", "MEGN261", "MEGN315", "MEGN351"]))
    return [
        V("-robotics-automation-design-track", 18, [base,
            ALL("track", "MEGN324, MEGN441", x.X(["MEGN324", "MEGN441"])),
            PICK("track-choice", "MEGN481, or MEGN416, or MEGN485", 3, x.X(["MEGN481", "MEGN416", "MEGN485"]))],
          "Robotics, Automation and Design track"),
        V("-solid-materials-track", 18, [base,
            ALL("track", "MEGN324, MEGN412", x.X(["MEGN324", "MEGN412"])),
            PICK("track-choice", "MEGN416 or MEGN481", 3, x.X(["MEGN416", "MEGN481"]))],
          "Solid Materials track"),
        V("-thermal-fluids-track", 18, [base,
            ALL("track", "MEGN451, MEGN461, MEGN471", x.X(["MEGN451", "MEGN461", "MEGN471"]))],
          "Thermal-Fluids track")]


def s_metmat(x):
    x.note("A 'logical sequence'; the PDF only recommends courses (MTGN202, MTGN211, MTGN348, MTGN348L, MTGN445, MTGN445L plus 4 credits at 300/400 level) and allows other sequences approved by the department head. Modelled as 18 credits from MTGN courses so the recommended sequence passes. Not open to MME majors. The minor declaration must be filed before half the credits are done.")
    return [V("", 18, [PICK("sequence", "18 credits of MTGN courses in a logical sequence (recommended list in the catalog)", 18,
        sorted(set(x.pool("MTGN", 100, 499) + x.X(["MTGN348L", "MTGN445L"]))))])]


def s_mpem(x):
    return [V("", 18, [
        ALL("required", "MNGN210, MNGN322, MNGN323", x.X(["MNGN210", "MNGN322", "MNGN323"])),
        PICK("electives", "At least three courses from the list", 9, x.region(r"^MNGN426", r"^Total Required"))])]


def s_mining(x):
    return [V("", 18, [
        ALL("required", "MNGN210", ["MNGN210"]),
        PICK("select-two", "Select two of MNGN312, MNGN314, MNGN316", 6, x.X(["MNGN312", "MNGN314", "MNGN316"])),
        PICK("other-mining", "Other mining engineering courses (list kept by the department office)", 9, x.pool("MNGN", 100, 499))])]


def s_music(x):
    x.note("Resolved: the PDF's LAIS422 is read as HASS429 Real World Recording/Research (the CSV lists HASS429 as equivalent to LAIS429, and the student registration portal shows a single 'Real World Recording' course, spring only). See data/CONFLICT-LOG.md.")
    return [V("", 18, [
        ALL("required", "Audio/acoustical engineering, music technology, western music traditions, music technology capstone",
            ["HASS324", "HASS327", "HASS315", "HASS330"]),
        PICK("recording-seminar", "One 400-level required course (PDF says LAIS422 Real World Recording Seminar; resolved to HASS429, see CONFLICT-LOG)", 3, ["HASS429"]),
        PICK("additional", "3 more credits: HASS326 Music Theory or Performance Enhancement", 3, ["HASS326"])])]


def s_or(x):
    det = x.region(r"^Deterministic Modeling", r"^Stochastic Modeling")
    sto = x.region(r"^Stochastic Modeling", r"^\*\s*Students can take")
    sur = x.region(r"^Survey Course", None)
    x.note("Only 3 credits may come from the student's own degree department; at most one survey course; CSCI423 and EBGN528 cannot both count. Not enforceable in this format.")
    return [V("", 18, [
        PICK("deterministic", "At least one deterministic modeling course", 3, det),
        PICK("stochastic", "At least one stochastic modeling course", 3, sto),
        PICK("remaining", "12 more credits from any of the three lists (at most one survey course)", 12, det + sto + sur)])]


def s_pda(x):
    x.note("Prerequisites before starting: MATH112 or MATH122, and EBGN201. The text says 'Seven courses (18 credits)' but lists only six courses (five required + one technical elective = 18 credits). Six used.")
    return [V("", 18, [
        ALL("required", "MATH201, CSCI128, CSCI303, PEGN440, PEGN438", x.X(["MATH201", "CSCI128", "CSCI303", "PEGN440", "PEGN438"])),
        PICK("technical-elective", "One 3-credit technical elective", 3, x.X(["EBGN461", "GEGN475", "MATH334"]))])]


def s_peen(x):
    return [V("", 18, [
        ALL("required", "PEGN201, PEGN308", x.X(["PEGN201", "PEGN308"])),
        PICK("pegn", "12 more credits of PEGN courses (sequence approved by the department)", 12, x.pool("PEGN", 100, 499))])]


def s_quantum(x):
    x.note("The PDF lists CSCI481 and EENG432 (with CSCI581 and EENG532); the course CSV has only the 500-level versions.")
    core = ["CSCI481", "CSCI581", "EENG432", "EENG532", "PHGN441", "PHGN435", "PHGN417", "PHGN519"]
    extra = x.region(r"^PHGN440", None)
    if "EENG428" in extra and "EENG430" not in extra:
        extra.append("EENG430")
    return [V("", 18, [
        PICK("linear-algebra", "MATH342 (honors) or MATH332", 3, x.X(["MATH342", "MATH332"])),
        PICK("core-three", "Three of the quantum core courses", 9, x.X(core)),
        PICK("specialization", "Two more courses from the core or the specialization list", 6, sorted(set(core + extra)))])]


def s_robotics(x):
    return [V("", 18, [
        ALL("core", "CSCI200, CSCI220, MATH334, MEGN441", x.X(["CSCI200", "CSCI220", "MATH334", "MEGN441"])),
        PICK("ai-vision-ml", "one of CSCI404, CSCI437, CSCI470", 3, x.X(["CSCI404", "CSCI437", "CSCI470"])),
        PICK("robot-programming", "one of CSCI473, CSCI436, CSCI534", 3, x.X(["CSCI473", "CSCI436", "CSCI534"]))])]


def s_space(x):
    x.note("SPRS401 (Space Resources Fundamentals) is required but is not in the course CSV; the CSV has SPRS501 with the same title, so 401 is probably the undergraduate number of SPRS501.")
    return [V("", 18, [
        ALL("required", "MNGN210, GEOL410, SPRS401", x.X(["MNGN210", "GEOL410", "SPRS401"])),
        PICK("electives", "At least three courses from the list", 9, x.region(r"^EBGN310", r"^Primary Contact"))])]


def s_structural(x):
    x.note("Civil Engineering majors cannot double count CEEN314 or CEEN443/CEEN445, so they must take the other six listed courses; at most three may double count as free electives.")
    return [V("", 18, [
        ALL("required", "CEEN314", ["CEEN314"]),
        PICK("electives", "Select five of the seven listed courses", 15, x.region(r"^CEEN406", r"^In order to ensure"))])]


def s_teaching(x):
    t, a, c = ["SCED262", "SCED333", "SCED363"], ["SCED464", "MAED464", "CSED464"], ["SCED465", "MAED465", "CSED465"]
    pr = x.X(["MAED405", "SCED415", "CSED430"])
    te = x.X(["SCED445", "MAED425", "CSED435"])
    x.note("Credits: the CSV gives SCED262 as 1-3 and SCED465/MAED465/CSED465 as 6-12; the PDF says 3 and 6.")
    x.note("The PDF titles the capstone courses 'Capstone Curriculum Design I/II'; the course CSV titles SCED464/CSED465 as student-teaching courses. Titles differ for the same codes.")
    return [
        V("", 18, [ALL("required", "SCED262, SCED333, SCED363", x.X(t)), PICK("capstone", "One of SCED464, MAED464, CSED464", 3, x.X(a)),
                   PICK("practices", "One practices course", 3, pr), PICK("techniques", "One teaching techniques course", 3, te)]),
        V("-with-licensure", 24, [ALL("required", "SCED262, SCED333, SCED363", t), PICK("capstone-1", "One of SCED464, MAED464, CSED464", 3, a),
                                  PICK("capstone-2", "One of SCED465, MAED465, CSED465 (6 credits)", 6, x.X(c)),
                                  PICK("practices", "One practices course", 3, pr), PICK("techniques", "One teaching techniques course", 3, te)],
          "with Licensure")]


def s_uct(x):
    x.note("Variable-credit independent studies (CEEN499, GEGN499, MNGN499) may count; additional courses by petition (takes one month).")
    return [V("", 18, [
        ALL("required", "CEEN312, MNGN321, MNGN404", x.X(["CEEN312", "MNGN321", "MNGN404"])),
        PICK("electives", "9 credits from the elective list", 9, x.region(r"^CEEN314", r"^Program Director"))])]


def s_water(x):
    x.note("The PDF says 'Select two of the following six courses' but lists only five (CEEN472, CEEN475, CEEN478, CEEN480, CEEN482). Five used.")
    return [V("", 18, [
        ALL("required", "CEEN301, CEEN310, CEEN381, CEEN470", x.X(["CEEN301", "CEEN310", "CEEN381", "CEEN470"])),
        PICK("electives", "Two of the listed elective courses", 6, x.region(r"^CEEN472", r"^Civil Engineering and Environmental"))])]


def s_cs(x):
    pool = x.pool("CSCI", 400) + ["MATH307", "EENG383"]
    return [V("", 18, [
        ALL("core", "CSCI200, CSCI210, CSCI220", ["CSCI200", "CSCI210", "CSCI220"]),
        PICK("discrete-or-probability", "CSCI358 or MATH334", 3, ["CSCI358", "MATH334"]),
        PICK("software-eng-or-elective", "CSCI306, or a CSCI elective", 3, ["CSCI306"] + pool),
        PICK("csci-elective", "CSCI elective: any 400/500-level CSCI course, MATH307, or EENG383", 3, pool)])]


def s_geophysics(x):
    return [V("", 18, [
        ALL("core", "GPGN229, GPGN328, GPGN329, GPGN318, GPGN319", ["GPGN229", "GPGN328", "GPGN329", "GPGN318", "GPGN319"]),
        PICK("approved-elective", "3 credits in geophysics, geology, math or computer science; the Geophysics department must approve it", 3)])]



# ---------------------------------------------------------------- ASIs (2025-2026 catalog pages)
ASI_PDF = os.path.join(PDFS, "ASIs (2025-2026 catalog, extracted pages).pdf")
ASI_YEAR = "2025-2026"


def a_civil(x):
    x.note("Civil Engineering majors cannot earn this ASI. Environmental Engineering majors must take CEEN312, CEEN314, CEEN331 and CEEN360, and at most three of them may double count as free electives. Not enforceable in this format.")
    return [V("", 12, [ALL("required", "CEEN312, CEEN314", x.X(["CEEN312", "CEEN314"])),
                       PICK("electives", "Select two of CEEN301, CEEN331, CEEN360, CEEN381", 6, x.X(["CEEN301", "CEEN331", "CEEN360", "CEEN381"]))])]


def a_enveng(x):
    x.note("Environmental Engineering majors cannot earn this ASI. Civil Engineering majors must take all five courses (15 credits) and only two may double count toward the major.")
    return [V("", 12, [PICK("four-of-five", "Complete 4 of the 5 listed courses", 12, x.X(["CEEN301", "CEEN302", "CEEN381", "CEEN470", "CEEN480"]))])]


def a_econ(x):
    return [V("", 12, [ALL("principles", "EBGN201", ["EBGN201"]),
                       PICK("electives", "Three other EBGN courses (not usable toward the degree except as free electives)", 9, x.pool("EBGN", 100, 499))])]


def a_entre(x):
    return [V("", 12, [ALL("required", "EBGN201, EBGN360, EBGN460", x.X(["EBGN201", "EBGN360", "EBGN460"])),
                       PICK("one-more", "One of EBGN280, EBGN304, EBGN321, EBGN345, EBGN346, EBGN485", 3,
                            x.X(["EBGN280", "EBGN304", "EBGN321", "EBGN345", "EBGN346", "EBGN485"]))])]


def a_humeng(x):
    return [V("", 12, [ALL("intro", "EDNS315", ["EDNS315"]),
                       PICK("one-of", "One of EDNS301, EDNS401, EDNS430", 3, x.X(["EDNS301", "EDNS401", "EDNS430"])),
                       PICK("two-of", "Two of EDNS477, EDNS478, EDNS479, EDNS480, HASS425, CEEN493", 6,
                            x.X(["EDNS477", "EDNS478", "EDNS479", "EDNS480", "HASS425", "CEEN493"]))])]


def a_eeng(x):
    return [V("", 12, [PICK("circuits", "EENG281 or PHGN215", 3, x.X(["EENG281", "PHGN215"])),
                       ALL("controls", "EENG307", ["EENG307"]),
                       PICK("eeng-electives", "6 credits of any EENG course at the 300 or 400 level", 6, x.pool("EENG", 300, 499))])]


def a_aero(x):
    return [V("", 12, [PICK("choose-12", "At least 12 credits from MEGN451, MEGN471, MEGN414, MEGN453", 12, x.X(["MEGN451", "MEGN471", "MEGN414", "MEGN453"]))])]


def a_meng(x):
    return [V("", 12, [ALL("required", "MEGN212, MEGN261, MEGN315, MEGN351", x.X(["MEGN212", "MEGN261", "MEGN315", "MEGN351"]))])]


def a_additive(x):
    return [V("", 12, [ALL("required", "AMFG401", x.X(["AMFG401"])),
                       PICK("electives", "9 credits of electives from Table 1 (AMFG531, AMFG511, FEGN526 need program director approval)", 9,
                            x.X(["MEGN381", "MEGN412", "AMFG421", "AMFG531", "AMFG498", "AMFG511", "FEGN525", "FEGN526"]))])]


def a_energy(x):
    x.note("'Two additional energy-related courses' is not defined in the text; modelled with the Energy minor's elective lists on the same page.")
    pool = x.region(r"^Social Sciences and Law", r"^Area of Special Interest in Energy")
    return [V("", 12, [ALL("required", "ENGY200, EBGN330", x.X(["ENGY200", "EBGN330"])),
                       PICK("energy-courses", "Two additional energy-related courses", 6, pool)])]


def a_spse(x):
    x.note("Up to 3 credits at the 200 level or below and up to 3 credits may overlap with the degree. Enrollment approved by the program director; courses not on the list may be approved by the SPSE ASI advisor.")
    return [V("", 12, [PICK("approved-courses", "12 credits from the SPSE-approved list (or other courses approved by the SPSE ASI advisor)", 12,
        x.X(["EDNS251", "EDNS491", "EDNS492", "GEGN469", "GEOL410", "GPGN438", "GPGN470", "PHGN418", "PHGN324", "PHGN423",
             "PHGN471", "PHGN481", "PHGN472", "PHGN482", "MEGN451", "MEGN453", "MEGN454", "MEGN452", "MEGN456", "MEGN455"]))])]


def a_uct(x):
    return [V("", 12, [ALL("required", "CEEN312, MNGN321, MNGN404", x.X(["CEEN312", "MNGN321", "MNGN404"])),
                       PICK("elective", "One elective course from the minor's elective list", 3, x.region(r"^CEEN314", r"^Program Requirements"))])]


def a_geol(x):
    x.note("Same rule as the Geological Engineering minor: a logical sequence approved by the department before starting; may include GEGN101 (4 credits) and up to 4 credits at the 200 level.")
    return [V("", 12, [PICK("approved-sequence", "12 credits in a sequence approved by the Geology and Geological Engineering department", 12)])]


def a_chem(x):
    x.note("The catalog names four ASIs (Chemistry, Polymer Chemistry, Environmental Chemistry, Biochemistry) but gives no course sequences; students design them with the Chemistry department.")
    return [V("", 12, [PICK("approved-sequence", "12 credits designed with and approved by the Chemistry department", 12)])]


def a_music(x):
    x.note("The catalog text names the ASI and its advisor (Prof. Bob Klimek) but lists no courses. Course codes in the Music Technology minor were renamed from LAIS to HASS.")
    return [V("", 12, [PICK("approved-sequence", "12 credits of music technology courses; course list not published, confirm with the program advisor", 12)])]


ASI_SPECS = [
    ("Civil Engineering", a_civil), ("Environmental Engineering", a_enveng), ("Economics", a_econ),
    ("Entrepreneurship", a_entre), ("Humanitarian Engineering", a_humeng), ("Electrical Engineering", a_eeng),
    ("Aerospace Engineering", a_aero), ("Mechanical Engineering", a_meng), ("Additive Manufacturing", a_additive),
    ("Energy", a_energy), ("Space and Planetary Science and Engineering", a_spse),
    ("Underground Construction and Tunneling", a_uct), ("Geological Engineering", a_geol),
    ("Chemistry", a_chem), ("Polymer Chemistry", a_chem), ("Environmental Chemistry", a_chem), ("Biochemistry", a_chem),
    ("Music Technology", a_music),
]

SPECS = {
    "Aerospace Engineering": s_aerospace, "Applied Mathematics and Statistics (AMS)": s_ams, "Biology": s_biology,
    "Biomechanical Engineering": s_biomech, "Biomedical Engineering (BME)": s_bme, "Business": s_business,
    "Chemistry": s_chemistry, "Computer Engineering": s_compeng, "Computer Science": s_cs,
    "Culture, Creativity, and Communication": s_ccc, "Data Science": s_datascience, "Economics": s_economics,
    "Electrical Engineering": s_ee, "Energy": s_energy, "Engineering Physics": s_engphys,
    "Environment and Sustainability Studies": s_ess, "Explosive Engineering": s_explosive,
    "Geological Engineering": s_geoleng, "Geophysics-Geophysical Engineering": s_geophysics,
    "Global Politics and Society": s_gps, "Guy T. McBride, Jr. Honors Program in Public Affairs": s_mcbride,
    "Humanitarian Engineering": s_humanitarian, "Humanities, Arts, and Social Science": s_hass,
    "Mechanical Engineering": s_megn, "Metallurgical and Materials Engineering": s_metmat,
    "Mineral Processing & Extractive Metallurgy (MPEM)": s_mpem, "Mining Engineering": s_mining,
    "Music, Audio Engineering, and the Recording Arts": s_music, "Operations Research": s_or,
    "Petroleum Data Analytics": s_pda, "Petroleum Engineering": s_peen, "Physics": s_physics,
    "Quantum Engineering": s_quantum, "Robotics and Intelligent Systems": s_robotics, "Space Mining": s_space,
    "Structural Engineering": s_structural, "Teaching": s_teaching, "Underground Construction and Tunneling": s_uct,
    "Water Sustainability": s_water,
}

# Official minor names where the PDF file name differs.
DISPLAY = {"Geophysics-Geophysical Engineering": "Geophysics/Geophysical Engineering",
           "Humanities, Arts, and Social Science": "Individualized Minor in Humanities, Arts, and Social Sciences"}


def words(s):
    return set(re.findall(r"[A-Z0-9]+", s.upper())) - {"AND", "OF", "THE", "TO", "FOR", "IN", "A", "OR"}


def main():
    courses = load_courses()
    programs, review = [], []
    files = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(PDFS, "*.pdf")))
    files = [f for f in files if not f.startswith(("General", "ASIs"))]
    for f in files:
        if f not in SPECS:
            review.append("- **%s**: NO SPEC, not built." % f)
            continue
        x = Ctx(f, courses)
        for v in SPECS[f](x):
            base = DISPLAY.get(f, f)
            if not v["label"]:
                name = "Minor in " + base
            elif v["label"] == "with Licensure":
                name = "Minor in %s with Licensure" % base
            else:
                name = "Minor in %s (%s)" % (base, v["label"])
            if base.startswith("Individualized"):
                name = base
            programs.append({
                "program_id": slug(base) + ("" if base.startswith("Individualized") else "-minor") + v["suffix"],
                "name": name, "degree_level": "minor", "catalog_year": YEAR,
                "total_credits_required": v["total"], "requirement_groups": v["groups"]})
            s = 0.0
            for gr in v["groups"]:
                s += sum(cr(courses, c) or 0 for c in gr["courses"]) if gr["kind"] == "all" else gr["credits_required"]
            if abs(s - v["total"]) > 0.01:
                review.append("- **%s**: required credits add up to %g but the total is %g (course credits come from the CSV)." % (name, s, v["total"]))
            for gr in v["groups"]:
                miss = sorted({c for c in gr.get("courses", []) if c not in courses})
                if miss:
                    review.append("- **%s**, group `%s`: not in the course CSV: %s" % (name, gr["group_id"], ", ".join(miss)))
        for code, t in x.pdf_titles.items():
            if code in courses:
                a, b = words(t), words(courses[code]["course_name"])
                if a and len(a & b) / len(a) < 0.5:
                    review.append("- **%s**, title differs: %s: PDF '%s' vs CSV '%s'" % (f, code, t.strip(), courses[code]["course_name"]))
        for n in x.notes:
            review.append("- **%s**, note: %s" % (f, n))
    asis = []
    ax = Ctx("ASIs", courses, ASI_PDF)
    for nm, fn in ASI_SPECS:
        ax.notes = []
        ax.pdf_titles = {}
        v = fn(ax)[0]
        asis.append({"program_id": slug(nm) + "-asi", "name": "Area of Special Interest in " + nm, "degree_level": "asi",
                     "catalog_year": ASI_YEAR, "total_credits_required": v["total"], "requirement_groups": v["groups"]})
        s = sum(sum(cr(courses, c) or 0 for c in gr["courses"]) if gr["kind"] == "all" else gr["credits_required"] for gr in v["groups"])
        if abs(s - v["total"]) > 0.01:
            review.append("- **ASI %s**: required credits add up to %g but the total is %g." % (nm, s, v["total"]))
        for gr in v["groups"]:
            miss = sorted({c for c in gr.get("courses", []) if c not in courses})
            if miss:
                review.append("- **ASI %s**, group `%s`: not in the 2026-2027 course CSV (probably renumbered or dropped since 2025-2026): %s" % (nm, gr["group_id"], ", ".join(miss)))
        for n in ax.notes:
            review.append("- **ASI %s**, note: %s" % (nm, n))
    ids = [p["program_id"] for p in programs]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    with open(os.path.join(OUT, "minors.json"), "w", encoding="utf-8") as fh:
        json.dump({"programs": programs}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(OUT, "asis.json"), "w", encoding="utf-8") as fh:
        json.dump({"programs": asis}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(os.path.join(OUT, "minors.REVIEW.md"), "w", encoding="utf-8") as fh:
        fh.write("# Minors: conflicts, gaps and notes\n\nGenerated by data/tools/build_minors_json.py. Items here are things in the catalog PDFs "
                 "that disagree with each other or with the course CSV, or rules the data format cannot express. How each conflict was resolved, and the rules used, are in data/CONFLICT-LOG.md.\n\n" + "\n".join(review) + "\n")
    print(len(programs), "programs from", len(files), "PDFs;", len(review), "review items")


if __name__ == "__main__":
    main()
