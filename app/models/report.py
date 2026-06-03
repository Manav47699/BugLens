from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class Severity(str, Enum):
    LOW = "low"           # 0–2  minor UI glitches
    MEDIUM = "medium"     # 3–5  broken flows, some users affected
    HIGH = "high"         # 6–8  critical features down
    CRITICAL = "critical" # 9–10 app unusable


def score_to_severity(score: float) -> Severity:
    if score <= 2:
        return Severity.LOW
    elif score <= 5:
        return Severity.MEDIUM
    elif score <= 8:
        return Severity.HIGH
    else:
        return Severity.CRITICAL


class NetworkRequest(BaseModel):
    """A captured HTTP request/response pair."""
    method: str
    url: str
    status: int
    duration_ms: Optional[float] = None


class BugEvidence(BaseModel):
    """Raw evidence collected by the browser agent for one finding."""
    route: str
    js_errors: list[str] = Field(default_factory=list)
    console_warnings: list[str] = Field(default_factory=list)
    failed_requests: list[NetworkRequest] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    reproduction_count: int = 1   # how many times out of attempts
    reproduction_attempts: int = 1


class BugReport(BaseModel):
    """A single actionable bug finding produced by the AI analysis engine."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Classification
    disaster_score: float = Field(ge=0.0, le=10.0)
    severity: Severity

    # Plain-English explanation
    title: str
    problem: str
    cause: str
    fix: str

    # Location
    route: str
    file: Optional[str] = None

    # Evidence
    evidence: BugEvidence

    # Meta
    reproduced: str = ""  # e.g. "3/3 attempts"


class DebugReport(BaseModel):
    """The full output of one BugLens session."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    framework: Optional[str] = None
    routes_explored: list[str] = Field(default_factory=list)
    bugs: list[BugReport] = Field(default_factory=list)

    # Aggregate stats
    @property
    def critical_count(self) -> int:
        return sum(1 for b in self.bugs if b.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for b in self.bugs if b.severity == Severity.HIGH)

    @property
    def top_disaster_score(self) -> float:
        return max((b.disaster_score for b in self.bugs), default=0.0)