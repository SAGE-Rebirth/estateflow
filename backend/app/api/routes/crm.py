import re
from datetime import UTC, datetime

import phonenumbers
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pymongo.errors import DuplicateKeyError

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbDep, get_owned
from app.core.db import coll, find, find_one, insert, save
from app.models import (
    Activity,
    ActivityKind,
    Contact,
    Conversation,
    ConversationMode,
    ConversationStatus,
    LeadStage,
    Message,
    Notification,
    Task,
)
from app.schemas.common import Page
from app.schemas.crm import (
    ActivityOut,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    ConversationListItem,
    ConversationOut,
    ConversationUpdate,
    InterestOut,
    MessageOut,
    NoteIn,
    NotificationOut,
    ReplyIn,
    TaskIn,
    TaskOut,
    TaskUpdate,
)
from app.services.inbound import send_staff_message
from app.services.storage import MEDIA_EXT, resolve

INLINE_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/amr",
}

router = APIRouter()


def normalize_phone(raw: str, region: str = "IN") -> str:
    try:
        num = phonenumbers.parse(raw, None if raw.startswith("+") else region)
        if not phonenumbers.is_possible_number(num):
            raise ValueError
    except (phonenumbers.NumberParseException, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid phone number") from None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def _rx(q: str) -> dict:
    return {"$regex": re.escape(q), "$options": "i"}


# --- Contacts ---------------------------------------------------------------------------


@router.get("/contacts", response_model=Page[ContactOut], tags=["contacts"])
async def list_contacts(
    p: CurrentPrincipal,
    db: DbDep,
    q: str | None = None,
    stage: LeadStage | None = None,
    assigned_to: str | None = None,
    mine: bool = False,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> Page[ContactOut]:
    query: dict = {"tenant_id": p.tenant_id}
    if q:
        query["$or"] = [{"name": _rx(q)}, {"phone": _rx(q)}, {"email": _rx(q)}]
    if stage:
        query["stage"] = stage
    if mine:
        assigned_to = p.user.id
    if assigned_to:
        query["assigned_to"] = assigned_to
    total = await coll(db, Contact).count_documents(query)
    rows = await find(db, Contact, query, sort=[("updated_at", -1)], limit=limit, skip=offset)
    return Page(items=[ContactOut.model_validate(r) for r in rows], total=total)


@router.post("/contacts", response_model=ContactOut, status_code=201, tags=["contacts"])
async def create_contact(body: ContactCreate, p: CurrentPrincipal, db: DbDep) -> Contact:
    phone = normalize_phone(body.phone)
    contact = Contact(
        tenant_id=p.tenant_id,
        phone=phone,
        wa_id=phone.lstrip("+"),
        **body.model_dump(exclude={"phone"}),
    )
    try:
        await insert(db, contact)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A contact with this phone exists") from None
    return contact


@router.get("/contacts/{contact_id}", response_model=ContactOut, tags=["contacts"])
async def get_contact(contact_id: str, p: CurrentPrincipal, db: DbDep) -> Contact:
    return await get_owned(db, Contact, contact_id, p.tenant_id)


@router.patch("/contacts/{contact_id}", response_model=ContactOut, tags=["contacts"])
async def update_contact(
    contact_id: str, body: ContactUpdate, p: CurrentPrincipal, db: DbDep
) -> Contact:
    contact = await get_owned(db, Contact, contact_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    if "stage" in data and data["stage"] != contact.stage:
        await insert(
            db,
            Activity(
                tenant_id=p.tenant_id,
                contact_id=contact.id,
                user_id=p.user.id,
                kind=ActivityKind.stage_change,
                summary=f"Stage: {contact.stage.value} → {data['stage'].value}",
                meta={"from": contact.stage.value, "to": data["stage"].value},
            ),
        )
    for k, v in data.items():
        setattr(contact, k, v)
    if data:
        await save(db, contact, *data)
    return contact


@router.delete("/contacts/{contact_id}", status_code=204, tags=["contacts"])
async def delete_contact(contact_id: str, p: AdminPrincipal, db: DbDep) -> None:
    contact = await get_owned(db, Contact, contact_id, p.tenant_id)
    convs = [c.id for c in await find(db, Conversation, {"contact_id": contact.id})]
    await coll(db, Message).delete_many({"conversation_id": {"$in": convs}})
    for model in (Conversation, Activity, Task):
        await coll(db, model).delete_many({"contact_id": contact.id})
    await coll(db, Contact).delete_one({"_id": contact.id})


@router.get(
    "/contacts/{contact_id}/activities", response_model=list[ActivityOut], tags=["contacts"]
)
async def contact_activities(contact_id: str, p: CurrentPrincipal, db: DbDep) -> list[Activity]:
    await get_owned(db, Contact, contact_id, p.tenant_id)
    return await find(
        db, Activity, {"contact_id": contact_id}, sort=[("created_at", -1)], limit=200
    )


@router.post(
    "/contacts/{contact_id}/activities",
    response_model=ActivityOut,
    status_code=201,
    tags=["contacts"],
)
async def add_note(contact_id: str, body: NoteIn, p: CurrentPrincipal, db: DbDep) -> Activity:
    await get_owned(db, Contact, contact_id, p.tenant_id)
    return await insert(
        db,
        Activity(
            tenant_id=p.tenant_id,
            contact_id=contact_id,
            user_id=p.user.id,
            kind=body.kind,
            summary=body.summary,
        ),
    )


@router.get("/contacts/{contact_id}/interests", response_model=list[InterestOut], tags=["contacts"])
async def contact_interests(contact_id: str, p: CurrentPrincipal, db: DbDep):
    contact = await get_owned(db, Contact, contact_id, p.tenant_id)
    return sorted(contact.interests, key=lambda i: i.at, reverse=True)


# --- Tasks / follow-ups -----------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut], tags=["tasks"])
async def list_tasks(
    p: CurrentPrincipal,
    db: DbDep,
    contact_id: str | None = None,
    mine: bool = False,
    include_done: bool = False,
    due_before: datetime | None = None,
) -> list[Task]:
    query: dict = {"tenant_id": p.tenant_id}
    if contact_id:
        query["contact_id"] = contact_id
    if mine:
        query["assigned_to"] = p.user.id
    if not include_done:
        query["done_at"] = None
    if due_before:
        query["due_at"] = {"$lt": due_before}
    return await find(db, Task, query, sort=[("due_at", 1)], limit=500)


@router.post("/tasks", response_model=TaskOut, status_code=201, tags=["tasks"])
async def create_task(body: TaskIn, p: CurrentPrincipal, db: DbDep) -> Task:
    if body.contact_id:
        await get_owned(db, Contact, body.contact_id, p.tenant_id)
    task = Task(tenant_id=p.tenant_id, **body.model_dump())
    task.assigned_to = task.assigned_to or p.user.id
    return await insert(db, task)


@router.patch("/tasks/{task_id}", response_model=TaskOut, tags=["tasks"])
async def update_task(task_id: str, body: TaskUpdate, p: CurrentPrincipal, db: DbDep) -> Task:
    task = await get_owned(db, Task, task_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    if (done := data.pop("done", None)) is not None:
        task.done_at = datetime.now(UTC) if done else None
        data["done_at"] = task.done_at
    if "due_at" in data:
        task.reminder_sent = False  # remind again for the new time
        data["reminder_sent"] = False
    for k, v in data.items():
        setattr(task, k, v)
    if data:
        await save(db, task, *data)
    return task


@router.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
async def delete_task(task_id: str, p: CurrentPrincipal, db: DbDep) -> None:
    task = await get_owned(db, Task, task_id, p.tenant_id)
    await coll(db, Task).delete_one({"_id": task.id})


# --- Inbox ------------------------------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationListItem], tags=["inbox"])
async def list_conversations(
    p: CurrentPrincipal,
    db: DbDep,
    status_: ConversationStatus | None = Query(default=ConversationStatus.open, alias="status"),
    mode: ConversationMode | None = None,
    unread: bool = False,
    limit: int = Query(default=50, le=200),
) -> list[ConversationListItem]:
    query: dict = {"tenant_id": p.tenant_id, "last_message_at": {"$ne": None}}
    if status_:
        query["status"] = status_
    if mode:
        query["mode"] = mode
    if unread:
        query["unread_count"] = {"$gt": 0}
    convs = await find(db, Conversation, query, sort=[("last_message_at", -1)], limit=limit)
    contacts = {
        c.id: c for c in await find(db, Contact, {"_id": {"$in": [c.contact_id for c in convs]}})
    }
    return [
        ConversationListItem(
            **ConversationOut.model_validate(c).model_dump(),
            contact_name=contacts[c.contact_id].name if c.contact_id in contacts else None,
            contact_phone=contacts[c.contact_id].phone if c.contact_id in contacts else "",
            last_message=c.last_message,
        )
        for c in convs
    ]


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut], tags=["inbox"])
async def conversation_messages(
    conv_id: str,
    p: CurrentPrincipal,
    db: DbDep,
    before: datetime | None = None,
    limit: int = Query(default=100, le=500),
) -> list[Message]:
    conv = await get_owned(db, Conversation, conv_id, p.tenant_id)
    query: dict = {"conversation_id": conv.id}
    if before:
        query["created_at"] = {"$lt": before}
    rows = await find(db, Message, query, sort=[("created_at", -1)], limit=limit)
    if conv.unread_count:
        await coll(db, Conversation).update_one({"_id": conv.id}, {"$set": {"unread_count": 0}})
    return list(reversed(rows))


@router.get("/conversations/{conv_id}/messages/{message_id}/media", tags=["inbox"])
async def message_media(conv_id: str, message_id: str, p: CurrentPrincipal, db: DbDep):
    """A buyer's photo / voice note / document. Private: staff of this tenant only."""
    msg = await find_one(
        db, Message, {"_id": message_id, "conversation_id": conv_id, "tenant_id": p.tenant_id}
    )
    if msg is None or not msg.media_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No media on this message")
    path = resolve(msg.media_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File no longer available")
    # Buyers choose what they send, so never let a file render as a page on our origin:
    # only known image/audio types display inline; everything else downloads, typed as
    # opaque bytes, with sniffing off and a sandboxing CSP as a backstop.
    mime = msg.media_mime or ""
    inline = mime in INLINE_MEDIA_TYPES
    return FileResponse(
        path,
        media_type=mime if inline else "application/octet-stream",
        filename=None if inline else f"whatsapp-{msg.id}{MEDIA_EXT.get(mime, '')}",
        content_disposition_type="inline" if inline else "attachment",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post(
    "/conversations/{conv_id}/messages", response_model=MessageOut, status_code=201, tags=["inbox"]
)
async def reply(conv_id: str, body: ReplyIn, p: CurrentPrincipal, db: DbDep) -> Message:
    """A team member replies. Replying takes the conversation over from the assistant."""
    conv = await get_owned(db, Conversation, conv_id, p.tenant_id)
    contact = await get_owned(db, Contact, conv.contact_id, p.tenant_id)
    conv.mode = ConversationMode.human
    return await send_staff_message(db, p.tenant, conv, contact, p.user.id, body.body)


@router.patch("/conversations/{conv_id}", response_model=ConversationOut, tags=["inbox"])
async def update_conversation(
    conv_id: str, body: ConversationUpdate, p: CurrentPrincipal, db: DbDep
) -> Conversation:
    """Take over from the assistant (mode=human), hand back (mode=bot), or close."""
    conv = await get_owned(db, Conversation, conv_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(conv, k, v)
    if data:
        await save(db, conv, *data)
    return conv


# --- Notifications ----------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut], tags=["notifications"])
async def list_notifications(
    p: CurrentPrincipal,
    db: DbDep,
    unread_only: bool = False,
    limit: int = Query(default=50, le=200),
) -> list[Notification]:
    query: dict = {"tenant_id": p.tenant_id, "user_id": p.user.id}
    if unread_only:
        query["read_at"] = None
    return await find(db, Notification, query, sort=[("created_at", -1)], limit=limit)


@router.get("/notifications/unread-count", tags=["notifications"])
async def unread_count(p: CurrentPrincipal, db: DbDep) -> dict[str, int]:
    n = await coll(db, Notification).count_documents({"user_id": p.user.id, "read_at": None})
    return {"count": n}


@router.post("/notifications/read", status_code=204, tags=["notifications"])
async def mark_read(p: CurrentPrincipal, db: DbDep, ids: list[str] | None = Query(None)) -> None:
    """Mark the given notifications (or all, when no ids are sent) as read."""
    query: dict = {"user_id": p.user.id, "read_at": None}
    if ids:
        query["_id"] = {"$in": ids}
    await coll(db, Notification).update_many(query, {"$set": {"read_at": datetime.now(UTC)}})
