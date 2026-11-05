from collections.abc import Iterable

from app.core.db import Db, coll
from app.models import Notification, Role, User


async def recipients_for(db: Db, tenant_id: str, assigned_to: str | None) -> list[str]:
    """The assigned team member, or every owner/admin when nobody is assigned."""
    if assigned_to is not None:
        return [assigned_to]
    cursor = coll(db, User).find(
        {"tenant_id": tenant_id, "is_active": True, "role": {"$in": [Role.owner, Role.admin]}},
        {"_id": 1},
    )
    return [u["_id"] async for u in cursor]


async def notify(
    db: Db,
    tenant_id: str,
    user_ids: Iterable[str],
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    session=None,
) -> None:
    docs = [
        Notification(
            tenant_id=tenant_id, user_id=u, kind=kind, title=title, body=body, link=link
        ).dump()
        for u in set(user_ids)
    ]
    if docs:
        await coll(db, Notification).insert_many(docs, session=session)
