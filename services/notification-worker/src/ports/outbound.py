from abc import ABC, abstractmethod


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        """Publish an event to a channel. Returns the event_id."""
        ...
