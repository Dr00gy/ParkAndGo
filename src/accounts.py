"""Application logic for accounts: register, login, sessions.

Kept separate from services.py, which stays focused on reservation
business rules -- this module owns account/session concerns only.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from . import auth as auth_utils
from .db import AccountORM, SessionORM

MIN_PASSWORD_LENGTH = 8


class AccountError(Exception):
    """Raised when registration or login can't proceed."""


def register(
    session: Session,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    date_of_birth: date | None,
    password: str,
) -> AccountORM:
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email_norm = (email or "").strip().lower()

    if not first_name or not last_name:
        raise AccountError("first and last name are required")
    if not email_norm or "@" not in email_norm:
        raise AccountError("a valid email is required")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    if session.query(AccountORM).filter(AccountORM.email == email_norm).first() is not None:
        raise AccountError("an account with this email already exists")

    password_hash, salt = auth_utils.hash_password(password)
    account = AccountORM(
        id=str(uuid.uuid4()),
        first_name=first_name,
        last_name=last_name,
        email=email_norm,
        phone=(phone or "").strip() or None,
        date_of_birth=date_of_birth,
        password_hash=password_hash,
        password_salt=salt,
    )
    session.add(account)
    session.commit()
    return account


def login(session: Session, email: str, password: str) -> AccountORM:
    email_norm = (email or "").strip().lower()
    account = session.query(AccountORM).filter(AccountORM.email == email_norm).first()
    if account is None or not auth_utils.verify_password(
        password or "", account.password_hash, account.password_salt
    ):
        raise AccountError("invalid email or password")
    return account


def create_session(session: Session, account: AccountORM) -> str:
    token = auth_utils.new_session_token()
    session.add(SessionORM(token=token, account_id=account.id, created_at=datetime.utcnow()))
    session.commit()
    return token


def get_account_for_token(session: Session, token: str) -> AccountORM | None:
    s = session.get(SessionORM, token)
    if s is None:
        return None
    return session.get(AccountORM, s.account_id)


def delete_session(session: Session, token: str) -> None:
    s = session.get(SessionORM, token)
    if s is not None:
        session.delete(s)
        session.commit()