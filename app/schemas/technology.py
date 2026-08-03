"""Схемы технологической карты."""
from typing import Literal

from pydantic import BaseModel, Field


class TechnologyOperation(BaseModel):
    number: int = Field(ge=1)
    name: str
    description: str
    equipment: str | None = None
    tooling: str | None = None
    time_norm_min: float | None = Field(default=None, ge=0)


class ManufacturingTechnology(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    part_designation: str
    part_name: str = ""
    material: str = ""
    summary: str = ""
    operations: list[TechnologyOperation] = Field(min_length=1)
    vertical_mapping_status: Literal["internal_only", "mapped"] = "internal_only"

    def to_store(self) -> dict:
        return self.model_dump(mode="json")


class TechnologyRouteStep(BaseModel):
    code: str = ""
    number: int | None = Field(default=None, ge=1)
    name: str = ""
    equipment: str | None = None
    transitions: str = ""
    final_sizes: str = ""


class TechnologyHeader(BaseModel):
    part_designation: str = ""
    part_name: str = ""
    material: str = ""
    features: str = ""


class TechnologyBlank(BaseModel):
    type: str = ""
    dimensions: str = ""
    allowances: str = ""


class TechnologyMetadata(BaseModel):
    card_version: str = "draft v1.0"
    author: str = "ИИ-ассистент"
    date: str = ""
    files_used: list[str] = Field(default_factory=list)
    allowance_rule_version: str = "v1.1"


class TechnologyCardV2(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    header: TechnologyHeader = Field(default_factory=TechnologyHeader)
    key_dimensions: str = ""
    blank: TechnologyBlank = Field(default_factory=TechnologyBlank)
    route: list[TechnologyRouteStep] = Field(min_length=1)
    heat_treatment: str = ""
    finish_after_heat_treatment: str = ""
    confirmation_required: str = ""
    metadata: TechnologyMetadata = Field(default_factory=TechnologyMetadata)
    dimensions_control: str = ""
    fields_needing_clarification: str = ""
    conflicts: str = ""

    def to_store(self) -> dict:
        return self.model_dump(mode="json")
