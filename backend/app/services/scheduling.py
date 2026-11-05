from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.db import Db, coll, find, find_one, in_transaction, insert
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Activity,
    ActivityKind,
    Appointment,
    AppointmentKind,
    Contact,
    LeadStage,
    Property,
    Tenant,
    User,
)
from app.services.notifications import notify

# Stages a booking should not move a lead backwards from.
_LATE_STAGES = {LeadStage.negotiation, LeadStage.won}


class SlotUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class Slot:
    user_id: str
    starts_at: datetime
    ends_at: datetime


def _t(hhmm: str) -> time:
    return time.fromisoformat(hhmm)


def _overlap_query(user_id: str, start: datetime, end: datetime) -> dict:
    return {
        "user_id": user_id,
        "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
        "starts_at": {"$lt": end},
        "ends_at": {"$gt": start},
    }


async def available_slots(
    db: Db,
    tenant: Tenant,
    *,
    start_day: date | None = None,
    days: int | None = None,
    user_id: str | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    """Free slots across the team (or one member), in UTC, sorted by start time."""
    s = get_settings()
    tz = ZoneInfo(tenant.timezone)
    now = now or datetime.now(UTC)
    earliest = now + timedelta(minutes=s.booking_min_lead_minutes)
    start_day = start_day or now.astimezone(tz).date()
    days = min(days or s.booking_horizon_days, s.booking_horizon_days)
    end_day = start_day + timedelta(days=days)

    q: dict = {"tenant_id": tenant.id, "is_active": True}
    if user_id:
        q["_id"] = user_id
    users = await find(db, User, q)

    window_start = datetime.combine(start_day, time.min, tz)
    window_end = datetime.combine(end_day, time.min, tz)
    busy: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    async for a in coll(db, Appointment).find(
        {
            "tenant_id": tenant.id,
            "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
            "starts_at": {"$lt": window_end},
            "ends_at": {"$gt": window_start},
        },
        {"user_id": 1, "starts_at": 1, "ends_at": 1},
    ):
        busy[a["user_id"]].append((a["starts_at"], a["ends_at"]))

    slots: list[Slot] = []
    for user in users:
        days_off = {d.day for d in user.days_off}
        for offset in range(days):
            day = start_day + timedelta(days=offset)
            if day.isoformat() in days_off:
                continue
            for rule in user.availability:
                if rule.weekday != day.weekday():
                    continue
                cursor = datetime.combine(day, _t(rule.start_time), tz)
                close = datetime.combine(day, _t(rule.end_time), tz)
                step = timedelta(minutes=rule.slot_minutes)
                while cursor + step <= close:
                    start, end = cursor.astimezone(UTC), (cursor + step).astimezone(UTC)
                    cursor += step
                    if start < earliest:
                        continue
                    if any(b0 < end and b1 > start for b0, b1 in busy[user.id]):
                        continue
                    slots.append(Slot(user.id, start, end))
    slots.sort(key=lambda sl: (sl.starts_at, sl.user_id))
    return slots


def dedupe_by_time(slots: list[Slot]) -> list[Slot]:
    """One entry per start time (the first free team member), for showing to buyers."""
    seen: set[datetime] = set()
    out = []
    for slot in slots:
        if slot.starts_at not in seen:
            seen.add(slot.starts_at)
            out.append(slot)
    return out


async def _pick_agent(db: Db, tenant: Tenant, starts_at: datetime, candidates: list[str]) -> str:
    """Least-loaded free team member that day; keeps visits spread across the team."""
    tz = ZoneInfo(tenant.timezone)
    day_start = datetime.combine(starts_at.astimezone(tz).date(), time.min, tz)
    counts: dict[str, int] = {}
    async for row in await coll(db, Appointment).aggregate(
        [
            {
                "$match": {
                    "tenant_id": tenant.id,
                    "user_id": {"$in": candidates},
                    "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)},
                    "starts_at": {"$gte": day_start, "$lt": day_start + timedelta(days=1)},
                }
            },
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]
    ):
        counts[row["_id"]] = row["n"]
    return min(candidates, key=lambda u: (counts.get(u, 0), u))


async def insert_without_overlap(db: Db, appt: Appointment, *, exclude_id: str | None = None):
    """Insert (or, with exclude_id, re-time) an appointment unless it overlaps another.

    Every booking bumps the agent's `calendar_rev` inside the transaction, so two
    concurrent bookings for the same agent write-conflict and one is retried; the retry
    then sees the other's appointment and is refused.
    """

    async def txn(session) -> None:
        await coll(db, User).update_one(
            {"_id": appt.user_id}, {"$inc": {"calendar_rev": 1}}, session=session
        )
        q = _overlap_query(appt.user_id, appt.starts_at, appt.ends_at)
        if exclude_id:
            q["_id"] = {"$ne": exclude_id}
        if await coll(db, Appointment).find_one(q, {"_id": 1}, session=session):
            raise SlotUnavailableError("That time overlaps another appointment.")
        if exclude_id:
            data = appt.dump()
            data.pop("_id")
            await coll(db, Appointment).update_one(
                {"_id": exclude_id}, {"$set": data}, session=session
            )
        else:
            await insert(db, appt, session=session)

    await in_transaction(txn)


async def book_appointment(
    db: Db,
    tenant: Tenant,
    *,
    contact: Contact,
    starts_at: datetime,
    kind: AppointmentKind,
    property_id: str | None = None,
    user_id: str | None = None,
    notes: str | None = None,
    location: str | None = None,
    by_bot: bool = False,
    actor_user_id: str | None = None,
    enforce_availability: bool = True,
    duration_minutes: int | None = None,
) -> Appointment:
    """Create an appointment. Bot/public bookings must match a free slot; staff may override."""
    starts_at = starts_at.astimezone(UTC)
    if enforce_availability:
        day = starts_at.astimezone(ZoneInfo(tenant.timezone)).date()
        slots = [
            sl
            for sl in await available_slots(db, tenant, start_day=day, days=1, user_id=user_id)
            if sl.starts_at == starts_at
        ]
        if not slots:
            raise SlotUnavailableError("That time is no longer available.")
        chosen = user_id or await _pick_agent(db, tenant, starts_at, [sl.user_id for sl in slots])
        ends_at = next(sl.ends_at for sl in slots if sl.user_id == chosen)
    else:
        if user_id is None:
            raise ValueError("user_id is required when availability is not enforced")
        chosen = user_id
        ends_at = starts_at + timedelta(minutes=duration_minutes or 60)

    if location is None and property_id is not None:
        prop = await find_one(db, Property, {"_id": property_id})
        if prop is not None:
            location = ", ".join(x for x in (prop.address, prop.locality, prop.city) if x) or None

    appt = Appointment(
        tenant_id=tenant.id,
        contact_id=contact.id,
        property_id=property_id,
        user_id=chosen,
        kind=kind,
        starts_at=starts_at,
        ends_at=ends_at,
        notes=notes,
        location=location,
        created_by_bot=by_bot,
    )
    await insert_without_overlap(db, appt)

    update: dict = {}
    if contact.stage not in _LATE_STAGES:
        contact.stage = update["stage"] = LeadStage.visit_scheduled
    if contact.assigned_to is None:
        contact.assigned_to = update["assigned_to"] = chosen
    if update:
        await coll(db, Contact).update_one({"_id": contact.id}, {"$set": update})

    when = starts_at.astimezone(ZoneInfo(tenant.timezone)).strftime("%a %d %b, %I:%M %p")
    label = kind.value.replace("_", " ")
    await insert(
        db,
        Activity(
            tenant_id=tenant.id,
            contact_id=contact.id,
            user_id=actor_user_id,
            kind=ActivityKind.appointment,
            summary=f"{label.title()} booked for {when}"
            + (" by the WhatsApp assistant" if by_bot else ""),
            meta={"appointment_id": appt.id},
        ),
    )
    await notify(
        db,
        tenant.id,
        [chosen],
        kind="appointment_booked",
        title=f"New {label} with {contact.name or contact.phone}",
        body=f"{when}, {location}" if location else when,
        link=f"/dashboard/calendar?appointment={appt.id}",
    )
    return appt
