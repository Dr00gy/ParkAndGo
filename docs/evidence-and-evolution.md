# C01 Engineering Spike

**Spike chosen: A — Persistence**

## Question / unknown
Does a reservation we create actually survive being written to a real
(on-disk) database and read back correctly, or is our "persistence" layer
secretly relying on in-process state that only happens to work within a
single run (e.g. an in-memory SQLite DB, or objects held alive by a shared
session)?

## What we did
Wrote `tests/test_persistence_spike.py`:
1. Created a reservation through the normal service layer
   (`services.create_draft`), against an on-disk SQLite database file
   (`sqlite:///spike_persistence_test.db`) — not `:memory:`.
2. Closed and disposed of that session and engine entirely.
3. Opened a **completely new** engine and session pointed at the same
   database file.
4. Read the reservation back by ID and asserted every field
   (resource, user, start/end time, state) matched what was written.

Ran it together with the rest of the test suite:

```
$ python -m pytest -v
tests/test_persistence_spike.py::test_reservation_survives_a_fresh_engine_and_session PASSED
tests/test_reservation_service.py::test_overlapping_confirmed_reservations_are_rejected PASSED
tests/test_reservation_service.py::test_non_overlapping_confirmed_reservations_are_allowed PASSED
tests/test_reservation_service.py::test_reservation_outside_operating_hours_is_rejected PASSED
tests/test_reservation_service.py::test_cancel_frees_up_the_slot_for_a_new_confirmation PASSED
tests/test_reservation_service.py::test_prolong_into_another_confirmed_reservation_is_rejected PASSED

6 passed in 0.27s
```

We also manually exercised the HTTP layer end-to-end (`POST /reservations`
→ `POST /reservations/{id}/confirm` → `GET /availability`) via FastAPI's
test client to confirm the walking skeleton works through the API, not
just the service layer directly.

## Observed result
The reservation written by the first engine/session was read back
correctly by the second, independent engine/session, with all fields
intact and the state correctly persisted as `DRAFT`. This confirms the
persistence layer is real (backed by an actual database file on disk),
not an artifact of shared in-process state.

## Decision / what changes because of the result
Persistence is confirmed to work at the level we need for CP1. Two
follow-ups were surfaced by writing this spike (not fixed now, but
recorded so they aren't lost):
1. The overlap check (`_has_overlapping_confirmed`) is a plain
   read-then-write within one session — fine for a single-process demo,
   but not safe under concurrent writers. This directly informs the
   selected future pressure (Q — scale) in `intent-and-change.md`.
2. We're using a single shared SQLite file (`parking.db`) for the running
   API. SQLite handles concurrent writers poorly; if we scale past a
   single-process demo this is one of the first things to swap (e.g. for
   Postgres), consistent with the "Persistence" rationale in
   `architecture-and-decisions.md`.

# C02 Specification — Running application

## Accepted baseline

## Demonstrated basic operations

## Realised verification examples

## Found issue / misalignment and a practical solution

## Summary of after-effects caused by the changes

## Remaining premise / unknown

## Architecture drivers translated into C03

## Commit / tag of the app

## After-effects of changes in C02 in-depth

### Changed conditional

### Affected requirements or parts of specification

### Unaffected reqs. or parts and why

### New actor in the system or operation

### Changed rules or semantics of a state

### Change of Use Case diagrams

### Change of State diagrams

### New Use Cases

### Architecture drivers for C03
