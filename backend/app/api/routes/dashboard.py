from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentPrincipal, DbDep
from app.api.routes.scheduling import details
from app.core.db import coll, find
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    Contact,
    Conversation,
    ConversationMode,
    ConversationStatus,
    Direction,
    LeadStage,
    Property,
    PropertyStatus,
    Task,
)
from app.schemas.crm import ContactOut, TaskOut
from app.schemas.scheduling import AppointmentDetail

router = APIRouter(tags=["dashboard"])


class TodayOut(BaseModel):
    date: str
    timezone: str
    appointments_today: list[AppointmentDetail]
    appointments_upcoming: list[AppointmentDetail]
    tasks_overdue: list[TaskOut]
    tasks_due_today: list[TaskOut]
    new_leads: list[ContactOut]
    conversations_needing_human: int
    unread_conversations: int
    awaiting_outcome: list[AppointmentDetail]


class StatsOut(BaseModel):
    pipeline: dict[str, int]
    leads_last_30_days: int
    visits_last_30_days: int
    won_last_30_days: int
    active_listings: int


@router.get("/dashboard/today", response_model=TodayOut)
async def today(p: CurrentPrincipal, db: DbDep, mine: bool = False) -> TodayOut:
    """Everything the team needs to act on today, in the tenant's local day."""
    tz = ZoneInfo(p.tenant.timezone)
    now = datetime.now(UTC)
    local_today = now.astimezone(tz).date()
    day_start = datetime.combine(local_today, time.min, tz)
    day_end = day_start + timedelta(days=1)

    appt_q: dict = {"tenant_id": p.tenant_id, "status": {"$in": list(ACTIVE_APPOINTMENT_STATUSES)}}
    task_q: dict = {"tenant_id": p.tenant_id, "done_at": None}
    if mine:
        appt_q["user_id"] = p.user.id
        task_q["assigned_to"] = p.user.id

    async def appts(extra: dict, sort: int = 1, limit: int = 0) -> list[AppointmentDetail]:
        rows = await find(
            db, Appointment, {**appt_q, **extra}, sort=[("starts_at", sort)], limit=limit
        )
        return await details(db, rows)

    open_conv = {"tenant_id": p.tenant_id, "status": ConversationStatus.open}
    return TodayOut(
        date=local_today.isoformat(),
        timezone=p.tenant.timezone,
        appointments_today=await appts({"starts_at": {"$gte": day_start, "$lt": day_end}}),
        appointments_upcoming=await appts(
            {"starts_at": {"$gte": day_end, "$lt": day_end + timedelta(days=3)}}, limit=20
        ),
        # Visits that already happened but nobody recorded how they went.
        awaiting_outcome=await appts(
            {"ends_at": {"$lt": now, "$gt": now - timedelta(days=14)}}, sort=-1, limit=20
        ),
        tasks_overdue=[
            TaskOut.model_validate(t)
            for t in await find(
                db, Task, {**task_q, "due_at": {"$lt": day_start}}, sort=[("due_at", 1)]
            )
        ],
        tasks_due_today=[
            TaskOut.model_validate(t)
            for t in await find(
                db,
                Task,
                {**task_q, "due_at": {"$gte": day_start, "$lt": day_end}},
                sort=[("due_at", 1)],
            )
        ],
        new_leads=[
            ContactOut.model_validate(c)
            for c in await find(
                db,
                Contact,
                {
                    "tenant_id": p.tenant_id,
                    "stage": LeadStage.new,
                    "created_at": {"$gte": now - timedelta(days=2)},
                },
                sort=[("created_at", -1)],
                limit=20,
            )
        ],
        # Handed over and the client spoke last: someone owes them a reply, whether or not
        # the thread has been opened.
        conversations_needing_human=await coll(db, Conversation).count_documents(
            {**open_conv, "mode": ConversationMode.human, "last_direction": Direction.inbound}
        ),
        unread_conversations=await coll(db, Conversation).count_documents(
            {**open_conv, "unread_count": {"$gt": 0}}
        ),
    )


@router.get("/dashboard/stats", response_model=StatsOut)
async def stats(p: CurrentPrincipal, db: DbDep) -> StatsOut:
    since = datetime.now(UTC) - timedelta(days=30)
    pipeline = {
        row["_id"]: row["n"]
        async for row in await coll(db, Contact).aggregate(
            [
                {"$match": {"tenant_id": p.tenant_id}},
                {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
            ]
        )
    }
    contacts = coll(db, Contact)
    return StatsOut(
        pipeline={s.value: pipeline.get(s.value, 0) for s in LeadStage},
        leads_last_30_days=await contacts.count_documents(
            {"tenant_id": p.tenant_id, "created_at": {"$gte": since}}
        ),
        visits_last_30_days=await coll(db, Appointment).count_documents(
            {
                "tenant_id": p.tenant_id,
                "starts_at": {"$gte": since},
                "status": {"$ne": AppointmentStatus.cancelled},
            }
        ),
        won_last_30_days=await contacts.count_documents(
            {"tenant_id": p.tenant_id, "stage": LeadStage.won, "updated_at": {"$gte": since}}
        ),
        active_listings=await coll(db, Property).count_documents(
            {"tenant_id": p.tenant_id, "published": True, "status": PropertyStatus.available}
        ),
    )
