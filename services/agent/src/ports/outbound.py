from abc import ABC, abstractmethod


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, channel: str, event_type: str, payload: dict) -> str:
        """Publish an event to a channel. Returns the event_id."""
        ...


class CodeRepository(ABC):
    @abstractmethod
    async def search_code(self, query: str) -> list[dict]:
        """Search code in the repository. Returns list of matching results."""
        ...

    @abstractmethod
    async def get_file_content(self, path: str) -> str:
        """Fetch file content by path. Returns file content as string."""
        ...
