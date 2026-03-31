from mcgill.models.course import CourseBase, CourseCreate, CourseDetail
from mcgill.models.faculty import Faculty, Department
from mcgill.models.graph import PrerequisiteRef, EntityResolution
from mcgill.models.chat import ChatRequest, SSEEvent

__all__ = [
    "CourseBase", "CourseCreate", "CourseDetail",
    "Faculty", "Department",
    "PrerequisiteRef", "EntityResolution",
    "ChatRequest", "SSEEvent",
]
