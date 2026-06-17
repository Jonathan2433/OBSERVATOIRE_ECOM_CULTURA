"""Gestion des comptes utilisateurs (réservé aux administrateurs)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.audit import record_audit
from ..core.db import get_db
from ..core.security import hash_password, require_admin
from ..models.user import ROLE_ADMIN, User
from ..schemas.user import UserCreate, UserOut, UserUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _count_active_admins(db: Session, exclude_id: int | None = None) -> int:
    q = db.query(User).filter(User.role == ROLE_ADMIN, User.is_active == True)  # noqa: E712
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.count()


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nom d'utilisateur déjà pris")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit(db, action="user.create", entity="user", entity_id=user.id, details=f"{user.username}/{user.role}")
    logger.info("Compte créé : %s (%s)", user.username, user.role)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")

    # Garde-fou : ne pas retirer le dernier admin actif (rétrogradation ou désactivation).
    losing_admin = (payload.role is not None and payload.role != ROLE_ADMIN and user.role == ROLE_ADMIN) or (
        payload.is_active is False and user.role == ROLE_ADMIN
    )
    if losing_admin and _count_active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Au moins un administrateur actif est requis")
    if payload.is_active is False and user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Impossible de se désactiver soi-même")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    logger.info("Compte modifié : %s", user.username)
    return user


@router.delete("/{user_id}", response_model=UserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Désactive un compte (suppression douce — on conserve la traçabilité)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Impossible de se désactiver soi-même")
    if user.role == ROLE_ADMIN and _count_active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Au moins un administrateur actif est requis")
    user.is_active = False
    db.commit()
    db.refresh(user)
    record_audit(db, action="user.deactivate", user=admin, entity="user", entity_id=user.id, details=user.username)
    logger.info("Compte désactivé : %s", user.username)
    return user
