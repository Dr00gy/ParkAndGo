"""C03 architecture conformance check (section L2).

Architectural rule (from ADR-01, see docs/architecture-and-decisions.md):
Only src/approval.py may decide the OUTCOME of an approval -- i.e. only it
may transition a reservation to REJECTED or EXPIRED, or decide that a
PENDING_APPROVAL reservation becomes CONFIRMED. services.py may still
perform the single DRAFT -> PENDING_APPROVAL entry transition (that's a
routing decision made at creation/confirm time, not an approval outcome),
but it must never reference REJECTED or EXPIRED at all, and it must not
contain a PENDING_APPROVAL -> CONFIRMED transition.

This is implemented as a simple, repeatable static source check (one of
the options the assignment explicitly allows: "script/repository check"),
not a full static-analysis tool -- proportionate to the size of this
project.
"""
from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def _read(name: str) -> str:
    return (SRC_DIR / name).read_text(encoding="utf-8")


def test_services_module_never_sets_rejected_or_expired():
    # Check the enum reference specifically, not bare prose -- services.py's
    # own docstrings are allowed to *talk about* REJECTED/EXPIRED while
    # explaining the ownership split; they must just never assign to them.
    source = _read("services.py")
    assert "ReservationState.REJECTED" not in source, (
        "services.py sets ReservationState.REJECTED -- only approval.py may "
        "decide that outcome (ADR-01)"
    )
    assert "ReservationState.EXPIRED" not in source, (
        "services.py sets ReservationState.EXPIRED -- only approval.py may "
        "decide that outcome (ADR-01)"
    )


def test_services_module_does_not_transition_pending_approval_to_confirmed():
    source = _read("services.py")
    # services.py is allowed to *create* PENDING_APPROVAL (the entry
    # transition inside confirm()), but must never read a reservation's
    # current PENDING_APPROVAL state and then decide CONFIRMED from it --
    # that decision belongs to approval.approve() alone.
    assert "state != ReservationState.PENDING_APPROVAL" not in source
    assert "state == ReservationState.PENDING_APPROVAL" not in source


def test_approval_module_owns_the_three_outcome_transitions():
    source = _read("approval.py")
    for marker in ("ReservationState.CONFIRMED", "ReservationState.REJECTED", "ReservationState.EXPIRED"):
        assert marker in source, f"approval.py no longer sets {marker} -- did ownership move?"
