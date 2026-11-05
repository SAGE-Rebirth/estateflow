"""Handle one inbound WhatsApp message end to end: CRM upsert, media, assistant reply, send."""

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import phonenumbers
import redis.asyncio as redis
import structlog
from pymongo.errors import DuplicateKeyError

from app.core.db import Db, coll, find_one, insert, save
from app.core.ratelimit import get_redis
from app.models import (
    Activity,
    ActivityKind,
    Contact,
    Conversation,
    ConversationMode,
    ConversationStatus,
    DeliveryStatus,
    Direction,
    LeadSource,
    LeadStage,
    Message,
    Property,
    SenderType,
    Tenant,
    utcnow,
)
from app.services import hf
from app.services.agent.agent import run_agent
from app.services.agent.tools import AgentContext, record_interest
from app.services.llm.base import ChatProvider
from app.services.notifications import notify, recipients_for
from app.services.storage import MEDIA_EXT, save_bytes
from app.services.whatsapp.client import WhatsAppClient, WhatsAppError
from app.services.whatsapp.webhook import InboundMessage, StatusUpdate

log = structlog.get_logger()

_SOURCE_LABEL = {LeadSource.whatsapp: "WhatsApp ", LeadSource.website: "website "}

REF_CODE_RE = re.compile(r"\b([A-Z]{2,4}-\d{2,6})\b", re.IGNORECASE)

LOCK_SECONDS = 180


def to_e164(wa_id: str) -> str:
    try:
        return phonenumbers.format_number(
            phonenumbers.parse(f"+{wa_id.lstrip('+')}"), phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        return f"+{wa_id.lstrip('+')}"


@asynccontextmanager
async def sender_lock(key: str):
    """Serialize work per sender so rapid-fire messages don't get parallel replies.
    Degrades to no lock if Redis is unavailable rather than dropping messages."""
    lock = get_redis().lock(f"lock:{key}", timeout=LOCK_SECONDS, blocking_timeout=LOCK_SECONDS)
    try:
        acquired = await lock.acquire()
    except redis.RedisError:
        log.warning("sender_lock_unavailable", key=key)
        acquired = False
    try:
        yield
    finally:
        if acquired:
            try:
                await lock.release()
            except redis.RedisError:
                pass


async def upsert_contact(
    db: Db,
    tenant: Tenant,
    wa_id: str,
    profile_name: str | None,
    source: LeadSource = LeadSource.whatsapp,
) -> Contact:
    phone = to_e164(wa_id)
    fresh = Contact(
        tenant_id=tenant.id, phone=phone, wa_id=wa_id, name=profile_name, source=source
    ).dump()
    key = {"tenant_id": tenant.id, "phone": phone}
    try:
        res = await coll(db, Contact).update_one(key, {"$setOnInsert": fresh}, upsert=True)
    except DuplicateKeyError:  # concurrent first message from the same number
        res = None
    contact = await find_one(db, Contact, key)
    assert contact is not None
    if res is not None and res.upserted_id is not None:
        users = await recipients_for(db, tenant.id, None)
        await notify(
            db,
            tenant.id,
            users,
            kind="new_lead",
            title=f"New {_SOURCE_LABEL.get(source, '')}lead: {profile_name or phone}",
            link=f"/dashboard/contacts/{contact.id}",
        )
    changed = []
    if contact.wa_id != wa_id:
        contact.wa_id = wa_id
        changed.append("wa_id")
    if not contact.name and profile_name:
        contact.name = profile_name
        changed.append("name")
    if changed:
        await save(db, contact, *changed)
    return contact


async def open_conversation(db: Db, tenant: Tenant, contact: Contact) -> Conversation:
    conv = await find_one(
        db,
        Conversation,
        {"tenant_id": tenant.id, "contact_id": contact.id, "status": ConversationStatus.open},
        sort=[("created_at", -1)],
    )
    if conv is None:
        conv = await insert(db, Conversation(tenant_id=tenant.id, contact_id=contact.id))
    return conv


async def _process_media(
    db: Db, tenant: Tenant, msg: Message, event: InboundMessage, client: WhatsAppClient | None
) -> None:
    """Store the file privately; turn photos/voice notes into text the assistant can use."""
    if not event.media_id or client is None:
        return
    try:
        data, mime = await client.download_media(event.media_id)
    except WhatsAppError as exc:
        log.warning("media_download_failed", error=str(exc)[:200])
        return
    mime = (event.media_mime or mime).split(";")[0].strip().lower()
    if mime not in MEDIA_EXT:  # only types we know; anything else is opaque bytes
        mime = "application/octet-stream"
    msg.media_kind = event.type
    msg.media_mime = mime
    msg.media_path = save_bytes(data, tenant.id, MEDIA_EXT.get(mime, ""), private=True)
    caption = (event.raw.get(event.type) or {}).get("caption")

    if event.type == "audio":
        transcript = await hf.transcribe(data)
        if transcript:
            msg.body = f"[voice note] {transcript}"
            msg.meta["transcript"] = transcript
    elif event.type == "image":
        description = await hf.describe_image(data, mime)
        if description:
            msg.meta["description"] = description
            msg.body = f"[photo] {description}" + (f"\nCaption: {caption}" if caption else "")
    await save(db, msg, "media_kind", "media_mime", "media_path", "body", "meta")


async def handle_inbound(
    db: Db,
    tenant: Tenant,
    event: InboundMessage,
    *,
    whatsapp: WhatsAppClient | None = None,
    provider: ChatProvider | None = None,
    now: datetime | None = None,
) -> Message | None:
    """Returns the assistant's outbound message, or None when it stayed silent."""
    now = now or datetime.now(UTC)
    async with sender_lock(f"inbound:{tenant.id}:{event.wa_id}"):
        contact = await upsert_contact(db, tenant, event.wa_id, event.profile_name)
        conv = await open_conversation(db, tenant, contact)

        msg = Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction=Direction.inbound,
            sender_type=SenderType.contact,
            body=event.text,
            wa_message_id=event.wa_message_id,
            status=DeliveryStatus.received,
            meta={"type": event.type},
        )
        try:
            await insert(db, msg)
        except DuplicateKeyError:
            log.info("duplicate_inbound_ignored", wa_message_id=event.wa_message_id)
            return None

        try:
            client = whatsapp or WhatsAppClient(tenant)
        except WhatsAppError:
            client = None
        await _process_media(db, tenant, msg, event, client)

        contact.last_inbound_at = now
        await save(db, contact, "last_inbound_at")
        await coll(db, Conversation).update_one(
            {"_id": conv.id},
            {
                "$set": {
                    "last_message_at": now,
                    "last_direction": Direction.inbound,
                    "last_message": msg.body[:200],
                    "updated_at": utcnow(),
                },
                "$inc": {"unread_count": 1},
            },
        )

        ctx = AgentContext(
            db=db, tenant=tenant, contact=contact, conversation=conv, now=now, whatsapp=client
        )

        # "Hi, I'm interested in PR-1042" from the listing page's WhatsApp button.
        for ref in {m.upper() for m in REF_CODE_RE.findall(msg.body)}:
            prop = await find_one(db, Property, {"tenant_id": tenant.id, "ref_code": ref})
            if prop is not None:
                await record_interest(ctx, prop)

        if conv.mode == ConversationMode.human:
            users = await recipients_for(db, tenant.id, contact.assigned_to)
            await notify(
                db,
                tenant.id,
                users,
                kind="inbound_message",
                title=f"{contact.name or contact.phone}: {msg.body[:80]}",
                link=f"/dashboard/inbox/{conv.id}",
            )
            return None

        reply, _ = await run_agent(ctx, provider)

        out = Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction=Direction.outbound,
            sender_type=SenderType.bot,
            body=reply,
            status=DeliveryStatus.queued,
        )
        await insert(db, out)
        if contact.stage == LeadStage.new:
            await coll(db, Contact).update_one(
                {"_id": contact.id, "stage": LeadStage.new},
                {"$set": {"stage": LeadStage.contacted}},
            )
        if client is None:
            out.status, out.error = DeliveryStatus.failed, "WhatsApp is not configured"
        else:
            try:
                out.wa_message_id = await client.send_text(contact.wa_id or event.wa_id, reply)
                out.status = DeliveryStatus.sent
                await client.mark_read(event.wa_message_id)
            except WhatsAppError as exc:
                out.status, out.error = DeliveryStatus.failed, str(exc)
        await save(db, out, "wa_message_id", "status", "error")
        await coll(db, Conversation).update_one(
            {"_id": conv.id},
            {
                "$set": {
                    "last_message_at": utcnow(),
                    "last_direction": Direction.outbound,
                    "last_message": reply[:200],
                }
            },
        )
        return out


async def send_staff_message(
    db: Db,
    tenant: Tenant,
    conv: Conversation,
    contact: Contact,
    user_id: str,
    body: str,
    *,
    whatsapp: WhatsAppClient | None = None,
) -> Message:
    msg = await insert(
        db,
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction=Direction.outbound,
            sender_type=SenderType.user,
            sender_user_id=user_id,
            body=body,
            status=DeliveryStatus.queued,
        ),
    )
    await insert(
        db,
        Activity(
            tenant_id=tenant.id,
            contact_id=contact.id,
            user_id=user_id,
            kind=ActivityKind.message,
            summary=f"Replied on WhatsApp: {body[:200]}",
        ),
    )
    try:
        client = whatsapp or WhatsAppClient(tenant)
        msg.wa_message_id = await client.send_text(contact.wa_id or contact.phone.lstrip("+"), body)
        msg.status = DeliveryStatus.sent
    except WhatsAppError as exc:
        msg.status, msg.error = DeliveryStatus.failed, str(exc)
    await save(db, msg, "wa_message_id", "status", "error")
    await coll(db, Conversation).update_one(
        {"_id": conv.id},
        {
            "$set": {
                "last_message_at": utcnow(),
                "last_direction": Direction.outbound,
                "last_message": body[:200],
                "unread_count": 0,
                "mode": conv.mode,
            }
        },
    )
    return msg


_STATUS_ORDER = {s: i for i, s in enumerate(["queued", "sent", "delivered", "read"])}


async def apply_status(db: Db, update_evt: StatusUpdate) -> None:
    try:
        new = DeliveryStatus(update_evt.status)
    except ValueError:
        return
    msg = await find_one(db, Message, {"wa_message_id": update_evt.wa_message_id})
    if msg is None:
        return
    # Webhooks can arrive out of order; never move delivered/read backwards.
    if new == DeliveryStatus.failed:
        msg.status, msg.error = new, update_evt.error
    elif _STATUS_ORDER.get(new.value, -1) > _STATUS_ORDER.get(msg.status.value, -1):
        msg.status = new
    else:
        return
    await save(db, msg, "status", "error")
