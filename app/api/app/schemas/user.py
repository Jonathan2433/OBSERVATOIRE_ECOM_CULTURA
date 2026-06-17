"""Schémas des comptes utilisateurs et de l'authentification."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["analyste", "admin"]


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=12, description="≥ 12 caractères")
    role: Role = "analyste"


class UserUpdate(BaseModel):
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12)
