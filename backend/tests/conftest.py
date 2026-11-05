import hashlib
import os

import pytest
from cryptography.fernet import Fernet

# Tests never touch the real database or Hugging Face, whatever the root .env says.
os.environ.update(
    {
        "MONGO_URL": os.environ.get(
            "TEST_MONGO_URL", "mongodb://localhost:27017/?directConnection=true"
        ),
        "DB_NAME": "estateflow_test",
        "COLLECTION_NAME": "chunks",
        "VECTOR_SEARCH_MODE": "exact",
        "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"),
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-jwt-secret-that-is-long-enough-32",
        "REFRESH_SECRET_KEY": "test-refresh-secret-long-enough-32-xx",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "WHATSAPP_APP_SECRET": "test-secret",
        "WHATSAPP_VERIFY_TOKEN": "verify-me",
        "BOOKING_MIN_LEAD_MINUTES": "0",
        "HUGGINGFACEHUB_API_TOKEN": "",
        "ANTHROPIC_API_KEY": "",
        "UPLOAD_DIR": os.path.join(os.path.dirname(__file__), ".uploads"),
    }
)

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import ensure_indexes, get_database, insert  # noqa: E402
from app.core.ratelimit import get_redis  # noqa: E402
from app.core.security import encrypt_secret, hash_password  # noqa: E402
from app.models import AvailabilityRule, Role, Tenant, User  # noqa: E402

ORIGIN = "http://localhost:3000"


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder, so tests need no model calls."""

    dim = get_settings().embedding_dim

    def _vec(self, text_: str) -> list[float]:
        v = [0.0] * self.dim
        for word in text_.lower().split():
            h = int(hashlib.md5(word.strip(".,:;!?").encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    async def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    async def embed_query(self, text_):
        return self._vec(text_)


class FakeWhatsApp:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str | None]] = []
        self.templates: list[tuple[str, str, list[str]]] = []
        self.read: list[str] = []
        self.media: dict[str, tuple[bytes, str]] = {}

    async def send_text(self, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"wamid.out.{len(self.sent)}"

    async def send_image(self, to: str, link: str, caption: str | None = None) -> str:
        self.images.append((to, link, caption))
        return f"wamid.img.{len(self.images)}"

    async def send_template(self, to, name, language, body_params=None) -> str:
        self.templates.append((to, name, body_params or []))
        return f"wamid.tpl.{len(self.templates)}"

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        return self.media[media_id]

    async def mark_read(self, wa_message_id: str) -> None:
        self.read.append(wa_message_id)


@pytest.fixture(scope="session", autouse=True)
async def _indexes():
    db = get_database()
    await db.client.drop_database(get_settings().db_name)
    await ensure_indexes(db)
    yield


@pytest.fixture(autouse=True)
async def _clean(monkeypatch):
    db = get_database()
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    await get_redis().flushdb()
    fake = FakeEmbedder()
    monkeypatch.setattr("app.services.rag.ingest.get_embedder", lambda: fake)
    monkeypatch.setattr("app.services.rag.retriever.get_embedder", lambda: fake)
    yield


@pytest.fixture
def db():
    return get_database()


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[tuple] = []

    async def fake_enqueue(job, *args, job_id=None):
        calls.append((job, *args))

    for mod in ("properties", "webhooks"):
        monkeypatch.setattr(f"app.api.routes.{mod}.enqueue", fake_enqueue)
    return calls


@pytest.fixture
def whatsapp() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
async def tenant_with_agent(db):
    """A tenant with WhatsApp configured and one agent available every day 10:00–13:00."""
    tenant = await insert(
        db,
        Tenant(
            name="Skyline Homes",
            slug="skyline",
            timezone="Asia/Kolkata",
            currency="INR",
            whatsapp_phone_number_id="PNID1",
            whatsapp_display_number="+91 98765 43210",
            whatsapp_access_token_enc=encrypt_secret("token"),
        ),
    )
    agent = await insert(
        db,
        User(
            tenant_id=tenant.id,
            email="agent@skyline.example.com",
            full_name="Asha Agent",
            password_hash=hash_password("password123"),
            role=Role.owner,
            availability=[
                AvailabilityRule(weekday=d, start_time="10:00", end_time="13:00") for d in range(7)
            ],
        ),
    )
    return tenant, agent


@pytest.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def signup(client, slug="acme", email="owner@acme.example.com") -> dict[str, str]:
    """Signs up in token mode and returns Bearer headers (API-client style)."""
    r = await client.post(
        "/api/v1/auth/signup",
        headers={"X-Auth-Mode": "token"},
        json={
            "business_name": f"{slug.title()} Realty",
            "slug": slug,
            "full_name": "Owner",
            "email": email,
            "password": "supersecret1",
        },
    )
    assert r.status_code == 201, r.text
    client.cookies.clear()  # keep tests on Bearer unless they opt into cookies
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
