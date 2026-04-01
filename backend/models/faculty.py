from pydantic import BaseModel


class Faculty(BaseModel):
    name: str
    slug: str
    department_codes: list[str] = []


class Department(BaseModel):
    code: str
    name: str | None = None
    faculty_slug: str
    course_count: int = 0
