"""Faculty and department browsing endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.scraping.faculties import ALL_FACULTIES

router = APIRouter(tags=["Faculties"])


@router.get("/faculties")
async def list_faculties():
    from backend.db.postgres import get_pool

    pool = await get_pool()

    faculties = []
    for name, slug, dept_codes in ALL_FACULTIES:
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM courses WHERE faculty = $1 OR dept = ANY($2::text[])",
                name,
                dept_codes,
            )
        faculties.append(
            {
                "name": name,
                "slug": slug,
                "department_codes": dept_codes,
                "course_count": count,
            }
        )

    return faculties


@router.get("/faculties/{slug}")
async def get_faculty(slug: str):
    match = next((f for f in ALL_FACULTIES if f[1] == slug), None)
    if not match:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Faculty not found")

    name, slug, dept_codes = match
    return {"name": name, "slug": slug, "department_codes": dept_codes}


@router.get("/faculties/{slug}/departments")
async def list_departments(slug: str):
    match = next((f for f in ALL_FACULTIES if f[1] == slug), None)
    if not match:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Faculty not found")

    name, slug, dept_codes = match
    from backend.db.postgres import get_pool

    pool = await get_pool()

    departments = []
    async with pool.acquire() as conn:
        for code in dept_codes:
            row = await conn.fetchrow(
                "SELECT d.code, d.name, d.website FROM departments d WHERE d.code = $1",
                code,
            )
            count = await conn.fetchval(
                "SELECT count(*) FROM courses WHERE dept = $1", code
            )
            departments.append(
                {
                    "code": code,
                    "name": row["name"] if row and row["name"] else code,
                    "website": row["website"] if row else None,
                    "faculty_slug": slug,
                    "course_count": count,
                }
            )

    return departments
