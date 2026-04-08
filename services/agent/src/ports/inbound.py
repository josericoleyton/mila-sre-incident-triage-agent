from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Optional

from src.ports.outbound import EventPublisher


class EventConsumer(ABC):
    @abstractmethod
    async def subscribe(self, channel: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Subscribe to a channel and route valid events to the handler callback."""
        ...

    @abstractmethod
    async def subscribe_multi(
        self,
        handlers: dict[str, Callable[[dict], Awaitable[None]]],
        error_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """Subscribe to multiple channels with per-channel handler routing."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and clean up resources."""
        ...
