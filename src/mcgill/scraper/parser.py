"""BeautifulSoup HTML parsing for McGill course pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from mcgill.models.course import CourseCreate

BASE_URL = "https://coursecatalogue.mcgill.ca"

_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b")


def parse_course(slug: str, html: str, faculty_names: list[str]) -> CourseCreate | None:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", id="contentarea") or soup.find("main") or soup.body
    if not content:
        return None

    h1 = content.find("h1")
    if not h1:
        return None

    raw = h1.get_text(strip=True)
    m = re.match(r"^([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)[.\s]+(.+?)[.\s]*$", raw)
    if not m:
        return None

    dept, number, title = m.group(1), m.group(2), m.group(3).strip().rstrip(".")

    credits = None
    faculty_str = faculty_names[0] if faculty_names else ""
    terms: list[str] = []
    prereq = restrict = notes = ""

    for el in content.find_all(["p", "li"]):
        t = el.get_text(strip=True)
        if t.startswith("Credits:"):
            try:
                credits = float(t.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif t.startswith("Offered by:"):
            faculty_str = t.split(":", 1)[1].strip()
        elif t.startswith("Terms offered:"):
            terms = list(dict.fromkeys(re.findall(r"\b(Fall|Winter|Summer)\b", t)))
        elif re.match(r"(Pre|Co)requisite", t):
            prereq = t
        elif t.startswith("Restriction"):
            restrict = t
        elif t.startswith("Note"):
            notes = t

    dh = content.find(re.compile(r"^h[23]$"), string=re.compile("Description", re.I))
    if dh and (nxt := dh.find_next_sibling()):
        description = nxt.get_text(strip=True)
    else:
        skip = re.compile(r"^(Credits|Offered|Terms|Pre|Co|Restric|Note)")
        paras = [
            p.get_text(strip=True)
            for p in content.find_all("p")
            if len(p.get_text(strip=True)) > 60
            and not skip.match(p.get_text(strip=True))
        ]
        description = max(paras, key=len) if paras else ""

    return CourseCreate(
        code=f"{dept} {number}",
        slug=slug,
        title=title,
        dept=dept,
        number=number,
        credits=credits,
        faculty=faculty_str,
        faculties=list(faculty_names),
        terms=terms,
        description=description,
        prerequisites_raw=prereq,
        restrictions_raw=restrict,
        notes_raw=notes,
        url=f"{BASE_URL}/courses/{slug}/index.html",
    )


def extract_variants(html: str, known_codes: set[str]) -> dict[str, list[str]]:
    ctx_re = re.compile(
        r"(?:completed?|take|must take|including|one of|two of|three of|"
        r"or equivalent|or permission|prerequisites?(?:\s*:)|"
        r"corequisites?(?:\s*:)|required course)[^.;\n]{0,200}",
        re.IGNORECASE,
    )
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", id="contentarea") or soup.body or soup
    text = content.get_text(separator=" ")
    out: dict[str, list[str]] = {}
    for ctx in ctx_re.findall(text):
        ctx_c = " ".join(ctx.split())
        for mc in _CODE_RE.finditer(ctx_c):
            code = f"{mc.group(1)} {mc.group(2)}"
            if code in known_codes:
                out.setdefault(code, []).append(ctx_c[:200])
    return out
