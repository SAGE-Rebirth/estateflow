"""Tools the WhatsApp assistant can call. Every tool is bound to one tenant and one contact."""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.db import Db, coll, find, find_one, insert, save
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    LISTABLE_STATUSES,
    Activity,
    ActivityKind,
    Appointment,
    AppointmentKind,
    AppointmentStatus,
    Contact,
    Conversation,
    ConversationMode,
    Interest,
    ListingType,
    MediaKind,
    Property,
    PropertyType,
    Tenant,
)
from app.services.llm.base import ToolError, ToolSpec
from app.services.money import format_money
from app.services.notifications import notify, recipients_for
from app.services.rag.retriever import search_chunks
from app.services.scheduling import (
    SlotUnavailableError,
    available_slots,
    book_appointment,
    dedupe_by_time,
)
from app.services.whatsapp.client import WhatsAppError


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "search_properties",
        "Find published listings by structured filters. Returns up to `limit` matches with "
        "ref code, price, size, locality and a link. Use for budget/bedroom/location/type "
        "questions.",
        _obj(
            {
                "text": {
                    "type": "string",
                    "description": "Keywords matched against title, locality and "
                    "description, e.g. 'sea view' or 'Whitefield'.",
                },
                "city": {"type": "string"},
                "locality": {"type": "string"},
                "property_type": {"type": "string", "enum": [t.value for t in PropertyType]},
                "listing_type": {"type": "string", "enum": [t.value for t in ListingType]},
                "min_price": {"type": "number"},
                "max_price": {"type": "number"},
                "min_bedrooms": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            }
        ),
    ),
    ToolSpec(
        "get_property_details",
        "Full details of one listing by ref code (e.g. PR-1042). Also marks it as the "
        "property the person is interested in.",
        _obj({"ref_code": {"type": "string"}}, ["ref_code"]),
    ),
    ToolSpec(
        "send_property_photos",
        "Send up to 4 photos of a listing to the person on WhatsApp.",
        _obj({"ref_code": {"type": "string"}}, ["ref_code"]),
    ),
    ToolSpec(
        "search_knowledge",
        "Semantic search over the business's brochures, price sheets, FAQs and listing text. "
        "Use for free-text questions. Optionally restrict to one listing.",
        _obj({"question": {"type": "string"}, "ref_code": {"type": "string"}}, ["question"]),
    ),
    ToolSpec(
        "get_available_slots",
        "Free appointment slots for site visits/calls, in local time. Returns ISO start "
        "times to pass to book_appointment.",
        _obj(
            {
                "from_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
                "days": {"type": "integer", "minimum": 1, "maximum": 14},
            }
        ),
    ),
    ToolSpec(
        "book_appointment",
        "Book a slot the person explicitly chose. start must be an ISO start time returned "
        "by get_available_slots.",
        _obj(
            {
                "start": {"type": "string"},
                "kind": {"type": "string", "enum": [k.value for k in AppointmentKind]},
                "ref_code": {"type": "string", "description": "Listing to visit, if any"},
                "notes": {"type": "string"},
            },
            ["start", "kind"],
        ),
    ),
    ToolSpec("list_my_appointments", "Upcoming appointments for this person.", _obj({})),
    ToolSpec(
        "cancel_appointment",
        "Cancel one of this person's upcoming appointments (id from list_my_appointments).",
        _obj(
            {"appointment_id": {"type": "string"}, "reason": {"type": "string"}},
            ["appointment_id"],
        ),
    ),
    ToolSpec(
        "update_lead_profile",
        "Save what the person told you about themselves and what they want.",
        _obj(
            {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "budget_min": {"type": "number"},
                "budget_max": {"type": "number"},
                "preferred_locations": {"type": "array", "items": {"type": "string"}},
                "property_type": {"type": "string", "enum": [t.value for t in PropertyType]},
                "bedrooms": {"type": "integer"},
                "notes": {"type": "string", "description": "Anything else worth remembering"},
            }
        ),
    ),
    ToolSpec(
        "request_human",
        "Hand the conversation to a team member. The assistant stops replying afterwards.",
        _obj({"reason": {"type": "string"}}, ["reason"]),
    ),
]


@dataclass
class AgentContext:
    db: Db
    tenant: Tenant
    contact: Contact
    conversation: Conversation
    now: datetime
    whatsapp: Any = None  # WhatsAppClient, for tools that send media

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tenant.timezone)


def _money(v: float | None, currency: str) -> str | None:
    return format_money(v, currency) if v is not None else None


def listing_url(tenant: Tenant, p: Property) -> str:
    return f"{get_settings().frontend_base_url}/properties/{tenant.slug}/{p.ref_code}"


def _summary(ctx: AgentContext, p: Property) -> dict[str, Any]:
    return {
        "ref_code": p.ref_code,
        "title": p.title,
        "type": p.property_type.value,
        "for": p.listing_type.value,
        "status": p.status.value,
        "price": _money(p.price, ctx.tenant.currency),
        "bedrooms": p.bedrooms,
        "area_sqft": p.area_sqft,
        "locality": ", ".join(x for x in (p.locality, p.city) if x),
        "link": listing_url(ctx.tenant, p),
    }


async def _property_by_ref(ctx: AgentContext, ref_code: str) -> Property:
    prop = await find_one(
        ctx.db,
        Property,
        {"tenant_id": ctx.tenant.id, "ref_code": ref_code.strip().upper(), "published": True},
    )
    if prop is None:
        raise ToolError(f"No published listing with ref code {ref_code}")
    return prop


async def record_interest(ctx: AgentContext, prop: Property, source: str = "whatsapp") -> None:
    ctx.conversation.focus_property_id = prop.id
    await save(ctx.db, ctx.conversation, "focus_property_id")
    if any(i.property_id == prop.id for i in ctx.contact.interests):
        return
    interest = Interest(
        property_id=prop.id, ref_code=prop.ref_code, title=prop.title, source=source
    )
    ctx.contact.interests.append(interest)
    await coll(ctx.db, Contact).update_one(
        {"_id": ctx.contact.id, "interests.property_id": {"$ne": prop.id}},
        {"$push": {"interests": interest.model_dump()}},
    )
    await insert(
        ctx.db,
        Activity(
            tenant_id=ctx.tenant.id,
            contact_id=ctx.contact.id,
            kind=ActivityKind.property_interest,
            summary=f"Interested in {prop.ref_code} - {prop.title}",
            meta={"property_id": prop.id},
        ),
    )


async def search_properties(ctx: AgentContext, args: dict[str, Any]) -> Any:
    q: dict[str, Any] = {
        "tenant_id": ctx.tenant.id,
        "published": True,
        "status": {"$in": list(LISTABLE_STATUSES)},
    }
    if text := args.get("text"):
        rx = {"$regex": re.escape(text), "$options": "i"}
        q["$or"] = [{"title": rx}, {"locality": rx}, {"city": rx}, {"description": rx}]
    for field in ("city", "locality"):
        if val := args.get(field):
            q[field] = {"$regex": re.escape(val), "$options": "i"}
    if pt := args.get("property_type"):
        q["property_type"] = PropertyType(pt)
    if lt := args.get("listing_type"):
        q["listing_type"] = ListingType(lt)
    price: dict[str, float] = {}
    if (mn := args.get("min_price")) is not None:
        price["$gte"] = float(mn)
    if (mx := args.get("max_price")) is not None:
        price["$lte"] = float(mx)
    if price:
        q["price"] = price
    if (beds := args.get("min_bedrooms")) is not None:
        q["bedrooms"] = {"$gte": int(beds)}
    limit = max(1, min(int(args.get("limit") or 5), 8))
    rows = await find(ctx.db, Property, q, sort=[("price", 1)], limit=limit)
    if not rows:
        return {"matches": [], "note": "No listings match. Suggest relaxing a filter."}
    return {"matches": [_summary(ctx, p) for p in rows]}


async def get_property_details(ctx: AgentContext, args: dict[str, Any]) -> Any:
    prop = await _property_by_ref(ctx, args["ref_code"])
    await record_interest(ctx, prop)
    return {
        **_summary(ctx, prop),
        "bathrooms": prop.bathrooms,
        "address": prop.address,
        "amenities": prop.amenities,
        "description": prop.description[:3000],
        "photo_count": sum(1 for m in prop.media if m.kind == MediaKind.image),
    }


async def send_property_photos(ctx: AgentContext, args: dict[str, Any]) -> Any:
    prop = await _property_by_ref(ctx, args["ref_code"])
    photos = [m for m in prop.media if m.kind in (MediaKind.image, MediaKind.floorplan)][:4]
    if not photos:
        return {"sent": 0, "note": "This listing has no photos yet. Offer a site visit."}
    if ctx.whatsapp is None:
        raise ToolError("Photos can't be sent right now")
    to = ctx.contact.wa_id or ctx.contact.phone.lstrip("+")
    sent = 0
    for i, m in enumerate(photos):
        try:
            await ctx.whatsapp.send_image(to, m.url, caption=prop.title if i == 0 else None)
            sent += 1
        except WhatsAppError:
            break
    await record_interest(ctx, prop)
    return {"sent": sent, "note": "Photos are already delivered; don't repeat their links."}


async def search_knowledge_tool(ctx: AgentContext, args: dict[str, Any]) -> Any:
    property_id = None
    if ref := args.get("ref_code"):
        property_id = (await _property_by_ref(ctx, ref)).id
    hits = await search_chunks(ctx.db, ctx.tenant.id, args["question"], property_id=property_id)
    if not hits:
        return {"results": [], "note": "Nothing relevant in the documents."}
    return {
        "results": [{"ref_code": h.ref_code, "source": h.source, "text": h.content} for h in hits]
    }


async def get_available_slots_tool(ctx: AgentContext, args: dict[str, Any]) -> Any:
    start_day = None
    if raw := args.get("from_date"):
        try:
            start_day = date.fromisoformat(raw)
        except ValueError as exc:
            raise ToolError("from_date must be YYYY-MM-DD") from exc
    slots = dedupe_by_time(
        await available_slots(
            ctx.db, ctx.tenant, start_day=start_day, days=args.get("days") or 5, now=ctx.now
        )
    )
    if not slots:
        return {"slots": [], "note": "No free slots in this range. Offer a human callback."}
    return {
        "slots": [
            {
                "start": s.starts_at.astimezone(ctx.tz).isoformat(),
                "label": s.starts_at.astimezone(ctx.tz).strftime("%a %d %b, %I:%M %p"),
            }
            for s in slots[:20]
        ]
    }


async def book_appointment_tool(ctx: AgentContext, args: dict[str, Any]) -> Any:
    try:
        start = datetime.fromisoformat(args["start"])
    except ValueError as exc:
        raise ToolError("start must be an ISO datetime from get_available_slots") from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=ctx.tz)
    prop = await _property_by_ref(ctx, args["ref_code"]) if args.get("ref_code") else None
    if prop is None and ctx.conversation.focus_property_id:
        prop = await find_one(ctx.db, Property, {"_id": ctx.conversation.focus_property_id})
    try:
        appt = await book_appointment(
            ctx.db,
            ctx.tenant,
            contact=ctx.contact,
            starts_at=start,
            kind=AppointmentKind(args["kind"]),
            property_id=prop.id if prop else None,
            notes=args.get("notes"),
            by_bot=True,
        )
    except SlotUnavailableError as exc:
        raise ToolError(f"{exc} Fetch slots again and offer alternatives.") from exc
    if prop is not None:
        await record_interest(ctx, prop)
    return {
        "booked": True,
        "appointment_id": appt.id,
        "when": appt.starts_at.astimezone(ctx.tz).strftime("%A %d %B, %I:%M %p"),
        "kind": appt.kind.value,
        "location": appt.location,
        "property": prop.ref_code if prop else None,
    }


async def list_my_appointments(ctx: AgentContext, args: dict[str, Any]) -> Any:
    rows = await find(
        ctx.db,
        Appointment,
        {
            "tenant_id": ctx.tenant.id,
            "contact_id": ctx.contact.id,
            "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
            "starts_at": {"$gte": ctx.now},
        },
        sort=[("starts_at", 1)],
    )
    return {
        "appointments": [
            {
                "id": a.id,
                "kind": a.kind.value,
                "when": a.starts_at.astimezone(ctx.tz).strftime("%a %d %b, %I:%M %p"),
                "location": a.location,
            }
            for a in rows
        ]
    }


async def cancel_appointment_tool(ctx: AgentContext, args: dict[str, Any]) -> Any:
    appt = await find_one(
        ctx.db,
        Appointment,
        {
            "_id": str(args["appointment_id"]),
            "tenant_id": ctx.tenant.id,
            "contact_id": ctx.contact.id,
            "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
        },
    )
    if appt is None:
        raise ToolError("No such upcoming appointment for this person")
    appt.status = AppointmentStatus.cancelled
    await save(ctx.db, appt, "status")
    reason = args.get("reason") or "no reason given"
    when = appt.starts_at.astimezone(ctx.tz).strftime("%a %d %b, %I:%M %p")
    await insert(
        ctx.db,
        Activity(
            tenant_id=ctx.tenant.id,
            contact_id=ctx.contact.id,
            kind=ActivityKind.appointment,
            summary=f"Appointment on {when} cancelled via WhatsApp ({reason})",
            meta={"appointment_id": appt.id},
        ),
    )
    await notify(
        ctx.db,
        ctx.tenant.id,
        [appt.user_id],
        kind="appointment_cancelled",
        title=f"{ctx.contact.name or ctx.contact.phone} cancelled their {when} appointment",
        body=reason,
        link=f"/dashboard/contacts/{ctx.contact.id}",
    )
    return {"cancelled": True, "when": when}


async def update_lead_profile(ctx: AgentContext, args: dict[str, Any]) -> Any:
    c = ctx.contact
    changed: list[str] = []

    def put(field: str, value: Any) -> None:
        setattr(c, field, value)
        changed.append(field)

    if args.get("name"):
        put("name", args["name"][:200])
    if args.get("email"):
        put("email", args["email"][:320])
    if args.get("budget_min") is not None:
        put("budget_min", float(args["budget_min"]))
    if args.get("budget_max") is not None:
        put("budget_max", float(args["budget_max"]))
    if args.get("preferred_locations"):
        merged = list(dict.fromkeys([*c.preferred_locations, *args["preferred_locations"]]))
        put("preferred_locations", merged[:10])
    if args.get("property_type"):
        put("preferred_property_type", PropertyType(args["property_type"]))
    if args.get("bedrooms") is not None:
        put("bedrooms", int(args["bedrooms"]))
    if args.get("notes"):
        stamp = ctx.now.astimezone(ctx.tz).strftime("%d %b")
        put("notes", ((c.notes or "") + f"\n[{stamp} assistant] {args['notes']}").strip())
    if changed:
        await save(ctx.db, c, *changed)
    return {"saved": True}


async def request_human(ctx: AgentContext, args: dict[str, Any]) -> Any:
    ctx.conversation.mode = ConversationMode.human
    await save(ctx.db, ctx.conversation, "mode")
    reason = args.get("reason", "")
    await insert(
        ctx.db,
        Activity(
            tenant_id=ctx.tenant.id,
            contact_id=ctx.contact.id,
            kind=ActivityKind.handoff,
            summary=f"Assistant handed over to the team: {reason}",
        ),
    )
    users = await recipients_for(ctx.db, ctx.tenant.id, ctx.contact.assigned_to)
    await notify(
        ctx.db,
        ctx.tenant.id,
        users,
        kind="handoff",
        title=f"{ctx.contact.name or ctx.contact.phone} needs a human on WhatsApp",
        body=reason,
        link=f"/dashboard/inbox/{ctx.conversation.id}",
    )
    return {"handed_over": True, "tell_user": "A team member will reply here shortly."}


HANDLERS = {
    "search_properties": search_properties,
    "get_property_details": get_property_details,
    "send_property_photos": send_property_photos,
    "search_knowledge": search_knowledge_tool,
    "get_available_slots": get_available_slots_tool,
    "book_appointment": book_appointment_tool,
    "list_my_appointments": list_my_appointments,
    "cancel_appointment": cancel_appointment_tool,
    "update_lead_profile": update_lead_profile,
    "request_human": request_human,
}


def make_executor(ctx: AgentContext):
    # Tools mutate the shared contact/conversation objects, so parallel tool calls from
    # the model run one at a time.
    lock = asyncio.Lock()

    async def execute(name: str, args: dict[str, Any]) -> str:
        handler = HANDLERS.get(name)
        if handler is None:
            raise ToolError(f"Unknown tool {name}")
        try:
            async with lock:
                result = await handler(ctx, args)
        except (KeyError, ValueError, TypeError) as exc:
            raise ToolError(f"Invalid arguments: {exc}") from exc
        return json.dumps(result, default=str, ensure_ascii=False)

    return execute


def utcnow() -> datetime:
    return datetime.now(UTC)
