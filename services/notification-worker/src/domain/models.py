from enum import Enum
from typing import Optional

from pydantic import BaseModel


class NotificationType(str, Enum):
    team_alert = "team_alert"
    reporter_update = "reporter_update"
    reporter_resolved = "reporter_resolved"


class Notification(BaseModel):
    type: NotificationType
    slack_channel: Optional[str] = None
    slack_user_id: Optional[str] = None
    message: str
    metadata: dict = {}
    allow_reescalation: bool = False
    incident_id: str
    confidence: Optional[float] = None
