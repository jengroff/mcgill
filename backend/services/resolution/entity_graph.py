"""Build the Neo4j entity graph from courses and resolved references."""

from __future__ import annotations

from backend.db.neo4j import run_query
from backend.models.course import CourseCreate
from backend.models.graph import PrerequisiteRef
from backend.services.scraping.faculties import ALL_FACULTIES


async def build_faculty_nodes() -> int:
    count = 0
    for name, slug, dept_codes in ALL_FACULTIES:
        await run_query(
            "MERGE (f:Faculty {slug: $slug}) SET f.name = $name",
            {"slug": slug, "name": name},
        )
        count += 1
        for code in dept_codes:
            await run_query(
                """MERGE (d:Department {code: $code})
                   WITH d
                   MATCH (f:Faculty {slug: $slug})
                   MERGE (d)-[:PART_OF]->(f)""",
                {"code": code, "slug": slug},
            )
    return count


async def build_course_nodes(courses: list[CourseCreate]) -> int:
    count = 0
    for c in courses:
        await run_query(
            """MERGE (c:Course {code: $code})
               SET c.slug = $slug,
                   c.title = $title,
                   c.dept = $dept,
                   c.number = $number,
                   c.credits = $credits,
                   c.description = $description""",
            {
                "code": c.code,
                "slug": c.slug,
                "title": c.title,
                "dept": c.dept,
                "number": c.number,
                "credits": c.credits,
                "description": c.description[:500],
            },
        )

        # Course → Department
        await run_query(
            """MATCH (c:Course {code: $code})
               MERGE (d:Department {code: $dept})
               MERGE (c)-[:BELONGS_TO]->(d)""",
            {"code": c.code, "dept": c.dept},
        )

        # Course → Term
        for term in c.terms:
            await run_query(
                """MATCH (c:Course {code: $code})
                   MERGE (t:Term {name: $term})
                   MERGE (c)-[:OFFERED_IN]->(t)""",
                {"code": c.code, "term": term},
            )

        # Course → Faculty (cross-listed)
        for fac_name in c.faculties:
            slug = fac_name.lower().replace(" ", "-").replace("&", "and")
            slug = slug.replace("(", "").replace(")", "")
            await run_query(
                """MATCH (c:Course {code: $code})
                   MERGE (f:Faculty {slug: $slug})
                   SET f.name = $name
                   MERGE (c)-[:CROSS_LISTED_IN]->(f)""",
                {"code": c.code, "slug": slug, "name": fac_name},
            )

        count += 1
    return count


async def build_relationships(refs: list[PrerequisiteRef]) -> int:
    count = 0
    for ref in refs:
        rel_type = ref.relationship
        await run_query(
            f"""MATCH (src:Course {{code: $src}})
                MATCH (tgt:Course {{code: $tgt}})
                MERGE (src)-[:{rel_type}]->(tgt)""",
            {"src": ref.source_code, "tgt": ref.target_code},
        )
        count += 1
    return count


async def get_graph_stats() -> dict:
    nodes = await run_query("MATCH (n) RETURN count(n) AS count")
    rels = await run_query("MATCH ()-[r]->() RETURN count(r) AS count")
    return {
        "nodes": nodes[0]["count"] if nodes else 0,
        "relationships": rels[0]["count"] if rels else 0,
    }
