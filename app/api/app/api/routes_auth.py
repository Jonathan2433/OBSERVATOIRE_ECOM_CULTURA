"""Endpoints d'authentification : login, logout, me."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..core.audit import record_audit
from ..core.db import get_db
from ..core.security import (
    clear_session_cookie,
    create_access_token,
    get_current_user,
    rate_limiter,
    set_session_cookie,
    verify_password,
)
from ..models.user import User
from ..schemas.user import LoginRequest, MeResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if rate_limiter.is_locked(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives. Réessayez dans quelques minutes.",
        )
    user = db.query(User).filter(User.username == username).one_or_none()
    # Message identique que le compte existe ou non (pas d'énumération).
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        rate_limiter.record_failure(username)
        record_audit(db, action="auth.login_failed", username=username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")

    rate_limiter.reset(username)
    token = create_access_token(user.id, user.role, user.username)
    set_session_cookie(response, token)
    record_audit(db, action="auth.login", user=user)
    logger.info("Connexion réussie : %s (%s)", user.username, user.role)
    return MeResponse(id=user.id, username=user.username, role=user.role)


@router.post("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user)):
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    return MeResponse(id=current_user.id, username=current_user.username, role=current_user.role)
