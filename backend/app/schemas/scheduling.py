from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import AppointmentKind, AppointmentStatus
from app.schemas.common import Out


class AvailabilityRuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    slot_minutes: int = Field(default=60, ge=15, le=240)

    @field_validator("start_time", "end_time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return v[:5]

    @model_validator(mode="after")
    def _order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityRuleOut(AvailabilityRuleIn, Out):
    pass


class AvailabilityExceptionIn(BaseModel):
    day: date
    reason: str | None = None


class AvailabilityExceptionOut(Out):
    id: str
    day: str
    reason: str | None


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    user_id: str | None = None


class AppointmentCreate(BaseModel):
    contact_id: str
    starts_at: datetime
    kind: AppointmentKind = AppointmentKind.site_visit
    property_id: str | None = None
    user_id: str | None = None
    duration_minutes: int = Field(default=60, ge=15, le=480)
    location: str | None = None
    notes: str | None = None
    # Staff can book outside published availability (e.g. a call arranged by phone).
    override_availability: bool = False
    notify_client: bool = True


class AppointmentUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: AppointmentStatus | None = None
    user_id: str | None = None
    location: str | None = None
    notes: str | None = None
    outcome: str | None = None


class AppointmentOut(Out):
    id: str
    contact_id: str
    property_id: str | None
    user_id: str
    kind: AppointmentKind
    status: AppointmentStatus
    starts_at: datetime
    ends_at: datetime
    location: str | None
    notes: str | None
    outcome: str | None
    created_by_bot: bool
    created_at: datetime


class AppointmentDetail(AppointmentOut):
    contact_name: str | None
    contact_phone: str
    property_ref: str | None
    property_title: str | None
    agent_name: str


class PublicBookingIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=6, max_length=32)
    email: str | None = None
    starts_at: datetime
    kind: AppointmentKind = AppointmentKind.site_visit
    property_ref: str | None = None
    notes: str | None = Field(default=None, max_length=1000)
