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
    hash_password,
    rate_limiter,
    set_session_cookie,
    verify_password,
)
from ..models.user import User
from ..schemas.user import LoginRequest, MeResponse
from pydantic import BaseModel, Field


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)

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


@router.post("/password")
def change_password(payload: PasswordChange, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Changement de mot de passe par l'utilisateur connecté (≥ 12 caractères)."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mot de passe actuel incorrect")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Le nouveau mot de passe doit différer de l'ancien")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    record_audit(db, action="auth.password_change", user=current_user)
    logger.info("Mot de passe changé : %s", current_user.username)
    return {"status": "ok"}
