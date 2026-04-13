from __future__ import annotations

import logging

from backend.db.neo4j import run_query
from backend.models.course import CourseCreate
from backend.models.graph import PrerequisiteRef
from backend.services.scraping.faculties import ALL_FACULTIES

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


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
    course_params = [
        {
            "code": c.code,
            "slug": c.slug,
            "title": c.title,
            "dept": c.dept,
            "number": c.number,
            "credits": c.credits,
            "description": c.description[:500],
        }
        for c in courses
    ]

    for i in range(0, len(course_params), BATCH_SIZE):
        batch = course_params[i : i + BATCH_SIZE]
        await run_query(
            """UNWIND $batch AS c
               MERGE (course:Course {code: c.code})
               SET course.slug = c.slug,
                   course.title = c.title,
                   course.dept = c.dept,
                   course.number = c.number,
                   course.credits = c.credits,
                   course.description = c.description
               MERGE (d:Department {code: c.dept})
               MERGE (course)-[:BELONGS_TO]->(d)""",
            {"batch": batch},
        )
        logger.info(
            "Neo4j: merged %d/%d course nodes",
            min(i + BATCH_SIZE, len(courses)),
            len(courses),
        )

    # Batch term relationships
    term_items = [{"code": c.code, "term": term} for c in courses for term in c.terms]
    for i in range(0, len(term_items), BATCH_SIZE):
        term_batch = term_items[i : i + BATCH_SIZE]
        await run_query(
            """UNWIND $batch AS item
               MATCH (c:Course {code: item.code})
               MERGE (t:Term {name: item.term})
               MERGE (c)-[:OFFERED_IN]->(t)""",
            {"batch": term_batch},
        )

    # Batch faculty cross-listings
    fac_items = [
        {
            "code": c.code,
            "slug": fac_name.lower()
            .replace(" ", "-")
            .replace("&", "and")
            .replace("(", "")
            .replace(")", ""),
            "name": fac_name,
        }
        for c in courses
        for fac_name in c.faculties
    ]
    if fac_items:
        for i in range(0, len(fac_items), BATCH_SIZE):
            fac_batch = fac_items[i : i + BATCH_SIZE]
            await run_query(
                """UNWIND $batch AS item
                   MATCH (c:Course {code: item.code})
                   MERGE (f:Faculty {slug: item.slug})
                   SET f.name = item.name
                   MERGE (c)-[:CROSS_LISTED_IN]->(f)""",
                {"batch": fac_batch},
            )

    return len(courses)


async def build_relationships(refs: list[PrerequisiteRef]) -> int:
    by_type: dict[str, list[dict]] = {}
    for ref in refs:
        by_type.setdefault(ref.relationship, []).append(
            {"src": ref.source_code, "tgt": ref.target_code}
        )

    count = 0
    for rel_type, items in by_type.items():
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i : i + BATCH_SIZE]
            await run_query(
                f"""UNWIND $batch AS item
                    MATCH (src:Course {{code: item.src}})
                    MATCH (tgt:Course {{code: item.tgt}})
                    MERGE (src)-[:{rel_type}]->(tgt)""",
                {"batch": batch},
            )
            count += len(batch)

    return count


async def get_graph_stats() -> dict:
    nodes = await run_query("MATCH (n) RETURN count(n) AS count")
    rels = await run_query("MATCH ()-[r]->() RETURN count(r) AS count")
    return {
        "nodes": nodes[0]["count"] if nodes else 0,
        "relationships": rels[0]["count"] if rels else 0,
    }
