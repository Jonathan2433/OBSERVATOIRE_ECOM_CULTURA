"""Sécurité : hachage de mot de passe (argon2), JWT, dépendances RBAC, anti-bruteforce."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db

logger = logging.getLogger(__name__)
_hasher = PasswordHasher()


# --------------------------------------------------------------------------- #
#  Mots de passe
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # hash corrompu / format inconnu
        return False


# --------------------------------------------------------------------------- #
#  JWT (stocké dans un cookie httpOnly)
# --------------------------------------------------------------------------- #
def create_access_token(user_id: int, role: str, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


# --------------------------------------------------------------------------- #
#  Dépendances RBAC
# --------------------------------------------------------------------------- #
def get_current_user(
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name),
):
    """Charge l'utilisateur courant depuis le cookie de session (JWT)."""
    from ..models.user import User  # import tardif (évite les cycles)

    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    if not session_token:
        raise cred_exc
    try:
        payload = jwt.decode(session_token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise cred_exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise cred_exc
    return user


def require_admin(current_user=Depends(get_current_user)):
    """Autorise uniquement les administrateurs."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return current_user


# --------------------------------------------------------------------------- #
#  Anti-bruteforce (en mémoire — best effort, réinitialisé au redémarrage)
# --------------------------------------------------------------------------- #
class LoginRateLimiter:
    def __init__(self, max_attempts: int, lockout_seconds: int):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._state: dict[str, tuple[int, float]] = {}  # username -> (échecs, lock_until)

    def is_locked(self, username: str) -> bool:
        fails, lock_until = self._state.get(username, (0, 0.0))
        return time.time() < lock_until

    def record_failure(self, username: str) -> None:
        fails, _ = self._state.get(username, (0, 0.0))
        fails += 1
        lock_until = time.time() + self.lockout_seconds if fails >= self.max_attempts else 0.0
        self._state[username] = (fails, lock_until)
        if lock_until:
            logger.warning("Compte '%s' verrouillé %ds après %d échecs.", username, self.lockout_seconds, fails)

    def reset(self, username: str) -> None:
        self._state.pop(username, None)


rate_limiter = LoginRateLimiter(
    settings.max_login_attempts, settings.lockout_minutes * 60
)
