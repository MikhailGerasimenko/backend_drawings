"""Схемы аутентификации и пользователей."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserPublic(BaseModel):
    id: UUID
    login: str
    display_name: str
    role: str
    team_id: UUID | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamPublic(BaseModel):
    id: UUID
    name: str
    archived: bool = False
    blank_allowance_step_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    login: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserPublic
    team: TeamPublic


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    password_confirm: str
