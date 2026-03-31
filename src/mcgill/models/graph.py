from pydantic import BaseModel


class PrerequisiteRef(BaseModel):
    source_code: str
    target_code: str
    relationship: str = "PREREQUISITE_OF"
    raw_text: str = ""


class EntityResolution(BaseModel):
    query: str
    matched_code: str | None = None
    matched_title: str | None = None
    score: float = 0.0
    method: str = "jaro_winkler"
