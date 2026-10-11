# Architecture and Decisions

## Stack
- **Language:** Python 3.12
- **Web framework:** FastAPI — chosen for low-boilerplate request validation
  (via Pydantic) and automatic OpenAPI docs, which makes the CP1 walking
  skeleton easy to poke at and demo without extra tooling.
- **Persistence:** SQLAlchemy ORM over SQLite (a real, on-disk database file,
  `parking.db`) — chosen over Postgres for this stage because it needs no
  separate server process, keeping the reproducible-build bar low (`pip
  install` + run), while still being a genuine relational DB with real
  durability, which is what the persistence spike needed to prove.
- **Testing:** pytest, with an in-memory SQLite DB (`sqlite:///:memory:`) for
  fast unit tests, and a dedicated on-disk DB file for the persistence spike
  test specifically (see `tests/test_persistence_spike.py`), so that test
  is actually exercising real file persistence rather than the same
  in-process state.

## Layering
- `src/models.py` — plain dataclasses for the domain concepts (Resource,
  User, Reservation, ReservationState). These are intentionally
  framework-agnostic.
- `src/db.py` — SQLAlchemy ORM models and engine/session setup.
- `src/services.py` — business rules and lifecycle for Create / Confirm /
  Cancel / Prolong / Check Availability: operating-hours validation, the
  overlap rule, duration/future-start rules, and the DRAFT -> CONFIRMED /
  PENDING_APPROVAL -> CANCELLED transitions it owns. As of C03 it
  deliberately does **not** own what happens to a PENDING_APPROVAL
  reservation next — see ADR-01 below.
- `src/approval.py` **(added in C03)** — the Approval Workflow: `approve`,
  `reject`, `expire_pending`. Owns the three outcome transitions out of
  PENDING_APPROVAL exclusively. See ADR-01.
- `src/accounts.py` / `src/auth.py` — registration, login, session tokens,
  PBKDF2 password hashing.
- `src/notification.py` — the Notification Service boundary, defined as an
  abstract interface (`NotificationService`) with a stub implementation
  (`StubNotificationService`) that can simulate success, timeout, or
  failure. This keeps the boundary explicit and swappable.
- `src/main.py` — the FastAPI HTTP layer. Thin: it only translates
  HTTP <-> service calls and turns `ReservationError` into HTTP 400s (and
  `NotAuthorizedError` into 403s). Also serves `static/index.html` at `/ui`.

## Key decision: fixed seeded resources instead of a resource-management API
A parking-spot inventory is created once at startup (`db.seed_resources`)
rather than through a create/delete API. C01's scope doesn't require the
maintenance role to add/retire spots yet, so a fixed seed list was simpler
than building resource CRUD we don't yet need.

## Key decision: plate number as the user identifier
The UI collects a name and a license plate. Rather than introducing a
separate `User` table for C01, the plate number is stored as `user_id`
(it's a natural unique identifier for "who's parking") and the name is
stored alongside it purely for display (`user_name`, optional).

## Key decision: cancel, not delete
"Cancel a reservation" calls the existing `cancel` operation rather than
deleting the row. This preserves history and keeps a single state machine
as the only way a reservation's status changes.

## Key decision: stdlib-only password hashing
Accounts hash passwords with PBKDF2-HMAC-SHA256 via Python's built-in
`hashlib`, rather than `bcrypt`/`passlib`/`argon2`, which ship as compiled
native packages and caused real build failures on Windows + Python 3.14 for
this team. PBKDF2 with a random per-account salt is a reasonable, standard
choice at this scope.

## Key decision: session tokens stored in the database, not in memory
Login sessions live in a `sessions` table (token -> account_id), not an
in-process dict, so a login survives an `--reload` restart.

## Key decision: 30-minute increments and a 4-hour cap
`RESERVATION_STEP_MINUTES = 30` and `MAX_DURATION_MINUTES = 240` in
`services.py` are simple constants, not configuration.

## Key decision: ORM objects as the working representation
We operate directly on `ReservationORM` objects in `services.py`/`approval.py`
rather than mapping every DB row to-and-from the plain `Reservation`
dataclass in `models.py`. This trades some architectural purity for less
code. If the Q/Scale future pressure (see `intent-and-change.md`) is acted
on, revisiting this boundary — alongside stricter transaction isolation
for the overlap check — is one of the first things we'd reconsider.

## Key decision: operating hours as a service-layer constant
`OPERATING_HOURS_START` / `OPERATING_HOURS_END` live in `services.py` as
constants rather than configuration, since the project doesn't require
per-resource or per-lot operating hours yet.

## ADR-01 — Where should the Approval Workflow be owned? (C03)
**Decision:** Alternative A — the Approval Workflow stays inside the same
deployable as the rest of the system, but as its own module
(`src/approval.py`) with exclusive, mechanically-checked ownership of the
`PENDING_APPROVAL -> {CONFIRMED, REJECTED, EXPIRED}` transitions (checked
by `tests/test_architecture_rule.py`). Rejected alternative: a separate
worker/service process — more operational and concurrency surface area
for a project of this size, without fixing the one real correctness gap
(the overlap re-check race, which is a transaction-isolation problem, not
a process-boundary problem).

Full context, drivers, both alternatives compared against drivers, the
scenario walkthrough, and all architecture views (context, static
architecture, state ownership, runtime/deployment, design sequence,
design class) are in **`c03-architecture.md`**.

## Engineering spike executed: Persistence (Spike A)
See `evidence-and-evolution.md` for the question, what we did, the
observed result, and the decision that followed.
