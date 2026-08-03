"""Схемы админ-панели."""
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserPublic


class TeamUpdateRequest(BaseModel):
    name: str | None = None


class BlankAllowanceStepRequest(BaseModel):
    team_id: UUID
    enabled: bool


class UserAdminPublic(UserPublic):
    team_name: str | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    team_id: UUID | None = None
    role: str | None = None
