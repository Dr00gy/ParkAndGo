# Campus Parking Reservation System

A reservation system for university campus parking spaces. Students and
staff can reserve a parking spot for a time slot, confirm it, prolong it,
or cancel it, without double-booking a spot.

See `docs/intent-and-change.md` for the full Project Frame.

## Stack
Python 3.12 · FastAPI · SQLAlchemy · SQLite · pytest.
Rationale: `docs/architecture-and-decisions.md`.

## Project structure
```
src/
  models.py        domain concepts (Resource, User, Reservation, states)
  db.py             SQLAlchemy ORM models + engine/session setup
  services.py       business rules and state transitions
  notification.py   Notification Service boundary (+ stub implementation)
  auth.py           password hashing + session token helpers
  accounts.py       register / login / session business logic
  main.py           FastAPI HTTP layer + resources/availability-grid/auth endpoints
static/
  index.html        point-and-click reservation UI with login/register, served at /ui/
tests/
  test_reservation_service.py   unit tests for business rules
  test_persistence_spike.py     C01 engineering spike (persistence)
docs/
  intent-and-change.md
  architecture-and-decisions.md
  evidence-and-evolution.md
```

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests
```bash
python -m pytest -v
```

## Run the API
```bash
uvicorn src.main:app --reload
```
Interactive API docs (Swagger) are then at `http://127.0.0.1:8000/docs`.

### Web UI
A simple point-and-click reservation page is served at
`http://127.0.0.1:8000/ui/`. Pick a date, a start time, and a duration
(30-minute increments up to 4 hours), then click a free (green) spot, fill
in your name and plate number, and confirm — you'll get a popup with your
reservation ID. Taken spots are shown in red and can't be clicked, like
picking a seat for a movie. You can only pick times from now onward.

**Accounts:** use "Register"/"Log in" in the top right to create an
account (first/last name, email, phone, date of birth, password) or sign
in. While logged in, the Name field auto-fills from your account, and
"My reservations" lists everything you've booked with a red Delete button
on each row — click a row to expand its full details. Booking without an
account still works; you'll just need to type your name each time and
won't have a "My reservations" list for those bookings.

Use the "Cancel a reservation" box in the corner with a reservation ID to
release any spot (yours or not — see the security note below).

### Example request
```bash
curl -X POST http://127.0.0.1:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{
        "resource_id": "spot-1",
        "user_id": "alice",
        "start_time": "2026-09-21T09:00:00",
        "end_time": "2026-09-21T10:00:00"
      }'
```

## Accounts
Registering stores first name, last name, email (unique), phone, date of
birth, and a password (hashed with PBKDF2-HMAC-SHA256 + a per-account salt,
stdlib-only — see `src/auth.py`). Logging in issues a session token stored
in the database (`sessions` table), sent back as `Authorization: Bearer
<token>` on later requests. A reservation made while logged in is tagged
with `account_id`, which is what `/reservations/mine` filters on.

## CP1 walking skeleton
The following end-to-end path must be truly runnable after C03 / before C04:

```
POST /reservations
  → validate    (operating hours; well-formed request body)
  → persist     (write a reservation row to the database)
  → return reservation ID
  → automated check   (an automated test creates a reservation via the API
                        and asserts a 200 response with a valid, persisted
                        reservation ID — see tests/test_persistence_spike.py
                        for the persistence half of this today; a
                        dedicated end-to-end API test is the remaining
                        piece for CP1 itself)
```

Today, `create_draft` → `confirm` → `check_availability` already works
end-to-end through the API (verified manually via FastAPI's test client);
formalizing that as an automated API-level test is part of CP1.