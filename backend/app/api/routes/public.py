"""Unauthenticated endpoints backing the tenant's public listing site and booking page."""

import re
import urllib.parse
from datetime import UTC, date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import DbDep
from app.api.routes.crm import normalize_phone
from app.core.db import Db, coll, find, find_one, save
from app.core.ratelimit import RateLimit, hit
from app.models import (
    LISTABLE_STATUSES,
    LeadSource,
    ListingType,
    Property,
    PropertyStatus,
    PropertyType,
    Tenant,
)
from app.schemas.property import MediaOut
from app.schemas.scheduling import AppointmentOut, PublicBookingIn, SlotOut
from app.services.client_messages import send_appointment_confirmation
from app.services.inbound import upsert_contact
from app.services.scheduling import (
    SlotUnavailableError,
    available_slots,
    book_appointment,
    dedupe_by_time,
)

router = APIRouter(
    prefix="/public", tags=["public"], dependencies=[Depends(RateLimit("public", 300, 60))]
)


class PublicTenant(BaseModel):
    name: str
    slug: str
    currency: str
    timezone: str
    whatsapp_number: str | None


class PublicProperty(BaseModel):
    ref_code: str
    title: str
    description: str
    listing_type: ListingType
    property_type: PropertyType
    status: PropertyStatus
    price: float | None
    area_sqft: float | None
    bedrooms: int | None
    bathrooms: int | None
    city: str | None
    locality: str | None
    amenities: list[str]
    media: list[MediaOut]
    whatsapp_url: str | None


async def _tenant(db: Db, slug: str) -> Tenant:
    tenant = await find_one(db, Tenant, {"slug": slug, "is_active": True})
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return tenant


def whatsapp_link(tenant: Tenant, prop: Property | None = None) -> str | None:
    """wa.me deep link; the prefilled ref code tells the assistant which listing they mean."""
    if not tenant.whatsapp_display_number:
        return None
    digits = "".join(ch for ch in tenant.whatsapp_display_number if ch.isdigit())
    text = (
        f"Hi, I'm interested in {prop.ref_code} - {prop.title}"
        if prop
        else f"Hi {tenant.name}, I'm looking for a property"
    )
    return f"https://wa.me/{digits}?text={urllib.parse.quote(text)}"


def _public(tenant: Tenant, p: Property) -> PublicProperty:
    fields = PublicProperty.model_fields.keys() - {"media", "whatsapp_url"}
    return PublicProperty(
        **{k: getattr(p, k) for k in fields},
        media=[MediaOut.model_validate(m) for m in p.media],
        whatsapp_url=whatsapp_link(tenant, p),
    )


@router.get("/{slug}", response_model=PublicTenant)
async def tenant_info(slug: str, db: DbDep) -> PublicTenant:
    t = await _tenant(db, slug)
    return PublicTenant(
        name=t.name,
        slug=t.slug,
        currency=t.currency,
        timezone=t.timezone,
        whatsapp_number=t.whatsapp_display_number,
    )


@router.get("/{slug}/properties")
async def public_properties(
    slug: str,
    db: DbDep,
    city: str | None = None,
    property_type: PropertyType | None = None,
    listing_type: ListingType | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_bedrooms: int | None = None,
    limit: int = Query(default=24, le=100),
    offset: int = 0,
) -> dict:
    tenant = await _tenant(db, slug)
    q: dict = {
        "tenant_id": tenant.id,
        "published": True,
        "status": {"$in": list(LISTABLE_STATUSES)},
    }
    if city:
        q["city"] = {"$regex": f"^{re.escape(city)}", "$options": "i"}
    if property_type:
        q["property_type"] = property_type
    if listing_type:
        q["listing_type"] = listing_type
    price: dict = {}
    if min_price is not None:
        price["$gte"] = min_price
    if max_price is not None:
        price["$lte"] = max_price
    if price:
        q["price"] = price
    if min_bedrooms is not None:
        q["bedrooms"] = {"$gte": min_bedrooms}
    total = await coll(db, Property).count_documents(q)
    rows = await find(db, Property, q, sort=[("created_at", -1)], limit=limit, skip=offset)
    return {"items": [_public(tenant, p) for p in rows], "total": total}


@router.get("/{slug}/properties/{ref_code}", response_model=PublicProperty)
async def public_property(slug: str, ref_code: str, db: DbDep) -> PublicProperty:
    tenant = await _tenant(db, slug)
    prop = await find_one(
        db,
        Property,
        {"tenant_id": tenant.id, "ref_code": ref_code.upper(), "published": True},
    )
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return _public(tenant, prop)


@router.get("/{slug}/slots", response_model=list[SlotOut])
async def public_slots(
    slug: str,
    db: DbDep,
    start_day: date | None = None,
    days: int = Query(default=7, ge=1, le=14),
) -> list[SlotOut]:
    tenant = await _tenant(db, slug)
    found = dedupe_by_time(await available_slots(db, tenant, start_day=start_day, days=days))
    # Don't reveal which team member is free.
    return [SlotOut(starts_at=s.starts_at, ends_at=s.ends_at) for s in found]


@router.post(
    "/{slug}/bookings",
    response_model=AppointmentOut,
    status_code=201,
    dependencies=[Depends(RateLimit("public_booking", 10, 3600))],
)
async def public_booking(slug: str, body: PublicBookingIn, db: DbDep):
    tenant = await _tenant(db, slug)
    phone = normalize_phone(body.phone)
    # Stops one number from filling the calendar, whatever IPs it comes from.
    await hit("public_booking_phone", f"{tenant.id}:{phone}", 3, 86400)
    # Check the slot before creating a lead, so a taken slot doesn't leave a stray contact.
    starts_at = body.starts_at.astimezone(UTC)
    day = starts_at.astimezone(ZoneInfo(tenant.timezone)).date()
    if not any(
        s.starts_at == starts_at for s in await available_slots(db, tenant, start_day=day, days=1)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "That time is no longer available.")
    contact = await upsert_contact(
        db, tenant, phone.lstrip("+"), body.name, source=LeadSource.website
    )
    if body.email and not contact.email:
        contact.email = body.email
        await save(db, contact, "email")
    prop = None
    if body.property_ref:
        prop = await find_one(
            db, Property, {"tenant_id": tenant.id, "ref_code": body.property_ref.upper()}
        )
    try:
        appt = await book_appointment(
            db,
            tenant,
            contact=contact,
            starts_at=body.starts_at,
            kind=body.kind,
            property_id=prop.id if prop else None,
            notes=body.notes,
        )
    except SlotUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await send_appointment_confirmation(db, tenant, contact, appt)
    return appt
