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


class ConfigResponse(BaseModel):
    operating_hours_start: str
    operating_hours_end: str
    step_minutes: int
    max_duration_minutes: int


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
def create_reservation(req: CreateReservationRequest, authorization: str | None = Header(None)):
    session = SessionLocal()
    try:
        account = _account_from_authorization(session, authorization)
        reservation = services.create_draft(
            session,
            req.resource_id,
            req.user_id,
            req.start_time,
            req.end_time,
            user_name=req.user_name,
            account_id=account.id if account else None,
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
def cancel_reservation(reservation_id: str, authorization: str | None = Header(None)):
    session = SessionLocal()
    try:
        account = _account_from_authorization(session, authorization)
        reservation = services.cancel(
            session, reservation_id, requesting_account_id=account.id if account else None
        )
        return _to_response(reservation)
    except services.NotAuthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e))
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


@app.get("/config", response_model=ConfigResponse)
def config():
    """The business-rule constants the UI needs to explain *why* a slot is
    unavailable (outside operating hours vs. actually booked), sourced from
    services.py so there's exactly one place these numbers live."""
    return ConfigResponse(
        operating_hours_start=services.OPERATING_HOURS_START.strftime("%H:%M"),
        operating_hours_end=services.OPERATING_HOURS_END.strftime("%H:%M"),
        step_minutes=services.RESERVATION_STEP_MINUTES,
        max_duration_minutes=services.MAX_DURATION_MINUTES,
    )


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


@app.get("/reservations/mine", response_model=list[ReservationResponse])
def my_reservations(authorization: str | None = Header(None)):
    session = SessionLocal()
    try:
        account = _account_from_authorization(session, authorization)
        if account is None:
            raise HTTPException(status_code=401, detail="login required")
        rows = services.list_reservations_for_account(session, account.id)
        return [_to_response(r) for r in rows]
    finally:
        session.close()


@app.post("/auth/register", response_model=SessionResponse)
def register(req: RegisterRequest):
    session = SessionLocal()
    try:
        account = accounts_service.register(
            session,
            req.first_name,
            req.last_name,
            req.email,
            req.phone,
            req.date_of_birth,
            req.password,
        )
        token = accounts_service.create_session(session, account)
        return SessionResponse(token=token, account=_account_to_response(account))
    except accounts_service.AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@app.post("/auth/login", response_model=SessionResponse)
def login(req: LoginRequest):
    session = SessionLocal()
    try:
        account = accounts_service.login(session, req.email, req.password)
        token = accounts_service.create_session(session, account)
        return SessionResponse(token=token, account=_account_to_response(account))
    except accounts_service.AccountError as e:
        raise HTTPException(status_code=401, detail=str(e))
    finally:
        session.close()


@app.post("/auth/logout")
def logout(authorization: str | None = Header(None)):
    session = SessionLocal()
    try:
        if authorization and authorization.startswith("Bearer "):
            accounts_service.delete_session(session, authorization[len("Bearer ") :].strip())
        return {"ok": True}
    finally:
        session.close()


@app.get("/auth/me", response_model=AccountResponse)
def me(authorization: str | None = Header(None)):
    session = SessionLocal()
    try:
        account = _account_from_authorization(session, authorization)
        if account is None:
            raise HTTPException(status_code=401, detail="not logged in")
        return _account_to_response(account)
    finally:
        session.close()