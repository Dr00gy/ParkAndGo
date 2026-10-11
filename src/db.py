"""Persistence layer.

We use SQLAlchemy ORM models directly as the persisted representation of
Resource / User / Reservation. This is a deliberate simplification for the
scope of C01 (see docs/architecture-and-decisions.md): a stricter layering
would map ORM rows <-> the plain dataclasses in models.py, but for a
project of this size that indirection wasn't worth the extra code yet.

C03 fixes applied here (see docs/evidence-and-evolution.md, "Mismatches
found" #3, and the C03 bug list):
1. `Boolean` was used by AccountORM.is_admin but never imported -> NameError
   on import, which is why the app could not start at all.
2. ResourceORM had no `requires_approval` column, even though services.py
   already read `resource.requires_approval` -- the approval branch could
   never actually trigger against a real database.
3. SEED_RESOURCES mixed a 2-tuple format with one 3-tuple entry that also
   reused the id "spot-8" -- seed_resources() unpacked 2-tuples only, so
   this raised ValueError on every startup.
"""
from __future__ import annotations

from sqlalchemy import create_engine, Column, String, DateTime, Date, Boolean, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker

from .models import ReservationState

Base = declarative_base()


class ResourceORM(Base):
    __tablename__ = "resources"
    id = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    # Whether a DRAFT reservation on this resource must go through
    # PENDING_APPROVAL before it can become CONFIRMED (C02 change).
    requires_approval = Column(Boolean, nullable=False, default=False)


class UserORM(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class AccountORM(Base):
    """A registered user who can log in. Distinct from the plate-number
    'user_id' on a Reservation -- one account could book under several
    plates (their own car, a family member's, etc.)."""
    __tablename__ = "accounts"
    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)


class SessionORM(Base):
    """A logged-in session token. Stored in the DB (not an in-memory dict)
    so a login survives an app restart, consistent with everything else
    in this project being real, persisted state."""
    __tablename__ = "sessions"
    token = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)


class ReservationORM(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True)
    resource_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)  # license plate number
    user_name = Column(String, nullable=True)  # display name, optional
    account_id = Column(String, nullable=True, index=True)  # set when the booker was logged in
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    state = Column(SAEnum(ReservationState), nullable=False, default=ReservationState.DRAFT)
    approval_expires_at = Column(DateTime, nullable=True)


def get_engine(db_url: str = "sqlite:///parking.db"):
    """db_url defaults to a real on-disk SQLite database file (not :memory:)
    so that data genuinely survives a process restart -- this matters for
    the persistence spike, which reloads from a fresh engine/session."""
    return create_engine(db_url)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


# A fixed set of campus parking spots. In a real system these would be
# managed separately (added/retired by a maintenance role); for C01/C02 we
# seed a small fixed list so the UI has real resources to display.
# Each entry is (id, label, requires_approval).
SEED_RESOURCES = [
    ("spot-1", "Lot A - Spot 1", False),
    ("spot-2", "Lot A - Spot 2", False),
    ("spot-3", "Lot A - Spot 3", False),
    ("spot-4", "Lot A - Spot 4", False),
    ("spot-5", "Lot B - Spot 1", False),
    ("spot-6", "Lot B - Spot 2", False),
    ("spot-7", "Lot B - Spot 3", False),
    ("spot-8", "Lot B - Spot 4", False),
    ("spot-9", "VIP Lot - Spot 1 (Requires Approval)", True),
]


def seed_resources(session_factory) -> None:
    session = session_factory()
    try:
        existing = {r.id: r for r in session.query(ResourceORM).all()}
        for resource_id, label, requires_approval in SEED_RESOURCES:
            if resource_id not in existing:
                session.add(
                    ResourceORM(id=resource_id, label=label, requires_approval=requires_approval)
                )
        session.commit()
    finally:
        session.close()


# Demo admin account, seeded once so there is a way to reach the
# approve/reject endpoints without a manual DB edit (closes "Mismatches
# found" #3 in evidence-and-evolution.md: "there is no way to create an
# admin"). Credentials are intentionally simple and documented in the
# README -- this is a course project, not a production login.
SEED_ADMIN_EMAIL = "admin@parkandgo.test"
SEED_ADMIN_PASSWORD = "admin12345"


def seed_admin_account(session_factory) -> None:
    from . import auth as auth_utils  # local import to avoid a cycle at module load time
    import uuid

    session = session_factory()
    try:
        existing = session.query(AccountORM).filter(AccountORM.email == SEED_ADMIN_EMAIL).first()
        if existing is not None:
            if not existing.is_admin:
                existing.is_admin = True
                session.commit()
            return
        password_hash, salt = auth_utils.hash_password(SEED_ADMIN_PASSWORD)
        session.add(
            AccountORM(
                id=str(uuid.uuid4()),
                first_name="Parking",
                last_name="Admin",
                email=SEED_ADMIN_EMAIL,
                phone=None,
                date_of_birth=None,
                password_hash=password_hash,
                password_salt=salt,
                is_admin=True,
            )
        )
        session.commit()
    finally:
        session.close()


def get_session_factory(engine):
    return sessionmaker(bind=engine)
