import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings, get_settings
from app.core.db import coll, ensure_vector_index, find, find_one, insert, save
from app.models import (
    Appointment,
    AppointmentKind,
    Chunk,
    Contact,
    Document,
    DocumentStatus,
    ListingType,
    Notification,
    Property,
    PropertyStatus,
    PropertyType,
    Task,
)
from app.services.rag import retriever
from app.services.rag.ingest import index_property, ingest_document
from app.services.rag.retriever import search_chunks
from app.services.storage import save_bytes
from app.workers.jobs import run_daily_digest, run_reminders

FAQ = (
    "Payment plan: 10% on booking, 80% construction linked, 10% on possession.\n\n"
    "Possession date is December 2031. Clubhouse with swimming pool and gym."
)


async def _villa(db, tenant, **kw) -> Property:
    return await insert(
        db,
        Property(
            tenant_id=tenant.id,
            ref_code="PR-1001",
            title="Garden Villa",
            listing_type=ListingType.sale,
            property_type=PropertyType.villa,
            status=PropertyStatus.available,
            price=30_000_000,
            published=True,
            description="Private garden with jacuzzi",
            amenities=["jacuzzi"],
            **kw,
        ),
    )


async def test_ingest_upload_and_search_scoped_to_tenant(db, tenant_with_agent):
    tenant, _ = tenant_with_agent
    path = save_bytes(FAQ.encode(), tenant.id, ".txt", private=True)
    doc = await insert(
        db,
        Document(
            tenant_id=tenant.id, filename="faq.txt", content_type="text/plain", storage_path=path
        ),
    )
    await ingest_document(db, doc.id)
    doc = await find_one(db, Document, {"_id": doc.id})
    assert doc.status == DocumentStatus.ready and doc.chunk_count >= 1

    hits = await search_chunks(db, tenant.id, "what is the payment plan on booking")
    assert hits and "Payment plan" in hits[0].content
    assert await search_chunks(db, "other-tenant", "payment plan") == []


async def test_failed_ingest_is_recorded(db, tenant_with_agent):
    tenant, _ = tenant_with_agent
    doc = await insert(
        db,
        Document(
            tenant_id=tenant.id,
            filename="missing.pdf",
            storage_path="private/x/nope.pdf",
            content_type="application/pdf",
        ),
    )
    await ingest_document(db, doc.id)
    doc = await find_one(db, Document, {"_id": doc.id})
    assert doc.status == DocumentStatus.failed and doc.error


async def test_listing_and_brochure_visibility_follow_status(db, tenant_with_agent):
    tenant, _ = tenant_with_agent
    prop = await _villa(db, tenant)
    path = save_bytes(
        b"Villa brochure: jacuzzi on the terrace, Italian marble.", tenant.id, ".txt", private=True
    )
    brochure = await insert(
        db,
        Document(
            tenant_id=tenant.id, property_id=prop.id, filename="brochure.txt", storage_path=path
        ),
    )
    await ingest_document(db, brochure.id)
    await index_property(db, prop.id, "INR")
    hits = await search_chunks(db, tenant.id, "villa with jacuzzi")
    assert {h.source for h in hits} == {"listing-PR-1001", "brochure.txt"}
    assert all(h.ref_code == "PR-1001" for h in hits)
    assert any("₹3,00,00,000 (3 crore)" in h.content for h in hits)

    prop.status = PropertyStatus.sold
    await save(db, prop, "status")
    await index_property(db, prop.id, "INR")
    assert await search_chunks(db, tenant.id, "villa with jacuzzi") == []

    prop.published = False
    await save(db, prop, "published")
    await index_property(db, prop.id, "INR")
    # The listing's own text is gone; the brochure stays stored but hidden.
    assert await coll(db, Chunk).count_documents({"source": "listing-PR-1001"}) == 0
    assert await coll(db, Chunk).count_documents({"active": True}) == 0


async def test_atlas_vector_search(db, tenant_with_agent, monkeypatch):
    """Real $vectorSearch against Atlas Local (skips on plain MongoDB)."""
    tenant, _ = tenant_with_agent
    monkeypatch.setattr(get_settings(), "vector_search_mode", "atlas")
    await ensure_vector_index(db)
    chunks = coll(db, Chunk)
    try:
        indexes = [i async for i in await chunks.list_search_indexes()]
    except Exception:
        pytest.skip("Atlas Search not available")
    if not indexes:
        pytest.skip("Atlas Search not available")

    prop = await _villa(db, tenant)
    path = save_bytes(FAQ.encode(), tenant.id, ".txt", private=True)
    faq = await insert(db, Document(tenant_id=tenant.id, filename="faq.txt", storage_path=path))
    await ingest_document(db, faq.id)
    await index_property(db, prop.id, "INR")

    called = []
    original = retriever._atlas

    async def spy(*a, **kw):
        called.append(True)
        return await original(*a, **kw)

    monkeypatch.setattr(retriever, "_atlas", spy)
    for _ in range(60):  # index sync is asynchronous
        hits = await search_chunks(db, tenant.id, "villa with jacuzzi")
        if hits:
            break
        await asyncio.sleep(1)
    assert called and hits[0].ref_code == "PR-1001"
    # Filters: other tenants see nothing; property scope keeps tenant-wide docs.
    assert await search_chunks(db, "someone-else", "villa with jacuzzi") == []
    scoped = await search_chunks(db, tenant.id, "payment plan possession", property_id=prop.id)
    assert any(h.source == "faq.txt" for h in scoped)


async def test_reminders_fire_once(db, tenant_with_agent, monkeypatch):
    tenant, agent = tenant_with_agent
    now = datetime(2030, 1, 7, 4, 0, tzinfo=UTC)
    contact = await insert(
        db,
        Contact(
            tenant_id=tenant.id,
            phone="+919000000001",
            wa_id="919000000001",
            name="Ravi",
            last_inbound_at=now - timedelta(hours=1),
        ),
    )
    await insert(
        db,
        Appointment(
            tenant_id=tenant.id,
            contact_id=contact.id,
            user_id=agent.id,
            kind=AppointmentKind.site_visit,
            starts_at=now + timedelta(minutes=50),
            ends_at=now + timedelta(minutes=110),
            location="Hebbal",
        ),
    )
    await insert(
        db,
        Task(
            tenant_id=tenant.id,
            contact_id=contact.id,
            assigned_to=agent.id,
            title="Call Ravi",
            due_at=now + timedelta(minutes=10),
        ),
    )
    sent = []

    async def fake_send(db_, tenant_, contact_, appt, whatsapp=None, now=None):
        sent.append(appt.id)
        return True

    monkeypatch.setattr("app.workers.jobs.send_appointment_reminder", fake_send)
    first = await run_reminders(db, now)
    second = await run_reminders(db, now + timedelta(minutes=5))
    assert first == {"client_24h": 0, "client_2h": 1, "agent_1h": 1, "tasks": 1}
    assert second == {"client_24h": 0, "client_2h": 0, "agent_1h": 0, "tasks": 0}
    assert len(sent) == 1
    assert sorted(n.kind for n in await find(db, Notification, {})) == [
        "appointment_soon",
        "task_due",
    ]


async def test_failed_client_reminder_is_retried(db, tenant_with_agent, monkeypatch):
    tenant, agent = tenant_with_agent
    now = datetime(2030, 1, 7, 4, 0, tzinfo=UTC)
    contact = await insert(db, Contact(tenant_id=tenant.id, phone="+919000000002"))
    await insert(
        db,
        Appointment(
            tenant_id=tenant.id,
            contact_id=contact.id,
            user_id=agent.id,
            kind=AppointmentKind.call,
            starts_at=now + timedelta(hours=5),
            ends_at=now + timedelta(hours=6),
        ),
    )
    outcomes = iter([False, True])

    async def flaky(*a, **kw):
        return next(outcomes)

    monkeypatch.setattr("app.workers.jobs.send_appointment_reminder", flaky)
    assert (await run_reminders(db, now))["client_24h"] == 0
    assert (await run_reminders(db, now))["client_24h"] == 1


async def test_daily_digest_at_7am_local_once(db, tenant_with_agent):
    tenant, agent = tenant_with_agent
    seven_ist = datetime(2030, 1, 7, 1, 35, tzinfo=UTC)  # 07:05 IST
    await insert(
        db,
        Task(
            tenant_id=tenant.id,
            assigned_to=agent.id,
            title="Follow up",
            due_at=seven_ist + timedelta(hours=3),
        ),
    )
    assert await run_daily_digest(db, seven_ist - timedelta(hours=1)) == 0
    assert await run_daily_digest(db, seven_ist) == 1
    assert await run_daily_digest(db, seven_ist + timedelta(minutes=30)) == 0
    note = await find_one(db, Notification, {})
    assert note.title == "Today: 0 meetings, 1 follow-up"


def test_settings_read_user_env_names():
    s = Settings(
        _env_file=None,
        MONGO_URL="mongodb+srv://x/",
        DB_NAME="crm",
        COLLECTION_NAME="knowledge",
        SECRET_KEY="a" * 40,
        REFRESH_SECRET_KEY="b" * 40,
        GEMINI_API_KEY="g_x",
    )
    assert (s.mongo_url, s.db_name, s.chunks_collection) == ("mongodb+srv://x/", "crm", "knowledge")
    assert (s.jwt_secret, s.jwt_refresh_secret, s.gemini_api_key) == ("a" * 40, "b" * 40, "g_x")


def test_production_refuses_default_secrets():
    with pytest.raises(ValueError, match="default secrets"):
        Settings(
            _env_file=None,
            environment="production",
            SECRET_KEY="change-me-in-production",
            encryption_key="",
            whatsapp_app_secret="",
        )


def test_inr_prices_use_indian_grouping_and_words():
    from app.services.money import format_money

    assert format_money(950, "INR") == "₹950"
    assert format_money(480_000, "INR") == "₹4,80,000 (4.8 lakh)"
    assert format_money(9_500_000, "INR") == "₹95,00,000 (95 lakh)"
    assert format_money(125_000_000, "INR") == "₹12,50,00,000 (12.5 crore)"
    assert format_money(1_250_000, "USD") == "USD 1,250,000"
