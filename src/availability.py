"""Availability Policy: the single contract that decides whether a resource
slot is free (C05 Detailed Design).

This exists as its own module because of a design decision made during C05:
before this, the overlap check lived as a *private* helper
(`services._has_overlapping_confirmed`) that `approval.py` reached across
the module boundary to import directly. That worked, but it meant the
contract for "is this slot free?" was not actually explicit anywhere --
two different units (Reservation Management and Approval Workflow) depended
on an implementation detail of a third module instead of on a declared
interface.

`has_overlap()` is that declared interface now. Both `services.py` (at
create/confirm/prolong time) and `approval.py` (at approve time, see ADR-01
driver #2) call this same public function, so there is exactly one place
that can decide "does this overlap a CONFIRMED reservation", and it is
testable on its own (see tests/test_availability_policy.py).

Contract
--------
Preconditions:
    - resource_id identifies a resource that may or may not exist (no FK
      check here -- that is the caller's responsibility, same as before).
    - start_time < end_time (callers validate duration/ordering upstream;
      this function does not re-validate it).
Postcondition:
    - Returns True iff at least one *CONFIRMED* reservation for the same
      resource_id has a time range that intersects [start_time, end_time)
      (half-open interval, BR-01). PENDING_APPROVAL, DRAFT, CANCELLED,
      REJECTED and EXPIRED reservations never count -- only CONFIRMED
      blocks a slot (BR-02, BR-12).
Failure behavior:
    - Never raises on its own. A caller passing an invalid range is a
      caller bug, not an availability-policy concern.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .db import ReservationORM
from .models import ReservationState


def has_overlap(
    session: Session,
    resource_id: str,
    start_time: datetime,
    end_time: datetime,
    exclude_reservation_id: str | None = None,
) -> bool:
    """True if resource_id already has a CONFIRMED reservation overlapping
    [start_time, end_time). See module docstring for the full contract."""
    query = session.query(ReservationORM).filter(
        ReservationORM.resource_id == resource_id,
        ReservationORM.state == ReservationState.CONFIRMED,
        ReservationORM.start_time < end_time,
        ReservationORM.end_time > start_time,
    )
    if exclude_reservation_id is not None:
        query = query.filter(ReservationORM.id != exclude_reservation_id)
    return session.query(query.exists()).scalar()