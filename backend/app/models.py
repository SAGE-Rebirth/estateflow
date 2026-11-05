"""MongoDB document models. Every tenant-owned document carries `tenant_id`, and every
query must filter on it (see app.core.db.get_owned)."""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class MongoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    collection: ClassVar[str]

    id: str = Field(default_factory=new_id, alias="_id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def load(cls, doc: dict[str, Any] | None) -> Self | None:
        return cls.model_validate(doc) if doc else None

    def dump(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class Embedded(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# --- Tenants and users ---------------------------------------------------------------


class Role(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    agent = "agent"


class Tenant(MongoModel):
    collection: ClassVar[str] = "tenants"

    name: str
    slug: str
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"
    contact_email: str | None = None
    # WhatsApp Cloud API: inbound webhooks are routed to a tenant by phone_number_id.
    whatsapp_phone_number_id: str | None = None
    whatsapp_display_number: str | None = None
    whatsapp_access_token_enc: str | None = None
    # persona, extra_instructions, reminder template names
    bot_settings: dict[str, Any] = Field(default_factory=dict)
    # Show this business's published listings on the public marketplace home page.
    list_on_marketplace: bool = True
    is_active: bool = True


class AvailabilityRule(Embedded):
    """Weekly recurring working window, in the tenant's timezone. Times are "HH:MM"."""

    weekday: int = Field(ge=0, le=6)  # 0 = Monday
    start_time: str
    end_time: str
    slot_minutes: int = 60


class DayOff(Embedded):
    id: str = Field(default_factory=new_id)
    day: str  # YYYY-MM-DD
    reason: str | None = None


class User(MongoModel):
    collection: ClassVar[str] = "users"

    tenant_id: str
    email: str
    password_hash: str
    full_name: str
    phone: str | None = None
    role: Role = Role.agent
    is_active: bool = True
    # Embedded in every token; incrementing it revokes all of the user's sessions.
    token_version: int = 0
    availability: list[AvailabilityRule] = Field(default_factory=list)
    days_off: list[DayOff] = Field(default_factory=list)


# --- Properties and knowledge --------------------------------------------------------


class ListingType(enum.StrEnum):
    sale = "sale"
    rent = "rent"


class PropertyType(enum.StrEnum):
    apartment = "apartment"
    villa = "villa"
    independent_house = "independent_house"
    plot = "plot"
    commercial = "commercial"
    office = "office"


class PropertyStatus(enum.StrEnum):
    draft = "draft"
    available = "available"
    under_offer = "under_offer"
    sold = "sold"
    rented = "rented"


LISTABLE_STATUSES = (PropertyStatus.available, PropertyStatus.under_offer)


class MediaKind(enum.StrEnum):
    image = "image"
    video = "video"
    floorplan = "floorplan"


class Media(Embedded):
    id: str = Field(default_factory=new_id)
    url: str
    path: str  # storage path, for deletion
    kind: MediaKind = MediaKind.image
    sort_order: int = 0


class Property(MongoModel):
    collection: ClassVar[str] = "properties"

    tenant_id: str
    ref_code: str
    title: str
    description: str = ""
    listing_type: ListingType
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.draft
    price: float | None = None
    area_sqft: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    city: str | None = None
    locality: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    amenities: list[str] = Field(default_factory=list)
    published: bool = False
    assigned_to: str | None = None
    media: list[Media] = Field(default_factory=list)

    @property
    def listable(self) -> bool:
        return self.published and self.status in LISTABLE_STATUSES


class DocumentStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class DocumentSource(enum.StrEnum):
    upload = "upload"
    property_listing = "property_listing"  # generated from the property record


class Document(MongoModel):
    collection: ClassVar[str] = "documents"

    tenant_id: str
    property_id: str | None = None
    source: DocumentSource = DocumentSource.upload
    filename: str
    content_type: str | None = None
    storage_path: str | None = None
    status: DocumentStatus = DocumentStatus.pending
    error: str | None = None
    chunk_count: int = 0


class Chunk(MongoModel):
    """Collection name comes from settings (COLLECTION_NAME)."""

    collection: ClassVar[str] = "chunks"

    tenant_id: str
    document_id: str
    property_id: str | None = None
    ref_code: str | None = None
    # False for chunks of unpublished/sold listings; filtered out at search time.
    active: bool = True
    ordinal: int
    content: str
    embedding: list[float]
    source: str = ""


# --- CRM ------------------------------------------------------------------------------


class LeadStage(enum.StrEnum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    visit_scheduled = "visit_scheduled"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class LeadSource(enum.StrEnum):
    whatsapp = "whatsapp"
    website = "website"
    referral = "referral"
    walk_in = "walk_in"
    other = "other"


class Interest(Embedded):
    property_id: str
    ref_code: str
    title: str
    source: str = "whatsapp"
    at: datetime = Field(default_factory=utcnow)


class Contact(MongoModel):
    collection: ClassVar[str] = "contacts"

    tenant_id: str
    phone: str  # E.164
    wa_id: str | None = None
    name: str | None = None
    email: str | None = None
    source: LeadSource = LeadSource.whatsapp
    stage: LeadStage = LeadStage.new
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_property_type: PropertyType | None = None
    bedrooms: int | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    assigned_to: str | None = None
    last_inbound_at: datetime | None = None
    interests: list[Interest] = Field(default_factory=list)


class Task(MongoModel):
    """A follow-up the team owes a contact ("call back Rahul about the 3BHK")."""

    collection: ClassVar[str] = "tasks"

    tenant_id: str
    contact_id: str | None = None
    assigned_to: str | None = None
    title: str
    description: str | None = None
    due_at: datetime
    done_at: datetime | None = None
    reminder_sent: bool = False


class ActivityKind(enum.StrEnum):
    note = "note"
    call = "call"
    message = "message"
    stage_change = "stage_change"
    appointment = "appointment"
    property_interest = "property_interest"
    handoff = "handoff"


class Activity(MongoModel):
    collection: ClassVar[str] = "activities"

    tenant_id: str
    contact_id: str
    user_id: str | None = None
    kind: ActivityKind
    summary: str
    meta: dict[str, Any] = Field(default_factory=dict)


class Notification(MongoModel):
    collection: ClassVar[str] = "notifications"

    tenant_id: str
    user_id: str
    kind: str
    title: str
    body: str | None = None
    link: str | None = None
    read_at: datetime | None = None


# --- Messaging ------------------------------------------------------------------------


class ConversationMode(enum.StrEnum):
    bot = "bot"  # the assistant replies automatically
    human = "human"  # a team member has taken over; the assistant stays silent


class ConversationStatus(enum.StrEnum):
    open = "open"
    closed = "closed"


class Direction(enum.StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class Conversation(MongoModel):
    collection: ClassVar[str] = "conversations"

    tenant_id: str
    contact_id: str
    channel: str = "whatsapp"
    mode: ConversationMode = ConversationMode.bot
    status: ConversationStatus = ConversationStatus.open
    focus_property_id: str | None = None
    last_message_at: datetime | None = None
    # Direction of the latest message: "inbound" on a human-mode chat means a reply is owed.
    last_direction: Direction | None = None
    last_message: str | None = None
    unread_count: int = 0


class SenderType(enum.StrEnum):
    contact = "contact"
    bot = "bot"
    user = "user"
    system = "system"


class DeliveryStatus(enum.StrEnum):
    received = "received"
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class Message(MongoModel):
    collection: ClassVar[str] = "messages"

    tenant_id: str
    conversation_id: str
    direction: Direction
    sender_type: SenderType
    sender_user_id: str | None = None
    body: str = ""
    # WhatsApp message id; unique (sparse) so webhook retries never double-process.
    wa_message_id: str | None = None
    status: DeliveryStatus = DeliveryStatus.received
    error: str | None = None
    # Inbound photos/voice notes/documents: stored privately, served to staff only.
    media_kind: str | None = None
    media_path: str | None = None
    media_mime: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# --- Scheduling -----------------------------------------------------------------------


class AppointmentKind(enum.StrEnum):
    site_visit = "site_visit"
    call = "call"
    office_meeting = "office_meeting"
    video_call = "video_call"


class AppointmentStatus(enum.StrEnum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


ACTIVE_APPOINTMENT_STATUSES = (AppointmentStatus.scheduled, AppointmentStatus.confirmed)


class Appointment(MongoModel):
    collection: ClassVar[str] = "appointments"

    tenant_id: str
    contact_id: str
    property_id: str | None = None
    user_id: str
    kind: AppointmentKind
    status: AppointmentStatus = AppointmentStatus.scheduled
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    notes: str | None = None
    outcome: str | None = None
    created_by_bot: bool = False
    client_reminder_24h_sent: bool = False
    client_reminder_2h_sent: bool = False
    agent_reminder_sent: bool = False
