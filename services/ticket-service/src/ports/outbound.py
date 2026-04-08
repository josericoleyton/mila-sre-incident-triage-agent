from abc import ABC, abstractmethod


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        """Publish an event to a channel. Returns the event_id."""
        ...


class TicketCreator(ABC):
    @abstractmethod
    async def create_issue(
        self,
        title: str,
        body: str,
        priority: int,
        labels: list[str],
        team_id: str,
    ) -> dict:
        """Create an issue in the ticket system. Returns dict with id, identifier, url."""
        ...
