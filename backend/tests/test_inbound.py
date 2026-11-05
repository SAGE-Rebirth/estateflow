import json
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.core.db import coll, find, find_one, insert
from app.models import (
    Appointment,
    Contact,
    Conversation,
    ConversationMode,
    Direction,
    LeadStage,
    ListingType,
    Media,
    Message,
    Notification,
    Property,
    PropertyStatus,
    PropertyType,
)
from app.services.inbound import handle_inbound
from app.services.llm.base import AgentResult, ToolCallRecord, run_tool
from app.services.storage import resolve
from app.services.whatsapp.webhook import InboundMessage

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2030, 1, 7, 8, 0, tzinfo=IST).astimezone(UTC)  # Monday 08:00 IST


class ScriptedProvider:
    """Plays back a fixed list of tool calls, then answers with a fixed reply."""

    def __init__(self, calls: list[tuple[str, dict]], reply: str = "Done!") -> None:
        self.calls = calls
        self.reply = reply
        self.outputs: list[ToolCallRecord] = []
        self.seen_history = None
        self.system = ""

    async def run(self, *, system_stable, system_dynamic, history, tools, execute, max_iterations):
        self.seen_history = history
        self.system = system_stable + system_dynamic
        for name, args in self.calls:
            self.outputs.append(await run_tool(execute, name, args))
        return AgentResult(text=self.reply, tool_calls=self.outputs)


def msg(text: str, wamid: str = "wamid.in.1", wa_id: str = "919876500001", **kw) -> InboundMessage:
    return InboundMessage(
        phone_number_id="PNID1",
        wa_message_id=wamid,
        wa_id=wa_id,
        profile_name="Ravi",
        timestamp=NOW,
        type=kw.pop("type", "text"),
        text=text,
        raw=kw.pop("raw", {}),
        **kw,
    )


async def _listing(db, tenant, **kw) -> Property:
    defaults = dict(
        ref_code="PR-1001",
        title="3BHK Lake View",
        listing_type=ListingType.sale,
        property_type=PropertyType.apartment,
        status=PropertyStatus.available,
        price=9_500_000,
        bedrooms=3,
        city="Bengaluru",
        locality="Hebbal",
        published=True,
        amenities=["gym"],
        description="Corner unit",
    )
    return await insert(db, Property(tenant_id=tenant.id, **{**defaults, **kw}))


async def test_first_message_creates_lead_and_assistant_books_visit(
    db, tenant_with_agent, whatsapp
):
    tenant, agent = tenant_with_agent
    prop = await _listing(db, tenant)
    await _listing(
        db,
        tenant,
        ref_code="PR-1002",
        title="2BHK Starter",
        price=4_500_000,
        bedrooms=2,
        locality="Yelahanka",
    )

    slot_start = datetime.combine(date(2030, 1, 7), time(11), IST).isoformat()
    provider = ScriptedProvider(
        [
            ("search_properties", {"min_bedrooms": 3, "max_price": 10_000_000}),
            (
                "update_lead_profile",
                {"budget_max": 10_000_000, "bedrooms": 3, "preferred_locations": ["Hebbal"]},
            ),
            ("get_available_slots", {"from_date": "2030-01-07", "days": 1}),
            ("book_appointment", {"start": slot_start, "kind": "site_visit"}),
        ],
        reply="Booked your visit for Monday 11 AM!",
    )
    out = await handle_inbound(
        db,
        tenant,
        msg("Hi, I'm interested in PR-1001. Can I visit?"),
        whatsapp=whatsapp,
        provider=provider,
        now=NOW,
    )

    assert out is not None and out.body == "Booked your visit for Monday 11 AM!"
    assert whatsapp.sent == [("919876500001", "Booked your visit for Monday 11 AM!")]
    assert whatsapp.read == ["wamid.in.1"]

    search, _, slots, booking = (json.loads(r.output) for r in provider.outputs)
    assert [m["ref_code"] for m in search["matches"]] == ["PR-1001"]
    assert "/properties/skyline/PR-1001" in search["matches"][0]["link"]
    assert slots["slots"][0]["label"].startswith("Mon 07 Jan, 10:00")
    assert booking["booked"] and booking["property"] == "PR-1001"  # focus from the ref code

    contact = await find_one(db, Contact, {})
    assert contact.phone == "+919876500001" and contact.name == "Ravi"
    assert contact.bedrooms == 3 and contact.budget_max == 10_000_000
    assert contact.stage == LeadStage.visit_scheduled
    assert contact.assigned_to == agent.id
    assert [i.ref_code for i in contact.interests] == ["PR-1001"]

    appt = await find_one(db, Appointment, {})
    assert appt.property_id == prop.id and appt.created_by_bot
    assert appt.location == "Hebbal, Bengaluru"

    kinds = {n.kind for n in await find(db, Notification, {})}
    assert kinds == {"new_lead", "appointment_booked"}
    assert [t.role for t in provider.seen_history] == ["user"]
    assert "Skyline Homes" in provider.system and "Property in focus: PR-1001" in provider.system

    conv = await find_one(db, Conversation, {})
    assert conv.last_direction == Direction.outbound and conv.unread_count == 1


async def test_duplicate_webhook_is_ignored(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent
    provider = ScriptedProvider([], reply="Hello!")
    await handle_inbound(db, tenant, msg("hi"), whatsapp=whatsapp, provider=provider, now=NOW)
    again = await handle_inbound(
        db, tenant, msg("hi"), whatsapp=whatsapp, provider=provider, now=NOW
    )
    assert again is None
    assert len(whatsapp.sent) == 1
    assert await coll(db, Message).count_documents({}) == 2


async def test_human_mode_silences_assistant_and_notifies(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent
    provider = ScriptedProvider(
        [("request_human", {"reason": "wants a discount"})], reply="Connecting you with our team."
    )
    await handle_inbound(
        db, tenant, msg("Can you do 10% off?"), whatsapp=whatsapp, provider=provider, now=NOW
    )
    conv = await find_one(db, Conversation, {})
    assert conv.mode == ConversationMode.human

    out = await handle_inbound(
        db, tenant, msg("hello?", wamid="wamid.in.2"), whatsapp=whatsapp, provider=provider, now=NOW
    )
    assert out is None
    assert len(whatsapp.sent) == 1
    kinds = {n.kind for n in await find(db, Notification, {})}
    assert {"handoff", "inbound_message"} <= kinds
    conv = await find_one(db, Conversation, {})
    assert conv.last_direction == Direction.inbound


async def test_history_alternates_roles(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent
    await handle_inbound(
        db,
        tenant,
        msg("hi"),
        whatsapp=whatsapp,
        provider=ScriptedProvider([], reply="Hi Ravi!"),
        now=NOW,
    )
    p2 = ScriptedProvider([], reply="Sure")
    await handle_inbound(
        db, tenant, msg("2bhk?", wamid="wamid.in.2"), whatsapp=whatsapp, provider=p2, now=NOW
    )
    assert [(t.role, t.content) for t in p2.seen_history] == [
        ("user", "hi"),
        ("assistant", "Hi Ravi!"),
        ("user", "2bhk?"),
    ]


async def test_tool_errors_go_back_to_model_and_unpublished_hidden(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent
    await _listing(db, tenant, ref_code="PR-2000", published=False)
    provider = ScriptedProvider(
        [
            ("get_property_details", {"ref_code": "PR-2000"}),
            ("book_appointment", {"start": "not-a-date", "kind": "site_visit"}),
        ]
    )
    await handle_inbound(db, tenant, msg("PR-2000?"), whatsapp=whatsapp, provider=provider, now=NOW)
    assert [r.is_error for r in provider.outputs] == [True, True]
    assert "No published listing" in provider.outputs[0].output


async def test_llm_failure_hands_off_with_safe_reply(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent

    class Broken:
        async def run(self, **_):
            raise RuntimeError("provider down")

    out = await handle_inbound(db, tenant, msg("hi"), whatsapp=whatsapp, provider=Broken(), now=NOW)
    assert "team" in out.body
    assert (await find_one(db, Conversation, {})).mode == ConversationMode.human


async def test_photo_is_stored_privately_and_described(
    db, tenant_with_agent, whatsapp, monkeypatch
):
    tenant, _ = tenant_with_agent
    await _listing(db, tenant)
    whatsapp.media["m1"] = (b"\x89PNG fake", "image/png")

    async def describe(data, mime):
        assert data == b"\x89PNG fake" and mime == "image/png"
        return "Screenshot of listing PR-1001 showing price 95 lakh"

    monkeypatch.setattr("app.services.hf.describe_image", describe)
    provider = ScriptedProvider([], reply="That's our Hebbal 3BHK!")
    await handle_inbound(
        db,
        tenant,
        msg(
            "[image] is this available?",
            type="image",
            media_id="m1",
            media_mime="image/png",
            raw={"image": {"id": "m1", "caption": "is this available?"}},
        ),
        whatsapp=whatsapp,
        provider=provider,
        now=NOW,
    )
    inbound = await find_one(db, Message, {"direction": "inbound"})
    assert inbound.media_kind == "image" and inbound.media_path.startswith("private/")
    assert resolve(inbound.media_path).read_bytes() == b"\x89PNG fake"
    assert inbound.body.startswith("[photo] Screenshot of listing PR-1001")
    assert "Caption: is this available?" in inbound.body
    # The ref code read off the photo links the buyer to the listing.
    assert provider.seen_history[-1].content == inbound.body
    assert "Property in focus: PR-1001" in provider.system


async def test_voice_note_is_transcribed(db, tenant_with_agent, whatsapp, monkeypatch):
    tenant, _ = tenant_with_agent
    whatsapp.media["v1"] = (b"OggS...", "audio/ogg; codecs=opus")

    async def transcribe(data):
        return "Do you have any villas in Whitefield?"

    monkeypatch.setattr("app.services.hf.transcribe", transcribe)
    provider = ScriptedProvider([], reply="Yes!")
    await handle_inbound(
        db,
        tenant,
        msg("[voice note]", type="audio", media_id="v1"),
        whatsapp=whatsapp,
        provider=provider,
        now=NOW,
    )
    inbound = await find_one(db, Message, {"direction": "inbound"})
    assert inbound.body == "[voice note] Do you have any villas in Whitefield?"
    assert inbound.media_mime == "audio/ogg" and inbound.media_path.endswith(".ogg")


async def test_assistant_sends_listing_photos(db, tenant_with_agent, whatsapp):
    tenant, _ = tenant_with_agent
    await _listing(
        db,
        tenant,
        media=[
            Media(url=f"https://cdn.example.com/{i}.jpg", path=f"public/x/{i}.jpg")
            for i in range(6)
        ],
    )
    provider = ScriptedProvider(
        [("send_property_photos", {"ref_code": "pr-1001"})], reply="Sent you the photos."
    )
    await handle_inbound(
        db, tenant, msg("photos please"), whatsapp=whatsapp, provider=provider, now=NOW
    )
    assert json.loads(provider.outputs[0].output)["sent"] == 4
    assert [link for _, link, _ in whatsapp.images] == [
        f"https://cdn.example.com/{i}.jpg" for i in range(4)
    ]
    assert whatsapp.images[0][2] == "3BHK Lake View"
