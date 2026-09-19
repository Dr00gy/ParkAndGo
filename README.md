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
  main.py           FastAPI HTTP layer + resources/availability-grid endpoints
static/
  index.html        simple point-and-click reservation UI, served at /ui/
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
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests
```bash
python -m pytest -v
```

## Run the API
```bash
uvicorn src.main:app --reload --port 8001
```
Interactive API docs (Swagger) are then at `http://127.0.0.1:8001/docs`.

### Web UI
A simple point-and-click reservation page is served at
`http://127.0.0.1:8001/ui/`. Pick a date and time range, click a free
(green) spot, fill in your name and plate number, and confirm — you'll get
a popup with your reservation ID. Taken spots are shown in red and can't be
clicked, like picking a seat for a movie. Use the "Cancel a reservation"
box in the corner with that ID to release the spot again.

### Example request
```bash
curl -X POST http://127.0.0.1:8001/reservations \
  -H "Content-Type: application/json" \
  -d '{
        "resource_id": "spot-1",
        "user_id": "alice",
        "start_time": "2026-09-21T09:00:00",
        "end_time": "2026-09-21T10:00:00"
      }'
```

## CP1 walking skeleton
The following end-to-end path must be truly runnable after C03 / before C04:

```
POST /reservations
  → validate    (operating hours; well-formed request body)
  → persist     (write a DRAFT reservation row to the database)
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

## Business rules implemented
- Two `CONFIRMED` reservations for the same parking spot must not overlap.
- A reservation must start and end within campus parking operating hours
  (06:00–23:00).

## Known open question
Whether `DRAFT` reservations should auto-expire after a period of
inactivity is not yet decided — see `docs/intent-and-change.md` → Unknown.

## Team workflow steps still to do (manual, on GitHub)
These require actual team members and can't be done for you:
1. Create an issue/task named **"C01 engineering spike"**.
2. Have one team member make a change (e.g. adding a new business rule
   or extending a test), and a different team member review it via a pull
   request before merging.
3. Merge only after that review.
