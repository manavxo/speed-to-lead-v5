"""Transport interface — abstract base for all notification channels.

Every transport (SMS, WhatsApp, Telegram) implements this interface so
notify_rep() can dispatch to any backend without knowing the details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TransportResult:
    """Outcome of a transport send attempt."""
    success: bool
    backend: str
    message_id: str | None         # Provider-side ID (or DRYRUN_/SKIPPED_ prefix)
    dry_run: bool = False
    error: str | None = None


class Transport(ABC):
    """Abstract notification transport.

    Subclasses implement send() for a specific channel (Telegram, SMS, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short backend name, e.g. 'telegram', 'sms'."""
        ...

    @abstractmethod
    def send(self, *, to: str, body: str, **kwargs) -> TransportResult:
        """Send a message. Returns TransportResult — never raises."""
        ...
