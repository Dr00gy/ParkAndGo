from datetime import datetime, timedelta

import pytest

from src import services
from src.db import get_engine, get_session_factory, init_db
from src.notification import StubNotificationService


def future(hour: int, minute: int = 0, days: int = 7) -> datetime:
    """A datetime `days` days from now at a fixed hour/minute, so tests
    stay valid regardless of when they're run (create_draft rejects
    start times in the past)."""
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


def test_overlapping_confirmed_reservations_are_rejected(session):
    notifier = StubNotificationService()
    r1 = services.create_draft(session, "spot-1", "alice", future(9), future(11))
    services.confirm(session, r1.id, notifier)

    r2 = services.create_draft(session, "spot-1", "bob", future(10), future(12))
    with pytest.raises(services.ReservationError):
        services.confirm(session, r2.id, notifier)


def test_non_overlapping_confirmed_reservations_are_allowed(session):
    notifier = StubNotificationService()
    r1 = services.create_draft(session, "spot-1", "alice", future(9), future(10))
    services.confirm(session, r1.id, notifier)

    r2 = services.create_draft(session, "spot-1", "bob", future(10), future(11))
    services.confirm(session, r2.id, notifier)  # should not raise
    assert len(notifier.sent) == 2


def test_reservation_outside_operating_hours_is_rejected(session):
    with pytest.raises(services.ReservationError):
        services.create_draft(session, "spot-1", "alice", future(4), future(5))


def test_reservation_in_the_past_is_rejected(session):
    with pytest.raises(services.ReservationError):
        services.create_draft(
            session, "spot-1", "alice",
            datetime.now() - timedelta(days=1),
            datetime.now() - timedelta(days=1) + timedelta(hours=1),
        )


def test_reservation_duration_must_be_a_multiple_of_30_minutes(session):
    with pytest.raises(services.ReservationError):
        services.create_draft(session, "spot-1", "alice", future(9, 0), future(9, 0).replace(minute=40))


def test_cancel_frees_up_the_slot_for_a_new_confirmation(session):
    notifier = StubNotificationService()
    r1 = services.create_draft(session, "spot-1", "alice", future(9), future(11))
    services.confirm(session, r1.id, notifier)
    services.cancel(session, r1.id)

    r2 = services.create_draft(session, "spot-1", "bob", future(9), future(11))
    services.confirm(session, r2.id, notifier)  # should not raise, r1 is cancelled


def test_prolong_into_another_confirmed_reservation_is_rejected(session):
    notifier = StubNotificationService()
    r1 = services.create_draft(session, "spot-1", "alice", future(9), future(10))
    services.confirm(session, r1.id, notifier)
    r2 = services.create_draft(session, "spot-1", "bob", future(11), future(12))
    services.confirm(session, r2.id, notifier)

    with pytest.raises(services.ReservationError):
        services.prolong(session, r1.id, future(11, 30))


def test_list_reservations_for_account(session):
    notifier = StubNotificationService()
    r1 = services.create_draft(
        session, "spot-1", "alice", future(9), future(10), account_id="acc-1"
    )
    services.confirm(session, r1.id, notifier)
    services.create_draft(session, "spot-2", "bob", future(9), future(10), account_id="acc-2")

    mine = services.list_reservations_for_account(session, "acc-1")
    assert [r.id for r in mine] == [r1.id]