from datetime import datetime

from pydantic import BaseModel, Field

from app.models import DocumentStatus, ListingType, MediaKind, PropertyStatus, PropertyType
from app.schemas.common import Out


class PropertyBase(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    listing_type: ListingType
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.draft
    price: float | None = Field(default=None, ge=0)
    area_sqft: float | None = Field(default=None, ge=0)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: int | None = Field(default=None, ge=0, le=50)
    city: str | None = None
    locality: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    amenities: list[str] = Field(default_factory=list)
    published: bool = False
    assigned_to: str | None = None


class PropertyCreate(PropertyBase):
    ref_code: str | None = Field(default=None, pattern=r"^[A-Z]{2,4}-\d{2,6}$")


class PropertyUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    listing_type: ListingType | None = None
    property_type: PropertyType | None = None
    status: PropertyStatus | None = None
    price: float | None = None
    area_sqft: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    city: str | None = None
    locality: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    amenities: list[str] | None = None
    published: bool | None = None
    assigned_to: str | None = None


class MediaOut(Out):
    id: str
    url: str
    kind: MediaKind
    sort_order: int


class PropertyOut(PropertyBase, Out):
    id: str
    ref_code: str
    media: list[MediaOut]
    created_at: datetime
    updated_at: datetime


class DocumentOut(Out):
    id: str
    property_id: str | None
    filename: str
    status: DocumentStatus
    error: str | None
    chunk_count: int
    created_at: datetime
