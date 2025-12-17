from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentTicket(BaseModel):
    id: str
    title: str
    description: str
    reported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "api"
    tags: List[str] = Field(default_factory=list)


class AgentRecommendation(BaseModel):
    summary: str
    severity: Severity
    recommended_actions: List[str]
    confidence: float
    escalation_required: bool
    rationale: str
    redacted: bool = False
    knowledge_refs: List[str] = Field(default_factory=list)
    history_refs: List[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    ticket_id: str
    expected_severity: Severity
    predicted_severity: Severity
    passed: bool
    confidence: float
    escalation_required: bool
    rationale: str


class IncidentResponse(BaseModel):
    ticket: IncidentTicket
    recommendation: AgentRecommendation


class FileTriageRequest(BaseModel):
    path: str
