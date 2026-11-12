"""Turn uploaded files and property records into embedded chunks."""

import asyncio
from pathlib import Path

import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.core.db import Db, coll, find_one, insert, save
from app.models import (
    Chunk,
    Document,
    DocumentSource,
    DocumentStatus,
    Property,
)
from app.services.money import format_money
from app.services.rag.embeddings import get_embedder
from app.services.storage import resolve

log = structlog.get_logger()

EMBED_BATCH = 100


def _load_text(path: Path, content_type: str | None) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        from pypdf import PdfReader

        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        import docx2txt

        return docx2txt.process(str(path))
    return path.read_text(encoding="utf-8", errors="replace")


def _splitter() -> RecursiveCharacterTextSplitter:
    s = get_settings()
    return RecursiveCharacterTextSplitter(chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)


def property_to_text(p: Property, currency: str) -> str:
    """Canonical text form of a listing so the assistant can answer free-text questions."""
    lines = [
        f"Property {p.ref_code}: {p.title}",
        f"Type: {p.property_type.value.replace('_', ' ')} for {p.listing_type.value}",
        f"Status: {p.status.value.replace('_', ' ')}",
    ]
    if p.price is not None:
        lines.append(f"Price: {format_money(p.price, currency)}")
    if p.area_sqft is not None:
        lines.append(f"Area: {p.area_sqft:,.0f} sq ft")
    if p.bedrooms is not None:
        lines.append(f"Bedrooms: {p.bedrooms}")
    if p.bathrooms is not None:
        lines.append(f"Bathrooms: {p.bathrooms}")
    location = ", ".join(x for x in (p.locality, p.city) if x)
    if location:
        lines.append(f"Location: {location}")
    if p.address:
        lines.append(f"Address: {p.address}")
    if p.amenities:
        lines.append(f"Amenities: {', '.join(p.amenities)}")
    if p.description:
        lines += ["", p.description]
    return "\n".join(lines)


async def _write_chunks(db: Db, doc: Document, text: str, prop: Property | None) -> int:
    pieces = [t for t in _splitter().split_text(text) if t.strip()]
    vectors: list[list[float]] = []
    embedder = get_embedder()
    for i in range(0, len(pieces), EMBED_BATCH):
        vectors += await embedder.embed_documents(pieces[i : i + EMBED_BATCH])
    # Embed first, then swap: a failed embedding call leaves the old chunks searchable.
    await coll(db, Chunk).delete_many({"document_id": doc.id})
    if pieces:
        await coll(db, Chunk).insert_many(
            [
                Chunk(
                    tenant_id=doc.tenant_id,
                    document_id=doc.id,
                    property_id=doc.property_id,
                    ref_code=prop.ref_code if prop else None,
                    active=prop.listable if prop else True,
                    ordinal=n,
                    content=content,
                    embedding=vector,
                    source=doc.filename,
                ).dump()
                for n, (content, vector) in enumerate(zip(pieces, vectors, strict=True))
            ]
        )
    return len(pieces)


async def ingest_document(db: Db, document_id: str) -> None:
    doc = await find_one(db, Document, {"_id": document_id})
    if doc is None:
        return
    doc.status = DocumentStatus.processing
    await save(db, doc, "status")
    try:
        text = await asyncio.to_thread(
            _load_text, resolve(doc.storage_path or ""), doc.content_type
        )
        if not text.strip():
            raise ValueError("No extractable text (scanned PDFs need OCR)")
        prop = await find_one(db, Property, {"_id": doc.property_id}) if doc.property_id else None
        doc.chunk_count = await _write_chunks(db, doc, text, prop)
        doc.status, doc.error = DocumentStatus.ready, None
    except Exception as exc:  # recorded on the document so the admin sees why
        doc.status, doc.error = DocumentStatus.failed, str(exc)[:2000]
        log.exception("ingest_failed", document_id=document_id)
    await save(db, doc, "status", "error", "chunk_count")


async def index_property(db: Db, property_id: str, currency: str) -> None:
    """(Re)build the listing's own document and sync visibility of all its chunks."""
    prop = await find_one(db, Property, {"_id": property_id})
    if prop is None:
        return
    # Brochures of a sold/unpublished listing must stop showing up in answers.
    await coll(db, Chunk).update_many(
        {"property_id": prop.id}, {"$set": {"active": prop.listable, "ref_code": prop.ref_code}}
    )
    doc = await find_one(
        db, Document, {"property_id": prop.id, "source": DocumentSource.property_listing}
    )
    if not prop.published:
        if doc is not None:
            await coll(db, Chunk).delete_many({"document_id": doc.id})
            await coll(db, Document).delete_one({"_id": doc.id})
        return
    if doc is None:
        doc = await insert(
            db,
            Document(
                tenant_id=prop.tenant_id,
                property_id=prop.id,
                source=DocumentSource.property_listing,
                filename=f"listing-{prop.ref_code}",
                content_type="text/plain",
            ),
        )
    doc.chunk_count = await _write_chunks(db, doc, property_to_text(prop, currency), prop)
    doc.status = DocumentStatus.ready
    await save(db, doc, "chunk_count", "status")


async def delete_document_chunks(db: Db, document_id: str) -> None:
    await coll(db, Chunk).delete_many({"document_id": document_id})
