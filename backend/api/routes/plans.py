from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from backend.api.auth import get_current_user
from backend.db.postgres import get_pool
from backend.models.plan import (
    PlanCreate,
    PlanUpdate,
    PlanSummary,
    PlanDetail,
    PlanSemester,
    PlanSemesterCreate,
    PlanDocumentInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["Plans"])


# ---------------------------------------------------------------------------
# Plan CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_plans(user: dict = Depends(get_current_user)) -> list[PlanSummary]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, title, program_slug, status, target_semesters,
                      created_at, updated_at
               FROM plans WHERE user_id = $1
               ORDER BY updated_at DESC""",
            user["id"],
        )
    return [PlanSummary(**dict(r)) for r in rows]


@router.post("", status_code=201)
async def create_plan(
    body: PlanCreate, user: dict = Depends(get_current_user)
) -> PlanDetail:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO plans (user_id, title, program_slug, target_semesters,
                                 student_interests, completed_codes)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING *""",
            user["id"],
            body.title,
            body.program_slug,
            body.target_semesters,
            body.student_interests,
            body.completed_codes,
        )
        plan_id = row["id"]

        semesters: list[PlanSemester] = []
        if body.program_slug:
            try:
                from backend.services.synthesis.plan_builder import PlanBuilder

                builder = PlanBuilder()
                semester_data = await builder.auto_populate(
                    program_slug=body.program_slug,
                    start_term=body.start_term,
                    target_semesters=body.target_semesters,
                    completed_codes=body.completed_codes,
                )
                for sem in semester_data:
                    sem_row = await conn.fetchrow(
                        """INSERT INTO plan_semesters
                               (plan_id, term, sort_order, courses, total_credits)
                           VALUES ($1, $2, $3, $4, $5)
                           RETURNING id, plan_id, term, sort_order, courses, total_credits""",
                        plan_id,
                        sem["term"],
                        sem["sort_order"],
                        sem["courses"],
                        sem["total_credits"],
                    )
                    semesters.append(PlanSemester(**dict(sem_row)))
            except Exception as e:
                logger.warning("Auto-populate failed for plan %d: %s", plan_id, e)

    detail = _plan_detail_from_row(row)
    detail.semesters = semesters
    return detail


@router.get("/{plan_id}")
async def get_plan(plan_id: int, user: dict = Depends(get_current_user)) -> PlanDetail:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM plans WHERE id = $1 AND user_id = $2",
            plan_id,
            user["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Plan not found")

        semesters = await conn.fetch(
            """SELECT id, plan_id, term, sort_order, courses, total_credits
               FROM plan_semesters WHERE plan_id = $1
               ORDER BY sort_order""",
            plan_id,
        )
        documents = await conn.fetch(
            """SELECT id, plan_id, filename, content_type, uploaded_at
               FROM plan_documents WHERE plan_id = $1
               ORDER BY uploaded_at""",
            plan_id,
        )
        convos = await conn.fetch(
            "SELECT conversation_id FROM plan_conversations WHERE plan_id = $1",
            plan_id,
        )

    detail = _plan_detail_from_row(row)
    detail.semesters = [PlanSemester(**dict(s)) for s in semesters]
    detail.documents = [PlanDocumentInfo(**dict(d)) for d in documents]
    detail.conversation_ids = [c["conversation_id"] for c in convos]
    return detail


@router.patch("/{plan_id}")
async def update_plan(
    plan_id: int, body: PlanUpdate, user: dict = Depends(get_current_user)
) -> PlanDetail:
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM plans WHERE id = $1 AND user_id = $2",
            plan_id,
            user["id"],
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Plan not found")

        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = []
        values = []
        for i, (key, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{key} = ${i}")
            values.append(val)
        set_clauses.append("updated_at = now()")
        values.extend([plan_id, user["id"]])

        row = await conn.fetchrow(
            f"""UPDATE plans SET {", ".join(set_clauses)}
                WHERE id = ${len(values) - 1} AND user_id = ${len(values)}
                RETURNING *""",
            *values,
        )
    return _plan_detail_from_row(row)


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, user: dict = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM plans WHERE id = $1 AND user_id = $2",
            plan_id,
            user["id"],
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Plan not found")


# ---------------------------------------------------------------------------
# Semesters
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/semesters", status_code=201)
async def add_semester(
    plan_id: int,
    body: PlanSemesterCreate,
    user: dict = Depends(get_current_user),
) -> PlanSemester:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        row = await conn.fetchrow(
            """INSERT INTO plan_semesters (plan_id, term, sort_order, courses, total_credits)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id, plan_id, term, sort_order, courses, total_credits""",
            plan_id,
            body.term,
            body.sort_order,
            body.courses,
            body.total_credits,
        )
        await conn.execute("UPDATE plans SET updated_at = now() WHERE id = $1", plan_id)
    return PlanSemester(**dict(row))


@router.put("/{plan_id}/semesters/{semester_id}")
async def update_semester(
    plan_id: int,
    semester_id: int,
    body: PlanSemesterCreate,
    user: dict = Depends(get_current_user),
) -> PlanSemester:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        row = await conn.fetchrow(
            """UPDATE plan_semesters
               SET term = $1, sort_order = $2, courses = $3, total_credits = $4
               WHERE id = $5 AND plan_id = $6
               RETURNING id, plan_id, term, sort_order, courses, total_credits""",
            body.term,
            body.sort_order,
            body.courses,
            body.total_credits,
            semester_id,
            plan_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Semester not found")
        await conn.execute("UPDATE plans SET updated_at = now() WHERE id = $1", plan_id)
    return PlanSemester(**dict(row))


@router.delete("/{plan_id}/semesters/{semester_id}", status_code=204)
async def delete_semester(
    plan_id: int,
    semester_id: int,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        result = await conn.execute(
            "DELETE FROM plan_semesters WHERE id = $1 AND plan_id = $2",
            semester_id,
            plan_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Semester not found")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/documents", status_code=201)
async def upload_document(
    plan_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> PlanDocumentInfo:
    pool = await get_pool()
    raw = await file.read()

    # Extract text from PDF if applicable
    extracted = ""
    if file.content_type == "application/pdf" or (
        file.filename and file.filename.lower().endswith(".pdf")
    ):
        try:
            from backend.services.pdf.extract import extract_text

            extracted = extract_text(raw)
        except Exception as e:
            logger.warning("PDF text extraction failed: %s", e)

    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        row = await conn.fetchrow(
            """INSERT INTO plan_documents (plan_id, filename, content_type, raw_bytes, extracted_text)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id, plan_id, filename, content_type, uploaded_at""",
            plan_id,
            file.filename or "upload",
            file.content_type or "",
            raw,
            extracted,
        )
        await conn.execute("UPDATE plans SET updated_at = now() WHERE id = $1", plan_id)
    return PlanDocumentInfo(**dict(row))


@router.get("/{plan_id}/documents")
async def list_documents(
    plan_id: int, user: dict = Depends(get_current_user)
) -> list[PlanDocumentInfo]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        rows = await conn.fetch(
            """SELECT id, plan_id, filename, content_type, uploaded_at
               FROM plan_documents WHERE plan_id = $1
               ORDER BY uploaded_at""",
            plan_id,
        )
    return [PlanDocumentInfo(**dict(r)) for r in rows]


@router.delete("/{plan_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    plan_id: int,
    doc_id: int,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        result = await conn.execute(
            "DELETE FROM plan_documents WHERE id = $1 AND plan_id = $2",
            doc_id,
            plan_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Document not found")


# ---------------------------------------------------------------------------
# Generate plan (trigger planner workflow)
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/generate")
async def generate_plan(
    plan_id: int, user: dict = Depends(get_current_user)
) -> PlanDetail:
    """Run the planner workflow against this plan's interests/program and persist results."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM plans WHERE id = $1 AND user_id = $2",
            plan_id,
            user["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="Plan not found")

    from backend.workflows.planner.graph import PlannerOrchestrator

    orchestrator = PlannerOrchestrator()
    result = await orchestrator.run(
        plan_id=plan_id,
        user_id=user["id"],
        student_interests=row["student_interests"] or [],
        program_slug=row["program_slug"] or "",
        completed_codes=row["completed_codes"] or [],
        target_semesters=row["target_semesters"] or 4,
    )

    if result.get("errors"):
        logger.warning("Plan %d generation had errors: %s", plan_id, result["errors"])

    # Return updated plan
    return await get_plan(plan_id, user)


# ---------------------------------------------------------------------------
# Conversation linking
# ---------------------------------------------------------------------------


@router.post("/{plan_id}/conversations/{conversation_id}", status_code=201)
async def link_conversation(
    plan_id: int,
    conversation_id: int,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        # Verify conversation belongs to user
        convo = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id = $1 AND user_id = $2",
            conversation_id,
            user["id"],
        )
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await conn.execute(
            """INSERT INTO plan_conversations (plan_id, conversation_id)
               VALUES ($1, $2)
               ON CONFLICT DO NOTHING""",
            plan_id,
            conversation_id,
        )
    return {"linked": True}


@router.delete("/{plan_id}/conversations/{conversation_id}", status_code=204)
async def unlink_conversation(
    plan_id: int,
    conversation_id: int,
    user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_plan_owner(conn, plan_id, user["id"])
        await conn.execute(
            "DELETE FROM plan_conversations WHERE plan_id = $1 AND conversation_id = $2",
            plan_id,
            conversation_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _assert_plan_owner(conn, plan_id: int, user_id: int):
    row = await conn.fetchrow(
        "SELECT id FROM plans WHERE id = $1 AND user_id = $2", plan_id, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")


def _plan_detail_from_row(row) -> PlanDetail:
    return PlanDetail(
        id=row["id"],
        title=row["title"],
        program_slug=row["program_slug"],
        status=row["status"],
        target_semesters=row["target_semesters"],
        student_interests=row["student_interests"] or [],
        completed_codes=row["completed_codes"] or [],
        plan_markdown=row["plan_markdown"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
