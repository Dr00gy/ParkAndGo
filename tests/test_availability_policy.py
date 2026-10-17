"""C05 unit tests for the Availability Policy contract (src/availability.py).

These verify the DD decision made when has_overlap() was extracted from a
private services.py helper into its own module: "only a CONFIRMED
reservation blocks a slot" is now a directly testable contract, not an
implementation detail two other modules happened to agree on.

Test level: unit -- a single pure function against an in-memory DB, no
HTTP, no other module involved. This is the right level because the
contract itself (what counts as 'overlap') is exactly what's being
verified, independent of who calls it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import availability
from src.db import ReservationORM, get_engine, get_session_factory, init_db
from src.models import ReservationState


def future(hour: int, minute: int = 0, days: int = 7) -> datetime:
    return (datetime.now() + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


@pytest.fixture()
def session():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    SessionLocal = get_session_factory(engine)
    s = SessionLocal()
    yield s
    s.close()


def _add_reservation(session, state, start, end, resource_id="spot-1", rid="r1"):
    r = ReservationORM(
        id=rid,
        resource_id=resource_id,
        user_id="plate-1",
        start_time=start,
        end_time=end,
        state=state,
    )
    session.add(r)
    session.commit()
    return r


def test_has_overlap_detects_confirmed_overlap(session):
    """Interface contract: a CONFIRMED reservation that intersects the
    requested range must be reported as an overlap."""
    _add_reservation(session, ReservationState.CONFIRMED, future(9), future(11))
    assert availability.has_overlap(session, "spot-1", future(10), future(12)) is True


def test_has_overlap_respects_half_open_interval(session):
    """BR-01: [start, end) is half-open -- a reservation ending exactly
    when another starts must NOT count as an overlap."""
    _add_reservation(session, ReservationState.CONFIRMED, future(9), future(10))
    assert availability.has_overlap(session, "spot-1", future(10), future(11)) is False


def test_has_overlap_ignores_non_confirmed_states(session):
    """Interface contract (BR-12): PENDING_APPROVAL, DRAFT, CANCELLED,
    REJECTED and EXPIRED must never block a slot -- only CONFIRMED does.
    This is the exact rule that lets two users wait on the same VIP spot
    at once."""
    for state in (
        ReservationState.PENDING_APPROVAL,
        ReservationState.DRAFT,
        ReservationState.CANCELLED,
        ReservationState.REJECTED,
        ReservationState.EXPIRED,
    ):
        session.query(ReservationORM).delete()
        session.commit()
        _add_reservation(session, state, future(9), future(11))
        assert availability.has_overlap(session, "spot-1", future(9), future(11)) is False, (
            f"state {state} must not block a slot"
        )


def test_has_overlap_excludes_given_reservation_id(session):
    """A reservation must not be reported as overlapping itself -- needed
    by prolong(), which re-checks overlap against the reservation's own
    (about to change) end time."""
    r = _add_reservation(session, ReservationState.CONFIRMED, future(9), future(11))
    assert (
        availability.has_overlap(
            session, "spot-1", future(9), future(11), exclude_reservation_id=r.id
        )
        is False
    )