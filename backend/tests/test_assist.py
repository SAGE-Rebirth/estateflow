"""Smart paste endpoint against a mocked Gemini client."""

from types import SimpleNamespace as NS

import pytest

from tests.conftest import signup

API = "/api/v1"


class FakeModels:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "prompt": contents[0], "config": config})
        if self.error:
            raise self.error
        return NS(text=self.reply)


@pytest.fixture
def gemini(monkeypatch):
    fake = FakeModels()
    monkeypatch.setattr("app.services.extract.gemini_client", lambda: NS(aio=NS(models=fake)))
    monkeypatch.setattr("app.services.extract.get_settings", _settings_with_key)
    return fake


def _settings_with_key():
    from app.core.config import get_settings

    return get_settings().model_copy(update={"gemini_api_key": "k"})


async def test_extract_property_fields(client, gemini):
    headers = await signup(client)
    gemini.reply = (
        '{"title": "3BHK in Varthur", "price": 16500000, "bedrooms": 3, "city": "Bengaluru",'
        ' "listing_type": "sale", "property_type": "apartment", "address": null,'
        ' "amenities": ["gym", "pool"]}'
    )
    text = "3 BHK flat for sale in Varthur, Bengaluru. 1.65 Cr. Gym, pool."
    r = await client.post(
        f"{API}/assist/extract", headers=headers, json={"form": "property", "text": text}
    )
    assert r.status_code == 200, r.text
    assert r.json()["fields"] == {
        "title": "3BHK in Varthur",
        "price": 16500000.0,
        "bedrooms": 3,
        "city": "Bengaluru",
        "listing_type": "sale",
        "property_type": "apartment",
        "amenities": ["gym", "pool"],
    }  # nulls dropped
    call = gemini.calls[0]
    assert text in call["prompt"] and "<pasted_text>" in call["prompt"]
    assert call["config"].response_mime_type == "application/json"
    assert set(call["config"].response_json_schema["properties"]) >= {"price", "bedrooms"}


async def test_extract_rejects_bad_output_and_reports_outages(client, gemini):
    headers = await signup(client)
    body = {"form": "property", "text": "Some listing text here"}
    gemini.reply = '{"property_type": "castle"}'  # not one of our types
    r = await client.post(f"{API}/assist/extract", headers=headers, json=body)
    assert r.status_code == 503 and "Couldn't read" in r.json()["detail"]
    gemini.error = RuntimeError("402 RESOURCE_EXHAUSTED")
    r = await client.post(f"{API}/assist/extract", headers=headers, json=body)
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]


async def test_extract_contact_and_validation(client, gemini):
    headers = await signup(client)
    gemini.reply = '{"name": "Ramesh", "phone": "+91 98450 12345", "source": "referral"}'
    r = await client.post(
        f"{API}/assist/extract",
        headers=headers,
        json={"form": "contact", "text": "Ramesh (referred by Anil) +91 98450 12345"},
    )
    assert r.json()["fields"] == {
        "name": "Ramesh",
        "phone": "+91 98450 12345",
        "source": "referral",
    }
    for bad in (
        {"form": "property", "text": "short"},
        {"form": "user", "text": "x" * 20},
        {"form": "contact", "text": "x" * 8001},
    ):
        r = await client.post(f"{API}/assist/extract", headers=headers, json=bad)
        assert r.status_code == 422
    r = await client.post(f"{API}/assist/extract", json={"form": "contact", "text": "x" * 20})
    assert r.status_code == 401


async def test_contact_email_and_phone_come_from_the_text(client, gemini):
    headers = await signup(client)
    text = "I'm Ramesh, referred by Anil.\nCall +91 98450 12345 or mail ramesh.k@example.com"
    # The model garbles the email and invents a phone digit; both get corrected from the text.
    gemini.reply = '{"name": "Ramesh", "email": "rameshmk@example.com", "phone": "+91 98450 12346"}'
    r = await client.post(
        f"{API}/assist/extract", headers=headers, json={"form": "contact", "text": text}
    )
    assert r.json()["fields"] == {
        "name": "Ramesh",
        "email": "ramesh.k@example.com",
        "phone": "+91 98450 12345",
    }
    # Nothing in the text: a made-up email is dropped, not kept.
    gemini.reply = '{"name": "Asha", "email": "asha@example.com"}'
    r = await client.post(
        f"{API}/assist/extract",
        headers=headers,
        json={"form": "contact", "text": "Asha called about the Baner flat, no email given"},
    )
    assert r.json()["fields"] == {"name": "Asha"}
