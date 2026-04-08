from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel


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
    reporter_slack_user_id: str
    source_type: Literal["userIntegration", "systemIntegration"]
    trace_data: Optional[dict] = None
    prompt_injection_detected: bool = False


class TriageResult(BaseModel):
    classification: Classification
    confidence: float
    reasoning: str
    file_refs: list[str] = []
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    resolution_explanation: Optional[str] = None
    severity_assessment: str = ""


@dataclass
class TriageState:
    incident_id: str
    source_type: str
    event_id: str = ""
    incident: dict = field(default_factory=dict)
    triage_result: Optional[TriageResult] = None
    reescalation: bool = False
    prompt_injection_detected: bool = False
