"""HTTP API for the parking reservation system (FastAPI).

This is the CP1 walking skeleton entry point:
POST /reservations -> validate -> persist -> return reservation ID

Also serves a small static single-page UI (static/index.html) at "/" so the
system can be tried out without needing the /docs Swagger page.
"""
from __future__ import annotations

import os
from datetime import date as date_type
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import accounts as accounts_service
from . import services
from .db import ResourceORM, get_engine, get_session_factory, init_db, seed_resources
from .notification import StubNotificationService

app = FastAPI(title="Campus Parking Reservation System")

engine = get_engine()
init_db(engine)
SessionLocal = get_session_factory(engine)
seed_resources(SessionLocal)
notifier = StubNotificationService()

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/ui", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")


class CreateReservationRequest(BaseModel):
    resource_id: str
    user_id: str  # license plate number
    start_time: datetime
    end_time: datetime
    user_name: str | None = None


class ProlongRequest(BaseModel):
    new_end_time: datetime


class ReservationResponse(BaseModel):
    id: str
    resource_id: str
    user_id: str
    user_name: str | None = None
    account_id: str | None = None
    start_time: datetime
    end_time: datetime
    state: str


class ResourceResponse(BaseModel):
    id: str
    label: str


class ResourceAvailability(BaseModel):
    id: str
    label: str
    available: bool


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    date_of_birth: date_type | None = None
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AccountResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    date_of_birth: date_type | None = None


class SessionResponse(BaseModel):
    token: str
    account: AccountResponse


def _to_response(r) -> ReservationResponse:
    return ReservationResponse(
        id=r.id,
        resource_id=r.resource_id,
        user_id=r.user_id,
        user_name=r.user_name,
        account_id=r.account_id,
        start_time=r.start_time,
        end_time=r.end_time,
        state=r.state.value if hasattr(r.state, "value") else r.state,
    )


def _account_to_response(a) -> AccountResponse:
    return AccountResponse(
        id=a.id,
        first_name=a.first_name,
        last_name=a.last_name,
        email=a.email,
        phone=a.phone,
        date_of_birth=a.date_of_birth,
    )


def _account_from_authorization(session, authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    return accounts_service.get_account_for_token(session, token)


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(req: CreateReservationRequest):
    session = SessionLocal()
    try:
        reservation = services.create_draft(
            session,
            req.resource_id,
            req.user_id,
            req.start_time,
            req.end_time,
            user_name=req.user_name,
        )
        return _to_response(reservation)
    except services.ReservationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(reservation_id: str):
    session = SessionLocal()
    try:
        reservation = services.confirm(session, reservation_id, notifier)
        return _to_response(reservation)
    except services.ReservationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(reservation_id: str):
    session = SessionLocal()
    try:
        reservation = services.cancel(session, reservation_id)
        return _to_response(reservation)
    except services.ReservationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@app.post("/reservations/{reservation_id}/prolong", response_model=ReservationResponse)
def prolong_reservation(reservation_id: str, req: ProlongRequest):
    session = SessionLocal()
    try:
        reservation = services.prolong(session, reservation_id, req.new_end_time)
        return _to_response(reservation)
    except services.ReservationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@app.get("/availability")
def availability(resource_id: str, start_time: datetime, end_time: datetime):
    session = SessionLocal()
    try:
        return {"available": services.check_availability(session, resource_id, start_time, end_time)}
    finally:
        session.close()


@app.get("/resources", response_model=list[ResourceResponse])
def list_resources():
    session = SessionLocal()
    try:
        return [
            ResourceResponse(id=r.id, label=r.label)
            for r in session.query(ResourceORM).order_by(ResourceORM.id).all()
        ]
    finally:
        session.close()


@app.get("/availability-grid", response_model=list[ResourceAvailability])
def availability_grid(start_time: datetime, end_time: datetime):
    """Availability of every parking spot for a given time window -- what
    the UI polls whenever the user picks a date/time, to show which spots
    are clickable."""
    session = SessionLocal()
    try:
        resources = session.query(ResourceORM).order_by(ResourceORM.id).all()
        return [
            ResourceAvailability(
                id=r.id,
                label=r.label,
                available=services.check_availability(session, r.id, start_time, end_time),
            )
            for r in resources
        ]
    finally:
        session.close()