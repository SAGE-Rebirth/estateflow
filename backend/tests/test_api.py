import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from app.core.db import find_one, insert
from app.models import Conversation, ConversationMode, Message, Tenant
from app.services.inbound import handle_inbound
from app.services.llm.base import AgentResult
from app.services.storage import save_bytes
from app.services.whatsapp.webhook import InboundMessage
from tests.conftest import ORIGIN, signup

API = "/api/v1"


async def test_cookie_session_lifecycle(client):
    r = await client.post(
        f"{API}/auth/signup",
        json={
            "business_name": "Acme Realty",
            "slug": "acme",
            "full_name": "Owner",
            "email": "owner@acme.example.com",
            "password": "supersecret1",
        },
    )
    assert r.status_code == 201
    # Browser mode: no credentials in the body, httpOnly cookies instead.
    assert r.json()["access_token"] is None
    set_cookie = r.headers.get_list("set-cookie")
    assert any(
        c.startswith("ef_access=") and "HttpOnly" in c and "SameSite=lax" in c for c in set_cookie
    )
    assert any(c.startswith("ef_refresh=") and "Path=/api/v1/auth" in c for c in set_cookie)

    me = await client.get(f"{API}/auth/me")
    assert me.status_code == 200 and me.json()["tenant"]["slug"] == "acme"

    # Cookie-authenticated writes need one of our origins (CSRF defence).
    body = {"title": "Plot", "listing_type": "sale", "property_type": "plot"}
    assert (await client.post(f"{API}/properties", json=body)).status_code == 403
    assert (
        await client.post(
            f"{API}/properties", json=body, headers={"Origin": "https://evil.example"}
        )
    ).status_code == 403

    # Refresh works from the cookie alone.
    client.cookies.delete("ef_access")
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    r = await client.post(f"{API}/auth/refresh", headers={"Origin": ORIGIN})
    assert r.status_code == 200
    assert (await client.get(f"{API}/auth/me")).status_code == 200

    # The public header's session check: always 200, and a refresh cookie alone counts.
    assert (await client.get(f"{API}/auth/session")).json() == {"signed_in": True}
    client.cookies.delete("ef_access")
    assert (await client.get(f"{API}/auth/session")).json() == {"signed_in": True}

    # Logout clears the cookies.
    r = await client.post(f"{API}/auth/logout", headers={"Origin": ORIGIN})
    assert r.status_code == 204
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    r = await client.get(f"{API}/auth/session")
    assert r.status_code == 200 and r.json() == {"signed_in": False}


async def test_logout_everywhere_and_password_change_revoke_tokens(client, enqueued):
    headers = await signup(client)
    old_refresh = (
        await client.post(
            f"{API}/auth/login",
            headers={"X-Auth-Mode": "token"},
            json={"email": "owner@acme.example.com", "password": "supersecret1"},
        )
    ).json()["refresh_token"]
    client.cookies.clear()

    r = await client.post(
        f"{API}/auth/password",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "newsecret123"},
    )
    assert r.status_code == 400
    r = await client.post(
        f"{API}/auth/password",
        headers={**headers, "X-Auth-Mode": "token"},
        json={"current_password": "supersecret1", "new_password": "newsecret123"},
    )
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.cookies.clear()
    # Tokens issued before the change no longer work; the new ones do.
    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 401
    assert (
        await client.post(f"{API}/auth/refresh", json={"refresh_token": old_refresh})
    ).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers=fresh)).status_code == 200

    assert (await client.post(f"{API}/auth/logout-all", headers=fresh)).status_code == 204
    assert (await client.get(f"{API}/auth/me", headers=fresh)).status_code == 401


async def test_login_rate_limit(client):
    await signup(client)
    codes = []
    for _ in range(12):
        r = await client.post(
            f"{API}/auth/login", json={"email": "owner@acme.example.com", "password": "nope-nope"}
        )
        codes.append(r.status_code)
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]
    assert "Retry-After" in r.headers
    # Even the right password is refused until the window passes.
    r = await client.post(
        f"{API}/auth/login", json={"email": "owner@acme.example.com", "password": "supersecret1"}
    )
    assert r.status_code == 429


async def test_properties_crud_and_tenant_isolation(client, enqueued):
    a = await signup(client, "acme", "a@acme.example.com")
    b = await signup(client, "beta", "b@beta.example.com")
    body = {
        "title": "Sea View Villa",
        "listing_type": "sale",
        "property_type": "villa",
        "price": 25000000,
        "bedrooms": 4,
        "city": "Goa",
        "published": True,
        "status": "available",
    }
    r = await client.post(f"{API}/properties", json=body, headers=a)
    assert r.status_code == 201, r.text
    prop = r.json()
    assert prop["ref_code"] == "PR-1001"
    assert enqueued == [("index_property", prop["id"])]
    assert (await client.post(f"{API}/properties", json=body, headers=a)).json()[
        "ref_code"
    ] == "PR-1002"
    assert (await client.post(f"{API}/properties", json=body, headers=b)).json()[
        "ref_code"
    ] == "PR-1001"

    assert (await client.get(f"{API}/properties/{prop['id']}", headers=b)).status_code == 404
    assert (
        await client.patch(f"{API}/properties/{prop['id']}", json={"title": "x"}, headers=b)
    ).status_code == 404
    assert (await client.get(f"{API}/properties", headers=a)).json()["total"] == 2
    assert (await client.get(f"{API}/properties", headers=b)).json()["total"] == 1

    enqueued.clear()
    r = await client.patch(f"{API}/properties/{prop['id']}", json={"price": 24000000}, headers=a)
    assert r.json()["price"] == 24000000
    assert enqueued == [("index_property", prop["id"])]


async def test_public_site_and_whatsapp_link(client, enqueued):
    headers = await signup(client)
    await client.put(
        f"{API}/tenant/whatsapp",
        headers=headers,
        json={"phone_number_id": "PN1", "display_number": "+91 98765 43210", "access_token": "t"},
    )
    for pub in (True, False):
        await client.post(
            f"{API}/properties",
            headers=headers,
            json={
                "title": f"Flat {pub}",
                "listing_type": "rent",
                "property_type": "apartment",
                "price": 30000,
                "published": pub,
                "status": "available",
            },
        )
    listing = (await client.get(f"{API}/public/acme/properties")).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["whatsapp_url"].startswith("https://wa.me/919876543210?text=Hi%2C%20I%27m%20")
    assert "PR-1001" in item["whatsapp_url"]
    assert (await client.get(f"{API}/public/acme/properties/PR-1002")).status_code == 404
    assert (await client.get(f"{API}/public/nope")).status_code == 404
    assert (await client.get(f"{API}/public/acme/properties?city=(((")).status_code == 200


async def test_public_booking_then_dashboard_today(client, enqueued):
    headers = await signup(client)
    slots = (await client.get(f"{API}/public/acme/slots?days=7")).json()
    assert slots and slots[0]["user_id"] is None
    start = slots[0]["starts_at"]
    r = await client.post(
        f"{API}/public/acme/bookings",
        json={"name": "Meera", "phone": "98765 11111", "starts_at": start, "kind": "site_visit"},
    )
    assert r.status_code == 201, r.text
    r2 = await client.post(
        f"{API}/public/acme/bookings",
        json={"name": "Other", "phone": "98765 22222", "starts_at": start},
    )
    assert r2.status_code == 409

    contact = (await client.get(f"{API}/contacts", headers=headers)).json()["items"][0]
    assert contact["phone"] == "+919876511111"
    assert contact["source"] == "website" and contact["stage"] == "visit_scheduled"

    appts = (await client.get(f"{API}/appointments", headers=headers)).json()
    assert appts[0]["contact_name"] == "Meera" and appts[0]["agent_name"] == "Owner"

    notes = (await client.get(f"{API}/notifications", headers=headers)).json()
    assert {n["kind"] for n in notes} == {"new_lead", "appointment_booked"}
    assert any(n["title"] == "New website lead: Meera" for n in notes)
    assert (await client.get(f"{API}/notifications/unread-count", headers=headers)).json() == {
        "count": 2
    }
    await client.post(f"{API}/notifications/read", headers=headers)
    assert (await client.get(f"{API}/notifications/unread-count", headers=headers)).json() == {
        "count": 0
    }


async def test_public_booking_limited_per_phone(client, enqueued):
    await signup(client)
    slots = (await client.get(f"{API}/public/acme/slots?days=7")).json()
    codes = []
    for s in slots[:4]:
        r = await client.post(
            f"{API}/public/acme/bookings",
            json={"name": "Spammer", "phone": "98765 33333", "starts_at": s["starts_at"]},
        )
        codes.append(r.status_code)
    assert codes == [201, 201, 201, 429]


async def test_staff_appointment_override_task_and_stage_timeline(client, enqueued):
    headers = await signup(client)
    contact = (
        await client.post(
            f"{API}/contacts", headers=headers, json={"phone": "+14155550123", "name": "Sam"}
        )
    ).json()
    start = (datetime.now(UTC) + timedelta(hours=3)).replace(microsecond=0)
    r = await client.post(
        f"{API}/appointments",
        headers=headers,
        json={
            "contact_id": contact["id"],
            "starts_at": start.isoformat(),
            "kind": "call",
            "override_availability": True,
            "duration_minutes": 30,
            "notify_client": False,
        },
    )
    assert r.status_code == 201, r.text
    appt = r.json()
    overlap = await client.post(
        f"{API}/appointments",
        headers=headers,
        json={
            "contact_id": contact["id"],
            "starts_at": (start + timedelta(minutes=15)).isoformat(),
            "override_availability": True,
            "notify_client": False,
        },
    )
    assert overlap.status_code == 409

    # Rescheduling onto another appointment is refused too.
    other = (
        await client.post(
            f"{API}/appointments",
            headers=headers,
            json={
                "contact_id": contact["id"],
                "starts_at": (start + timedelta(hours=2)).isoformat(),
                "override_availability": True,
                "notify_client": False,
            },
        )
    ).json()
    r = await client.patch(
        f"{API}/appointments/{other['id']}", headers=headers, json={"starts_at": start.isoformat()}
    )
    assert r.status_code == 409
    r = await client.patch(
        f"{API}/appointments/{appt['id']}",
        headers=headers,
        json={"status": "completed", "outcome": "Liked it"},
    )
    assert r.json()["status"] == "completed"

    task = (
        await client.post(
            f"{API}/tasks",
            headers=headers,
            json={
                "title": "Send brochure",
                "due_at": (start - timedelta(days=2)).isoformat(),
                "contact_id": contact["id"],
            },
        )
    ).json()
    today = (await client.get(f"{API}/dashboard/today", headers=headers)).json()
    assert [t["id"] for t in today["tasks_overdue"]] == [task["id"]]
    await client.patch(f"{API}/tasks/{task['id']}", headers=headers, json={"done": True})
    today = (await client.get(f"{API}/dashboard/today", headers=headers)).json()
    assert today["tasks_overdue"] == []

    await client.patch(
        f"{API}/contacts/{contact['id']}", headers=headers, json={"stage": "negotiation"}
    )
    timeline = (
        await client.get(f"{API}/contacts/{contact['id']}/activities", headers=headers)
    ).json()
    assert timeline[0]["kind"] == "stage_change"
    assert timeline[0]["summary"] == "Stage: visit_scheduled → negotiation"

    stats = (await client.get(f"{API}/dashboard/stats", headers=headers)).json()
    assert stats["pipeline"]["negotiation"] == 1


async def test_agent_role_cannot_manage_team(client):
    owner = await signup(client)
    r = await client.post(
        f"{API}/users",
        headers=owner,
        json={"email": "agent@acme.example.com", "full_name": "Agent", "password": "password123"},
    )
    assert r.status_code == 201
    tok = (
        await client.post(
            f"{API}/auth/login",
            headers={"X-Auth-Mode": "token"},
            json={"email": "agent@acme.example.com", "password": "password123"},
        )
    ).json()["access_token"]
    client.cookies.clear()
    agent = {"Authorization": f"Bearer {tok}"}
    assert (
        await client.post(
            f"{API}/users",
            headers=agent,
            json={"email": "x@acme.example.com", "full_name": "X", "password": "password123"},
        )
    ).status_code == 403
    assert (
        await client.patch(f"{API}/tenant", headers=agent, json={"name": "Hacked"})
    ).status_code == 403
    # Deactivating the agent ends their session immediately.
    await client.patch(f"{API}/users/{r.json()['id']}", headers=owner, json={"is_active": False})
    assert (await client.get(f"{API}/auth/me", headers=agent)).status_code == 401


async def test_availability_rules_and_days_off(client):
    headers = await signup(client)
    rules = (await client.get(f"{API}/availability/rules", headers=headers)).json()
    assert len(rules) == 6 and rules[0]["start_time"] == "10:00"
    r = await client.put(
        f"{API}/availability/rules",
        headers=headers,
        json=[{"weekday": 0, "start_time": "09:00:00", "end_time": "12:00", "slot_minutes": 30}],
    )
    assert r.json() == [
        {"weekday": 0, "start_time": "09:00", "end_time": "12:00", "slot_minutes": 30}
    ]
    day = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    off = (
        await client.post(f"{API}/availability/exceptions", headers=headers, json={"day": day})
    ).json()
    assert off["day"] == day
    assert len((await client.get(f"{API}/availability/exceptions", headers=headers)).json()) == 1
    assert (
        await client.delete(f"{API}/availability/exceptions/{off['id']}", headers=headers)
    ).status_code == 204


async def test_whatsapp_webhook_verification_and_signature(client, enqueued):
    r = await client.get(
        f"{API}/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"},
    )
    assert r.status_code == 200 and r.text == "42"
    assert (
        await client.get(
            f"{API}/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "42"},
        )
    ).status_code == 403

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PN1"},
                            "contacts": [{"wa_id": "9198", "profile": {"name": "Ravi"}}],
                            "messages": [
                                {
                                    "id": "wamid.A",
                                    "from": "9198",
                                    "timestamp": "1700000000",
                                    "type": "interactive",
                                    "interactive": {"button_reply": {"title": "Book a visit"}},
                                }
                            ],
                            "statuses": [{"id": "wamid.out.1", "status": "read"}],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    bad = await client.post(
        f"{API}/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=deadbeef"}
    )
    assert bad.status_code == 401
    sig = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    ok = await client.post(
        f"{API}/webhooks/whatsapp",
        content=raw,
        headers={"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"},
    )
    assert ok.status_code == 200
    assert [c[0] for c in enqueued] == ["process_inbound_message", "process_status_update"]


async def test_handed_over_chat_counts_until_someone_replies(client, db, whatsapp, monkeypatch):
    headers = await signup(client)
    tenant = await find_one(db, Tenant, {"slug": "acme"})

    class Handoff:
        async def run(self, *, execute, **_):
            await execute("request_human", {"reason": "price negotiation"})
            return AgentResult(text="Connecting you to the team.")

    def event(wamid, text):
        return InboundMessage(
            "PN", wamid, "919800000000", "Kiran", datetime.now(UTC), "text", text, {}
        )

    await handle_inbound(
        db, tenant, event("wamid.x", "Best price?"), whatsapp=whatsapp, provider=Handoff()
    )
    conv = await find_one(db, Conversation, {})
    assert conv.mode == ConversationMode.human

    async def waiting():
        r = await client.get(f"{API}/dashboard/today", headers=headers)
        return r.json()["conversations_needing_human"]

    assert await waiting() == 0  # the assistant's handover message was last
    await handle_inbound(
        db, tenant, event("wamid.y", "Hello?"), whatsapp=whatsapp, provider=Handoff()
    )
    assert await waiting() == 1
    # Opening the thread marks it read but doesn't make the reply happen.
    await client.get(f"{API}/conversations/{conv.id}/messages", headers=headers)
    assert await waiting() == 1
    monkeypatch.setattr("app.services.inbound.WhatsAppClient", lambda tenant: whatsapp)
    r = await client.post(
        f"{API}/conversations/{conv.id}/messages",
        headers=headers,
        json={"body": "Hi Kiran, calling you now."},
    )
    assert r.status_code == 201 and r.json()["status"] == "sent"
    assert await waiting() == 0


async def test_buyer_media_is_private_to_the_tenant(client, db):
    a = await signup(client, "acme", "a@acme.example.com")
    b = await signup(client, "beta", "b@beta.example.com")
    tenant = await find_one(db, Tenant, {"slug": "acme"})
    conv = await insert(db, Conversation(tenant_id=tenant.id, contact_id="c1"))
    path = save_bytes(b"voice-bytes", tenant.id, ".ogg", private=True)
    m = await insert(
        db,
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction="inbound",
            sender_type="contact",
            body="[voice note]",
            media_kind="audio",
            media_path=path,
            media_mime="audio/ogg",
        ),
    )
    url = f"{API}/conversations/{conv.id}/messages/{m.id}/media"
    r = await client.get(url, headers=a)
    assert r.status_code == 200 and r.content == b"voice-bytes"
    assert r.headers["content-type"] == "audio/ogg"
    assert (await client.get(url, headers=b)).status_code == 404
    assert (await client.get(url)).status_code == 401
    # Not reachable through the public static mount either.
    assert (await client.get(f"/media/{path}")).status_code == 404
    assert (await client.get(f"/media/../{path}")).status_code == 404


async def test_admin_cannot_grant_owner_role(client):
    owner = await signup(client)
    await client.post(
        f"{API}/users",
        headers=owner,
        json={
            "email": "admin@acme.example.com",
            "full_name": "Admin",
            "password": "password123",
            "role": "admin",
        },
    )
    agent = (
        await client.post(
            f"{API}/users",
            headers=owner,
            json={"email": "pawn@acme.example.com", "full_name": "Pawn", "password": "password123"},
        )
    ).json()
    tok = (
        await client.post(
            f"{API}/auth/login",
            headers={"X-Auth-Mode": "token"},
            json={"email": "admin@acme.example.com", "password": "password123"},
        )
    ).json()["access_token"]
    client.cookies.clear()
    admin = {"Authorization": f"Bearer {tok}"}
    r = await client.patch(f"{API}/users/{agent['id']}", headers=admin, json={"role": "owner"})
    assert r.status_code == 403
    assert (
        await client.patch(f"{API}/users/{agent['id']}", headers=owner, json={"role": "owner"})
    ).status_code == 200


async def test_untrusted_media_types_download_instead_of_rendering(client, db):
    headers = await signup(client)
    tenant = await find_one(db, Tenant, {"slug": "acme"})
    conv = await insert(db, Conversation(tenant_id=tenant.id, contact_id="c1"))
    path = save_bytes(b"<script>alert(1)</script>", tenant.id, "", private=True)
    m = await insert(
        db,
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction="inbound",
            sender_type="contact",
            body="[document]",
            media_kind="document",
            media_path=path,
            media_mime="text/html",
        ),
    )
    r = await client.get(f"{API}/conversations/{conv.id}/messages/{m.id}/media", headers=headers)
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]


async def test_website_booking_records_interest_only_for_published_listing(client, enqueued):
    headers = await signup(client)
    listing = {"listing_type": "sale", "property_type": "apartment"}
    shown = (
        await client.post(
            f"{API}/properties",
            headers=headers,
            json={**listing, "title": "Shown", "published": True},
        )
    ).json()
    hidden = (
        await client.post(f"{API}/properties", headers=headers, json={**listing, "title": "Hidden"})
    ).json()
    slots = (await client.get(f"{API}/public/acme/slots?days=7")).json()
    for slot, ref, phone in ((slots[0], shown, "98765 44444"), (slots[1], hidden, "98765 55555")):
        r = await client.post(
            f"{API}/public/acme/bookings",
            json={
                "name": "B",
                "phone": phone,
                "starts_at": slot["starts_at"],
                "property_ref": ref["ref_code"],
            },
        )
        assert r.status_code == 201, r.text
    appts = (await client.get(f"{API}/appointments", headers=headers)).json()
    contacts = {
        c["phone"]: c
        for c in (await client.get(f"{API}/contacts", headers=headers)).json()["items"]
    }
    seen = (
        await client.get(
            f"{API}/contacts/{contacts['+919876544444']['id']}/interests", headers=headers
        )
    ).json()
    assert [i["ref_code"] for i in seen] == [shown["ref_code"]]
    unseen = contacts["+919876555555"]
    assert (
        await client.get(f"{API}/contacts/{unseen['id']}/interests", headers=headers)
    ).json() == []
    # A guessed ref code of an unpublished listing doesn't get attached to the booking.
    assert sorted(a["property_id"] or "" for a in appts) == sorted(["", shown["id"]])


async def test_published_listing_from_api_is_live_by_default(client, enqueued):
    headers = await signup(client)
    body = {"title": "Sea view", "listing_type": "sale", "property_type": "apartment"}
    prop = (
        await client.post(f"{API}/properties", headers=headers, json={**body, "published": True})
    ).json()
    assert prop["status"] == "available"
    items = (await client.get(f"{API}/market/listings")).json()["items"]
    assert [i["ref_code"] for i in items] == [prop["ref_code"]]


async def test_agents_cannot_delete_listings_or_contacts(client, enqueued):
    owner = await signup(client)
    await client.post(
        f"{API}/users",
        headers=owner,
        json={"email": "agent@acme.example.com", "full_name": "Agent", "password": "password123"},
    )
    tok = (
        await client.post(
            f"{API}/auth/login",
            headers={"X-Auth-Mode": "token"},
            json={"email": "agent@acme.example.com", "password": "password123"},
        )
    ).json()["access_token"]
    client.cookies.clear()
    agent = {"Authorization": f"Bearer {tok}"}
    prop = (
        await client.post(
            f"{API}/properties",
            headers=owner,
            json={"title": "Plot", "listing_type": "sale", "property_type": "plot"},
        )
    ).json()
    contact = (
        await client.post(f"{API}/contacts", headers=owner, json={"phone": "98765 66666"})
    ).json()
    assert (await client.delete(f"{API}/properties/{prop['id']}", headers=agent)).status_code == 403
    assert (
        await client.delete(f"{API}/contacts/{contact['id']}", headers=agent)
    ).status_code == 403
    assert (await client.delete(f"{API}/properties/{prop['id']}", headers=owner)).status_code == 204
    assert (
        await client.delete(f"{API}/contacts/{contact['id']}", headers=owner)
    ).status_code == 204
