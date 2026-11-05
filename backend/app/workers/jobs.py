"""Background work. All jobs are idempotent and safe to retry."""

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.core.db import coll, ensure_indexes, find, find_one, get_database, save
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    Contact,
    Notification,
    Property,
    Task,
    Tenant,
    User,
)
from app.services.client_messages import send_appointment_reminder
from app.services.inbound import apply_status, handle_inbound
from app.services.notifications import notify
from app.services.rag.ingest import index_property as _index_property
from app.services.rag.ingest import ingest_document as _ingest_document
from app.services.whatsapp.webhook import StatusUpdate, parse_webhook

log = structlog.get_logger()

DIGEST_LOCAL_HOUR = 7


async def startup_indexes(ctx: dict[str, Any]) -> None:
    await ensure_indexes()


async def ingest_document(ctx: dict[str, Any], document_id: str) -> None:
    await _ingest_document(get_database(), document_id)


async def index_property(ctx: dict[str, Any], property_id: str) -> None:
    db = get_database()
    prop = await find_one(db, Property, {"_id": property_id})
    if prop is None:
        return
    tenant = await find_one(db, Tenant, {"_id": prop.tenant_id})
    await _index_property(db, prop.id, tenant.currency if tenant else "INR")


async def process_inbound_message(
    ctx: dict[str, Any], phone_number_id: str, raw_message: dict, profile_name: str | None
) -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "contacts": [
                                {
                                    "wa_id": raw_message.get("from"),
                                    "profile": {"name": profile_name},
                                }
                            ],
                            "messages": [raw_message],
                        }
                    }
                ]
            }
        ]
    }
    (event,), _ = parse_webhook(payload)
    db = get_database()
    tenant = await find_one(
        db, Tenant, {"whatsapp_phone_number_id": phone_number_id, "is_active": True}
    )
    if tenant is None:
        log.warning("inbound_for_unknown_number", phone_number_id=phone_number_id)
        return
    await handle_inbound(db, tenant, event)


async def process_status_update(
    ctx: dict[str, Any], wa_message_id: str, status: str, error: str | None
) -> None:
    await apply_status(get_database(), StatusUpdate("", wa_message_id, status, error))


async def run_reminders(db, now: datetime) -> dict[str, int]:
    """Client reminders 24h and 2h before, agent reminder 1h before; due-task nudges."""
    sent = {"client_24h": 0, "client_2h": 0, "agent_1h": 0, "tasks": 0}
    upcoming = await find(
        db,
        Appointment,
        {
            "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
            "starts_at": {"$gt": now, "$lte": now + timedelta(hours=24)},
        },
    )
    tenants: dict[str, Tenant] = {}
    for appt in upcoming:
        tenant = tenants.get(appt.tenant_id) or await find_one(db, Tenant, {"_id": appt.tenant_id})
        contact = await find_one(db, Contact, {"_id": appt.contact_id})
        if tenant is None or contact is None:
            continue
        tenants[tenant.id] = tenant
        until = appt.starts_at - now
        when = appt.starts_at.astimezone(ZoneInfo(tenant.timezone)).strftime("%I:%M %p")

        if until <= timedelta(hours=1) and not appt.agent_reminder_sent:
            await notify(
                db,
                tenant.id,
                [appt.user_id],
                kind="appointment_soon",
                title=f"At {when}: {appt.kind.value.replace('_', ' ')} with "
                f"{contact.name or contact.phone}",
                body=appt.location,
                link=f"/dashboard/calendar?appointment={appt.id}",
            )
            appt.agent_reminder_sent = True
            await save(db, appt, "agent_reminder_sent")
            sent["agent_1h"] += 1

        # Flags are only set on success, so a failed send is retried on the next run.
        if until <= timedelta(hours=2):
            if not appt.client_reminder_2h_sent and await send_appointment_reminder(
                db, tenant, contact, appt, now=now
            ):
                # 24h reminder is redundant once we're inside 2h.
                appt.client_reminder_2h_sent = appt.client_reminder_24h_sent = True
                await save(db, appt, "client_reminder_2h_sent", "client_reminder_24h_sent")
                sent["client_2h"] += 1
        elif not appt.client_reminder_24h_sent and await send_appointment_reminder(
            db, tenant, contact, appt, now=now
        ):
            appt.client_reminder_24h_sent = True
            await save(db, appt, "client_reminder_24h_sent")
            sent["client_24h"] += 1

    for task in await find(
        db,
        Task,
        {
            "done_at": None,
            "reminder_sent": False,
            "assigned_to": {"$ne": None},
            "due_at": {"$lte": now + timedelta(minutes=30)},
        },
    ):
        await notify(
            db,
            task.tenant_id,
            [task.assigned_to],
            kind="task_due",
            title=f"Follow-up due: {task.title}",
            link=f"/dashboard/contacts/{task.contact_id}" if task.contact_id else "/dashboard",
        )
        task.reminder_sent = True
        await save(db, task, "reminder_sent")
        sent["tasks"] += 1
    return sent


async def run_daily_digest(db, now: datetime) -> int:
    """At 07:00 tenant-local time, tell each active team member what today holds."""
    created = 0
    for tenant in await find(db, Tenant, {"is_active": True}):
        tz = ZoneInfo(tenant.timezone)
        local = now.astimezone(tz)
        if local.hour != DIGEST_LOCAL_HOUR:
            continue
        day_start = datetime.combine(local.date(), time.min, tz)
        day_end = day_start + timedelta(days=1)
        for user in await find(db, User, {"tenant_id": tenant.id, "is_active": True}):
            # One digest per day even if the cron fires several times at 07:xx.
            already = await coll(db, Notification).count_documents(
                {
                    "user_id": user.id,
                    "kind": "daily_digest",
                    "created_at": {"$gt": datetime.now(UTC) - timedelta(hours=20)},
                }
            )
            if already:
                continue
            appts = await coll(db, Appointment).count_documents(
                {
                    "user_id": user.id,
                    "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
                    "starts_at": {"$gte": day_start, "$lt": day_end},
                }
            )
            tasks = await coll(db, Task).count_documents(
                {"assigned_to": user.id, "done_at": None, "due_at": {"$lt": day_end}}
            )
            if not appts and not tasks:
                continue
            await notify(
                db,
                tenant.id,
                [user.id],
                kind="daily_digest",
                title=f"Today: {appts} meeting{'s' * (appts != 1)}, "
                f"{tasks} follow-up{'s' * (tasks != 1)}",
                body="Open the Today view to see who you're meeting and where.",
                link="/dashboard",
            )
            created += 1
    return created


async def reminders_cron(ctx: dict[str, Any]) -> None:
    sent = await run_reminders(get_database(), datetime.now(UTC))
    if any(sent.values()):
        log.info("reminders_sent", **sent)


async def digest_cron(ctx: dict[str, Any]) -> None:
    n = await run_daily_digest(get_database(), datetime.now(UTC))
    if n:
        log.info("daily_digests_sent", count=n)
