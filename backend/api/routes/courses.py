"""Course browsing and detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["Courses"])


@router.get("/departments/{code}/courses")
async def list_department_courses(code: str):
    from backend.db.postgres import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT code, slug, title, dept, number, credits, faculty, terms, description
               FROM courses WHERE dept = $1 ORDER BY number""",
            code.upper(),
        )
    return [dict(r) for r in rows]


@router.get("/courses")
async def list_courses(
    dept: str | None = None,
    faculty: str | None = None,
    term: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    from backend.db.postgres import get_pool

    pool = await get_pool()

    conditions = []
    params = []
    idx = 1

    if dept:
        conditions.append(f"dept = ${idx}")
        params.append(dept.upper())
        idx += 1
    if faculty:
        conditions.append(f"faculty ILIKE ${idx}")
        params.append(f"%{faculty}%")
        idx += 1
    if term:
        conditions.append(f"${idx} = ANY(terms)")
        params.append(term)
        idx += 1
    if q:
        conditions.append(f"tsv @@ websearch_to_tsquery('english', ${idx})")
        params.append(q)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT count(*) FROM courses {where}", *params)
        rows = await conn.fetch(
            f"""SELECT code, slug, title, dept, number, credits, faculty, terms, description
                FROM courses {where}
                ORDER BY dept, number
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params,
            limit,
            offset,
        )

    return {"total": total, "courses": [dict(r) for r in rows]}


@router.get("/courses/{code}")
async def get_course(code: str):
    from backend.db.postgres import get_pool

    pool = await get_pool()

    # Normalize code: "COMP-250" or "comp250" → "COMP 250"
    import re

    code = code.upper().replace("-", " ")
    m = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if m:
        code = f"{m.group(1)} {m.group(2)}"

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM courses WHERE code = $1", code)

    if not row:
        raise HTTPException(status_code=404, detail="Course not found")

    course = dict(row)

    # Fetch resolved prerequisites from Neo4j
    try:
        from backend.db.neo4j import run_query

        prereqs = await run_query(
            "MATCH (c:Course {code: $code})-[:PREREQUISITE_OF]->(p:Course) RETURN p.code AS code, p.title AS title",
            {"code": code},
        )
        coreqs = await run_query(
            "MATCH (c:Course {code: $code})-[:COREQUISITE_OF]->(p:Course) RETURN p.code AS code, p.title AS title",
            {"code": code},
        )
        restrictions = await run_query(
            "MATCH (c:Course {code: $code})-[:RESTRICTED_WITH]->(p:Course) RETURN p.code AS code, p.title AS title",
            {"code": code},
        )
        course["prerequisites"] = [r["code"] for r in prereqs]
        course["corequisites"] = [r["code"] for r in coreqs]
        course["restrictions"] = [r["code"] for r in restrictions]
    except Exception:
        course["prerequisites"] = []
        course["corequisites"] = []
        course["restrictions"] = []

    return course


@router.get("/graph/prereqs/{code}")
async def get_prerequisite_tree(code: str, depth: int = Query(default=3, le=5)):
    """Get the prerequisite chain tree for a course."""
    from backend.db.neo4j import run_query
    import re

    code = code.upper().replace("-", " ")
    m = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if m:
        code = f"{m.group(1)} {m.group(2)}"

    result = await run_query(
        """MATCH path = (c:Course {code: $code})-[:PREREQUISITE_OF*1..%d]->(p:Course)
           RETURN [n IN nodes(path) | {code: n.code, title: n.title}] AS chain"""
        % depth,
        {"code": code},
    )
    return {"code": code, "chains": [r["chain"] for r in result]}


@router.get("/graph/tree/{code}")
async def get_prerequisite_tree_graph(code: str):
    import re

    code = code.upper().replace("-", " ")
    m = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if m:
        code = f"{m.group(1)} {m.group(2)}"

    from backend.db.neo4j import run_query

    # Query 1: all nodes reachable from root, with shortest-path depth.
    # min(length(path)) handles nodes reachable via multiple paths.
    node_rows = await run_query(
        """
        MATCH path = (root:Course {code: $code})-[:PREREQUISITE_OF*0..4]->(n:Course)
        RETURN DISTINCT n.code AS code, n.title AS title, n.credits AS credits,
               min(length(path)) AS depth
        """,
        {"code": code},
    )

    if not node_rows:
        return {"root": code, "nodes": [], "edges": []}

    codes = [r["code"] for r in node_rows]

    # Query 2: all PREREQUISITE_OF edges where both endpoints are in the node set.
    # Pass codes as a parameter — do not interpolate into the query string.
    prereq_edges = await run_query(
        """
        MATCH (src:Course)-[:PREREQUISITE_OF]->(tgt:Course)
        WHERE src.code IN $codes AND tgt.code IN $codes
        RETURN src.code AS source, tgt.code AS target
        """,
        {"codes": codes},
    )

    # Query 3: corequisite edges within the same node set.
    coreq_edges = await run_query(
        """
        MATCH (src:Course)-[:COREQUISITE_OF]->(tgt:Course)
        WHERE src.code IN $codes AND tgt.code IN $codes
        RETURN src.code AS source, tgt.code AS target
        """,
        {"codes": codes},
    )

    nodes = [
        {
            "code": r["code"],
            "title": r["title"] or r["code"],
            "credits": r["credits"],
            "depth": r["depth"],
        }
        for r in node_rows
    ]
    edges = [
        {"source": r["source"], "target": r["target"], "type": "prerequisite"}
        for r in prereq_edges
    ] + [
        {"source": r["source"], "target": r["target"], "type": "corequisite"}
        for r in coreq_edges
    ]

    return {"root": code, "nodes": nodes, "edges": edges}
