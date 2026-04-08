from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Classification(str, Enum):
    bug = "bug"
    non_incident = "non_incident"


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
    incident: dict = field(default_factory=dict)
    triage_result: Optional[TriageResult] = None
    reescalation: bool = False
    prompt_injection_detected: bool = False
