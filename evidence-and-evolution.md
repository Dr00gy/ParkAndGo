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

Ran it together with the rest of the test suite (23 tests total as of
C05, after the approval-workflow, architecture-conformance and C05
unit/component tests were added — see the C03 and C05 sections below):

```
$ python -m pytest -v
tests/test_approval_workflow.py::test_approve_pending_within_deadline_confirms_and_notifies PASSED
tests/test_approval_workflow.py::test_reject_pending_sets_rejected PASSED
tests/test_approval_workflow.py::test_approve_past_deadline_marks_expired_and_raises PASSED
tests/test_approval_workflow.py::test_approve_non_pending_state_raises PASSED
tests/test_approval_workflow.py::test_reject_non_pending_state_raises PASSED
tests/test_approval_workflow.py::test_concurrent_overlapping_approvals_second_is_rejected PASSED
tests/test_approval_workflow.py::test_expire_pending_only_expires_past_deadline PASSED
tests/test_architecture_rule.py::test_services_module_never_sets_rejected_or_expired PASSED
tests/test_architecture_rule.py::test_services_module_does_not_transition_pending_approval_to_confirmed PASSED
tests/test_architecture_rule.py::test_approval_module_owns_the_three_outcome_transitions PASSED
tests/test_availability_policy.py::test_has_overlap_detects_confirmed_overlap PASSED
tests/test_availability_policy.py::test_has_overlap_respects_half_open_interval PASSED
tests/test_availability_policy.py::test_has_overlap_ignores_non_confirmed_states PASSED
tests/test_availability_policy.py::test_has_overlap_excludes_given_reservation_id PASSED
tests/test_persistence_spike.py::test_reservation_survives_a_fresh_engine_and_session PASSED
tests/test_reservation_service.py::test_overlapping_confirmed_reservations_are_rejected PASSED
tests/test_reservation_service.py::test_non_overlapping_confirmed_reservations_are_allowed PASSED
tests/test_reservation_service.py::test_reservation_outside_operating_hours_is_rejected PASSED
tests/test_reservation_service.py::test_reservation_in_the_past_is_rejected PASSED
tests/test_reservation_service.py::test_reservation_duration_must_be_a_multiple_of_30_minutes PASSED
tests/test_reservation_service.py::test_cancel_frees_up_the_slot_for_a_new_confirmation PASSED
tests/test_reservation_service.py::test_prolong_into_another_confirmed_reservation_is_rejected PASSED
tests/test_reservation_service.py::test_list_reservations_for_account PASSED

23 passed in 0.53s
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
follow-ups were surfaced by writing this spike (not fixed then, directly
relevant to the C03 decision below):
1. The overlap check (`_has_overlapping_confirmed`, now `availability.has_overlap`)
   is a plain read-then-write within one session — fine for a single-process
   demo, but not safe under concurrent writers. This directly informs the
   selected future pressure (Q — scale) in `intent-and-change.md`, and is
   the central driver behind ADR-01 in `c03-architecture.md`.
2. We're using a single shared SQLite file (`parking.db`) for the running
   API. SQLite handles concurrent writers poorly; if we scale past a
   single-process demo this is one of the first things to swap (e.g. for
   Postgres), consistent with the "Persistence" rationale in
   `architecture-and-decisions.md`.

---

# C02: Change Impact and Evidence

**Change C02:** some Resources require approval by an authorized person (admin) before a Reservation can become CONFIRMED. Approval may be delayed, rejected, or may expire. This applies to both logged-in users and anonymous users.

> **Update (C03):** the note that used to be here said "the code was only
> read, not run... the application would not start." That is no longer
> true. Three concrete bugs that prevented the application from starting
> were found and fixed during C03 (missing `Boolean` import in `db.py`,
> a broken `Resource` dataclass field in `models.py`, and mismatched
> seed-data tuples in `db.py` — full list in `c03-architecture.md`,
> "AS-IS findings"). All verification examples below were then **actually
> executed** against the running application. Results are filled in, not
> placeholders.

---

## Change Impact C02

### Changed condition
Some Resources require approval by an authorized person (admin) before a Reservation can become CONFIRMED. Approval may be delayed, rejected, or may expire.

### Affected requirements / parts of the specification
- **Reservation confirmation (DRAFT → ?).** Confirmation no longer always leads to CONFIRMED. For a resource with the `requires_approval` flag it leads to the new PENDING_APPROVAL state.
- **Reservation lifecycle.** The states PENDING_APPROVAL, REJECTED and EXPIRED are added.
- **Roles and permissions.** A new admin role (`AccountORM.is_admin`) and authorization on the approve / reject / expiration operations.
- **Resource.** Gains a `requires_approval` property. A VIP spot (`spot-9`) is seeded with it set to `True`.
- **Time behavior.** An approval deadline (24 h, `approval_expires_at`) and an expiration mechanism are introduced.
- **Notifications.** The confirmation is sent only after approval. Nothing is sent for pending, rejection or expiry (the interface currently only supports `send_reservation_confirmed`) — recorded as an open architectural driver, not fixed in C03.
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
| `/config`, `/resources`, `/reservations/mine` | Contract unchanged; `/resources` now additionally exposes `requires_approval` (C03 fix, additive). |

### New actor / operations, if any
- **Admin** (authorized person): a specialization of the logged-in user with `is_admin = True`. A demo admin account is now seeded on startup (`admin@parkandgo.test` / `admin12345` — see `c03-architecture.md`, this closes the C02 mismatch "there is no way to create an admin").
- **Time / scheduler:** an actor for expiration. Still a manually-triggered admin endpoint as of C03 (see ADR-01 in `c03-architecture.md` — a real scheduler is an accepted, deliberate gap, not an oversight).
- **New operations:**
  - Approve: `POST /reservations/{id}/approve`
  - Reject: `POST /reservations/{id}/reject`
  - Expire pending: `POST /admin/reservations/trigger-expiration` → `expire_pending`
  - (C03 addition) List pending: `GET /reservations/pending` — admin view of everything awaiting a decision
- **Changed operation:** Confirm reservation now has two branches depending on the resource.

### Changed rules / meaning of states
| State | Meaning | Entered by | Left by |
|---|---|---|---|
| DRAFT | Draft, does not block the slot | create | confirm, cancel |
| **PENDING_APPROVAL** | Waiting for admin, does not block the slot, 24 h deadline running | confirm (resource with `requires_approval`) | approve, reject, expire, cancel |
| CONFIRMED | Confirmed, blocks the slot | confirm (regular resource), approve | prolong, cancel |
| **REJECTED** | Admin rejected, final | reject | – |
| **EXPIRED** | Approval deadline passed, final | expire_pending, or `approve()` itself when called past the deadline (C03 fix) | – |
| CANCELLED | Cancelled by the user, final | cancel (only from DRAFT/PENDING_APPROVAL/CONFIRMED as of C03 — see mismatches) | – |

New rules:
- A resource with `requires_approval` cannot be confirmed directly.
- `approve` may be performed only by an admin, only from PENDING_APPROVAL, after re-checking overlap, **and only before the approval deadline** (C03 fix — see mismatch #1).
- `reject` may be performed only by an admin, and only from PENDING_APPROVAL.
- `expire_pending` marks PENDING_APPROVAL reservations whose `approval_expires_at` has passed as EXPIRED.
- `cancel` is only allowed from DRAFT, PENDING_APPROVAL or CONFIRMED (C03 fix — see mismatch #2).

### Use case diagram change
In uml-ult.png, uml is an old file before fixing mismatches in C02, but kept for documentation purposes in regards to the process.

Admin is also a logged-in user. Only the use cases marked NEW and the branching in "Confirm reservation" changed.

### State diagram change
In stateX.png files.

### New verification examples — now actually executed (C03)
| # | Scenario | Expected result | Actual result (executed via FastAPI TestClient against the real app) |
|---|---|---|---|
| 1 | Confirm a reservation on a regular spot | CONFIRMED, notification sent | **PASS** — `200 CONFIRMED` |
| 2 | Confirm a reservation on the VIP spot | PENDING_APPROVAL, `approval_expires_at` ≈ now + 24 h, no notification sent | **PASS** — `200 PENDING_APPROVAL`, deadline set |
| 3 | Admin approves a pending reservation | CONFIRMED, `approval_expires_at = None`, notification sent | **PASS** — `200 CONFIRMED`, deadline cleared |
| 4 | Admin rejects a pending reservation | REJECTED, slot remains free | **PASS** — `200 REJECTED`, availability `True` afterwards |
| 5 | Non-admin / anonymous user calls approve or reject | 403 | **PASS** — `403` |
| 6 | Approve from a state other than PENDING_APPROVAL | 400 | **PASS** — `400` |
| 7 | Two pending reservations on the same slot, the first is approved, then the second | Second: 400 (overlap), stays PENDING_APPROVAL | **PASS** — first `200 CONFIRMED`, second `400 overlapping confirmed reservation` |
| 8 | Pending reservation with an expired deadline, trigger-expiration is called | EXPIRED, count returned in the response | **PASS** — `200 {"expired_count": 1}` |
| 9 | Pending reservation with an expired deadline, expiration has not run yet, admin calls approve | Was expected to incorrectly succeed (mismatch #1) | **FIXED in C03** — now correctly `400 "approval window has expired; reservation marked EXPIRED"`, and the row is flipped to EXPIRED as a side effect |
| 10 | Anonymous pending reservation, admin approves | CONFIRMED, notification goes to the plate number (`user_id`) | **PASS** — `200 CONFIRMED`, `user_id` = plate |
| 11 | Pending on the VIP spot, meanwhile an overlapping one is confirmed | Approve fails because overlap is re-checked | **PASS** — covered by #7 above |

### Mismatches found and how they were resolved
| # | Mismatch | Status |
|---|---|---|
| 1 | `approve` does not check `approval_expires_at`, so an expired but not yet expired-marked reservation can be approved | **Resolved in C03.** `approval.approve()` now checks the deadline, marks EXPIRED and rejects if it has passed. Verified (scenario #9). |
| 2 | `cancel` allows cancelling REJECTED and EXPIRED reservations (it only checked for CANCELLED) | **Resolved in C03.** `cancel()` now only accepts `{DRAFT, PENDING_APPROVAL, CONFIRMED}`. Verified: cancelling a REJECTED reservation now returns `400`. |
| 3 | There is no way to create an admin (`is_admin` is never set) and `AccountResponse` does not expose it | **Resolved in C03.** A demo admin is seeded on startup; `AccountResponse.is_admin` is exposed. |
| 4 | The deadline is 24 h regardless of the reservation start, so approval can arrive after the start | **Not resolved — remaining, explicit gap.** Recorded in `c03-architecture.md`, AS-IS→TO-BE delta, row "Deadline capped at reservation start", marked `VERIFY / open` rather than silently dropped. |

### Summary of the change impact
The change adds a branch in confirmation, three new states, an admin role and time-driven expiration. The rules for operating hours, duration, non-overlap and authentication remain. The biggest impact is on the state diagram, authorization, and the ties to time, notifications and concurrency — which is exactly what C03's architecture work (below) addresses.

### Remaining assumptions / unknowns
- What "cancel" means for an admin is still undecided: implemented as rejecting a pending reservation, but an admin cannot yet cancel other people's already-confirmed reservations.
- Pending reservations still do not block the slot (by design — BR-12), so two users can wait on the same slot; only one can win at approval time (demonstrated in scenario #7/#11).
- `prolong` on a resource requiring approval bypasses approval, since extending a confirmed reservation does not require a new approval. Unchanged in C03.
- Behavior when notification delivery fails after a commit is unchanged from C01 (the interface can simulate timeout/failure, but nothing currently retries).
- Mismatch #4 (deadline not capped to reservation start) remains open — see above.

### Architectural drivers carried over to C03
Points 1–5 from "B. Architectural drivers" in `c03-architecture.md`: time/expiration & scheduler, concurrency of the approval re-check, authorization of a new actor, the anonymous-user return-channel gap, and the notification interface needing more outcomes. ADR-01 addresses #1–#3 directly; #4 and #5 are recorded as still open.

### Application commit / tag
ae3bf4f58b8f70f97874fd5e7c6dfac888fb73d6

---

# C03 — Architecture Evidence

Full detail (drivers, domain model, responsibilities, decision question,
alternatives, scenario walkthrough, ADR-01, all views, cross-view check,
AS-IS→TO-BE delta) is in **`c03-architecture.md`** — kept as its own
document because of its length. Summary for this evidence log:

**Baseline:** v0.2 (this document, C02 section above)

**Part A:** application did not start; three bugs found and fixed (bad
import, broken dataclass field, mismatched seed-data tuples) — see
"AS-IS findings" in `c03-architecture.md`.

**Drivers:** delayed/time-driven approval decision; concurrency of the
overlap re-check at approval time; a new admin actor; anonymous users'
missing return channel; notification interface needing more outcomes.

**Decision question:** where should the Approval Workflow (the
PENDING_APPROVAL outcome decision + expiration) be owned, and how is
BR-02 kept true when that decision happens later than the original
request?

**Alternatives:** (A) same deployable, separate module; (B) separate
worker/service process.

**Scenario walkthrough:** two overlapping PENDING_APPROVAL reservations
on the VIP spot, first approved then second — run against the real
implementation of Alternative A: first → `200 CONFIRMED`, second →
`400` (overlap re-check holds).

**ADR:** ADR-01 — Alternative A chosen (module boundary inside the same
process); accepted negative consequences: expiration stays lazy, the
underlying race window is narrowed but not eliminated. Full text in
`c03-architecture.md`.

**Views produced:** domain class model, context diagram, static
architecture (component) diagram, state-ownership table, runtime/
deployment mapping, design sequence diagram, design class diagram — all
in `c03-architecture.md` (ASCII) and `c03-plantuml-diagrams.md` (PlantUML,
ready to render).

**Cross-view issues found/resolved:** the architecture-conformance test
initially flagged `services.py`'s own explanatory docstring as a
violation (it mentions REJECTED/EXPIRED in prose); fixed by checking the
specific enum reference (`ReservationState.REJECTED`) rather than the
bare word, so the check tests what the code does, not what its comments
say.

**AS-IS → TO-BE delta:** 6 `CHANGE` rows (all implemented), 3 `KEEP`
rows (unaffected), 1 explicit open `VERIFY` row (the uncapped deadline,
mismatch #4) — full table in `c03-architecture.md`.

**Implementation changes:** `src/db.py`, `src/models.py`, `src/services.py`
fixed; `src/approval.py` added (new module, owns the three approval
outcome transitions); `src/main.py` wired to it; `tests/test_architecture_rule.py`
added.

**Behaviour verification:** all 11 C02 approval scenarios re-run against
the real HTTP API — all PASS, including the two that were previously
broken (mismatch #1, #2) and are now fixed and verified. All 12 automated
tests pass (`pytest -v`) as of C03.

**Architecture conformance rule + result:** "Only `src/approval.py` may
decide a pending approval's outcome" — checked by
`tests/test_architecture_rule.py` — **PASS** (3/3 conformance tests).

**Remaining uncertainty / risk:** the overlap-check race under true
concurrent load (the Q/Scale future pressure from `intent-and-change.md`)
is unchanged by this ADR — narrowing the module boundary made the gap
easier to find and reason about, not harder to hit. Expiration remains
reactive (manually triggered), not proactive. The notification interface
still only supports a "confirmed" outcome. The deadline is not capped to
the reservation's start time (mismatch #4).

**Commit/tag:** 377535ad581179111a732cceea0427888547dab6

---

# C05 DD Verification Evidence

Full Detailed Design (selected unit, detailed responsibilities, design
elements/ownership, interface contract, focused structural view, detailed
sequence, methods/operations, algorithm) is in
**`architecture-and-decisions.md`**, section "C05 Detailed Design".
Summary for this evidence log:

**Selected unit:** Approval Workflow (`src/approval.py`) + the new
Availability Policy contract it depends on (`src/availability.py`).

### Tests derived from DD

| DD element / decision | What must hold? | Test level | Test case |
|---|---|---|---|
| `AvailabilityPolicy.has_overlap` interface contract (only CONFIRMED blocks) | PENDING_APPROVAL / DRAFT / CANCELLED / REJECTED / EXPIRED never count as an overlap | unit | `test_availability_policy.py::test_has_overlap_ignores_non_confirmed_states` |
| `AvailabilityPolicy.has_overlap` interface contract (half-open interval) | a reservation ending exactly when another starts is not an overlap (BR-01) | unit | `test_availability_policy.py::test_has_overlap_respects_half_open_interval` |
| `approve()` algorithm branch: deadline check | past-deadline approve must self-correct the row to EXPIRED and raise, never silently approve | unit | `test_approval_workflow.py::test_approve_past_deadline_marks_expired_and_raises` |
| state transition: `approve()` entry guard | `approve()` on a reservation that is not `PENDING_APPROVAL` must raise and write nothing | unit | `test_approval_workflow.py::test_approve_non_pending_state_raises` |
| state transition: `reject()` entry guard (terminal states) | `reject()` on an already-decided reservation must raise, not silently re-decide it | unit | `test_approval_workflow.py::test_reject_non_pending_state_raises` |
| collaboration: `ApprovalWorkflow` ↔ `AvailabilityPolicy` under the C03 race scenario | two PENDING_APPROVAL reservations for the same slot: first `approve()` succeeds, second must be rejected by the overlap re-check (BR-02 after the delay, ADR-01 driver #2) | component | `test_approval_workflow.py::test_concurrent_overlapping_approvals_second_is_rejected` |
| batch algorithm: `expire_pending()` | only rows whose deadline has passed are flipped to EXPIRED; everything else is left untouched | unit | `test_approval_workflow.py::test_expire_pending_only_expires_past_deadline` |

Two selected for the required deeper explanation:

- **`test_has_overlap_ignores_non_confirmed_states`** — *Selected level:* unit. *Why this level:* the contract itself (what counts as "overlap") is exactly what's being verified, independent of who calls it — no HTTP, no second module needed to observe it. *Design decision verified:* that `has_overlap()` is now the one authoritative answer to "is this slot free", decoupled from any particular caller — the entire reason it was extracted out of `services.py` in this DD pass.
- **`test_concurrent_overlapping_approvals_second_is_rejected`** — *Selected level:* component. *Why this level:* this is specifically testing the *collaboration* between two units (`ApprovalWorkflow` calling into `AvailabilityPolicy`) across two sequential calls with real DB state in between — a single-function unit test can't exercise that. *Design decision verified:* ADR-01 driver #2 and the C05 algorithm-ordering decision (overlap re-checked at approval time, not just at confirm time) actually hold end-to-end, not just on paper.

### Unit/component tests executed

```
$ python -m pytest -v
tests/test_approval_workflow.py::test_approve_pending_within_deadline_confirms_and_notifies PASSED
tests/test_approval_workflow.py::test_reject_pending_sets_rejected PASSED
tests/test_approval_workflow.py::test_approve_past_deadline_marks_expired_and_raises PASSED
tests/test_approval_workflow.py::test_approve_non_pending_state_raises PASSED
tests/test_approval_workflow.py::test_reject_non_pending_state_raises PASSED
tests/test_approval_workflow.py::test_concurrent_overlapping_approvals_second_is_rejected PASSED
tests/test_approval_workflow.py::test_expire_pending_only_expires_past_deadline PASSED
tests/test_availability_policy.py::test_has_overlap_detects_confirmed_overlap PASSED
tests/test_availability_policy.py::test_has_overlap_respects_half_open_interval PASSED
tests/test_availability_policy.py::test_has_overlap_ignores_non_confirmed_states PASSED
tests/test_availability_policy.py::test_has_overlap_excludes_given_reservation_id PASSED

11 passed (plus all 12 pre-existing tests still pass -- 23 passed in 0.53s total)
```

### Design ↔ implementation mismatch

| DD decision | Implemented? | Evidence | Action |
|---|---|---|---|
| `AvailabilityPolicy.has_overlap()` as a standalone, named interface | YES | `src/availability.py`; `services.py` and `approval.py` both import it | keep |
| `approve()` checks deadline before overlap | YES | algorithm in `src/approval.py::approve`; `test_approve_past_deadline_marks_expired_and_raises` | keep |
| Admin authorization kept outside the unit (HTTP layer) | YES | `main.py::_require_admin`; `approve`/`reject` take a plain `admin_account_id` | keep |
| `expire_pending()` as a separate batch responsibility | YES | `src/approval.py::expire_pending`; `test_expire_pending_only_expires_past_deadline` | keep |
| Notification on reject/expire | **NO** (by design, not an oversight) | `reject()`/`expire_pending()` call no notifier — see `architecture-and-decisions.md`, driver #5, still open | keep as an explicitly recorded gap, do not silently implement |

No mismatch required reconciling the DD against the code — every decision documented in the DD was found implemented exactly as designed when checked against the actual source, with the one exception (notification on reject/expire) that was already a *known*, intentionally-recorded open gap rather than a surprise.

### Remaining design risk

- The overlap re-check inside `approve()` and the eventual write are still not wrapped in a single DB-level transaction with a stronger isolation level — under true concurrent requests (not just the sequential two-admin scenario the tests exercise), a narrower race than the one already closed could still exist at the SQLite layer. This is the same risk already recorded against ADR-01 and the Q/Scale future pressure in `intent-and-change.md`; C05 narrowed where that risk lives (one named function, `has_overlap`) but did not close it.
- `expire_pending()` is still only reachable via a manually-triggered endpoint, not a scheduler — unchanged from ADR-01's accepted consequence.

**Commit/tag:** 377535ad581179111a732cceea0427888547dab6