import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class LoginIn(BaseModel):
    email: str
    password: str


class CreateOrderIn(BaseModel):
    contact_name: str | None = None
    contact_phone: str | None = None

    @field_validator("contact_name", "contact_phone", mode="before")
    @classmethod
    def blank_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("contact_name")
    @classmethod
    def name_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) > 200:
            raise ValueError("Name is too long")
        return stripped

    @field_validator("contact_phone")
    @classmethod
    def phone_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) < 8 or len(stripped) > 20:
            raise ValueError("Enter a valid phone number")
        return stripped


class SegmentIn(BaseModel):
    file_id: uuid.UUID
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    paper_size: str
    color_mode: str
    sides: str
    orientation: str
    copies: int = Field(ge=1, le=500)

    @model_validator(mode="after")
    def choices(self) -> "SegmentIn":
        if self.paper_size not in {"A4", "A3", "LETTER"}:
            raise ValueError("Unsupported paper size")
        if self.color_mode not in {"BW", "COLOR"}:
            raise ValueError("Unsupported color mode")
        if self.sides not in {"SIMPLEX", "DUPLEX"}:
            raise ValueError("Unsupported sides")
        if self.orientation not in {"PORTRAIT", "LANDSCAPE"}:
            raise ValueError("Unsupported orientation")
        return self


class SegmentsIn(BaseModel):
    segments: list[SegmentIn] = Field(min_length=1)


class MarkPaidIn(BaseModel):
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("Send amount as a string")
        return value


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PricingRuleIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    paper_size: str
    color_mode: str
    sides: str
    unit_price: Decimal
    unit: str

    @field_validator("unit_price", mode="before")
    @classmethod
    def reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("Send unit_price as a string")
        return value

    @model_validator(mode="after")
    def unit_matches(self) -> "PricingRuleIn":
        if self.paper_size not in {"A4", "A3", "LETTER"}:
            raise ValueError("Unsupported paper size")
        if self.color_mode not in {"BW", "COLOR"}:
            raise ValueError("Unsupported color mode")
        if self.sides not in {"SIMPLEX", "DUPLEX"}:
            raise ValueError("Unsupported sides")
        if self.sides == "DUPLEX" and self.unit != "SHEET":
            raise ValueError("Duplex rules must use SHEET")
        if self.sides == "SIMPLEX" and self.unit != "PAGE":
            raise ValueError("Simplex rules must use PAGE")
        if self.unit_price < 0:
            raise ValueError("Price cannot be negative")
        return self


class PricingPut(BaseModel):
    rules: list[PricingRuleIn] = Field(min_length=1)


class SettingsPut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    primary_color: str
    logo_url: str | None = None


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=80)
    admin_email: str
    admin_password: str = Field(min_length=8, max_length=200)
    phone: str | None = None
    currency: str = "INR"
    address: str | None = None


class TenantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    address: str | None = None
