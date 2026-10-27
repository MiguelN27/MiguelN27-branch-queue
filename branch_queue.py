"""Banco Meridional branch queue manager.

Each service type has its own FIFO queue, so an agent can call their next
client without scanning clients waiting for other services. See DESIGN.md
for why the queues are structured this way and how concurrent calls are handled.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

SERVICE_TYPES = ("deposit", "withdrawal", "account_management")


class InvalidServiceTypeError(ValueError):
    """Raised when a service type is not one of SERVICE_TYPES."""

    def __init__(self, service_type):
        super().__init__(
            f"Invalid service type {service_type!r}. "
            f"Valid types: {', '.join(SERVICE_TYPES)}."
        )
        self.service_type = service_type


class EmptyQueueError(LookupError):
    """Raised when calling the next client from a service queue with nobody waiting."""

    def __init__(self, service_type):
        super().__init__(f"No clients waiting for {service_type!r}.")
        self.service_type = service_type


@dataclass(frozen=True)
class Ticket:
    """A client's ticket. Frozen: once issued, a ticket never changes."""

    number: int
    client_name: str
    service_type: str
    issued_at: datetime


class BranchQueue:
    """One waiting queue per service type, plus a global ticket counter."""

    def __init__(self):
        self._queues = {service: deque() for service in SERVICE_TYPES}
        # Shared across all services so no two tickets ever get the same number.
        self._next_number = 1

    def _queue_for(self, service_type: str) -> deque:
        """Return the queue for a service type, or raise InvalidServiceTypeError."""
        try:
            return self._queues[service_type]
        except (KeyError, TypeError):
            raise InvalidServiceTypeError(service_type) from None

    def issue_ticket(self, client_name: str, service_type: str) -> Ticket:
        """Register a new client at the back of their service queue."""
        queue = self._queue_for(service_type)
        if not isinstance(client_name, str) or not client_name.strip():
            raise ValueError("Client name cannot be empty.")

        # Validation is done, so the number is only used up by a real ticket.
        ticket = Ticket(
            number=self._next_number,
            client_name=client_name.strip(),
            service_type=service_type,
            issued_at=datetime.now(),
        )
        self._next_number += 1
        queue.append(ticket)
        return ticket

    def call_next(self, service_type: str) -> Ticket:
        """Remove and return the client who has waited longest for this service."""
        queue = self._queue_for(service_type)
        # A single popleft() both checks and removes, so there is no gap between
        # "is anyone waiting?" and "take them" (see DESIGN.md).
        try:
            return queue.popleft()
        except IndexError:
            raise EmptyQueueError(service_type) from None

    def peek_next(self, service_type: str) -> Optional[Ticket]:
        """Return the next client for this service without removing them, or None."""
        queue = self._queue_for(service_type)
        return queue[0] if queue else None

    def list_waiting(self) -> Dict[str, List[Ticket]]:
        """Return every service's waiting tickets, in the order they will be called.

        The lists are copies, so changing them does not affect the queues.
        """
        return {service: list(queue) for service, queue in self._queues.items()}

    def stats(self) -> Dict[str, int]:
        """Return the number of waiting clients per service type, plus "total"."""
        counts = {service: len(queue) for service, queue in self._queues.items()}
        counts["total"] = sum(counts.values())
        return counts
