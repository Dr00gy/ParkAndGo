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
- `src/services.py` — all business rules and state transitions live here:
  operating-hours validation, the overlap rule, and the DRAFT → CONFIRMED →
  CANCELLED state machine. Nothing outside this module should decide
  whether an operation is allowed.
- `src/notification.py` — the Notification Service boundary, defined as an
  abstract interface (`NotificationService`) with a stub implementation
  (`StubNotificationService`) that can simulate success, timeout, or
  failure. This keeps the boundary explicit and swappable.
- `src/main.py` — the FastAPI HTTP layer. Thin: it only translates
  HTTP <-> service calls and turns `ReservationError` into HTTP 400s. Also
  serves `static/index.html`, a small dependency-free reservation UI, at
  `/ui/`.

## Key decision: fixed seeded resources instead of a resource-management API
A parking-spot inventory is created once at startup (`db.seed_resources`)
rather than through a create/delete API. C01's scope doesn't require the
maintenance role to add/retire spots yet, so a fixed seed list was simpler
than building resource CRUD we don't yet need.

## Key decision: plate number as the user identifier
The UI collects a name and a license plate. Rather than introducing a
separate `User` table for C01, the plate number is stored as `user_id`
(it's a natural unique identifier for "who's parking") and the name is
stored alongside it purely for display (`user_name`, optional). If
authentication is added later, this is the natural seam to introduce a
real `User` entity.

## Key decision: cancel, not delete
The UI's "cancel a reservation" button calls the existing `cancel`
operation (`DRAFT`/`CONFIRMED` -> `CANCELLED`) rather than deleting the
row. This preserves history and keeps a single state machine as the only
way a reservation's status changes, consistent with the Project Frame.

## Key decision: stdlib-only password hashing
Accounts (`src/accounts.py`, `src/auth.py`) hash passwords with
PBKDF2-HMAC-SHA256 via Python's built-in `hashlib`, rather than
`bcrypt`/`passlib`/`argon2`. Those ship as compiled native packages, and
after hitting a Rust build failure installing `pydantic-core` on Windows
+ Python 3.14, adding another compiled dependency wasn't worth the risk
for a course project. PBKDF2 with a random per-account salt is a
reasonable, standard choice at this scope.

## Key decision: session tokens stored in the database, not in memory
Login sessions live in a `sessions` table (token -> account_id), not an
in-process dict, so a login survives an `--reload` restart, consistent
with everything else in this project being real, persisted state rather
than something that only works within one run.

## Key decision: 30-minute increments and a 4-hour cap
`RESERVATION_STEP_MINUTES = 30` and `MAX_DURATION_MINUTES = 240` in
`services.py` are simple constants, not configuration -- a reasonable
default for a parking reservation, revisited if the domain needs it
(e.g. an overnight lot).

## Key decision: ORM objects as the working representation
For C01's scope we operate directly on `ReservationORM` objects in
`services.py` rather than mapping every DB row to-and-from the plain
`Reservation` dataclass. This trades some architectural purity for less
code to write and review in the time available. If/when we act on the
selected future pressure (see intent-and-change.md), revisiting this
boundary is one of the first things we'd reconsider, alongside stricter
transaction isolation for the overlap check.

## Key decision: operating hours as a service-layer constant
`OPERATING_HOURS_START` / `OPERATING_HOURS_END` live in `services.py` as
constants rather than configuration, since C01 doesn't require
per-resource or per-lot operating hours yet. This is a known simplification
we'd revisit if the domain grows (e.g. a 24/7 lot alongside a
daytime-only one).

## Engineering spike executed: Persistence (Spike A)
See `docs/evidence-and-evolution.md` for the question, what we did, the
observed result, and the decision that followed.
