"""Application/business logic for reservations: lifecycle + the core rules.

Encodes the rules from the Project Frame / specification:
- BR-01 interval semantics ([start,end))
- BR-02 common rule: two CONFIRMED reservations of the same resource must
  not overlap
- BR-03 lifecycle: DRAFT -> CONFIRMED -> CANCELLED (+ the approval branch)
- BR-04 domain-specific rule: campus parking operating hours
- BR-05 a reservation's start time must not be in the past
- BR-06 duration must be a multiple of 30 minutes, up to 4 hours
- BR-07 cancellation authorization (ownership)

C03 architecture decision (see docs/architecture-and-decisions.md, ADR-01):
this module owns the Reservation lifecycle EXCEPT the outcome of an
approval decision. It performs the single entry transition
DRAFT -> PENDING_APPROVAL (inside confirm(), when the resource requires
approval), but it never sets REJECTED or EXPIRED, and it is not the one
that decides PENDING_APPROVAL -> CONFIRMED. Those three transitions are
owned exclusively by `approval.py`. This split is what
tests/test_architecture_rule.py checks automatically.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from sqlalchemy.orm import Session

from .db import ReservationORM, ResourceORM
from .models import Reservation, ReservationState
from .notification import NotificationService

# Domain-specific business rule: campus parking operating hours.
OPERATING_HOURS_START = time(6, 0)
OPERATING_HOURS_END = time(23, 0)

# Reservations must be booked in fixed increments, and can't run forever.
RESERVATION_STEP_MINUTES = 30
MAX_DURATION_MINUTES = 240  # 4 hours -- a reasonable cap for one parking slot

# How long a PENDING_APPROVAL reservation waits before it is eligible to
# expire. Owned here because it's created at the same moment as the
# PENDING_APPROVAL entry transition; approval.py is what actually acts on it.
APPROVAL_WINDOW = timedelta(hours=24)

# States from which a reservation may still be cancelled by its owner.
# REJECTED and EXPIRED are terminal outcomes of the approval workflow and
# are intentionally excluded (fixes evidence-and-evolution.md "Mismatches
# found" #2: cancel used to only reject an already-CANCELLED reservation,
# so a REJECTED/EXPIRED one could be silently re-labelled CANCELLED).
CANCELLABLE_STATES = {
    ReservationState.DRAFT,
    ReservationState.PENDING_APPROVAL,
    ReservationState.CONFIRMED,
}


class ReservationError(Exception):
    """Raised when a requested operation violates a business rule."""


class NotAuthorizedError(ReservationError):
    """Raised when the requester is not allowed to act on this reservation.

    Kept as a subclass of ReservationError so existing callers that only
    catch ReservationError still catch this too; main.py catches it
    specifically first to return 403 instead of 400.
    """


def _within_operating_hours(start_time: datetime, end_time: datetime) -> bool:
    if end_time <= start_time:
        return False
    return (
        OPERATING_HOURS_START <= start_time.time() <= OPERATING_HOURS_END
        and OPERATING_HOURS_START <= end_time.time() <= OPERATING_HOURS_END
    )


def _is_valid_duration(start_time: datetime, end_time: datetime) -> bool:
    if end_time <= start_time:
        return False
    duration_minutes = (end_time - start_time).total_seconds() / 60
    return (
        duration_minutes % RESERVATION_STEP_MINUTES == 0
        and 0 < duration_minutes <= MAX_DURATION_MINUTES
    )


def _not_in_the_past(start_time: datetime) -> bool:
    return start_time >= datetime.now()


def _has_overlapping_confirmed(
    session: Session,
    resource_id: str,
    start_time: datetime,
    end_time: datetime,
    exclude_reservation_id: str | None = None,
) -> bool:
    query = session.query(ReservationORM).filter(
        ReservationORM.resource_id == resource_id,
        ReservationORM.state == ReservationState.CONFIRMED,
        ReservationORM.start_time < end_time,
        ReservationORM.end_time > start_time,
    )
    if exclude_reservation_id is not None:
        query = query.filter(ReservationORM.id != exclude_reservation_id)
    return session.query(query.exists()).scalar()


def check_availability(
    session: Session, resource_id: str, start_time: datetime, end_time: datetime
) -> bool:
    """True if a CONFIRMED reservation could legally be made for this slot.

    Only CONFIRMED reservations block a slot -- PENDING_APPROVAL does not
    (BR-12 / approval_workflow_impact_analysis.md: explicitly non-blocking,
    so two users may wait on the same slot and the first approval wins)."""
    if not _within_operating_hours(start_time, end_time):
        return False
    return not _has_overlapping_confirmed(session, resource_id, start_time, end_time)


def create_draft(
    session: Session,
    resource_id: str,
    user_id: str,
    start_time: datetime,
    end_time: datetime,
    user_name: str | None = None,
    account_id: str | None = None,
) -> ReservationORM:
    if not _within_operating_hours(start_time, end_time):
        raise ReservationError(
            f"reservation must be within operating hours "
            f"({OPERATING_HOURS_START}-{OPERATING_HOURS_END}) and end after it starts"
        )
    if not _not_in_the_past(start_time):
        raise ReservationError("reservation start time must be in the future")
    if not _is_valid_duration(start_time, end_time):
        raise ReservationError(
            f"reservation duration must be a multiple of {RESERVATION_STEP_MINUTES} minutes, "
            f"up to {MAX_DURATION_MINUTES} minutes"
        )
    reservation = ReservationORM(
        id=Reservation.new_id(),
        resource_id=resource_id,
        user_id=user_id,
        user_name=user_name,
        account_id=account_id,
        start_time=start_time,
        end_time=end_time,
        state=ReservationState.DRAFT,
    )
    session.add(reservation)
    session.commit()
    return reservation


def confirm(
    session: Session, reservation_id: str, notifier: NotificationService
) -> ReservationORM:
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")
    if reservation.state != ReservationState.DRAFT:
        raise ReservationError(
            f"cannot confirm a reservation in state {reservation.state}, must be DRAFT"
        )
    if _has_overlapping_confirmed(
        session,
        reservation.resource_id,
        reservation.start_time,
        reservation.end_time,
        exclude_reservation_id=reservation.id,
    ):
        raise ReservationError("resource already has an overlapping confirmed reservation")

    resource = session.get(ResourceORM, reservation.resource_id)
    if resource is not None and resource.requires_approval:
        # The single entry transition into the approval workflow. The
        # *outcome* (CONFIRMED / REJECTED / EXPIRED) is decided exclusively
        # by approval.py -- see the module docstring above and ADR-01.
        reservation.state = ReservationState.PENDING_APPROVAL
        reservation.approval_expires_at = datetime.now() + APPROVAL_WINDOW
        session.commit()
        return reservation

    reservation.state = ReservationState.CONFIRMED
    session.commit()
    notifier.send_reservation_confirmed(reservation.user_id, reservation.id)
    return reservation


def cancel(
    session: Session,
    reservation_id: str,
    requesting_account_id: str | None = None,
) -> ReservationORM:
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")
    if reservation.state not in CANCELLABLE_STATES:
        raise ReservationError(
            f"cannot cancel a reservation in state {reservation.state}"
        )

    # Ownership check: an account-tied reservation can only be cancelled by
    # that same account; an anonymous reservation can only be cancelled
    # anonymously. This closes the gap where the reservation ID alone used
    # to be enough to cancel anyone's booking.
    if reservation.account_id is not None:
        if requesting_account_id != reservation.account_id:
            raise NotAuthorizedError("you are not authorized to cancel this reservation")
    elif requesting_account_id is not None:
        raise NotAuthorizedError("you are not authorized to cancel this reservation")

    reservation.state = ReservationState.CANCELLED
    reservation.approval_expires_at = None
    session.commit()
    return reservation


def prolong(session: Session, reservation_id: str, new_end_time: datetime) -> ReservationORM:
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")
    if reservation.state != ReservationState.CONFIRMED:
        raise ReservationError("only a CONFIRMED reservation can be prolonged")
    if not _within_operating_hours(reservation.start_time, new_end_time):
        raise ReservationError("prolonged reservation must stay within operating hours")
    if not _is_valid_duration(reservation.start_time, new_end_time):
        raise ReservationError(
            f"reservation duration must be a multiple of {RESERVATION_STEP_MINUTES} minutes, "
            f"up to {MAX_DURATION_MINUTES} minutes"
        )
    if _has_overlapping_confirmed(
        session,
        reservation.resource_id,
        reservation.start_time,
        new_end_time,
        exclude_reservation_id=reservation.id,
    ):
        raise ReservationError("prolonging would overlap another confirmed reservation")

    reservation.end_time = new_end_time
    session.commit()
    return reservation


def list_reservations_for_account(session: Session, account_id: str) -> list[ReservationORM]:
    return (
        session.query(ReservationORM)
        .filter(ReservationORM.account_id == account_id)
        .order_by(ReservationORM.start_time.desc())
        .all()
    )
