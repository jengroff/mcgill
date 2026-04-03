"""BeautifulSoup HTML parsing for McGill course pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from backend.models.course import CourseCreate

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


def parse_program_page(html: str) -> tuple[str, str]:
    """Extract title and text content from a program guide page.

    Returns (title, content) where content is the full page text
    suitable for chunking and embedding.  Preserves section headings
    as markdown markers and converts HTML tables to markdown tables
    so downstream consumers can distinguish "Required Courses" from
    "Complementary Courses", etc.
    """
    soup = BeautifulSoup(html, "html.parser")
    area = soup.find("div", id="contentarea") or soup.find("main") or soup.body
    if not area:
        return "", ""

    h1 = area.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Walk top-level elements preserving structure
    blocks: list[str] = []
    seen_tables: set[int] = set()  # avoid duplicating nested tables

    for el in area.find_all(["h2", "h3", "h4", "p", "li", "table"]):
        if el.name == "table":
            tid = id(el)
            if tid in seen_tables:
                continue
            seen_tables.add(tid)
            md = _table_to_markdown(el)
            if md:
                blocks.append(md)
        elif el.name in ("h2", "h3", "h4"):
            prefix = {"h2": "## ", "h3": "### ", "h4": "#### "}[el.name]
            text = el.get_text(strip=True)
            if text:
                blocks.append(f"{prefix}{text}")
        else:
            # Skip content that is already inside a table cell
            if el.find_parent("table"):
                continue
            text = el.get_text(strip=True)
            if len(text) > 20:
                blocks.append(text)

    content = "\n".join(blocks)
    return title, content


def _table_to_markdown(table) -> str:
    """Convert a BeautifulSoup <table> element to a markdown table string."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    md_rows: list[list[str]] = []
    for tr in rows:
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row = [c.get_text(strip=True).replace("|", "/") for c in cells]
        # Skip rows that are just expanded course descriptions (single wide cell)
        if len(row) == 1 and len(md_rows) > 0 and len(md_rows[0]) > 1:
            continue
        md_rows.append(row)

    if not md_rows:
        return ""

    # Normalize column count to the header row width
    ncols = len(md_rows[0])
    lines: list[str] = []
    for i, row in enumerate(md_rows):
        # Pad or truncate to match header width
        padded = (row + [""] * ncols)[:ncols]
        lines.append("| " + " | ".join(padded) + " |")
        if i == 0:
            lines.append("| " + " | ".join("---" for _ in range(ncols)) + " |")

    return "\n".join(lines)


def discover_sub_pages(html: str, parent_path: str) -> list[str]:
    """Find child program page links within a scraped program page.

    Returns paths that are direct children of ``parent_path`` (i.e. the href
    starts with the parent path and goes one level deeper).  This lets the
    scraper follow department → sub-program links automatically.
    """
    soup = BeautifulSoup(html, "html.parser")
    area = soup.find("div", id="contentarea") or soup.find("main") or soup.body
    if not area:
        return []

    # Normalise parent to ensure trailing slash
    prefix = parent_path.rstrip("/") + "/"
    found: list[str] = []
    for a in area.find_all("a", href=True):
        href: str = a["href"]
        # Only internal relative links that extend the parent path
        if href.startswith(prefix) and href != prefix:
            # Normalise to path with trailing slash
            clean = href.rstrip("/") + "/"
            if clean not in found:
                found.append(clean)
    return found


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
