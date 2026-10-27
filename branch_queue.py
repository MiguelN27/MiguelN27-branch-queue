"""Banco Meridional branch queue manager.

Each service type has its own FIFO queue, so an agent can call their next
client without scanning clients waiting for other services.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime

SERVICE_TYPES = ("deposit", "withdrawal", "account_management")


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
