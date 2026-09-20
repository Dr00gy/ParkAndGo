# Project Frame

## Reservation domain
University campus parking spaces.

## Purpose
Useful for students and teachers alike, to make sure they can make it to class on time without worrying about parking and changing plans to find a space for their car within a reasonable distance from the campus. Also could be potentially useful metrics-wise, who parks when, at what volume, etc.

## Users / Stakeholders
The reservee and potentially a maintenance role for drastic changes to the parking spaces.

## Core concepts
Reservation, Resource, User + (Time) Slot.

## Core operations
- Create reservation or just a draft of it
- Confirm reservation
- Cancel reservation
- Check availability (implicit)
- Prolong reservation

## Persistent state
Which user is parking at which parking space (ID). Period in which the parking space is considered to be taken. State of the parking space reservation itself.

## State-changing operation
DRAFT → CONFIRMED
CONFIRMED → CANCELLED
Confirmed - reserved space. Draft and cancelled - not a reserved space.

## Common business rule
Confirmed reservations for the same resource must not overlap.

## Domain-specific business rule
Reservation must start and end within the campus parking operating hours (06:00-23:00). A reservation's start time must not be in the past. A reservation's duration must be a multiple of 30 minutes, up to 4 hours.

## External / system boundary
Notification about a successful reservation (Notification Service).

## Assumption
The system receives valid, unique identifiers for users and parking resources.

## Unknown
We do not yet know whether draft reservations should expire automatically after a period of inactivity (neither confirmed nor cancelled for a certain period).

## Selected future pressure
Category: Q — Quality / Scale

Concrete pressure: 10x more concurrent reservation requests during the first week of each semester, when most students try to reserve a campus parking spot for the same set of popular time slots within a short window.

Why it is relevant to our reservation system: our overlap check currently runs as a single read-then-write inside one DB session per request. Under high concurrency, two nearly-simultaneous confirm requests for the same resource and overlapping slot could both pass the overlap check before either commits (a race condition), double-booking the spot. At 10x scale this stops being a rare edge case and becomes a real risk to the "no overlapping confirmed reservations" guarantee, so this pressure would push us toward stricter transaction isolation or a DB-level uniqueness/exclusion constraint rather than an application-level check alone. We are not implementing this in C01 — it's recorded here as the pressure we've chosen to design against later.
