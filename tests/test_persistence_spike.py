"""C01 Engineering Spike A -- Persistence.

Question/unknown: does a reservation we create actually survive being
written to a real (on-disk) database and read back by a completely fresh
engine/session -- i.e. is our persistence layer real, not just in-memory
state that happens to work within one process run?

What this test does:
1. Creates a reservation through the normal service layer, against an
   on-disk SQLite file (a real DB engine, not sqlite:///:memory:).
2. Throws away the engine and session entirely.
3. Opens a brand new engine/session pointed at the same file.
4. Reads the reservation back and verifies every field round-tripped.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from src import services
from src.db import ReservationORM, get_engine, get_session_factory, init_db

DB_FILE = "spike_persistence_test.db"
DB_URL = f"sqlite:///{DB_FILE}"

# A week out, so this test stays valid regardless of when it's run --
# create_draft rejects reservations with a start time in the past.
START = (datetime.now() + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0)
END = START + timedelta(hours=2)


def test_reservation_survives_a_fresh_engine_and_session():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    # --- Step 1: write, using one engine/session ---
    engine_1 = get_engine(DB_URL)
    init_db(engine_1)
    Session1 = get_session_factory(engine_1)
    session_1 = Session1()

    created = services.create_draft(
        session_1,
        resource_id="spot-42",
        user_id="alice",
        start_time=START,
        end_time=END,
    )
    created_id = created.id
    session_1.close()
    engine_1.dispose()

    # --- Step 2: read back with a completely fresh engine/session ---
    engine_2 = get_engine(DB_URL)
    Session2 = get_session_factory(engine_2)
    session_2 = Session2()

    reloaded = session_2.get(ReservationORM, created_id)

    assert reloaded is not None
    assert reloaded.id == created_id
    assert reloaded.resource_id == "spot-42"
    assert reloaded.user_id == "alice"
    assert reloaded.start_time == START
    assert reloaded.end_time == END
    assert reloaded.state.value == "DRAFT"

    session_2.close()
    engine_2.dispose()
    os.remove(DB_FILE)
