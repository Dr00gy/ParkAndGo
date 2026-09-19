"""Persistence layer.

We use SQLAlchemy ORM models directly as the persisted representation of
Resource / User / Reservation. This is a deliberate simplification for the
scope of C01 (see docs/architecture-and-decisions.md): a stricter layering
would map ORM rows <-> the plain dataclasses in models.py, but for a
project of this size that indirection wasn't worth the extra code yet.
"""
from __future__ import annotations

from sqlalchemy import create_engine, Column, String, DateTime, Date, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker

from .models import ReservationState

Base = declarative_base()


class ResourceORM(Base):
    __tablename__ = "resources"
    id = Column(String, primary_key=True)
    label = Column(String, nullable=False)


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


def get_engine(db_url: str = "sqlite:///parking.db"):
    """db_url defaults to a real on-disk SQLite database file (not :memory:)
    so that data genuinely survives a process restart -- this matters for
    the persistence spike, which reloads from a fresh engine/session."""
    return create_engine(db_url)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


# A fixed set of campus parking spots. In a real system these would be
# managed separately (added/retired by a maintenance role); for C01 we
# seed a small fixed list so the UI has real resources to display.
SEED_RESOURCES = [
    ("spot-1", "Lot A - Spot 1"),
    ("spot-2", "Lot A - Spot 2"),
    ("spot-3", "Lot A - Spot 3"),
    ("spot-4", "Lot A - Spot 4"),
    ("spot-5", "Lot B - Spot 1"),
    ("spot-6", "Lot B - Spot 2"),
    ("spot-7", "Lot B - Spot 3"),
    ("spot-8", "Lot B - Spot 4"),
]


def seed_resources(session_factory) -> None:
    session = session_factory()
    try:
        existing_ids = {r.id for r in session.query(ResourceORM).all()}
        for resource_id, label in SEED_RESOURCES:
            if resource_id not in existing_ids:
                session.add(ResourceORM(id=resource_id, label=label))
        session.commit()
    finally:
        session.close()


def get_session_factory(engine):
    return sessionmaker(bind=engine)