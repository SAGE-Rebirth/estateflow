"""Re-embed every listing and uploaded document: `uv run python -m app.scripts.reindex`.

Run after changing GEMINI_EMBEDDING_MODEL or EMBEDDING_DIM. Vectors from different models
or sizes can't be compared, so search returns nothing useful until this finishes. Uses the
database in MONGO_URL / DB_NAME and also updates the Atlas vector index if needed.
"""

import asyncio
import sys

from app.core.db import close_client, coll, ensure_indexes, find, get_database
from app.models import Chunk, Document, DocumentSource, Property, Tenant
from app.services.rag.ingest import index_property, ingest_document


async def main() -> int:
    db = get_database()
    await ensure_indexes(db)
    currencies = {t.id: t.currency for t in await find(db, Tenant, {})}
    props = await find(db, Property, {})
    for n, p in enumerate(props, 1):
        try:
            await index_property(db, p.id, currencies.get(p.tenant_id, "INR"))
        except Exception as exc:  # stop early: the cause (key, quota, network) hits every item
            print(f"\nListing {p.ref_code} failed: {str(exc)[:300]}")
            print("Fix the cause above and run this again; finished items are already done.")
            return 1
        print(f"\rListings  {n}/{len(props)}", end="", flush=True)
    print()
    docs = await find(db, Document, {"source": DocumentSource.upload})
    failed = 0
    for n, d in enumerate(docs, 1):
        await ingest_document(db, d.id)
        failed += (await coll(db, Document).find_one({"_id": d.id}, {"status": 1}))[
            "status"
        ] == "failed"
        print(f"\rDocuments {n}/{len(docs)}", end="", flush=True)
    print()
    # Chunks whose document no longer exists would keep stale vectors forever.
    live = {d.id for d in await find(db, Document, {})}
    orphans = await coll(db, Chunk).delete_many({"document_id": {"$nin": list(live)}})
    print(
        f"Re-embedded {len(props)} listings and {len(docs)} documents "
        f"({failed} failed; see Documents in the dashboard). "
        f"Removed {orphans.deleted_count} orphaned chunks."
    )
    return 0


async def _run() -> int:
    try:
        return await main()
    finally:
        await close_client()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
