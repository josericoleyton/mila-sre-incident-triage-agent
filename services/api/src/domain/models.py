from typing import Literal, Optional

from pydantic import BaseModel


class IncidentReport(BaseModel):
    title: str
    description: Optional[str] = None
    component: Optional[str] = None
    severity: Optional[str] = None
    attachment_url: Optional[str] = None
    reporter_email: Optional[str] = None
    source_type: Literal["userIntegration", "systemIntegration"]


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
