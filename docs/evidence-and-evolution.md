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

# C02: Change Impact and Evidence

**Change C02:** some Resources require approval by an authorized person (admin) before a Reservation can become CONFIRMED. Approval may be delayed, rejected, or may expire. This applies to both logged-in users and anonymous users.

> **Note on verification:** the code was only read, not run. As delivered, the application would not start (see "Mismatches found"). The verification examples are therefore listed as scenarios, and the actual results must be filled in. It is assumed that `models.py` is unchanged (it was not included in the second upload).

---

## Change Impact C02

### Changed condition
Some Resources require approval by an authorized person (admin) before a Reservation can become CONFIRMED. Approval may be delayed, rejected, or may expire.

### Affected requirements / parts of the specification
- **Reservation confirmation (DRAFT → ?).** Confirmation no longer always leads to CONFIRMED. For a resource with the `requires_approval` flag it leads to the new PENDING_APPROVAL state.
- **Reservation lifecycle.** The states PENDING_APPROVAL, REJECTED and EXPIRED are added.
- **Roles and permissions.** A new admin role (`AccountORM.is_admin`) and authorization on the approve / reject / expiration operations.
- **Resource.** Gains an "requires approval" property. A VIP spot is added to the seed data.
- **Time behavior.** An approval deadline (24 h, `approval_expires_at`) and an expiration mechanism are introduced.
- **Notifications.** The confirmation is sent only after approval. Nothing is sent for pending, rejection or expiry (the interface currently only supports `send_reservation_confirmed`).
- **Non-overlap rule.** Its meaning is refined: only CONFIRMED reservations block a slot, PENDING_APPROVAL does not hold it. The overlap is therefore re-checked on approval.

### Unaffected requirements / parts + why
| Part | Why it does not change |
|---|---|
| Operating hours 06:00–23:00, 30-min step, max 4 h, start in the future | These rules concern time and duration, not the approval path. They are validated in `create_draft`, before any approval takes place. |
| Creating a draft (DRAFT), anonymous and logged-in | Approval only begins at `confirm`. |
| Non-overlap of CONFIRMED reservations | The rule itself is unchanged, it is just additionally checked at `approve`. |
| `check_availability`, `/availability`, `/availability-grid` | Still count only CONFIRMED reservations. A pending reservation does not block a slot (see unknowns). |
| Registration, login, logout, session tokens, password hashing | Admin is just a flag on an existing account. The login mechanism stays the same. |
| Ownership check on `cancel` | Rule unchanged (an account cancels its own, an anonymous user cancels anonymous ones). Admin cannot yet cancel other people's reservations. |
| `prolong` | Unchanged, but it raises an open question (see unknowns). |
| Notification boundary (interface) | Interface is the same, no methods were added. |
| `/config`, `/resources`, `/reservations/mine` | Contract unchanged. The `requires_approval` flag is not yet exposed through the API. |

### New actor / operations, if any
- **Admin** (authorized person): a specialization of the logged-in user with `is_admin = True`.
- **Time / scheduler:** an actor for expiration. In the code it is currently replaced by a manual admin endpoint or cron.
- **New operations:**
  - Approve: `POST /reservations/{id}/approve`
  - Reject: `POST /reservations/{id}/reject`
  - Expire pending: `POST /admin/reservations/trigger-expiration` → `expire_pending`
- **Changed operation:** Confirm reservation now has two branches depending on the resource.

### Changed rules / meaning of states
| State | Meaning | Entered by | Left by |
|---|---|---|---|
| DRAFT | Draft, does not block the slot | create | confirm, cancel |
| **PENDING_APPROVAL** (new) | Waiting for admin, does not block the slot, 24 h deadline running | confirm (resource with `requires_approval`) | approve, reject, expire, cancel |
| CONFIRMED | Confirmed, blocks the slot | confirm (regular resource), approve | prolong, cancel |
| **REJECTED** (new) | Admin rejected, final | reject | – |
| **EXPIRED** (new) | Approval deadline passed, final | expire_pending | – |
| CANCELLED | Cancelled by the user, final | cancel | – |

New rules:
- A resource with `requires_approval` cannot be confirmed directly.
- `approve` may be performed only by an admin, only from PENDING_APPROVAL, and after re-checking overlap.
- `reject` may be performed only by an admin, and only from PENDING_APPROVAL.
- `expire_pending` marks PENDING_APPROVAL reservations whose `approval_expires_at` has passed as EXPIRED.

### Use case diagram change
In uml-ult.png, uml is an old file before fixing mismatches in C02, but kept for documentation purposes in regards to the process.

Admin is also a logged-in user. Only the use cases marked NEW and the branching in "Confirm reservation" changed.

### State diagram change
In stateX.png files

### New verification examples
| # | Scenario | Expected result |
|---|---|---|
| 1 | Confirm a reservation on a regular spot | CONFIRMED, notification sent (unchanged from C01) |
| 2 | Confirm a reservation on the VIP spot | PENDING_APPROVAL, `approval_expires_at` ≈ now + 24 h, no notification sent |
| 3 | Admin approves a pending reservation | CONFIRMED, `approval_expires_at = None`, notification sent |
| 4 | Admin rejects a pending reservation | REJECTED, slot remains free |
| 5 | Non-admin / anonymous user calls approve or reject | 403 |
| 6 | Approve from a state other than PENDING_APPROVAL | 400 |
| 7 | Two pending reservations on the same slot, the first is approved, then the second | Second: 400 (overlap), stays PENDING_APPROVAL |
| 8 | Pending reservation with an expired deadline, trigger-expiration is called | EXPIRED, count returned in the response |
| 9 | Pending reservation with an expired deadline, expiration has not run yet, admin calls approve | 400 expected, but the code approves it (mismatch no. 6) |
| 10 | Anonymous pending reservation, admin approves | CONFIRMED, notification goes to the plate number (`user_id`) |
| 11 | Pending on the VIP spot, meanwhile an overlapping one is confirmed | Approve fails because overlap is re-checked |

### Architectural drivers for C03

1. **Time and expiration.** Expiration is currently lazy and triggered manually. An autonomous time component (scheduler) is needed, along with a lazy vs. eager decision. Races between approve and expire follow from this.
2. **Concurrency.** The "check overlap, then write" sequence is not atomic. Concurrent approval of two overlapping pending reservations can confirm both. A transactional or DB-level guarantee is needed.
3. **Asynchronous notifications.** Approval arrives hours later and outside the original request. Notifications must be reliable (retry, outbox) and the interface must be extended for pending / rejected / expired.
4. **Authorization.** Currently a global `is_admin`. The assignment speaks of an "authorized person" for a resource, so per-resource permissions (RBAC) may be needed.
5. **Anonymous user with no return channel.** An anonymous user has no contact, only a plate number, and there is no endpoint to look up a reservation's status.
6. **Audit.** `admin_account_id` is passed in but never stored.
7. **Schema evolution.** `create_all` does not add columns to an existing DB, so migrations are needed.
8. **Model consistency.** `models.py` has drifted from the ORM (states, fields).
9. **Time zone.** `datetime.now()` and naive datetimes will diverge once a scheduler and multiple instances are involved.

---

## Evidence C02: specification → running application

### Accepted baseline
State of C01: reservations with DRAFT → CONFIRMED → CANCELLED, operating hours, 30-min step, max 4 h, non-overlap of CONFIRMED, accounts with session tokens, ownership check on `cancel`, notification stub.

### Basic operations demonstrated
Creating a draft, confirming (both branches), approving, rejecting, expiring, cancelling, availability.

### Verification examples actually performed
Scenarios 1–11 above.

### Mismatches found and how they were resolved
| # | Mismatch | Proposed resolution |
|---|---|---|
| 1 | `approve` does not check `approval_expires_at`, so an expired but not yet expired-marked reservation can be approved | In `approve`, reject after the deadline, or mark it EXPIRED first |
| 2 | `cancel` allows cancelling REJECTED and EXPIRED reservations (it only checks for CANCELLED) | Allow cancel only from DRAFT, PENDING_APPROVAL, CONFIRMED |
| 3 | There is no way to create an admin (`is_admin` is never set) and `AccountResponse` does not expose it | Seed an admin or provide a CLI script, add `is_admin` to the response |
| 4 | The deadline is 24 h regardless of the reservation start, so approval can arrive after the start | Cap the deadline at `min(24 h, start_time)` |

The resolutions are not yet implemented; they are proposals.

### Summary of the change impact
The change adds a branch in confirmation, three new states, an admin role and time-driven expiration. The rules for operating hours, duration, non-overlap and authentication remain. The biggest impact is on the state diagram, authorization, and the ties to time, notifications and concurrency (the basis for C03).

### Remaining assumptions / unknowns
- What "cancel" means in the assignment. Implemented as rejecting a pending reservation, but an admin cannot cancel other people's already-confirmed reservations.
- Do pending reservations block the slot? Implemented as no, so two users can wait on the same slot.
- `prolong` on a resource requiring approval bypasses approval, since extending a confirmed reservation does not require a new approval.
- Behavior when notification fails after commit (unchanged from C01).

### Architectural drivers carried over to C03
Points 1–9 from "Change Impact": expiration / scheduler, concurrency, asynchronous reliable notifications, authorization, anonymous user with no return channel, audit, schema migration, model consistency and time zones.

### Application commit / tag
initial commit:
593435b925f999066b9c05e94ce76dc68fbf0d48
merge:
dfed555a992608506e109724e1223c0f4e4a36e0
