"""MongoDB access: one async client per process, typed helpers, indexes."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from fastapi import HTTPException, status
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, IndexModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from app.core.config import get_settings
from app.models import (
    Activity,
    Appointment,
    Chunk,
    Contact,
    Conversation,
    Document,
    Message,
    MongoModel,
    Notification,
    Property,
    Task,
    Tenant,
    User,
    utcnow,
)

log = structlog.get_logger()

M = TypeVar("M", bound=MongoModel)
Db = AsyncDatabase[dict[str, Any]]

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(get_settings().mongo_url, tz_aware=True, appname="estateflow")
    return _client


def get_database() -> Db:
    return get_client()[get_settings().db_name]


async def get_db() -> Db:
    """FastAPI dependency."""
    return get_database()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def coll(db: Db, model: type[MongoModel]) -> AsyncCollection:
    if model is Chunk:
        return db[get_settings().chunks_collection]
    return db[model.collection]


# --- Typed helpers -------------------------------------------------------------------


async def insert(db: Db, obj: M, session: AsyncClientSession | None = None) -> M:
    await coll(db, type(obj)).insert_one(obj.dump(), session=session)
    return obj


async def find_one(db: Db, model: type[M], query: dict[str, Any], **kw: Any) -> M | None:
    return model.load(await coll(db, model).find_one(query, **kw))


async def find(
    db: Db,
    model: type[M],
    query: dict[str, Any],
    *,
    sort: list[tuple[str, int]] | None = None,
    limit: int = 0,
    skip: int = 0,
    session: AsyncClientSession | None = None,
) -> list[M]:
    cursor = coll(db, model).find(query, sort=sort, limit=limit, skip=skip, session=session)
    return [model.model_validate(d) async for d in cursor]


async def save(
    db: Db, obj: MongoModel, *fields: str, session: AsyncClientSession | None = None
) -> None:
    """Persist the named fields of `obj` (all fields when none are named)."""
    obj.updated_at = utcnow()
    data = obj.dump()
    data.pop("_id")
    if fields:
        data = {k: data[k] for k in (*fields, "updated_at")}
    await coll(db, type(obj)).update_one({"_id": obj.id}, {"$set": data}, session=session)


async def get_owned(db: Db, model: type[M], obj_id: str, tenant_id: str) -> M:
    """Fetch a tenant-owned document or 404 — never leak another tenant's data."""
    obj = await find_one(db, model, {"_id": obj_id, "tenant_id": tenant_id})
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


async def in_transaction(fn: Callable[[AsyncClientSession], Awaitable[Any]]) -> Any:
    """Run `fn` in a multi-document transaction, retrying transient conflicts."""
    async with get_client().start_session() as s:
        return await s.with_transaction(fn)


# --- Indexes -------------------------------------------------------------------------

INDEXES: dict[type[MongoModel], list[IndexModel]] = {
    Tenant: [
        IndexModel("slug", unique=True),
        IndexModel(
            "whatsapp_phone_number_id",
            unique=True,
            partialFilterExpression={"whatsapp_phone_number_id": {"$type": "string"}},
        ),
    ],
    User: [IndexModel("email", unique=True), IndexModel("tenant_id")],
    Property: [
        IndexModel([("tenant_id", ASCENDING), ("ref_code", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING), ("published", ASCENDING), ("status", ASCENDING)]),
    ],
    Document: [IndexModel([("tenant_id", ASCENDING), ("property_id", ASCENDING)])],
    Chunk: [
        IndexModel("document_id"),
        IndexModel([("tenant_id", ASCENDING), ("active", ASCENDING)]),
    ],
    Contact: [
        IndexModel([("tenant_id", ASCENDING), ("phone", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING), ("stage", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("updated_at", DESCENDING)]),
    ],
    Task: [IndexModel([("tenant_id", ASCENDING), ("done_at", ASCENDING), ("due_at", ASCENDING)])],
    Activity: [IndexModel([("contact_id", ASCENDING), ("created_at", DESCENDING)])],
    Notification: [
        IndexModel([("user_id", ASCENDING), ("read_at", ASCENDING), ("created_at", DESCENDING)])
    ],
    Conversation: [
        IndexModel([("tenant_id", ASCENDING), ("contact_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("last_message_at", DESCENDING)]),
    ],
    Message: [
        IndexModel([("conversation_id", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel(
            "wa_message_id",
            unique=True,
            partialFilterExpression={"wa_message_id": {"$type": "string"}},
        ),
    ],
    Appointment: [
        IndexModel([("tenant_id", ASCENDING), ("starts_at", ASCENDING)]),
        IndexModel([("user_id", ASCENDING), ("starts_at", ASCENDING)]),
        IndexModel([("status", ASCENDING), ("starts_at", ASCENDING)]),
    ],
}


async def ensure_indexes(db: Db | None = None) -> None:
    db = db if db is not None else get_database()
    for model, indexes in INDEXES.items():
        await coll(db, model).create_indexes(indexes)
    if get_settings().vector_search_mode == "atlas":
        await ensure_vector_index(db)


async def ensure_vector_index(db: Db) -> None:
    s = get_settings()
    chunks = coll(db, Chunk)
    try:
        existing = [i async for i in await chunks.list_search_indexes(s.vector_index_name)]
        if existing:
            return
        if s.chunks_collection not in await db.list_collection_names():
            await db.create_collection(s.chunks_collection)
        await chunks.create_search_index(
            SearchIndexModel(
                name=s.vector_index_name,
                type="vectorSearch",
                definition={
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": s.embedding_dim,
                            "similarity": "cosine",
                        },
                        {"type": "filter", "path": "tenant_id"},
                        {"type": "filter", "path": "property_id"},
                        {"type": "filter", "path": "active"},
                    ]
                },
            )
        )
        log.info("vector_index_created", index=s.vector_index_name)
    except OperationFailure as exc:
        log.warning("vector_index_unavailable", error=str(exc)[:200])
