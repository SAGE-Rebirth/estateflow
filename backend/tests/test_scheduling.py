import asyncio
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.db import coll, find, find_one, insert, save
from app.models import (
    Appointment,
    AppointmentKind,
    AppointmentStatus,
    Contact,
    DayOff,
    LeadStage,
    Notification,
    User,
)
from app.services.scheduling import (
    SlotUnavailableError,
    available_slots,
    book_appointment,
)

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2030, 1, 7)  # a Monday, safely in the future


def at(hour: int, day: date = DAY, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).astimezone(UTC)


async def _contact(db, tenant, n: int = 1) -> Contact:
    return await insert(
        db, Contact(tenant_id=tenant.id, phone=f"+91999990000{n}", wa_id=f"91999990000{n}")
    )


async def test_slots_follow_rules_and_lead_time(db, tenant_with_agent):
    tenant, _ = tenant_with_agent
    now = at(10) - timedelta(minutes=30)
    slots = await available_slots(db, tenant, start_day=DAY, days=1, now=now)
    assert [s.starts_at for s in slots] == [at(10), at(11), at(12)]

    later = at(11) + timedelta(minutes=1)
    slots = await available_slots(db, tenant, start_day=DAY, days=1, now=later)
    assert [s.starts_at for s in slots] == [at(12)]


async def test_days_off_block_the_whole_day(db, tenant_with_agent):
    tenant, agent = tenant_with_agent
    agent.days_off = [DayOff(day=DAY.isoformat())]
    await save(db, agent, "days_off")
    slots = await available_slots(db, tenant, start_day=DAY, days=2, now=at(0))
    assert all(s.starts_at.astimezone(IST).date() != DAY for s in slots)
    assert slots, "next day is still open"


async def test_booking_consumes_slot_and_updates_crm(db, tenant_with_agent):
    tenant, agent = tenant_with_agent
    contact = await _contact(db, tenant)
    appt = await book_appointment(
        db,
        tenant,
        contact=contact,
        starts_at=at(11),
        kind=AppointmentKind.site_visit,
        by_bot=True,
    )
    assert appt.user_id == agent.id
    assert appt.ends_at - appt.starts_at == timedelta(hours=1)
    stored = await find_one(db, Contact, {"_id": contact.id})
    assert stored.stage == LeadStage.visit_scheduled
    assert stored.assigned_to == agent.id

    slots = await available_slots(db, tenant, start_day=DAY, days=1, now=at(0))
    assert at(11) not in [s.starts_at for s in slots]
    assert await coll(db, Notification).count_documents({}) == 1

    with pytest.raises(SlotUnavailableError):
        await book_appointment(
            db, tenant, contact=contact, starts_at=at(11), kind=AppointmentKind.call
        )


async def test_overlap_blocked_even_without_slot_check(db, tenant_with_agent):
    tenant, agent = tenant_with_agent
    contact = await _contact(db, tenant)
    await book_appointment(
        db,
        tenant,
        contact=contact,
        starts_at=at(15),
        kind=AppointmentKind.call,
        user_id=agent.id,
        enforce_availability=False,
        duration_minutes=60,
    )
    with pytest.raises(SlotUnavailableError):
        await book_appointment(
            db,
            tenant,
            contact=contact,
            starts_at=at(15, minute=30),
            kind=AppointmentKind.call,
            user_id=agent.id,
            enforce_availability=False,
        )
    ok = await book_appointment(
        db,
        tenant,
        contact=contact,
        starts_at=at(16),
        kind=AppointmentKind.call,
        user_id=agent.id,
        enforce_availability=False,
    )
    assert ok.status == AppointmentStatus.scheduled
    assert await coll(db, Appointment).count_documents({}) == 2


async def test_concurrent_bookings_for_same_time_only_one_wins(db, tenant_with_agent):
    tenant, agent = tenant_with_agent
    contacts = [await _contact(db, tenant, n) for n in range(1, 7)]

    async def attempt(c):
        try:
            return await book_appointment(
                db,
                tenant,
                contact=c,
                starts_at=at(17),
                kind=AppointmentKind.call,
                user_id=agent.id,
                enforce_availability=False,
            )
        except SlotUnavailableError:
            return None

    results = await asyncio.gather(*(attempt(c) for c in contacts))
    assert sum(r is not None for r in results) == 1
    assert len(await find(db, Appointment, {"user_id": agent.id})) == 1
    # The losing transactions bumped nothing visible besides the calendar revision.
    assert (await coll(db, User).find_one({"_id": agent.id}))["calendar_rev"] >= 1


async def test_cancelled_appointments_free_the_slot(db, tenant_with_agent):
    tenant, _ = tenant_with_agent
    contact = await _contact(db, tenant)
    appt = await book_appointment(
        db, tenant, contact=contact, starts_at=at(10), kind=AppointmentKind.site_visit
    )
    appt.status = AppointmentStatus.cancelled
    await save(db, appt, "status")
    slots = await available_slots(db, tenant, start_day=DAY, days=1, now=at(0))
    assert at(10) in [s.starts_at for s in slots]
