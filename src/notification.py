"""External / system boundary: Notification Service.

The reservation system depends on a Notification Service to tell a user
their reservation was confirmed. We model it as an abstract interface plus
a stub implementation, so the boundary is explicit and swappable (e.g. for
a real email/SMS provider later) and so it can be made to fail/time out on
purpose -- useful for the boundary-failure engineering spike (Spike B).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationError(Exception):
    """Raised when the notification boundary fails (non-timeout failure)."""


class NotificationService(ABC):
    @abstractmethod
    def send_reservation_confirmed(self, user_id: str, reservation_id: str) -> None:
        ...


class StubNotificationService(NotificationService):
    """In-process stub standing in for a real notification provider.

    Pass simulate_timeout/simulate_failure=True to exercise the boundary's
    failure paths (see tests/test_boundary_spike.py).
    """

    def __init__(self, simulate_timeout: bool = False, simulate_failure: bool = False):
        self.simulate_timeout = simulate_timeout
        self.simulate_failure = simulate_failure
        self.sent: list[str] = []

    def send_reservation_confirmed(self, user_id: str, reservation_id: str) -> None:
        if self.simulate_timeout:
            raise TimeoutError(
                f"notification service timed out sending confirmation for {reservation_id}"
            )
        if self.simulate_failure:
            raise NotificationError(
                f"notification service failed to send confirmation for {reservation_id}"
            )
        message = f"reservation {reservation_id} confirmed for user {user_id}"
        self.sent.append(message)
