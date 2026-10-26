"""C04 measurement: BR-02 (no overlapping CONFIRMED reservations) under the
10x concurrent workload selected as the future pressure in
docs/intent-and-change.md ("Q -- Quality / Scale").

This test exists because of C06 finding F1 (AutoRepo's review, 2026-10-25):
`docs/intent-and-change.md` *describes* the 10x concurrency pressure and
names the race risk, but until now nothing in the project actually measured
it -- the existing tests (`test_approval_workflow.py::
test_concurrent_overlapping_approvals_second_is_rejected`) only exercise two
*sequential* calls, not a real concurrent burst.

Criterion measured (this is the evaluable criterion C04 was missing):
  Under 10 concurrent confirm attempts for the same resource and the same
  fully-overlapping time slot, exactly one must end up CONFIRMED and the
  other nine must be rejected with a ReservationError -- never zero, never
  more than one CONFIRMED, and no silent corruption/crash.

This is a correctness measurement (does the invariant hold under load), not
a performance/latency measurement -- the C04 quality concern as originally
written ("prevention of double-booking") is about correctness under
concurrency, not response time, so that is what this test actually measures
and reports.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pytest

from src import services
from src.db import ResourceORM, get_session_factory, init_db
from src.models import ReservationState
from src.notification import StubNotificationService

CONCURRENT_REQUESTS = 10  # the exact "10x" figure named in intent-and-change.md


def _attempt_one_booking(session_factory, resource_id, start, end, plate):
    """Runs in its own thread with its own Session (SQLAlchemy sessions are
    not thread-safe to share) against the *same* underlying SQLite file, so
    the overlap check in availability.has_overlap() is genuinely racing
    against the other threads' checks -- not just called 10 times in a
    for-loop on one connection."""
    session = session_factory()
    notifier = StubNotificationService()
    t0 = time.perf_counter()
    try:
        draft = services.create_draft(session, resource_id, plate, start, end)
        confirmed = services.confirm(session, draft.id, notifier)
        return {"plate": plate, "state": confirmed.state, "error": None,
                "seconds": time.perf_counter() - t0}
    except services.ReservationError as exc:
        return {"plate": plate, "state": None, "error": str(exc),
                "seconds": time.perf_counter() - t0}
    finally:
        session.close()


@pytest.mark.xfail(
    reason=(
        "Documents, with an actual measurement, the race condition already "
        "named as an accepted risk in docs/intent-and-change.md (future "
        "pressure Q/Scale) and in ADR-01 / docs/evidence-and-evolution.md "
        "('Remaining design risk'): the overlap check in "
        "availability.has_overlap() is a plain read-then-write with no "
        "DB-level transaction isolation or uniqueness constraint, so two "
        "truly concurrent confirm() calls on the same slot can both read "
        "'no overlap' before either commits. This is expected to fail under "
        "real thread-level concurrency until that constraint is added -- "
        "which is deliberately out of scope for this project per the "
        "already-documented decision not to add DB-level locking. If this "
        "test ever unexpectedly PASSES, strict=False lets it go green "
        "without breaking the build, but check the printed report either way."
    ),
    strict=False,
)
def test_ten_concurrent_confirms_on_the_same_slot_never_double_book(tmp_path):
    db_path = tmp_path / "concurrency_measurement.db"
    # check_same_thread=False: multiple threads *do* open their own
    # connections against this same file through the shared engine, which is
    # exactly the scenario intent-and-change.md's future pressure describes
    # (one shared parking.db, many concurrent requests).
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    init_db(engine)
    SessionLocal = get_session_factory(engine)

    setup_session = SessionLocal()
    setup_session.add(ResourceORM(id="measure-1", label="Measurement spot", requires_approval=False))
    setup_session.commit()
    setup_session.close()

    start = (datetime.now() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    wall_clock_start = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as pool:
        futures = [
            pool.submit(_attempt_one_booking, SessionLocal, "measure-1", start, end, f"plate-{i}")
            for i in range(CONCURRENT_REQUESTS)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    wall_clock_seconds = time.perf_counter() - wall_clock_start

    confirmed = [r for r in results if r["state"] == ReservationState.CONFIRMED]
    rejected = [r for r in results if r["error"] is not None]
    per_request_seconds = sorted(r["seconds"] for r in results)

    report = (
        f"\n--- C04 measurement: {CONCURRENT_REQUESTS} concurrent confirm() calls, "
        f"same resource + same slot ---\n"
        f"confirmed: {len(confirmed)} (must be exactly 1)\n"
        f"rejected (overlap): {len(rejected)} (must be exactly {CONCURRENT_REQUESTS - 1})\n"
        f"total wall-clock time: {wall_clock_seconds:.4f}s\n"
        f"per-request time, fastest/median/slowest: "
        f"{per_request_seconds[0]:.4f}s / {per_request_seconds[len(per_request_seconds)//2]:.4f}s / "
        f"{per_request_seconds[-1]:.4f}s\n"
        f"winner: {confirmed[0]['plate'] if confirmed else 'NONE'}\n"
    )
    print(report)
    # Persist the measurement so it is evidence, not just a console line
    # that disappears after the test run.
    (tmp_path.parent / "concurrency_measurement_result.txt").write_text(report)

    # The actual C04 criterion: BR-02 must hold under the declared load.
    assert len(confirmed) == 1, f"expected exactly 1 CONFIRMED, got {len(confirmed)}: {results}"
    assert len(rejected) == CONCURRENT_REQUESTS - 1
    assert all("overlap" in r["error"] for r in rejected)
