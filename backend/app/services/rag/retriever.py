import math
from dataclasses import dataclass
from typing import Any

import structlog
from pymongo.errors import OperationFailure

from app.core.config import get_settings
from app.core.db import Db, coll
from app.models import Chunk
from app.services.rag.embeddings import get_embedder

log = structlog.get_logger()

# Cosine similarity below this is treated as "not relevant" and dropped.
MIN_SCORE = 0.4
EXACT_SCAN_LIMIT = 5000


@dataclass
class RetrievedChunk:
    content: str
    property_id: str | None
    ref_code: str | None
    source: str
    score: float


def _filter(tenant_id: str, property_id: str | None) -> dict[str, Any]:
    f: dict[str, Any] = {"tenant_id": tenant_id, "active": True}
    if property_id is not None:
        # The listing's own chunks plus tenant-wide documents (FAQs, policies).
        f["property_id"] = {"$in": [property_id, None]}
    return f


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


async def _atlas(db: Db, vector: list[float], f: dict[str, Any], k: int) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": get_settings().vector_index_name,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(100, k * 20),
                "limit": k,
                "filter": f,
            }
        },
        {"$project": {"embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
    ]
    rows = [r async for r in await coll(db, Chunk).aggregate(pipeline)]
    # Atlas cosine score is (1 + cos) / 2; convert back so thresholds are comparable.
    for r in rows:
        r["score"] = 2 * r["score"] - 1
    return rows


async def _exact(db: Db, vector: list[float], f: dict[str, Any], k: int) -> list[dict]:
    rows = [r async for r in coll(db, Chunk).find(f, limit=EXACT_SCAN_LIMIT)]
    for r in rows:
        r["score"] = _cosine(vector, r.pop("embedding"))
    return sorted(rows, key=lambda r: r["score"], reverse=True)[:k]


async def search_chunks(
    db: Db, tenant_id: str, query: str, *, property_id: str | None = None, k: int = 6
) -> list[RetrievedChunk]:
    vector = await get_embedder().embed_query(query)
    f = _filter(tenant_id, property_id)
    if get_settings().vector_search_mode == "atlas":
        try:
            rows = await _atlas(db, vector, f, k)
        except OperationFailure as exc:
            log.warning("vector_search_fallback", error=str(exc)[:200])
            rows = await _exact(db, vector, f, k)
    else:
        rows = await _exact(db, vector, f, k)
    return [
        RetrievedChunk(
            content=r["content"],
            property_id=r.get("property_id"),
            ref_code=r.get("ref_code"),
            source=r.get("source", ""),
            score=float(r["score"]),
        )
        for r in rows
        if r["score"] >= MIN_SCORE
    ]
