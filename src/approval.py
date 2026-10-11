"""Approval Workflow: owns every transition OUT of PENDING_APPROVAL.

This module exists as its own file because of ADR-01 (see
docs/architecture-and-decisions.md): the C02 approval-workflow change
introduced a second actor (an admin) and a delayed, time-driven decision
that can race against other operations. We decided to keep it in the same
deployable as the rest of the reservation system (Alternative A), but give
it a hard module boundary anyway, so that:

- exactly one place in the codebase decides PENDING_APPROVAL -> CONFIRMED,
  PENDING_APPROVAL -> REJECTED, and PENDING_APPROVAL -> EXPIRED;
- that ownership is mechanically checkable (tests/test_architecture_rule.py
  greps services.py and asserts it never mentions REJECTED or EXPIRED).

services.py still owns the single entry transition DRAFT -> PENDING_APPROVAL
(inside confirm()), because that is a creation-time routing decision, not
an approval outcome -- the same split the C03 assignment's own G3 example
table uses (different owners for different transitions of the same state).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .db import ReservationORM
from .models import ReservationState
from .notification import NotificationService
from .services import ReservationError, _has_overlapping_confirmed


def approve(
    session: Session,
    reservation_id: str,
    admin_account_id: str,
    notifier: NotificationService,
) -> ReservationORM:
    """An authorized admin approves a PENDING_APPROVAL reservation.

    Fixes evidence-and-evolution.md "Mismatches found" #1: this used to
    approve a reservation whose approval_expires_at had already passed
    (because expiry was only applied lazily by a separate endpoint). Now
    approve() itself refuses -- and flips the row to EXPIRED -- once the
    deadline is in the past, so "approve" can never race past "expire".
    """
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")

    if reservation.state != ReservationState.PENDING_APPROVAL:
        raise ReservationError("only reservations in PENDING_APPROVAL state can be approved")

    if reservation.approval_expires_at is not None and reservation.approval_expires_at < datetime.now():
        reservation.state = ReservationState.EXPIRED
        reservation.approval_expires_at = None
        session.commit()
        raise ReservationError("approval window has expired; reservation marked EXPIRED")

    # Re-check overlap: time has passed since the reservation entered
    # PENDING_APPROVAL, and another reservation for the same slot may have
    # been confirmed in the meantime (BR-02 must still hold on the way out).
    if _has_overlapping_confirmed(
        session,
        reservation.resource_id,
        reservation.start_time,
        reservation.end_time,
        exclude_reservation_id=reservation.id,
    ):
        raise ReservationError(
            "resource already has an overlapping confirmed reservation, cannot approve"
        )

    reservation.state = ReservationState.CONFIRMED
    reservation.approval_expires_at = None
    session.commit()
    notifier.send_reservation_confirmed(reservation.user_id, reservation.id)
    return reservation


def reject(
    session: Session,
    reservation_id: str,
    admin_account_id: str,
    notifier: NotificationService,
) -> ReservationORM:
    """An authorized admin rejects a PENDING_APPROVAL reservation."""
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")

    if reservation.state != ReservationState.PENDING_APPROVAL:
        raise ReservationError("only reservations in PENDING_APPROVAL state can be rejected")

    reservation.state = ReservationState.REJECTED
    reservation.approval_expires_at = None
    session.commit()
    # No NotificationService method exists yet for a rejection -- recorded
    # as an architectural driver (notification interface needs extending).
    return reservation


def expire_pending(session: Session) -> int:
    """Finds every PENDING_APPROVAL reservation whose deadline has passed
    and marks it EXPIRED. Intended to be called periodically (currently a
    manually-triggered admin endpoint; see architectural driver #1 in
    docs/evidence-and-evolution.md about replacing this with a scheduler).
    """
    expired = (
        session.query(ReservationORM)
        .filter(
            ReservationORM.state == ReservationState.PENDING_APPROVAL,
            ReservationORM.approval_expires_at < datetime.now(),
        )
        .all()
    )

    for reservation in expired:
        reservation.state = ReservationState.EXPIRED
        reservation.approval_expires_at = None

    if expired:
        session.commit()

    return len(expired)
