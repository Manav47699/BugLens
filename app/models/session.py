from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class SessionStatus(str, Enum):
    PENDING = "pending"       # uploaded, not yet started
    SANDBOXING = "sandboxing" # unzipping, installing deps, booting server
    EXPLORING = "exploring"   # Playwright discovering routes
    CAPTURING = "capturing"   # agent interacting, collecting evidence
    ANALYZING = "analyzing"   # Claude generating bug reports
    DONE = "done"             # report ready
    FAILED = "failed"         # something went wrong


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "info"       # info | warning | error
    message: str


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Upload info
    filename: str = ""
    framework: Optional[str] = None  # react | nextjs | vite | unknown

    # Live progress
    logs: list[LogEntry] = Field(default_factory=list)
    routes_discovered: list[str] = Field(default_factory=list)
    routes_explored: list[str] = Field(default_factory=list)

    # Result
    report_id: Optional[str] = None
    error: Optional[str] = None

    def log(self, message: str, level: str = "info") -> None:
        self.logs.append(LogEntry(message=message, level=level))
        self.updated_at = datetime.utcnow()

    def set_status(self, status: SessionStatus) -> None:
        self.status = status
        self.updated_at = datetime.utcnow()