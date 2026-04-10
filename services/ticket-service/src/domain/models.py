from typing import Optional

from pydantic import BaseModel


class TicketCommand(BaseModel):
    action: str
    title: str
    body: str
    severity: str
    labels: list[str] = []
    reporter_email: Optional[str] = None
    incident_id: str
    component: Optional[str] = None
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    root_cause_summary: Optional[str] = None


class TicketResult(BaseModel):
    ticket_id: str
    identifier: str
    url: str
    incident_id: str


class TicketStatusEvent(BaseModel):
    ticket_id: str
    old_status: str
    new_status: str
    incident_id: str
    reporter_email: Optional[str] = None
