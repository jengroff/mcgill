from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.db.postgres import get_pool, init_db
from backend.db.neo4j import init_neo4j
from backend.services.scraping.faculties import DEPARTMENT_WEBSITES

logger = logging.getLogger(__name__)


SEED_FILE = Path(__file__).resolve().parents[3] / "data" / "courses.json"


async def run_migrations() -> None:
    await init_db()
    await init_neo4j()


async def seed_from_json(path: Path | None = None) -> int:
    path = path or SEED_FILE
    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return 0

    with open(path) as f:
        courses = json.load(f)

    await run_migrations()

    pool = await get_pool()
    count = 0

    async with pool.acquire() as conn:
        # Upsert faculties
        faculties_seen: dict[str, int] = {}
        for c in courses:
            for fac_name in c.get("faculties", [c.get("faculty", "")]):
                if fac_name and fac_name not in faculties_seen:
                    slug = fac_name.lower().replace(" ", "-").replace("&", "and")
                    slug = slug.replace("(", "").replace(")", "")
                    row = await conn.fetchrow(
                        """INSERT INTO faculties (name, slug)
                           VALUES ($1, $2)
                           ON CONFLICT (name) DO UPDATE SET slug = EXCLUDED.slug
                           RETURNING id""",
                        fac_name,
                        slug,
                    )
                    faculties_seen[fac_name] = row["id"]

        # Upsert departments
        depts_seen: dict[str, int] = {}
        for c in courses:
            dept = c.get("dept", "")
            if dept and dept not in depts_seen:
                fac_name = c.get("faculty", "")
                fac_id = faculties_seen.get(fac_name)
                row = await conn.fetchrow(
                    """INSERT INTO departments (code, faculty_id, website)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (code) DO UPDATE SET
                           faculty_id = COALESCE(EXCLUDED.faculty_id, departments.faculty_id),
                           website = COALESCE(EXCLUDED.website, departments.website)
                       RETURNING id""",
                    dept,
                    fac_id,
                    DEPARTMENT_WEBSITES.get(dept),
                )
                depts_seen[dept] = row["id"]

        # Upsert courses
        for c in courses:
            await conn.execute(
                """INSERT INTO courses (code, slug, title, dept, number, credits,
                       faculty, terms, description, prerequisites_raw,
                       restrictions_raw, notes_raw, url, name_variants)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                   ON CONFLICT (code) DO UPDATE SET
                       title = EXCLUDED.title,
                       description = EXCLUDED.description,
                       prerequisites_raw = EXCLUDED.prerequisites_raw,
                       restrictions_raw = EXCLUDED.restrictions_raw,
                       terms = EXCLUDED.terms,
                       updated_at = now()""",
                c["code"],
                c["slug"],
                c["title"],
                c["dept"],
                c["number"],
                c.get("credits"),
                c.get("faculty", ""),
                c.get("terms", []),
                c.get("description", ""),
                c.get("prerequisites_raw", ""),
                c.get("restrictions_raw", ""),
                c.get("notes_raw", ""),
                c.get("url", ""),
                c.get("name_variants", []),
            )

            # Link course ↔ faculties
            course_row = await conn.fetchrow(
                "SELECT id FROM courses WHERE code = $1", c["code"]
            )
            if course_row:
                for fac_name in c.get("faculties", []):
                    fac_id = faculties_seen.get(fac_name)
                    if fac_id:
                        await conn.execute(
                            """INSERT INTO course_faculties (course_id, faculty_id)
                               VALUES ($1, $2)
                               ON CONFLICT DO NOTHING""",
                            course_row["id"],
                            fac_id,
                        )
            count += 1

    logger.info(
        "Seeded %d courses, %d faculties, %d departments",
        count,
        len(faculties_seen),
        len(depts_seen),
    )
    return count
