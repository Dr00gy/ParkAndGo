# C03 — Architecture

Baseline used: Specification Baseline v0.2 (parking_reservation_specification.md) + the approval-workflow change from `approval_workflow_impact_analysis.md`. Part A (AS-IS mapping) = the three code bugs found and fixed (see "AS-IS findings" below) plus the four mismatches already listed in `evidence-and-evolution.md`.

---

## AS-IS findings (Part A, condensed)

The application **could not start** as delivered. Three concrete defects, all in the code that implements the C02 approval-workflow change:

| # | File | Defect | Effect |
|---|---|---|---|
| 1 | `db.py` | `AccountORM.is_admin = Column(Boolean, ...)` but `Boolean` was never imported | `NameError` at import time — the app crashes before it can even bind a port |
| 2 | `db.py` | `SEED_RESOURCES` mixed 2-tuples with one 3-tuple, reusing id `"spot-8"`; `seed_resources()` unpacked 2-tuples only | `ValueError: too many values to unpack` on every startup |
| 3 | `models.py` | The plain `Resource` dataclass contained `requires_approval = Column(Boolean, default=False)` — a SQLAlchemy construct with no import, inside a dataclass that isn't an ORM model | `NameError` at import time |

Additionally, `ResourceORM` had **no** `requires_approval` column at all, so even if the above didn't crash, the approval branch in `services.confirm()` could never actually trigger against a real database — `getattr(resource, 'requires_approval', False)` silently always returned `False`.

All four are fixed in the files pushed back to this project (see the bottom of this document for the list). This is **Part A** for C03: these are exactly the kind of structural problems C03 asks you to find before touching architecture.

---

## B. Architectural drivers (carried over from C02 + Part A)

| # | Driver | Source | Why it affects architecture | Question architecture must answer |
|---|---|---|---|---|
| 1 | Approval is a **delayed, time-driven** decision, not an immediate transaction | `approval_workflow_impact_analysis.md` | State must survive past the end of the original HTTP request; something must eventually act on an expired deadline | Who/what owns the pending-approval deadline and the act of expiring it? |
| 2 | Concurrent approval of two overlapping `PENDING_APPROVAL` reservations must not both reach `CONFIRMED` (BR-02 must still hold *after* the delay) | BR-02, REQ-04, evidence.md driver #2 | The original "read-then-write" overlap check must be repeated at approval time, and is itself not atomic | Where is the authoritative "does this still not overlap?" decision made, and can two concurrent approvals race past it? |
| 3 | A new actor (**admin**) with different permissions than the reservation owner | `approval_workflow_impact_analysis.md` | Authorization must be enforced somewhere before a state transition is allowed | Which component decides "is this caller allowed to approve/reject"? |
| 4 | Anonymous users have no return channel (only a license plate, no login) | evidence.md driver #5 | Notification / status lookup for anonymous bookers is structurally different from logged-in ones | Does this change who owns notification delivery? (Answered: no — out of scope for this ADR, recorded as a remaining gap.) |
| 5 | Notifications must eventually support more outcomes (pending / rejected / expired), not just "confirmed" | evidence.md driver #3 | The `NotificationService` interface boundary needs to stay isolated from whoever decides state | Does the approval decision-maker also own notification dispatch, or does it stay behind the existing boundary? |

Driver is not a solution — none of these dictate "separate microservice" or "message queue" by themselves; that's what Part E is for.

---

## C1. Domain class model (relevant to this scenario)

```
Resource                 Reservation                    Account
---------                -----------                    -------
id                        id                              id
label                      resource_id ---------1..1----> (resolves to Resource)
requires_approval: bool    user_id (plate)                 is_admin: bool
                           user_name
                           account_id  --------0..1------> (resolves to Account)
                           start_time, end_time
                           state: ReservationState
                           approval_expires_at: datetime?

ReservationState = DRAFT | CONFIRMED | CANCELLED
                  | PENDING_APPROVAL | REJECTED | EXPIRED

NotificationService (interface)
  + send_reservation_confirmed(user_id, reservation_id)
```

Multiplicities that matter: one `Resource` has 0..* `Reservation`s; a `Reservation` has 0..1 `Account` (anonymous bookings are explicitly allowed); `requires_approval` on `Resource` is what routes a `Reservation` into the approval branch at all.

No Controller/Repository/HTTP classes here — those belong in H2, not here.

---

## C2. Responsibilities for this scenario (5–8, with ownership)

| Source | Responsibility | Must decide/own | Needs one clear owner? | Reason |
|---|---|---|---|---|
| REQ-01 / BR-04–06 | validate & create a DRAFT reservation | DRAFT entry | yes | creation rules must be applied exactly once, consistently |
| BR-02 / REQ-02 | decide slot availability | which states block a slot | yes | every caller must see the same answer |
| REQ-03 / resource flag | route confirm into CONFIRMED vs PENDING_APPROVAL | the DRAFT exit transition | yes | must not be decided differently in two places |
| BR-08/09 | decide the **outcome** of a pending approval | PENDING_APPROVAL → {CONFIRMED, REJECTED, EXPIRED} | yes | concurrency/consistency (driver #2) requires one authority |
| BR-09 | authorize the approve/reject caller | admin check | yes | a missed check anywhere is a security hole |
| BR-10 | detect and apply expiration | the EXPIRED transition specifically | yes | same owner as the rest of the outcome decision (driver #1) |
| BR-07 | authorize cancellation | CANCELLED transition | yes | same ownership logic as approval authorization |
| external boundary | deliver a notification | delivery, not business state | yes (separate from the above) | must stay swappable/isolatable (driver #5) |

Grouping: "decide the outcome of PENDING_APPROVAL" + "detect expiration" share the same state and the same invariant (BR-02 on the way out) → must be grouped together.
Separation: "validate & create DRAFT" has a different reason to change (business rules about time/duration) than "decide a pending approval's outcome" (a workflow/authorization concern) → kept apart.

---

## D. Decision question

**Where should the Approval Workflow (the PENDING_APPROVAL → {CONFIRMED, REJECTED, EXPIRED} decision, including expiration) be owned, and how is BR-02 kept true when that decision happens later than the original request?**

This comes directly from drivers #1–#3, affects structure (one module vs. a separate runtime element) and runtime (how/when expiration actually fires), and has at least two materially different real alternatives (below).

---

## E1. Two alternatives

**Alternative A — same deployable, separate module**
```
[ParkAndGo Application process]
  ├─ [Reservation Management]   (services.py)
  ├─ [Approval Workflow]        (approval.py)   <- new module boundary
  ├─ [Accounts & Auth]
  └─ [Notification Integration]
        |
        v
   [SQLite: parking.db]
```
Expiration is applied lazily: checked inside `approve()` itself, and swept by a manually-triggered `/admin/reservations/trigger-expiration` endpoint (callable by an external cron, but no in-process scheduler).

**Alternative B — separate runtime element**
```
[ParkAndGo Application process]          [Approval Worker process]
  ├─ Reservation Management                 ├─ owns PENDING_APPROVAL -> {CONFIRMED,REJECTED,EXPIRED}
  ├─ Accounts & Auth                        ├─ internal timer loop (proactive expiration)
  └─ Notification Integration               └─ its own DB session/transaction
        |                                          |
        v                                          v
   [SQLite: parking.db]  <------------------------/  (shared DB, both processes read/write it)
```
Approve/reject requests are handed to the worker (e.g. via a queue or a dedicated internal API); the worker is the only process allowed to write the three outcome states.

## E2. Comparison against drivers

| Driver / criterion | Alternative A (same deployable) | Alternative B (separate worker) |
|---|---|---|
| Consistency under concurrency (driver #2) | One process, one DB session per request; the overlap re-check happens in the same transaction model as everything else — easy to reason about, same known race window as the rest of the system (not worse) | Two processes now write the same rows; the same race window exists *plus* a second kind (worker vs. app writing concurrently) unless both are disciplined about re-checking — strictly more surface area, no inherent fix |
| Failure behaviour | If the process crashes, reservation creation/confirmation and approvals fail together (one simple failure mode) | Approval can stall silently while the rest of the app keeps working if the worker dies — requires its own monitoring to even notice |
| Change / ownership (driver #3) | One codebase, one deploy — fast to change, but approval logic can't evolve on its own release cycle | Approval logic could evolve independently (e.g. swapped for a real workflow tool later) at the cost of a defined cross-process contract |
| Operational complexity | Already what we have: one `uvicorn` process, one SQLite file | Needs a second deployable, a way to hand off commands (queue or internal API), and its own supervision — far beyond this project's current scope |
| Time / expiration (driver #1) | Lazy/manually triggered — acceptable but not proactive | A worker can run its own loop and expire proactively, closer to production behaviour |

No cell above is unexplained — each names the concrete mechanism.

## E3. Scenario walkthrough (same scenario as C02 verification #7: two overlapping PENDING_APPROVAL reservations on the VIP spot, first approved, then second)

| Step / event | Alternative A | Alternative B |
|---|---|---|
| Confirm Reservation begins (VIP spot) | Reservation Management writes PENDING_APPROVAL directly | identical — Reservation Management is unchanged in B |
| approval is required | row carries `approval_expires_at`; no cross-process call yet | identical |
| request ends | HTTP response returns PENDING_APPROVAL immediately either way | identical |
| approval arrives later (first reservation) | Admin calls `POST /approve` in the same running app; `approval.approve()` re-checks overlap in the same DB session, writes CONFIRMED | Admin's approve command reaches the worker; worker opens its own session against the same DB, re-checks overlap, writes CONFIRMED |
| second overlapping PENDING_APPROVAL is then approved | Second `approve()` call re-queries CONFIRMED overlaps in the same process and is **rejected with 400** — this is the actual, executed result (see Evidence below) | Same outcome is achievable, but now depends on the worker's session seeing the first write with the right isolation — one more place this can go wrong |

**Result actually observed when this was run against Alternative A (our implementation):** first `approve()` → `200 CONFIRMED`; second `approve()` → `400 "resource already has an overlapping confirmed reservation, cannot approve"`. BR-02 held.

---

## F. ADR-01

```
## ADR-01 — Where should the Approval Workflow be owned?

Context:
C02 added a delayed, admin-driven approval decision (PENDING_APPROVAL ->
CONFIRMED/REJECTED/EXPIRED) with a 24h deadline. This is architecturally
different from the rest of the lifecycle because the decision happens
after the original HTTP request ends, by a different actor, and must
still preserve BR-02.

Drivers:
#1 time/expiration, #2 concurrency, #3 authorization (see section B).

Alternative A: same deployable, separate module (src/approval.py).
Alternative B: separate worker/service process.

Decision:
Alternative A. Approval Workflow is extracted into its own module
(src/approval.py) inside the same FastAPI process, with exclusive,
mechanically-checked ownership of the three outcome transitions.

Reason:
This is a single small SQLite-backed course project. A separate process
would add deployment and concurrency surface area (a second component
that must get the overlap re-check right) without closing the one real
correctness gap, which is a database-transaction-isolation problem, not
a process-boundary problem. A module boundary gives us clear, testable
ownership today at near-zero operational cost.

Accepted negative consequences:
- Expiration is lazy / manually triggered, not proactive (driver #1
  stays open).
- A crash anywhere in the process still takes down reservation
  creation/confirmation together with approval handling.
- The underlying read-then-write race on the overlap check at approval
  time is narrowed (easy to locate, single module) but not eliminated.
  This is the same gap already recorded as the Q/Scale future pressure
  in intent-and-change.md.

Reconsider when:
the "10x concurrent requests" future pressure materializes in practice,
or approval needs its own operational lifecycle (retries, SLAs,
independent scaling) separate from the reservation API's.
```

---

## G1. Context diagram

```
[User / Admin]
      | reservation commands / login / approve / reject
      v
+----------------------------+
|  ParkAndGo Reservation      |
|  System                     |
+----------------------------+
      | confirmation notification request
      +---------------------------------> [Notification Service (stub)]
```
No IdP or other external system is used; authentication is self-hosted (Accounts & Auth, inside the system boundary).

## G2. Static architecture (TO-BE)

```
+----------------------------- ParkAndGo Reservation System -----------------------------+
|                                                                                          |
|  [Reservation Management]            (src/services.py)                                 |
|  role: create/cancel/prolong, availability, single DRAFT->PENDING_APPROVAL entry         |
|  owns: DRAFT / CONFIRMED / CANCELLED transitions                                         |
|      |                                                                                    |
|      | overlap check / read Resource.requires_approval                                   |
|      v                                                                                    |
|  [Availability]  (part of services.py)                                                   |
|                                                                                            |
|  [Approval Workflow]                 (src/approval.py)            <-- ADR-01             |
|  role: approve / reject / expire_pending                                                  |
|  owns: PENDING_APPROVAL -> {CONFIRMED, REJECTED, EXPIRED}                                 |
|                                                                                            |
|  [Accounts & Auth]                   (src/accounts.py, src/auth.py)                       |
|  role: register/login/session tokens, admin flag                                          |
|  owns: Account + Session state                                                            |
|                                                                                            |
|  [Notification Integration]          (src/notification.py)                                |
|  role: isolates the Notification Service boundary                                         |
|                                                                                            |
|  [HTTP API]                          (src/main.py)                                        |
|  role: HTTP <-> the above, enforces admin-only on approve/reject/expire                   |
+----------------------|-------------------------------------------------------------------+
                        | send confirmation notification
                        v
               [Notification Service]
```
ADR-01 is visible here as the `[Approval Workflow]` box: its own element, inside the same system, with exclusive ownership called out.

## G3. State ownership (extends the C02 statechart)

| Transition | Owner (decides) | Who may only request it |
|---|---|---|
| `[initial]` → DRAFT | Reservation Management | User (authenticated or anonymous) |
| DRAFT → CONFIRMED | Reservation Management | User |
| DRAFT → PENDING_APPROVAL | Reservation Management (routing on `Resource.requires_approval`) | User, indirectly via confirm |
| PENDING_APPROVAL → CONFIRMED | **Approval Workflow** | Admin |
| PENDING_APPROVAL → REJECTED | **Approval Workflow** | Admin |
| PENDING_APPROVAL → EXPIRED | **Approval Workflow** | Time / admin-triggered sweep |
| DRAFT / PENDING_APPROVAL / CONFIRMED → CANCELLED | Reservation Management | Owning account, or matching anonymous caller |

Every owner here matches a box in G2.

## G4. Runtime / deployment mapping

```
[ParkAndGo Application process (uvicorn)]
contains:
- HTTP API              (main.py)
- Reservation Management (services.py)
- Approval Workflow      (approval.py)
- Accounts & Auth        (accounts.py, auth.py)
- Notification Integration (notification.py)

        | read/write (SQLAlchemy)
        v
   [SQLite file: parking.db]

        +--------------------> [Notification Service (stub, in-process)]
```
One process, one deployable, one DB file — matches Alternative A.

---

## H1. Design sequence diagram

**Scenario: confirm a VIP (approval-required) spot, then two admins' overlapping approvals race (alt branch).**

```
User          HTTP API        Reservation Mgmt      Approval Workflow      DB            Notification
 |  POST /reservations/{id}/confirm                                                           
 |------------->|                                                                            
 |              |--confirm(id)-->|                                                           
 |              |                |--read Reservation, Resource-------->|                     
 |              |                |--overlap check (CONFIRMED only)---->|                     
 |              |                | alt resource.requires_approval                              
 |              |                |   [true] write state=PENDING_APPROVAL, expires_at=+24h -->|
 |              |<--PENDING_APPROVAL--|                                                       
 |<----200------|                                                                             

Admin A       HTTP API                               Approval Workflow      DB            Notification
 |  POST /reservations/{id}/approve                                                          
 |------------->|--require_admin (Accounts & Auth)                                           
 |              |--approve(id, admin)-------------------->|                                  
 |              |                                          |--read Reservation------------->|
 |              |                                          | alt approval_expires_at < now    
 |              |                                          |   [expired] write EXPIRED------>|
 |              |                                          |   [ok] overlap re-check -------->|
 |              |                                          |     alt overlap exists            
 |              |                                          |       [yes] return 400 (no write) 
 |              |                                          |       [no]  write CONFIRMED ---->|
 |              |                                          |            send_reservation_confirmed------->|
 |<----200/400--|<-----------------------------------------|                                  

Admin B (second, overlapping, approved just after Admin A)
 |  POST /reservations/{id2}/approve
 |------------->|--approve(id2, admin)-------------------->|
 |              |                                          |--overlap re-check: now sees Admin A's CONFIRMED row
 |              |                                          |--return 400 "overlapping confirmed reservation"
 |<----400------|
```
This is the exact scenario we ran against the real application; results are in the Evidence section below.

## H2. Design class diagram

```
+----------------------+       +------------------------+
| ReservationORM        |       | ResourceORM             |
+------------------------+     +------------------------+
| id                     |      | id                       |
| resource_id ---------->|----->| label                    |
| user_id, user_name      |     | requires_approval: bool   |
| account_id -----------> |---->+------------------------+
| start_time, end_time    |            ^        AccountORM
| state: ReservationState |            |      +------------------+
| approval_expires_at     |            |      | id               |
+------------------------+             |      | first/last name  |
                                        |      | email            |
                                        +------| is_admin: bool   |
                                               +------------------+

+---------------------------+          +---------------------------+
| ReservationManagement     |          | ApprovalWorkflow           |
| (services.py, stateless)  |          | (approval.py, stateless)   |
+---------------------------+          +---------------------------+
| create_draft()            |          | approve(id, admin_id)      |
| confirm()                 |          | reject(id, admin_id)       |
| cancel()                  |          | expire_pending()           |
| prolong()                 |          +---------------------------+
| check_availability()      |                     |
+---------------------------+                     | uses
         | uses                                   v
         v                             +---------------------------+
+---------------------------+          | NotificationService (ABC) |
| (shared) overlap check    |          +---------------------------+
+---------------------------+                     ^
                                                    |
                                        +---------------------------+
                                        | StubNotificationService    |
                                        +---------------------------+
```
`ReservationManagement` and `ApprovalWorkflow` are drawn as classes for this diagram even though they are implemented as module-level functions in Python — a stateless module of functions is the same design shape as a stateless service class with no instance fields. Every lifeline/operation used in H1 (`confirm`, `approve`, `reject`, overlap check, `send_reservation_confirmed`) has an owner here.

---

## I. Cross-view consistency check

| Check | Result |
|---|---|
| C02 ↔ G2 — can the architecture realize the required behaviour and rules? | Yes — verified by actually running all 11 approval scenarios (see Evidence) against this structure. |
| C2 ↔ G2 — does every significant responsibility have one owner? | Yes, table in C2 maps 1:1 onto G2's boxes. |
| G2 ↔ H1 — does the sequence only use existing/allowed dependencies? | Yes — H1 only calls HTTP API → Reservation Management / Approval Workflow → DB / Notification, matching G2's arrows. |
| H1 ↔ H2 — does every significant message/operation have a structural owner? | Yes — `confirm`, `approve`, `reject`, overlap check, `send_reservation_confirmed` all appear in H2. |
| statechart ↔ G3/H1 — does the right owner decide each transition? | Yes, and this is now also a mechanical test (`tests/test_architecture_rule.py`), not just a diagram claim. |
| G2 ↔ G4 — is every logical element realistically mapped to a runtime process? | Yes — all 5 logical elements map into the single `uvicorn` process in G4. |
| ADR ↔ G2/G4 | Yes — the `[Approval Workflow]` module boundary and the single-process runtime mapping are the decision from ADR-01, visibly drawn. |

One issue was found and fixed during this check, not after: the first draft of `test_architecture_rule.py` flagged `services.py`'s own docstring (which *talks about* REJECTED/EXPIRED while explaining the ownership split) as a violation. Fixed by checking for the enum reference `ReservationState.REJECTED` specifically rather than the bare word — the rule now checks what the code *does*, not what its comments *say*.

---

## J. AS-IS → TO-BE delta

| Area | AS-IS | TO-BE | Action |
|---|---|---|---|
| `approve`/`reject`/`expire_pending` location | inside `services.py`, mixed with the rest of the lifecycle, no ownership boundary | own module `src/approval.py`, exclusive owner of the three outcome transitions | **CHANGE** |
| `ResourceORM.requires_approval` | column didn't exist; approval branch could never trigger for real | column added | **CHANGE** |
| `AccountORM.is_admin` import | `NameError` (missing `Boolean` import) | fixed import | **CHANGE** |
| Admin account creation | no way to create one | a seeded demo admin account (`admin@parkandgo.test`) | **CHANGE** |
| `cancel()` allowed states | only blocked an already-CANCELLED reservation; silently allowed cancelling REJECTED/EXPIRED | restricted to `{DRAFT, PENDING_APPROVAL, CONFIRMED}` | **CHANGE** |
| `approve()` deadline check | missing — could approve past the 24h window | checks `approval_expires_at`, flips to EXPIRED and rejects if passed | **CHANGE** |
| Operating hours / duration / future-start rules (BR-04–06) | in `services.py`, unaffected by approval | unchanged | **KEEP** |
| `check_availability` / overlap rule (BR-01/02) | only CONFIRMED blocks a slot | unchanged | **KEEP** |
| `NotificationService` interface | one method, confirmation only | unchanged in C03 (gap recorded, not fixed) | **KEEP** (driver #5 stays open) |
| Deadline capped at reservation start (mismatch #4) | 24h flat regardless of start time | **not implemented** | **VERIFY / open** — recorded as a remaining gap, not silently dropped |
| Expiration mechanism | manual endpoint only | same in C03 (Alternative A accepted; a scheduler is future work per ADR-01) | **KEEP**, consciously |

---

## K. Implementation changes made

All six `CHANGE` rows above were implemented (not just planned) in the files delivered with this document: `src/db.py`, `src/models.py`, `src/services.py`, `src/approval.py` (new), `src/main.py`. The application now starts, and every C02 verification scenario (1–11) was re-run against the real HTTP API — see Evidence below.

---

## L1. Behaviour verification (C02 scenarios, re-run for real)

| Verification | Result | Evidence |
|---|---|---|
| Regular spot confirm → CONFIRMED, notification sent | PASS | `200 CONFIRMED` |
| VIP spot confirm → PENDING_APPROVAL, `approval_expires_at` set, no notification | PASS | `200 PENDING_APPROVAL`, `expires_at set: True` |
| Admin approves pending → CONFIRMED, `approval_expires_at` cleared, notified | PASS | `200 CONFIRMED`, `expires_at cleared: True` |
| Admin rejects pending → REJECTED, slot free | PASS | `200 REJECTED`; availability `True` afterwards |
| Non-admin/anonymous calls approve → 403 | PASS | `403` |
| Approve from non-pending state → 400 | PASS | `400` |
| Two overlapping pending, first approved then second → second rejected | PASS | first `200 CONFIRMED`, second `400 overlapping confirmed reservation` |
| Expired pending + `trigger-expiration` → EXPIRED, count returned | PASS | `200 {"ok": true, "expired_count": 1}` |
| Expired pending, `approve()` called directly before any sweep (mismatch #9, was a known bug) | **now PASS** (previously would incorrectly approve) | `400 "approval window has expired; reservation marked EXPIRED"` |
| Anonymous pending, admin approves → CONFIRMED, notification uses plate number | PASS | `200 CONFIRMED`, `user_id` = plate |
| Cancel a REJECTED reservation (mismatch #2, was a known bug) | **now PASS** (previously would incorrectly allow it) | `400 "cannot cancel a reservation in state ReservationState.REJECTED"` |

All 12 automated tests also pass (`pytest -v`): the 6 original C01 unit tests, the persistence spike, and 3 new architecture-conformance tests.

## L2. Architecture conformance rule + check

**Architectural rule:** Only `src/approval.py` may decide the *outcome* of a pending approval — i.e. only it may set `ReservationState.REJECTED` or `ReservationState.EXPIRED`, or transition `PENDING_APPROVAL → CONFIRMED`. `services.py` may still perform the single entry transition `DRAFT → PENDING_APPROVAL`, but nothing else about that state.

**Check:** `tests/test_architecture_rule.py` — a repeatable static source check (one of the forms the assignment explicitly allows: "script/repository check"). It greps `services.py` for `ReservationState.REJECTED` / `ReservationState.EXPIRED` (must be absent) and for the specific pattern of reading `PENDING_APPROVAL` state (must be absent — that decision belongs to `approval.py`), and greps `approval.py` to confirm it still owns all three outcomes.

**Result:** `PASS` — `pytest tests/test_architecture_rule.py -v` → 3 passed.

---

## Files changed/added for C03

- `src/db.py` — fixed missing import, added `requires_approval` column, fixed seed data, added admin seeding
- `src/models.py` — fixed the broken `Resource` dataclass field
- `src/services.py` — restricted `cancel()`'s allowed states; approval outcome logic moved out
- `src/approval.py` — **new**: `approve`, `reject`, `expire_pending`, with the deadline-check fix
- `src/main.py` — wired to `approval.py`; added `is_admin` to `AccountResponse`; added `/reservations/pending`
- `tests/test_architecture_rule.py` — **new**: the L2 conformance check
