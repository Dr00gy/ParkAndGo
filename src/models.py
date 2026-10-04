"""Domain concepts for the parking reservation system.

These are plain, framework-agnostic representations of the core concepts
from the Project Frame: Resource, User, Reservation (+ its states).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid


class ReservationState(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Resource:
    """A reservable parking spot."""
    id: str
    label: str  # e.g. "Lot A - Spot 12"
    requires_approval = Column(Boolean, default=False)


@dataclass
class User:
    """A person who can create reservations (the 'reservee')."""
    id: str
    name: str


@dataclass
class Reservation:
    id: str
    resource_id: str
    user_id: str
    start_time: datetime
    end_time: datetime
    state: ReservationState = ReservationState.DRAFT
    approval_expires_at: datetime | None = None

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())
