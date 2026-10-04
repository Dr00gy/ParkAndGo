# Domain Rules (Shared Across Operations)

| ID | Domain Rule | Description | Source |
|------|------|------|------|
| **BR-01** | Interval Semantics | Reservation intervals use **[start_time, end_time)** semantics. Two reservations overlap when `existing.start < requested.end` and `existing.end > requested.start`. |
| **BR-02** | Exclusive Resource Invariant | At no committed system state may two **CONFIRMED** reservations overlap for the same parking spot (resource). Draft reservations may overlap. |
| **BR-03** | Reservation Lifecycle | Reservation states follow the lifecycle **DRAFT → CONFIRMED → CANCELLED**. A cancelled reservation cannot be confirmed again. |
| **BR-04** | Operating Hours Rule | Reservations must start and end within campus parking operating hours **06:00–23:00**. |
| **BR-05** | Future Start Rule | A reservation may only be created if the start time is in the future relative to the current system time. |
| **BR-06** | Duration Rule | Reservation duration must be a multiple of **30 minutes** and must not exceed **240 minutes (4 hours)**. |
| **BR-07** | Cancellation Authorization | A reservation associated with an account may only be cancelled by the same account. Anonymous reservations may only be cancelled anonymously. |

---

# OP-01 — Create Reservation

**Goal / User Value:**  
Allow a user to reserve a parking spot for a future time interval.

**Trigger Event:**  
User submits a reservation request.

**Observable Request(s):**  
`POST /reservations`

**Preconditions:**

- Resource identifier is provided.
- User identifier (license plate) is provided.
- Start and end times are provided.
- BR-04, BR-05 and BR-06 must be satisfied.

**State After Successful Completion:**

- A new reservation exists in persistent storage.
- Reservation state is **DRAFT**.

**State Change:**

- No reservation → DRAFT reservation.

**References to Domain Rules:**

- BR-03
- BR-04
- BR-05
- BR-06

## Main Success Scenario

1. User submits reservation details.
2. System validates operating hours.
3. System validates that the start time is in the future.
4. System validates duration constraints.
5. System creates a reservation with state DRAFT.
6. System persists the reservation.
7. System returns reservation details including generated reservation ID.

## Alternative / Error Outcomes

- Start or end time outside operating hours → error.
- Start time in the past → error.
- Duration is not a multiple of 30 minutes → error.
- Duration exceeds 240 minutes → error.
- End time is not after start time → error.

## Verification Examples

| Input | Expected Result |
|---------|---------|
| 08:00-10:00 tomorrow | DRAFT reservation created |
| 05:00-07:00 tomorrow | Rejected (outside operating hours) |
| Start time yesterday | Rejected |
| 09:00-13:15 | Rejected (invalid duration increment) |

---

# OP-02 — Check Availability

**Goal / User Value:**  
Allow a user to determine whether a parking spot is currently available for a requested time interval.

**Trigger Event:**  
User requests availability information.

**Observable Request(s):**  
`GET /availability`

**Preconditions:**

- Resource exists.
- Start and end times are provided.

**State After Successful Completion:**

- No persistent data is modified.

**State Change:**

- None.

**References to Domain Rules:**

- BR-01
- BR-02
- BR-04

## Main Success Scenario

1. User specifies a parking spot and time interval.
2. System validates operating-hour compliance.
3. System checks for overlapping CONFIRMED reservations.
4. System returns availability status.

## Alternative / Error Outcomes

- Interval outside operating hours → availability reported as false.
- Overlapping CONFIRMED reservation exists → availability reported as false.

## Verification Examples

| Situation | Expected Result |
|------------|------------|
| No conflicting confirmed reservation | Available = true |
| Overlapping confirmed reservation exists | Available = false |
| Request outside operating hours | Available = false |

---

# OP-03 — Confirm Reservation

**Goal / User Value:**  
Finalize a draft reservation and secure the parking spot.

**Trigger Event:**  
User confirms a previously created reservation.

**Observable Request(s):**  
`POST /reservations/{reservation_id}/confirm`

**Preconditions:**

- Reservation exists.
- Reservation state is DRAFT.
- No overlapping CONFIRMED reservation exists for the same resource.

**State After Successful Completion:**

- Reservation state becomes CONFIRMED.
- Confirmation notification is sent.

**State Change:**

- DRAFT → CONFIRMED.

**References to Domain Rules:**

- BR-01
- BR-02
- BR-03

## Main Success Scenario

1. User requests confirmation.
2. System retrieves the reservation.
3. System verifies reservation exists.
4. System verifies state is DRAFT.
5. System checks overlap against confirmed reservations.
6. System changes state to CONFIRMED.
7. System persists the update.
8. System sends confirmation notification.
9. System returns updated reservation details.

## Alternative / Error Outcomes

- Reservation does not exist.
- Reservation is already CONFIRMED.
- Reservation is CANCELLED.
- Overlapping CONFIRMED reservation exists.

## Verification Examples

| Situation | Expected Result |
|------------|------------|
| DRAFT without conflicts | CONFIRMED |
| DRAFT with overlap to confirmed reservation | Rejected |
| Already CONFIRMED | Rejected |
| CANCELLED reservation | Rejected |

---

# OP-04 — Cancel Reservation

**Goal / User Value:**  
Release a parking spot and invalidate a reservation.

**Trigger Event:**  
User requests cancellation.

**Observable Request(s):**  
`POST /reservations/{reservation_id}/cancel`

**Preconditions:**

- Reservation exists.
- Reservation is not already CANCELLED.
- Authorization rules are satisfied.

**State After Successful Completion:**

- Reservation state becomes CANCELLED.

**State Change:**

- DRAFT → CANCELLED, or
- CONFIRMED → CANCELLED.

**References to Domain Rules:**

- BR-03
- BR-07

## Main Success Scenario

1. User requests cancellation.
2. System retrieves the reservation.
3. System verifies reservation exists.
4. System verifies reservation is not already cancelled.
5. System verifies caller authorization.
6. System changes state to CANCELLED.
7. System persists the update.
8. System returns updated reservation details.

## Alternative / Error Outcomes

- Reservation does not exist.
- Reservation already CANCELLED.
- Caller is not authorized to cancel the reservation.

## Verification Examples

| Situation | Expected Result |
|------------|------------|
| Owner cancels confirmed reservation | CANCELLED |
| Owner cancels draft reservation | CANCELLED |
| Non-owner attempts cancellation | Authorization error |
| Already cancelled reservation | Rejected |

---

# Requirements Quality Checklist

| Dimension | Assessment for This Parking Reservation System |
|------------|------------|
| **Meaning** | The key concepts are unambiguous: a Resource is a parking spot, a Reservation has states DRAFT/CONFIRMED/CANCELLED, a User ID corresponds to a vehicle license plate, and availability is determined by overlap of CONFIRMED reservations only. |
| **Need / Rationale** | The main business need is preventing double-booking of parking spots while allowing users to reserve, confirm, and cancel parking space usage within campus operating hours. |
| **Observable Outcome** | Every operation produces a visible result: reservation creation returns a reservation ID and DRAFT state, availability returns true/false, confirmation changes state to CONFIRMED, and cancellation changes state to CANCELLED. |
| **Feasibility** | The requirements are achievable with the current implementation. Resource exclusivity is enforced through overlap checks, reservation lifecycle rules are implemented, and all required data is persisted in the database. |
| **Verifiability** | Compliance can be verified through API tests. For example, attempting to confirm two overlapping reservations for the same parking spot should result in one confirmation succeeding and the other being rejected. |
| **State / Time** | The domain is highly time-dependent. Reservation validity depends on start/end timestamps, operating hours (06:00–23:00), duration limits (30-minute increments, maximum 4 hours), future-time validation, and reservation state transitions. |
| **Concurrency** | The most critical concurrency risk occurs during reservation confirmation. Multiple users may create overlapping DRAFT reservations, but BR-02 requires that only one overlapping reservation can ultimately become CONFIRMED for a given parking spot and time interval. |
| **Consistency** | All operations consistently enforce the same reservation lifecycle, overlap detection logic, operating-hour restrictions, duration limits, and authorization rules. No operation bypasses these business constraints. |
| **Uncertainty** | The implementation leaves a few business questions open. For example, cancellation of already-started reservations is currently allowed, and no expiration policy exists for abandoned DRAFT reservations. These behaviors should be explicitly accepted or defined as future requirements (TBD). |
