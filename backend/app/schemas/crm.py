from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import (
    ActivityKind,
    ConversationMode,
    ConversationStatus,
    DeliveryStatus,
    Direction,
    LeadSource,
    LeadStage,
    PropertyType,
    SenderType,
)
from app.schemas.common import Out


class ContactBase(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    source: LeadSource = LeadSource.other
    stage: LeadStage = LeadStage.new
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_property_type: PropertyType | None = None
    bedrooms: int | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    assigned_to: str | None = None


class ContactCreate(ContactBase):
    phone: str


class ContactUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    stage: LeadStage | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_locations: list[str] | None = None
    preferred_property_type: PropertyType | None = None
    bedrooms: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
    assigned_to: str | None = None


class ContactOut(ContactBase, Out):
    id: str
    phone: str
    email: str | None = None
    last_inbound_at: datetime | None
    created_at: datetime


class InterestOut(Out):
    property_id: str
    ref_code: str
    title: str
    at: datetime


class ActivityOut(Out):
    id: str
    kind: ActivityKind
    summary: str
    user_id: str | None
    meta: dict
    created_at: datetime


class NoteIn(BaseModel):
    summary: str = Field(min_length=1, max_length=5000)
    kind: ActivityKind = ActivityKind.note


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_at: datetime
    contact_id: str | None = None
    assigned_to: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    assigned_to: str | None = None
    done: bool | None = None


class TaskOut(Out):
    id: str
    title: str
    description: str | None
    due_at: datetime
    done_at: datetime | None
    contact_id: str | None
    assigned_to: str | None
    created_at: datetime


class ConversationOut(Out):
    id: str
    contact_id: str
    mode: ConversationMode
    status: ConversationStatus
    unread_count: int
    last_message_at: datetime | None
    focus_property_id: str | None


class ConversationListItem(ConversationOut):
    contact_name: str | None
    contact_phone: str
    last_message: str | None


class MessageOut(Out):
    id: str
    direction: Direction
    sender_type: SenderType
    sender_user_id: str | None
    body: str
    status: DeliveryStatus
    error: str | None
    media_kind: str | None
    created_at: datetime


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4096)


class ConversationUpdate(BaseModel):
    mode: ConversationMode | None = None
    status: ConversationStatus | None = None


class NotificationOut(Out):
    id: str
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime
