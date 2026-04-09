from abc import ABC, abstractmethod
from typing import Optional


class TicketMappingStore(ABC):
    @abstractmethod
    async def save_mapping(
        self,
        linear_ticket_id: str,
        incident_id: str,
        reporter_email: Optional[str],
        identifier: str,
        url: str,
    ) -> None:
        """Persist a ticket-to-incident mapping for later resolution correlation."""
        ...

    @abstractmethod
    async def get_mapping(self, linear_ticket_id: str) -> Optional[dict]:
        """Retrieve a ticket mapping by Linear ticket ID. Returns None if not tracked."""
        ...

    @abstractmethod
    async def mark_resolved(self, linear_ticket_id: str) -> bool:
        """Mark a ticket as resolved. Returns False if already resolved (idempotency)."""
        ...
