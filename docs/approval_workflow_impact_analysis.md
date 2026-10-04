# Approval Workflow Impact Analysis

| Area | Impact Analysis |
|--------|--------|
| **Create** | **No change to creation behavior.** Create should still create a reservation in an initial non-final state. However, for resources requiring approval, the initial state should become **PENDING_APPROVAL** instead of directly proceeding toward confirmation. For resources not requiring approval, the existing DRAFT → CONFIRMED flow can remain unchanged, or DRAFT may still be used as a temporary editing state before submission. |
| **Availability** | A business decision is required. For exclusive parking resources, **PENDING_APPROVAL should normally block availability**, otherwise multiple users could receive approval requests for the same slot and later compete for approval. Blocking preserves user expectations and reduces approval conflicts. An alternative design is to ignore PENDING_APPROVAL during availability checks and resolve conflicts during approval, but this increases complexity and potential user frustration. |
| **Confirm** | **Confirm is no longer a single operation for approval-required resources.** The current operation must be split into: (1) user submits reservation request, (2) authorized approver reviews it, (3) approver approves or rejects it. Confirmation becomes the result of an approval decision rather than a direct user action. For resources not requiring approval, the current immediate confirmation flow may remain unchanged. |
| **Approve** | **A new actor goal and operation are introduced.** New operation: Approve Reservation (or Review Reservation Request). Only users with an administrative or approval role may perform it. The operation changes reservation state from PENDING_APPROVAL to CONFIRMED or REJECTED. |
| **Cancel** | **Yes, PENDING_APPROVAL reservations should be cancellable.** A requester may decide they no longer need the reservation while waiting for approval. Cancellation should probably be allowed from both PENDING_APPROVAL and CONFIRMED states. Business ownership rules would still apply. |
| **State Diagram** | The current state model is insufficient. At minimum, introduce: **PENDING_APPROVAL** (awaiting decision), **REJECTED** (approval denied), and **EXPIRED** (approval window expired without decision). A possible lifecycle would be: DRAFT → PENDING_APPROVAL → CONFIRMED, DRAFT → PENDING_APPROVAL → REJECTED, DRAFT → PENDING_APPROVAL → EXPIRED, and both PENDING_APPROVAL and CONFIRMED → CANCELLED. |
| **Use Case Diagram** | **Yes.** A new actor such as Administrator, Approver, or Parking Manager is required. New use cases include Approve Reservation, Reject Reservation, View Pending Requests, and possibly Review Expired Requests. |
| **Verification** | Additional test scenarios become necessary: (1) reservation enters PENDING_APPROVAL after submission, (2) admin approval transitions it to CONFIRMED, (3) admin rejection transitions it to REJECTED, (4) unanswered request transitions to EXPIRED after timeout, (5) availability reflects the chosen PENDING_APPROVAL policy, (6) cancelled pending requests are removed from consideration, (7) overlapping pending requests are handled according to business rules. |
| **Architecture** | **Yes, this introduces a new architectural driver.** Approval is now a potentially delayed process rather than an immediate transaction. If expiration is required, the system needs a persistent mechanism to track approval deadlines. This may require a scheduled background job, timer, workflow process, or asynchronous event handling. Optional notification mechanisms may be needed to inform approvers of pending requests and users of approval, rejection, or expiration outcomes. |

---

# Recommended New Domain Rules

| ID | Rule |
|------|------|
| **BR-08** | Some Resources require approval before a Reservation may become CONFIRMED. |
| **BR-09** | A Reservation in PENDING_APPROVAL may only be approved or rejected by an authorized approver. |
| **BR-10** | A Reservation remaining in PENDING_APPROVAL beyond the approval deadline automatically becomes EXPIRED. |
| **BR-11** | REJECTED and EXPIRED reservations cannot later become CONFIRMED. |
| **BR-12** | Availability treatment of PENDING_APPROVAL reservations must be explicitly defined (blocking or non-blocking). |
