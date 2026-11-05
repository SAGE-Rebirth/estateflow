from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbDep, Principal, get_owned
from app.core.db import Db, coll, find, find_one, insert
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Activity,
    ActivityKind,
    Appointment,
    AppointmentStatus,
    AvailabilityRule,
    Contact,
    DayOff,
    Property,
    User,
    utcnow,
)
from app.schemas.scheduling import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentOut,
    AppointmentUpdate,
    AvailabilityExceptionIn,
    AvailabilityExceptionOut,
    AvailabilityRuleIn,
    AvailabilityRuleOut,
    SlotOut,
)
from app.services.client_messages import send_appointment_confirmation
from app.services.scheduling import (
    SlotUnavailableError,
    available_slots,
    book_appointment,
    insert_without_overlap,
)

router = APIRouter(tags=["scheduling"])


async def _target_user(p: Principal, db: Db, user_id: str | None) -> User:
    """Agents manage their own calendar; admins may manage anyone's."""
    if user_id is None or user_id == p.user.id:
        return p.user
    if not p.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return await get_owned(db, User, user_id, p.tenant_id)


# --- Availability -----------------------------------------------------------------------


@router.get("/availability/rules", response_model=list[AvailabilityRuleOut])
async def get_rules(p: CurrentPrincipal, db: DbDep, user_id: str | None = None):
    user = await _target_user(p, db, user_id)
    return sorted(user.availability, key=lambda r: (r.weekday, r.start_time))


@router.put("/availability/rules", response_model=list[AvailabilityRuleOut])
async def replace_rules(
    body: list[AvailabilityRuleIn], p: CurrentPrincipal, db: DbDep, user_id: str | None = None
):
    """Replace a member's whole weekly schedule in one go (what the settings UI saves)."""
    user = await _target_user(p, db, user_id)
    rules = [AvailabilityRule(**r.model_dump()) for r in body]
    await coll(db, User).update_one(
        {"_id": user.id}, {"$set": {"availability": [r.model_dump() for r in rules]}}
    )
    return rules


@router.get("/availability/exceptions", response_model=list[AvailabilityExceptionOut])
async def list_exceptions(p: CurrentPrincipal, db: DbDep, user_id: str | None = None):
    user = await _target_user(p, db, user_id)
    today = date.today().isoformat()
    return sorted((d for d in user.days_off if d.day >= today), key=lambda d: d.day)


@router.post("/availability/exceptions", response_model=AvailabilityExceptionOut, status_code=201)
async def add_exception(
    body: AvailabilityExceptionIn, p: CurrentPrincipal, db: DbDep, user_id: str | None = None
) -> DayOff:
    user = await _target_user(p, db, user_id)
    off = DayOff(day=body.day.isoformat(), reason=body.reason)
    await coll(db, User).update_one({"_id": user.id}, {"$push": {"days_off": off.model_dump()}})
    return off


@router.delete("/availability/exceptions/{exc_id}", status_code=204)
async def delete_exception(exc_id: str, p: CurrentPrincipal, db: DbDep) -> None:
    owner = await find_one(db, User, {"tenant_id": p.tenant_id, "days_off.id": exc_id})
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Day off not found")
    await _target_user(p, db, owner.id)
    await coll(db, User).update_one({"_id": owner.id}, {"$pull": {"days_off": {"id": exc_id}}})


@router.get("/availability/slots", response_model=list[SlotOut])
async def slots(
    p: CurrentPrincipal,
    db: DbDep,
    start_day: date | None = None,
    days: int = 7,
    user_id: str | None = None,
) -> list[SlotOut]:
    found = await available_slots(
        db, p.tenant, start_day=start_day, days=max(1, min(days, 31)), user_id=user_id
    )
    return [SlotOut(starts_at=s.starts_at, ends_at=s.ends_at, user_id=s.user_id) for s in found]


# --- Appointments -----------------------------------------------------------------------


async def details(db: Db, appts: list[Appointment]) -> list[AppointmentDetail]:
    """Join contact, property and agent names in three queries."""
    contacts = {
        c.id: c
        for c in await find(db, Contact, {"_id": {"$in": list({a.contact_id for a in appts})}})
    }
    props = {
        p.id: p
        for p in await find(
            db, Property, {"_id": {"$in": list({a.property_id for a in appts if a.property_id})}}
        )
    }
    users = {
        u.id: u for u in await find(db, User, {"_id": {"$in": list({a.user_id for a in appts})}})
    }
    out = []
    for a in appts:
        c, pr, u = contacts.get(a.contact_id), props.get(a.property_id or ""), users.get(a.user_id)
        out.append(
            AppointmentDetail(
                **AppointmentOut.model_validate(a).model_dump(),
                contact_name=c.name if c else None,
                contact_phone=c.phone if c else "",
                property_ref=pr.ref_code if pr else None,
                property_title=pr.title if pr else None,
                agent_name=u.full_name if u else "",
            )
        )
    return out


@router.get("/appointments", response_model=list[AppointmentDetail])
async def list_appointments(
    p: CurrentPrincipal,
    db: DbDep,
    start: datetime | None = None,
    end: datetime | None = None,
    user_id: str | None = None,
    contact_id: str | None = None,
    mine: bool = False,
    include_cancelled: bool = False,
) -> list[AppointmentDetail]:
    """Calendar feed. Defaults to the next 30 days."""
    start = start or datetime.now(UTC) - timedelta(days=1)
    end = end or start + timedelta(days=31)
    query: dict = {"tenant_id": p.tenant_id, "starts_at": {"$lt": end}, "ends_at": {"$gt": start}}
    if mine:
        user_id = p.user.id
    if user_id:
        query["user_id"] = user_id
    if contact_id:
        query["contact_id"] = contact_id
    if not include_cancelled:
        query["status"] = {"$ne": AppointmentStatus.cancelled}
    return await details(
        db, await find(db, Appointment, query, sort=[("starts_at", 1)], limit=1000)
    )


@router.get("/appointments/{appt_id}", response_model=AppointmentDetail)
async def get_appointment(appt_id: str, p: CurrentPrincipal, db: DbDep):
    return (await details(db, [await get_owned(db, Appointment, appt_id, p.tenant_id)]))[0]


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
async def create_appointment(body: AppointmentCreate, p: CurrentPrincipal, db: DbDep):
    contact = await get_owned(db, Contact, body.contact_id, p.tenant_id)
    if body.property_id:
        await get_owned(db, Property, body.property_id, p.tenant_id)
    user_id = body.user_id
    if user_id:
        await get_owned(db, User, user_id, p.tenant_id)
    elif body.override_availability:
        user_id = p.user.id
    try:
        appt = await book_appointment(
            db,
            p.tenant,
            contact=contact,
            starts_at=body.starts_at,
            kind=body.kind,
            property_id=body.property_id,
            user_id=user_id,
            notes=body.notes,
            location=body.location,
            actor_user_id=p.user.id,
            enforce_availability=not body.override_availability,
            duration_minutes=body.duration_minutes,
        )
    except SlotUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    if body.notify_client:
        await send_appointment_confirmation(db, p.tenant, contact, appt)
    return appt


@router.patch("/appointments/{appt_id}", response_model=AppointmentOut)
async def update_appointment(
    appt_id: str, body: AppointmentUpdate, p: CurrentPrincipal, db: DbDep
) -> Appointment:
    appt = await get_owned(db, Appointment, appt_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("user_id"):
        await get_owned(db, User, data["user_id"], p.tenant_id)
    if "starts_at" in data and "ends_at" not in data:
        data["ends_at"] = data["starts_at"] + (appt.ends_at - appt.starts_at)
    rescheduled = "starts_at" in data and data["starts_at"] != appt.starts_at
    old_status = appt.status
    for k, v in data.items():
        setattr(appt, k, v)
    if rescheduled:
        # Reminders must go out again for the new time.
        appt.client_reminder_24h_sent = appt.client_reminder_2h_sent = False
        appt.agent_reminder_sent = False
    appt.updated_at = utcnow()
    try:
        if appt.status in ACTIVE_APPOINTMENT_STATUSES and (rescheduled or "user_id" in data):
            await insert_without_overlap(db, appt, exclude_id=appt.id)
        else:
            payload = appt.dump()
            payload.pop("_id")
            await coll(db, Appointment).update_one({"_id": appt.id}, {"$set": payload})
    except SlotUnavailableError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That time overlaps another appointment"
        ) from None
    if data.get("status") and data["status"] != old_status:
        await insert(
            db,
            Activity(
                tenant_id=p.tenant_id,
                contact_id=appt.contact_id,
                user_id=p.user.id,
                kind=ActivityKind.appointment,
                summary=f"Appointment marked {data['status'].value.replace('_', ' ')}"
                + (f": {appt.outcome}" if appt.outcome else ""),
                meta={"appointment_id": appt.id},
            ),
        )
    if rescheduled and appt.status in ACTIVE_APPOINTMENT_STATUSES:
        contact = await find_one(db, Contact, {"_id": appt.contact_id})
        if contact is not None:
            await send_appointment_confirmation(db, p.tenant, contact, appt)
    return appt


@router.get("/team/availability-overview", response_model=dict[str, int])
async def team_slot_counts(p: AdminPrincipal, db: DbDep) -> dict[str, int]:
    """Free slots in the next 7 days per team member — spot who is overbooked."""
    counts: dict[str, int] = {}
    for s in await available_slots(db, p.tenant, days=7):
        counts[s.user_id] = counts.get(s.user_id, 0) + 1
    return counts
