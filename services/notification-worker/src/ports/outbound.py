from abc import ABC, abstractmethod
from typing import Optional


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        """Publish an event to a channel. Returns the event_id."""
        ...


class TeamNotifier(ABC):
    @abstractmethod
    async def send_team_alert(self, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        """Post a formatted alert to the team channel. Returns True on success."""
        ...


class ReporterNotifier(ABC):
    @abstractmethod
    async def send_dm(self, reporter_email: str, blocks: list[dict], fallback_text: str, event_id: str = "unknown") -> bool:
        """Send a DM to the reporter by email via Slack Bot Token. Returns True on success."""
        ...
