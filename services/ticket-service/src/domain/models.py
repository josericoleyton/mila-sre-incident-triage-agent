from typing import Optional

from pydantic import BaseModel


class TicketCommand(BaseModel):
    action: str
    title: str
    body: str
    severity: str
    labels: list[str] = []
    reporter_slack_user_id: Optional[str] = None
    incident_id: str


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
    reporter_slack_user_id: Optional[str] = None
