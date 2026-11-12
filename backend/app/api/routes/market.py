"""Public marketplace: listings from every active business that opts in, for buyers.

The per-business storefront endpoints live in public.py; these aggregate across sellers.
"""

import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import DbDep
from app.api.routes.public import whatsapp_link
from app.core.db import Db, coll, find, find_one
from app.core.ratelimit import RateLimit
from app.models import (
    LISTABLE_STATUSES,
    ListingType,
    MediaKind,
    Property,
    PropertyStatus,
    PropertyType,
    Tenant,
)

router = APIRouter(
    prefix="/market", tags=["marketplace"], dependencies=[Depends(RateLimit("market", 300, 60))]
)

Sort = Literal["newest", "price_asc", "price_desc", "area_desc"]
SORTS: dict[str, list[tuple[str, int]]] = {
    "newest": [("created_at", -1)],
    "price_asc": [("price", 1), ("created_at", -1)],
    "price_desc": [("price", -1), ("created_at", -1)],
    "area_desc": [("area_sqft", -1), ("created_at", -1)],
}


class Seller(BaseModel):
    name: str
    slug: str
    whatsapp_number: str | None


class MarketListing(BaseModel):
    id: str
    slug: str  # seller slug; listing URL is /properties/{slug}/{ref_code}
    ref_code: str
    title: str
    listing_type: ListingType
    property_type: PropertyType
    status: PropertyStatus
    price: float | None
    price_per_sqft: float | None
    area_sqft: float | None
    bedrooms: int | None
    bathrooms: int | None
    locality: str | None
    city: str | None
    amenities: list[str]
    photo: str | None
    photo_count: int
    seller_name: str
    whatsapp_url: str | None
    listed_at: datetime


class MarketListingDetail(MarketListing):
    description: str
    photos: list[str]
    floorplans: list[str]
    latitude: float | None
    longitude: float | None
    seller: Seller
    similar: list[MarketListing]


class Count(BaseModel):
    value: str
    count: int


class MarketSummary(BaseModel):
    total: int
    for_sale: int
    for_rent: int
    cities: list[Count]
    localities: list[Count]
    property_types: list[Count]


async def _sellers(db: Db) -> dict[str, Tenant]:
    tenants = await find(db, Tenant, {"is_active": True, "list_on_marketplace": {"$ne": False}})
    return {t.id: t for t in tenants}


def _base(sellers: dict[str, Tenant]) -> dict:
    return {
        "tenant_id": {"$in": list(sellers)},
        "published": True,
        "status": {"$in": list(LISTABLE_STATUSES)},
    }


def _images(p: Property, *kinds: MediaKind) -> list[str]:
    return [m.url for m in sorted(p.media, key=lambda m: m.sort_order) if m.kind in kinds]


def to_listing(p: Property, seller: Tenant) -> MarketListing:
    photos = _images(p, MediaKind.image)
    return MarketListing(
        id=p.id,
        slug=seller.slug,
        ref_code=p.ref_code,
        title=p.title,
        listing_type=p.listing_type,
        property_type=p.property_type,
        status=p.status,
        price=p.price,
        price_per_sqft=round(p.price / p.area_sqft)
        if p.price and p.area_sqft and p.listing_type == ListingType.sale
        else None,
        area_sqft=p.area_sqft,
        bedrooms=p.bedrooms,
        bathrooms=p.bathrooms,
        locality=p.locality,
        city=p.city,
        amenities=p.amenities[:6],
        photo=photos[0] if photos else None,
        photo_count=len(photos),
        seller_name=seller.name,
        whatsapp_url=whatsapp_link(seller, p),
        listed_at=p.created_at,
    )


def _ci(value: str) -> dict:
    return {"$regex": f"^{re.escape(value.strip())}$", "$options": "i"}


@router.get("/listings")
async def listings(
    db: DbDep,
    q: str | None = Query(None, max_length=100, description="Words in title, area or description"),
    city: str | None = None,
    locality: str | None = None,
    listing_type: ListingType | None = None,
    property_type: list[PropertyType] | None = Query(None),
    bedrooms: list[int] | None = Query(None, description="4 means 4 or more"),
    min_price: float | None = None,
    max_price: float | None = None,
    seller: str | None = Query(None, description="Seller slug"),
    sort: Sort = "newest",
    limit: int = Query(default=20, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
) -> dict:
    sellers = await _sellers(db)
    query = _base(sellers)
    and_: list[dict] = []
    if seller:
        ids = [t.id for t in sellers.values() if t.slug == seller]
        query["tenant_id"] = {"$in": ids}
    if q:
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        and_.append(
            {
                "$or": [
                    {"title": rx},
                    {"locality": rx},
                    {"city": rx},
                    {"description": rx},
                    {"ref_code": rx},
                ]
            }
        )
    if city:
        query["city"] = _ci(city)
    if locality:
        query["locality"] = _ci(locality)
    if listing_type:
        query["listing_type"] = listing_type
    if property_type:
        query["property_type"] = {"$in": property_type}
    if bedrooms:
        exact = [b for b in bedrooms if b < 4]
        options: list[dict] = [{"bedrooms": {"$in": exact}}] if exact else []
        if any(b >= 4 for b in bedrooms):
            options.append({"bedrooms": {"$gte": 4}})
        and_.append({"$or": options})
    price: dict = {}
    if min_price is not None:
        price["$gte"] = min_price
    if max_price is not None:
        price["$lte"] = max_price
    if price:
        query["price"] = price
    if and_:
        query["$and"] = and_
    total = await coll(db, Property).count_documents(query)
    rows = await find(db, Property, query, sort=SORTS[sort], limit=limit, skip=offset)
    return {
        "items": [to_listing(p, sellers[p.tenant_id]) for p in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/listings/{slug}/{ref_code}", response_model=MarketListingDetail)
async def listing_detail(slug: str, ref_code: str, db: DbDep) -> MarketListingDetail:
    seller = await find_one(db, Tenant, {"slug": slug, "is_active": True})
    prop = (
        await find_one(
            db,
            Property,
            {
                "tenant_id": seller.id,
                "ref_code": ref_code.upper(),
                "published": True,
                # Sold/rented pages stay up for shared links; drafts are never public.
                "status": {"$ne": PropertyStatus.draft},
            },
        )
        if seller
        else None
    )
    if seller is None or prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")

    sellers = await _sellers(db)
    similar_q = {
        **_base(sellers),
        "_id": {"$ne": prop.id},
        "listing_type": prop.listing_type,
        "city": prop.city,
    }
    similar = await find(
        db,
        Property,
        {**similar_q, "property_type": prop.property_type},
        sort=[("created_at", -1)],
        limit=4,
    )
    if len(similar) < 4:  # widen to any type in the same city
        similar += await find(
            db,
            Property,
            {**similar_q, "_id": {"$nin": [prop.id, *(s.id for s in similar)]}},
            sort=[("created_at", -1)],
            limit=4 - len(similar),
        )
    return MarketListingDetail(
        **to_listing(prop, seller).model_dump(),
        description=prop.description,
        photos=_images(prop, MediaKind.image),
        floorplans=_images(prop, MediaKind.floorplan),
        latitude=prop.latitude,
        longitude=prop.longitude,
        seller=Seller(
            name=seller.name, slug=seller.slug, whatsapp_number=seller.whatsapp_display_number
        ),
        similar=[to_listing(s, sellers[s.tenant_id]) for s in similar if s.tenant_id in sellers],
    )


@router.get("/summary", response_model=MarketSummary)
async def summary(db: DbDep) -> MarketSummary:
    """Counts for the home page: how many homes, where, and of what kind."""
    query = _base(await _sellers(db))

    async def counts(field: str, limit: int) -> list[Count]:
        rows = await coll(db, Property).aggregate(
            [
                {"$match": {**query, field: {"$nin": [None, ""]}}},
                {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
                {"$limit": limit},
            ]
        )
        return [Count(value=r["_id"], count=r["count"]) async for r in rows]

    props = coll(db, Property)
    return MarketSummary(
        total=await props.count_documents(query),
        for_sale=await props.count_documents({**query, "listing_type": ListingType.sale}),
        for_rent=await props.count_documents({**query, "listing_type": ListingType.rent}),
        cities=await counts("city", 12),
        localities=await counts("locality", 16),
        property_types=await counts("property_type", 6),
    )
