from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlanSemesterBase(BaseModel):
    term: str
    sort_order: int = 0
    courses: list[str] = []
    total_credits: float = 0


class PlanSemesterCreate(PlanSemesterBase):
    pass


class PlanSemester(PlanSemesterBase):
    id: int
    plan_id: int


class PlanDocumentInfo(BaseModel):
    id: int
    plan_id: int
    filename: str
    content_type: str
    uploaded_at: datetime | None = None


class PlanCreate(BaseModel):
    title: str = "Untitled Plan"
    program_slug: str | None = None
    target_semesters: int = 4
    student_interests: list[str] = []
    completed_codes: list[str] = []


class PlanUpdate(BaseModel):
    title: str | None = None
    program_slug: str | None = None
    status: str | None = None
    target_semesters: int | None = None
    student_interests: list[str] | None = None
    completed_codes: list[str] | None = None
    plan_markdown: str | None = None


class PlanSummary(BaseModel):
    id: int
    title: str
    program_slug: str | None = None
    status: str
    target_semesters: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlanDetail(PlanSummary):
    student_interests: list[str] = []
    completed_codes: list[str] = []
    plan_markdown: str = ""
    semesters: list[PlanSemester] = []
    documents: list[PlanDocumentInfo] = []
    conversation_ids: list[int] = []
