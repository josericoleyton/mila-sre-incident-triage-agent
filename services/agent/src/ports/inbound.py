from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class EventConsumer(ABC):
    @abstractmethod
    async def subscribe(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Subscribe to a channel and route valid events to the handler callback."""
        ...
