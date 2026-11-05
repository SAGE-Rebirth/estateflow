"""Proactive WhatsApp messages to clients (confirmations, reminders).

WhatsApp only allows free-form text within 24h of the client's last message. Outside that
window we must use a pre-approved template, configured per tenant in
bot_settings["templates"] = {"appointment_confirmation": {"name": ..., "language": "en"},
                             "appointment_reminder": {...}}
Templates are expected to take body params: {{1}} client name, {{2}} when, {{3}} where.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from app.core.db import Db, coll, find_one, insert
from app.models import (
    Appointment,
    Contact,
    Conversation,
    ConversationStatus,
    DeliveryStatus,
    Direction,
    Message,
    SenderType,
    Tenant,
    utcnow,
)
from app.services.whatsapp.client import WhatsAppClient, WhatsAppError

log = structlog.get_logger()

SERVICE_WINDOW = timedelta(hours=24)


def describe(appt: Appointment, tenant: Tenant) -> tuple[str, str]:
    when = appt.starts_at.astimezone(ZoneInfo(tenant.timezone)).strftime("%A %d %B, %I:%M %p")
    return when, appt.location or "our office"


async def send_to_client(
    db: Db,
    tenant: Tenant,
    contact: Contact,
    *,
    text: str,
    template_key: str,
    template_params: list[str],
    whatsapp: WhatsAppClient | None = None,
    now: datetime | None = None,
) -> bool:
    """Send text inside the service window, else the configured template. Logs to the inbox."""
    now = now or datetime.now(UTC)
    in_window = (
        contact.last_inbound_at is not None and now - contact.last_inbound_at < SERVICE_WINDOW
    )
    template = ((tenant.bot_settings or {}).get("templates") or {}).get(template_key)
    if not in_window and not template:
        log.info("client_message_skipped_no_template", contact=contact.id, key=template_key)
        return False
    try:
        client = whatsapp or WhatsAppClient(tenant)
        to = contact.wa_id or contact.phone.lstrip("+")
        if in_window:
            wa_id = await client.send_text(to, text)
        else:
            wa_id = await client.send_template(
                to, template["name"], template.get("language", "en"), template_params
            )
    except WhatsAppError as exc:
        log.warning("client_message_failed", contact=contact.id, error=str(exc))
        return False

    conv = await find_one(
        db,
        Conversation,
        {"tenant_id": tenant.id, "contact_id": contact.id, "status": ConversationStatus.open},
    )
    if conv is None:
        conv = await insert(db, Conversation(tenant_id=tenant.id, contact_id=contact.id))
    await insert(
        db,
        Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction=Direction.outbound,
            sender_type=SenderType.system,
            body=text,
            wa_message_id=wa_id or None,
            status=DeliveryStatus.sent,
            meta={"template": None if in_window else template_key},
        ),
    )
    await coll(db, Conversation).update_one(
        {"_id": conv.id},
        {
            "$set": {
                "last_message_at": now,
                "last_direction": Direction.outbound,
                "last_message": text[:200],
                "updated_at": utcnow(),
            }
        },
    )
    return True


async def send_appointment_confirmation(
    db: Db,
    tenant: Tenant,
    contact: Contact,
    appt: Appointment,
    whatsapp: WhatsAppClient | None = None,
) -> bool:
    when, where = describe(appt, tenant)
    name = contact.name or "there"
    text = (
        f"Hi {name}, your {appt.kind.value.replace('_', ' ')} with {tenant.name} is confirmed "
        f"for *{when}* at {where}. Reply here if you need to reschedule."
    )
    return await send_to_client(
        db,
        tenant,
        contact,
        text=text,
        template_key="appointment_confirmation",
        template_params=[name, when, where],
        whatsapp=whatsapp,
    )


async def send_appointment_reminder(
    db: Db,
    tenant: Tenant,
    contact: Contact,
    appt: Appointment,
    whatsapp: WhatsAppClient | None = None,
    now: datetime | None = None,
) -> bool:
    when, where = describe(appt, tenant)
    name = contact.name or "there"
    text = (
        f"Reminder: your {appt.kind.value.replace('_', ' ')} with {tenant.name} is on "
        f"*{when}* at {where}. Reply 'reschedule' if the time no longer works."
    )
    return await send_to_client(
        db,
        tenant,
        contact,
        text=text,
        template_key="appointment_reminder",
        template_params=[name, when, where],
        whatsapp=whatsapp,
        now=now,
    )
