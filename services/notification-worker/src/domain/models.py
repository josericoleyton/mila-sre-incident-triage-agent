from enum import Enum
from typing import Optional

from pydantic import BaseModel


class NotificationType(str, Enum):
    team_alert = "team_alert"
    reporter_update = "reporter_update"
    reporter_resolved = "reporter_resolved"


class Notification(BaseModel):
    type: NotificationType
    incident_id: str
    message: Optional[str] = None
    slack_channel: Optional[str] = None
    slack_user_id: Optional[str] = None
    # team_alert fields
    title: Optional[str] = None
    ticket_url: Optional[str] = None
    severity: Optional[str] = None
    component: Optional[str] = None
    summary: Optional[str] = None
    source_type: Optional[str] = None
    reporter_slack_user_id: Optional[str] = None
    metadata: dict = {}
    confidence: Optional[float] = None
