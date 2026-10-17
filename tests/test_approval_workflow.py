"""C05 unit/component tests for the Approval Workflow unit (src/approval.py).

Derived directly from the C05 Detailed Design (see
docs/architecture-and-decisions.md, "C05 Detailed Design" section):
each test traces back to one DD decision -- a state transition, an
algorithm branch, a failure behavior, or a cross-module collaboration.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import approval, services
from src.db import ResourceORM, get_engine, get_session_factory, init_db
from src.models import ReservationState
from src.notification import StubNotificationService


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
    s.add(ResourceORM(id="vip-1", label="VIP test spot", requires_approval=True))
    s.commit()
    yield s
    s.close()


def _pending_reservation(session, start=None, end=None, deadline_hours=24):
    """Creates a DRAFT on the VIP resource, confirms it into
    PENDING_APPROVAL, then optionally back-dates the deadline for
    expiration tests."""
    notifier = StubNotificationService()
    start = start or future(9)
    end = end or future(11)
    r = services.create_draft(session, "vip-1", "plate-1", start, end)
    services.confirm(session, r.id, notifier)
    assert r.state == ReservationState.PENDING_APPROVAL
    if deadline_hours != 24:
        r.approval_expires_at = datetime.now() + timedelta(hours=deadline_hours)
        session.commit()
    return r


# -- state transition --------------------------------------------------

def test_approve_pending_within_deadline_confirms_and_notifies(session):
    notifier = StubNotificationService()
    r = _pending_reservation(session)

    approved = approval.approve(session, r.id, admin_account_id="admin-1", notifier=notifier)

    assert approved.state == ReservationState.CONFIRMED
    assert approved.approval_expires_at is None
    assert len(notifier.sent) == 1


def test_reject_pending_sets_rejected(session):
    notifier = StubNotificationService()
    r = _pending_reservation(session)

    rejected = approval.reject(session, r.id, admin_account_id="admin-1", notifier=notifier)

    assert rejected.state == ReservationState.REJECTED
    assert rejected.approval_expires_at is None


# -- algorithm branch: deadline check inside approve() ------------------

def test_approve_past_deadline_marks_expired_and_raises(session):
    """DD algorithm decision: approve() checks the deadline BEFORE the
    overlap re-check, and flips the row to EXPIRED itself rather than
    silently approving a stale request (fixes mismatch #1 from C02)."""
    notifier = StubNotificationService()
    r = _pending_reservation(session, deadline_hours=-1)  # deadline already passed

    with pytest.raises(services.ReservationError, match="expired"):
        approval.approve(session, r.id, admin_account_id="admin-1", notifier=notifier)

    session.refresh(r)
    assert r.state == ReservationState.EXPIRED
    assert len(notifier.sent) == 0


# -- failure behavior: wrong starting state -----------------------------

def test_approve_non_pending_state_raises(session):
    notifier = StubNotificationService()
    r = services.create_draft(session, "vip-1", "plate-1", future(9), future(11))
    # still DRAFT, never confirmed into PENDING_APPROVAL

    with pytest.raises(services.ReservationError, match="PENDING_APPROVAL"):
        approval.approve(session, r.id, admin_account_id="admin-1", notifier=notifier)


def test_reject_non_pending_state_raises(session):
    notifier = StubNotificationService()
    r = _pending_reservation(session)
    approval.reject(session, r.id, admin_account_id="admin-1", notifier=notifier)

    with pytest.raises(services.ReservationError, match="PENDING_APPROVAL"):
        approval.reject(session, r.id, admin_account_id="admin-1", notifier=notifier)


# -- collaboration: Approval Workflow <-> Availability Policy -----------

def test_concurrent_overlapping_approvals_second_is_rejected(session):
    """Component-level test: verifies the collaboration between
    ApprovalWorkflow and the Availability Policy (has_overlap), not either
    one in isolation. This is the scenario from C03 E3/H1: two PENDING
    reservations for the same slot, the first approval must win and the
    second must be rejected by the overlap re-check -- BR-02 must still
    hold after the delay, which is driver #2 from C03."""
    notifier = StubNotificationService()
    r1 = _pending_reservation(session, future(9), future(11))

    r2_draft = services.create_draft(session, "vip-1", "plate-2", future(9), future(11))
    # Can be confirmed into PENDING_APPROVAL too: PENDING_APPROVAL never
    # blocks a slot (BR-12), so a second person is allowed to wait.
    services.confirm(session, r2_draft.id, notifier)
    r2 = r2_draft

    approval.approve(session, r1.id, admin_account_id="admin-1", notifier=notifier)

    with pytest.raises(services.ReservationError, match="overlapping confirmed reservation"):
        approval.approve(session, r2.id, admin_account_id="admin-1", notifier=notifier)


# -- batch algorithm: expire_pending ------------------------------------

def test_expire_pending_only_expires_past_deadline(session):
    notifier = StubNotificationService()
    expired = _pending_reservation(session, future(9), future(11), deadline_hours=-1)
    still_waiting = _pending_reservation(
        session, future(13), future(15), deadline_hours=24
    )

    count = approval.expire_pending(session)

    session.refresh(expired)
    session.refresh(still_waiting)
    assert count == 1
    assert expired.state == ReservationState.EXPIRED
    assert still_waiting.state == ReservationState.PENDING_APPROVAL