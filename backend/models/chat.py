from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SSEEvent(BaseModel):
    type: str  # "assistant", "step_update", "error", "sources"
    content: str = ""
    phase: int | None = None
    status: str | None = None
    label: str | None = None
    sources: list[dict] | None = None
