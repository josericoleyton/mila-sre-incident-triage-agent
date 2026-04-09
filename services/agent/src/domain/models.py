from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.ports.outbound import CodeRepository, EventPublisher


class Classification(str, Enum):
    bug = "bug"
    non_incident = "non_incident"


class IncidentEvent(BaseModel):
    incident_id: str
    title: str
    description: Optional[str] = None
    component: Optional[str] = None
    severity: Optional[str] = None
    attachment_url: Optional[str] = None
    reporter_email: Optional[str] = None
    source_type: Literal["userIntegration", "systemIntegration"]
    trace_data: Optional[dict] = None
    prompt_injection_detected: bool = False
    reporter_feedback: Optional[str] = None
    original_classification: Optional[str] = None


class TriageResult(BaseModel):
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    file_refs: list[str] = []
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    resolution_explanation: Optional[str] = None
    severity_assessment: str = ""
    attachment_analysis: Optional[str] = None


@dataclass
class TriageState:
    incident_id: str
    source_type: str
    event_id: str = ""
    incident: dict = field(default_factory=dict)
    triage_result: Optional[TriageResult] = None
    reescalation: bool = False
    reporter_feedback: str = ""
    original_classification: str = ""
    prompt_injection_detected: bool = False
    # Signals extracted by AnalyzeInputNode
    signals: dict = field(default_factory=dict)
    # Multimodal content (images as base64, logs as text)
    multimodal_content: list[dict] = field(default_factory=list)
    # Code context gathered by SearchCodeNode
    code_context: str = ""
    # Triage duration tracking (monotonic clock)
    triage_started_at: Optional[float] = None
    # Forced escalation for proactive (systemIntegration) incidents
    forced_escalation: bool = False


@dataclass
class TriageDeps:
    github_client: CodeRepository
    publisher: EventPublisher
