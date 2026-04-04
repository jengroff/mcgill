from datetime import datetime

from pydantic import BaseModel


class CourseBase(BaseModel):
    code: str
    slug: str
    title: str
    dept: str
    number: str
    credits: float | None = None
    faculty: str
    faculties: list[str] = []
    terms: list[str] = []
    description: str = ""
    prerequisites_raw: str = ""
    restrictions_raw: str = ""
    notes_raw: str = ""
    url: str = ""
    name_variants: list[str] = []


class CourseCreate(CourseBase):
    """Used for scraper output → DB insert."""

    pass


class CourseDetail(CourseBase):
    id: int
    prerequisites: list[str] = []
    restrictions: list[str] = []
    corequisites: list[str] = []
    scraped_at: datetime | None = None
