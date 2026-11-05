import re

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pymongo.errors import DuplicateKeyError

from app.api.deps import CurrentPrincipal, DbDep, get_owned
from app.core.db import coll, find, insert, save
from app.core.queue import enqueue
from app.models import (
    Chunk,
    Document,
    DocumentSource,
    DocumentStatus,
    ListingType,
    Media,
    MediaKind,
    Property,
    PropertyStatus,
    PropertyType,
)
from app.schemas.common import Page
from app.schemas.property import (
    DocumentOut,
    MediaOut,
    PropertyCreate,
    PropertyOut,
    PropertyUpdate,
)
from app.services.storage import DOC_TYPES, IMAGE_TYPES, delete_file, public_url, save_upload

router = APIRouter(tags=["properties"])

# Fields whose change alters what the assistant should know about a listing.
_INDEXED_FIELDS = {
    "title",
    "description",
    "listing_type",
    "property_type",
    "status",
    "price",
    "area_sqft",
    "bedrooms",
    "bathrooms",
    "city",
    "locality",
    "address",
    "amenities",
    "published",
}


async def _next_ref_code(db, tenant_id: str) -> str:
    highest = 1000
    async for row in coll(db, Property).find(
        {"tenant_id": tenant_id, "ref_code": {"$regex": r"^PR-\d+$"}}, {"ref_code": 1}
    ):
        highest = max(highest, int(row["ref_code"][3:]))
    return f"PR-{highest + 1}"


@router.get("/properties", response_model=Page[PropertyOut])
async def list_properties(
    p: CurrentPrincipal,
    db: DbDep,
    q: str | None = None,
    status_: PropertyStatus | None = Query(default=None, alias="status"),
    property_type: PropertyType | None = None,
    listing_type: ListingType | None = None,
    published: bool | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
) -> Page[PropertyOut]:
    query: dict = {"tenant_id": p.tenant_id}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"ref_code": rx}, {"locality": rx}, {"city": rx}]
    if status_:
        query["status"] = status_
    if property_type:
        query["property_type"] = property_type
    if listing_type:
        query["listing_type"] = listing_type
    if published is not None:
        query["published"] = published
    total = await coll(db, Property).count_documents(query)
    rows = await find(db, Property, query, sort=[("updated_at", -1)], limit=limit, skip=offset)
    return Page(items=[PropertyOut.model_validate(r) for r in rows], total=total)


@router.post("/properties", response_model=PropertyOut, status_code=201)
async def create_property(body: PropertyCreate, p: CurrentPrincipal, db: DbDep) -> Property:
    data = body.model_dump()
    ref = data.pop("ref_code") or await _next_ref_code(db, p.tenant_id)
    prop = Property(tenant_id=p.tenant_id, ref_code=ref, **data)
    try:
        await insert(db, prop)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ref code {ref} already exists") from None
    if prop.published:
        await enqueue("index_property", prop.id)
    return prop


@router.get("/properties/{property_id}", response_model=PropertyOut)
async def get_property(property_id: str, p: CurrentPrincipal, db: DbDep) -> Property:
    return await get_owned(db, Property, property_id, p.tenant_id)


@router.patch("/properties/{property_id}", response_model=PropertyOut)
async def update_property(
    property_id: str, body: PropertyUpdate, p: CurrentPrincipal, db: DbDep
) -> Property:
    prop = await get_owned(db, Property, property_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(prop, k, v)
    if data:
        await save(db, prop, *data)
    if _INDEXED_FIELDS & data.keys():
        await enqueue("index_property", prop.id)
    return prop


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str, p: CurrentPrincipal, db: DbDep) -> None:
    prop = await get_owned(db, Property, property_id, p.tenant_id)
    for d in await find(db, Document, {"property_id": prop.id}):
        delete_file(d.storage_path)
    for m in prop.media:
        delete_file(m.path)
    await coll(db, Chunk).delete_many({"property_id": prop.id})
    await coll(db, Document).delete_many({"property_id": prop.id})
    await coll(db, Property).delete_one({"_id": prop.id})


@router.post("/properties/{property_id}/media", response_model=MediaOut, status_code=201)
async def upload_media(
    property_id: str,
    p: CurrentPrincipal,
    db: DbDep,
    file: UploadFile = File(...),
    kind: MediaKind = Form(MediaKind.image),
) -> Media:
    prop = await get_owned(db, Property, property_id, p.tenant_id)
    # Listing photos are public: they appear on the listing page and are sent on WhatsApp.
    rel = await save_upload(file, p.tenant_id, IMAGE_TYPES, private=False)
    media = Media(url=public_url(rel), path=rel, kind=kind, sort_order=len(prop.media))
    await coll(db, Property).update_one({"_id": prop.id}, {"$push": {"media": media.model_dump()}})
    return media


@router.delete("/properties/{property_id}/media/{media_id}", status_code=204)
async def delete_media(property_id: str, media_id: str, p: CurrentPrincipal, db: DbDep) -> None:
    prop = await get_owned(db, Property, property_id, p.tenant_id)
    media = next((m for m in prop.media if m.id == media_id), None)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    delete_file(media.path)
    await coll(db, Property).update_one({"_id": prop.id}, {"$pull": {"media": {"id": media_id}}})


# --- Knowledge documents ----------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentOut], tags=["knowledge"])
async def list_documents(
    p: CurrentPrincipal, db: DbDep, property_id: str | None = None
) -> list[Document]:
    query: dict = {"tenant_id": p.tenant_id, "source": DocumentSource.upload}
    if property_id:
        query["property_id"] = property_id
    return await find(db, Document, query, sort=[("created_at", -1)])


@router.post("/documents", response_model=DocumentOut, status_code=202, tags=["knowledge"])
async def upload_document(
    p: CurrentPrincipal,
    db: DbDep,
    file: UploadFile = File(...),
    property_id: str | None = Form(None),
) -> Document:
    """Brochures, price sheets, FAQs. Optionally linked to a listing. Indexed in the background."""
    if property_id:
        await get_owned(db, Property, property_id, p.tenant_id)
    # Private: brochures may include unpublished pricing; only the assistant reads them.
    rel = await save_upload(file, p.tenant_id, DOC_TYPES, private=True)
    doc = await insert(
        db,
        Document(
            tenant_id=p.tenant_id,
            property_id=property_id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            storage_path=rel,
            status=DocumentStatus.pending,
        ),
    )
    await enqueue("ingest_document", doc.id)
    return doc


@router.post("/documents/{document_id}/retry", response_model=DocumentOut, tags=["knowledge"])
async def retry_document(document_id: str, p: CurrentPrincipal, db: DbDep) -> Document:
    doc = await get_owned(db, Document, document_id, p.tenant_id)
    doc.status, doc.error = DocumentStatus.pending, None
    await save(db, doc, "status", "error")
    await enqueue("ingest_document", doc.id)
    return doc


@router.delete("/documents/{document_id}", status_code=204, tags=["knowledge"])
async def delete_document(document_id: str, p: CurrentPrincipal, db: DbDep) -> None:
    doc = await get_owned(db, Document, document_id, p.tenant_id)
    delete_file(doc.storage_path)
    await coll(db, Chunk).delete_many({"document_id": doc.id})
    await coll(db, Document).delete_one({"_id": doc.id})
