"""Переиспользуемые Pydantic-базовые схемы."""
from typing import Literal

from pydantic import BaseModel, Field


class PassportField(BaseModel):
    value: str | None = None
    missing_on_drawing: bool = False
    unit: str | None = None


class PartPassport(BaseModel):
    """Паспорт детали v2.0 (см. part-passport.schema.json)."""

    schema_version: Literal["2.0"] = "2.0"
    part_type: PassportField
    designation: PassportField
    overall_dimensions: PassportField
    material_hardness: PassportField
    outer_geometry: PassportField
    inner_geometry: PassportField
    special_elements: PassportField
    gdt: PassportField
    notes: str = ""

    def to_store(self) -> dict:
        return self.model_dump(mode="json")
