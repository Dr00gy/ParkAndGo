"""Application/business logic for reservations.

Encodes the rules from the Project Frame:
- common rule: two CONFIRMED reservations of the same resource must not overlap
- domain-specific rule: a reservation must start and end within campus
  parking operating hours
- state machine: DRAFT -> CONFIRMED -> CANCELLED
"""
from __future__ import annotations

from datetime import datetime, time
from sqlalchemy.orm import Session

from .db import ReservationORM
from .models import Reservation, ReservationState
from .notification import NotificationService

# Domain-specific business rule: campus parking operating hours.
OPERATING_HOURS_START = time(6, 0)
OPERATING_HOURS_END = time(23, 0)

# Reservations must be booked in fixed increments, and can't run forever.
RESERVATION_STEP_MINUTES = 30
MAX_DURATION_MINUTES = 240  # 4 hours -- a reasonable cap for one parking slot


class ReservationError(Exception):
    """Raised when a requested operation violates a business rule."""


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
    """True if a CONFIRMED reservation could legally be made for this slot."""
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

    reservation.state = ReservationState.CONFIRMED
    session.commit()
    notifier.send_reservation_confirmed(reservation.user_id, reservation.id)
    return reservation


def cancel(session: Session, reservation_id: str) -> ReservationORM:
    reservation = session.get(ReservationORM, reservation_id)
    if reservation is None:
        raise ReservationError(f"no reservation with id {reservation_id}")
    if reservation.state == ReservationState.CANCELLED:
        raise ReservationError("reservation is already cancelled")
    reservation.state = ReservationState.CANCELLED
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