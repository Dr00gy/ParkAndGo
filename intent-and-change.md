# Project Frame

## Reservation domain
University campus parking spaces.

## Purpose
Useful for students and teachers alike, to make sure they can make it to class on time without worrying about parking and changing plans to find a space for their car within a reasonable distance from the campus. Also could be potentially useful metrics-wise, who parks when, at what volume, etc.

## Users / Stakeholders
The reserveé and potentially a maintanence role for drastic changes to the parking spaces.

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
Reservation must start and end within the campus parking operating hours.

## External / system boundary
Notification about a successful reservation.

## Assumption
The system receives valid, unique identifiers for users and parking resources.

## Unknown
We do not yet know whether draft reservations should expire automatically after a period of inactivity (neither confirmed or cancelled for a certain period).