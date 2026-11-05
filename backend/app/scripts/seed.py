"""Demo data: `uv run python -m app.scripts.seed` → log in as demo@estateflow.dev / demo12345.

Writes to the database in MONGO_URL / DB_NAME. Listing embeddings use the configured
Hugging Face model; pass --no-embed to skip them (e.g. while HF credits are unavailable).
"""

import asyncio
import sys
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.db import close_client, ensure_indexes, find_one, get_database, insert
from app.core.security import hash_password
from app.models import (
    Activity,
    ActivityKind,
    Appointment,
    AppointmentKind,
    AvailabilityRule,
    Contact,
    Conversation,
    ConversationMode,
    DeliveryStatus,
    Direction,
    LeadSource,
    LeadStage,
    ListingType,
    Message,
    Property,
    PropertyStatus,
    PropertyType,
    Role,
    SenderType,
    Task,
    Tenant,
    User,
)
from app.services.rag.ingest import index_property

LISTINGS = [
    (
        "PR-1001",
        "3BHK Lake View Apartment",
        PropertyType.apartment,
        ListingType.sale,
        9_500_000,
        3,
        1650,
        "Hebbal",
        ["gym", "pool", "clubhouse", "power backup"],
        "East-facing corner unit on the 12th floor overlooking Hebbal lake. Two covered parking "
        "slots. Possession ready. 10 minutes to the airport road.",
    ),
    (
        "PR-1002",
        "2BHK Starter Home",
        PropertyType.apartment,
        ListingType.sale,
        4_800_000,
        2,
        1050,
        "Yelahanka",
        ["park", "security"],
        "Compact 2BHK in a gated community, ideal for first-time buyers. Bank loan approved by "
        "SBI and HDFC.",
    ),
    (
        "PR-1003",
        "4BHK Garden Villa",
        PropertyType.villa,
        ListingType.sale,
        32_000_000,
        4,
        3600,
        "Whitefield",
        ["private garden", "home theatre", "solar"],
        "Independent villa with a 1200 sq ft private garden, home theatre and rooftop solar.",
    ),
    (
        "PR-1004",
        "Furnished 1BHK for Rent",
        PropertyType.apartment,
        ListingType.rent,
        28_000,
        1,
        650,
        "Koramangala",
        ["furnished", "wifi"],
        "Fully furnished, walk to Forum mall. 2 months deposit. Available immediately.",
    ),
]


def hours() -> list[AvailabilityRule]:
    return [AvailabilityRule(weekday=d, start_time="10:00", end_time="18:00") for d in range(6)]


# A second seller so the marketplace shows several businesses, cities and property types.
SKYLINE = [
    (
        "PR-2001",
        "Skyline Greens 2BHK",
        PropertyType.apartment,
        ListingType.sale,
        7_200_000,
        2,
        1180,
        "Hinjewadi",
        "Pune",
        ["gym", "pool", "kids play area", "24x7 security"],
        "Two-bedroom home in a 22-acre township next to the IT park. Ready to move in. "
        "Covered parking and power backup included.",
    ),
    (
        "PR-2002",
        "Skyline Greens 3BHK Corner",
        PropertyType.apartment,
        ListingType.sale,
        11_500_000,
        3,
        1620,
        "Baner",
        "Pune",
        ["clubhouse", "jogging track", "gym"],
        "Corner unit with three balconies and hill views. Possession December 2027.",
    ),
    (
        "PR-2003",
        "Skyline Courtyard Villa",
        PropertyType.villa,
        ListingType.sale,
        45_000_000,
        4,
        4100,
        "Gachibowli",
        "Hyderabad",
        ["private pool", "home automation", "garden"],
        "Gated villa community of 60 homes with a private pool in every villa.",
    ),
    (
        "PR-2004",
        "Residential Plot, East Facing",
        PropertyType.plot,
        ListingType.sale,
        6_800_000,
        None,
        2400,
        "Shamshabad",
        "Hyderabad",
        ["gated layout", "clear title"],
        "HMDA-approved plot in a gated layout, 15 minutes from the airport.",
    ),
    (
        "PR-2005",
        "2BHK Near Metro for Rent",
        PropertyType.apartment,
        ListingType.rent,
        32_000,
        2,
        1050,
        "Madhapur",
        "Hyderabad",
        ["semi-furnished", "lift", "power backup"],
        "Semi-furnished, 5 minutes' walk from the metro. Family preferred. 3 months deposit.",
    ),
    (
        "PR-2006",
        "Office Space, 40 Seats",
        PropertyType.office,
        ListingType.rent,
        180_000,
        None,
        3200,
        "Koramangala",
        "Bengaluru",
        ["furnished", "meeting rooms", "parking"],
        "Plug-and-play office with two meeting rooms and a pantry. Available from next month.",
    ),
]


async def seed_second_seller(db) -> None:
    if await find_one(db, Tenant, {"slug": "skyline"}):
        return
    tenant = await insert(
        db,
        Tenant(name="Skyline Builders", slug="skyline", whatsapp_display_number="+91 99000 12345"),
    )
    await insert(
        db,
        User(
            tenant_id=tenant.id,
            email="sales@skyline.example.com",
            full_name="Rohan Mehta",
            role=Role.owner,
            password_hash=hash_password("demo12345"),
            availability=hours(),
        ),
    )
    for ref, title, ptype, ltype, price, beds, area, loc, city, amen, desc in SKYLINE:
        await insert(
            db,
            Property(
                tenant_id=tenant.id,
                ref_code=ref,
                title=title,
                property_type=ptype,
                listing_type=ltype,
                status=PropertyStatus.available,
                price=price,
                bedrooms=beds,
                bathrooms=beds,
                area_sqft=area,
                city=city,
                locality=loc,
                amenities=amen,
                description=desc,
                published=True,
            ),
        )


async def main(embed: bool = True) -> None:
    db = get_database()
    await ensure_indexes(db)
    await seed_second_seller(db)
    if await find_one(db, Tenant, {"slug": "demo"}):
        print("Demo tenant already exists.")
        return
    tenant = await insert(
        db, Tenant(name="Demo Realty", slug="demo", whatsapp_display_number="+91 98765 43210")
    )
    owner = await insert(
        db,
        User(
            tenant_id=tenant.id,
            email="demo@estateflow.dev",
            full_name="Priya Sharma",
            role=Role.owner,
            password_hash=hash_password("demo12345"),
            availability=hours(),
        ),
    )
    agent = await insert(
        db,
        User(
            tenant_id=tenant.id,
            email="agent@estateflow.dev",
            full_name="Arjun Rao",
            role=Role.agent,
            password_hash=hash_password("demo12345"),
            availability=hours(),
        ),
    )
    props = []
    for ref, title, ptype, ltype, price, beds, area, loc, amen, desc in LISTINGS:
        props.append(
            await insert(
                db,
                Property(
                    tenant_id=tenant.id,
                    ref_code=ref,
                    title=title,
                    property_type=ptype,
                    listing_type=ltype,
                    status=PropertyStatus.available,
                    price=price,
                    bedrooms=beds,
                    bathrooms=max(1, beds - 1),
                    area_sqft=area,
                    city="Bengaluru",
                    locality=loc,
                    amenities=amen,
                    description=desc,
                    published=True,
                ),
            )
        )

    tz = ZoneInfo(tenant.timezone)
    today = datetime.now(tz).date()
    recent = datetime.now(UTC) - timedelta(hours=2)
    contacts = []
    for phone, name, stage, assignee in [
        ("+919811100001", "Ravi Kumar", LeadStage.visit_scheduled, owner),
        ("+919811100002", "Meera Iyer", LeadStage.qualified, agent),
        ("+919811100003", "Sameer Khan", LeadStage.new, None),
        ("+919811100004", "Anita Desai", LeadStage.negotiation, owner),
    ]:
        contacts.append(
            await insert(
                db,
                Contact(
                    tenant_id=tenant.id,
                    phone=phone,
                    wa_id=phone.lstrip("+"),
                    name=name,
                    stage=stage,
                    source=LeadSource.whatsapp,
                    preferred_locations=["Hebbal"],
                    budget_max=10_000_000,
                    bedrooms=3,
                    assigned_to=assignee.id if assignee else None,
                    last_inbound_at=recent,
                ),
            )
        )

    def at(day_offset: int, hour: int) -> datetime:
        return datetime.combine(today + timedelta(days=day_offset), time(hour), tz)

    for contact, user, prop, day, hour, kind in [
        (contacts[0], owner, props[0], 0, 11, AppointmentKind.site_visit),
        (contacts[3], owner, props[2], 0, 16, AppointmentKind.office_meeting),
        (contacts[1], agent, props[1], 1, 12, AppointmentKind.site_visit),
    ]:
        await insert(
            db,
            Appointment(
                tenant_id=tenant.id,
                contact_id=contact.id,
                user_id=user.id,
                property_id=prop.id,
                kind=kind,
                starts_at=at(day, hour),
                ends_at=at(day, hour + 1),
                created_by_bot=True,
                location=f"{prop.locality}, Bengaluru",
            ),
        )
        await insert(
            db,
            Activity(
                tenant_id=tenant.id,
                contact_id=contact.id,
                kind=ActivityKind.appointment,
                summary=f"{kind.value.replace('_', ' ').title()} booked by the WhatsApp assistant",
            ),
        )
    await insert(
        db,
        Task(
            tenant_id=tenant.id,
            contact_id=contacts[3].id,
            assigned_to=owner.id,
            title="Share revised price sheet with Anita",
            due_at=at(0, 15),
        ),
    )
    await insert(
        db,
        Task(
            tenant_id=tenant.id,
            contact_id=contacts[2].id,
            assigned_to=owner.id,
            title="Call Sameer — new lead from WhatsApp",
            due_at=at(-1, 17),
        ),
    )

    now = datetime.now(UTC)
    ravi_chat = [
        (
            Direction.inbound,
            SenderType.contact,
            "Hi, I'm interested in PR-1001 - 3BHK Lake View Apartment",
        ),
        (
            Direction.outbound,
            SenderType.bot,
            "Hi Ravi! PR-1001 is a 3BHK, 1,650 sq ft corner unit in Hebbal at INR 95,00,000, "
            "possession ready. Would you like to visit?",
        ),
        (Direction.inbound, SenderType.contact, "Yes, today 11am works"),
        (
            Direction.outbound,
            SenderType.bot,
            "Done! Your site visit is booked for today at 11:00 AM at Hebbal, Bengaluru.",
        ),
    ]
    conv = await insert(
        db,
        Conversation(
            tenant_id=tenant.id,
            contact_id=contacts[0].id,
            focus_property_id=props[0].id,
            last_message_at=now,
            last_direction=Direction.outbound,
            last_message=ravi_chat[-1][2],
        ),
    )
    for i, (direction, sender, body) in enumerate(ravi_chat):
        await insert(
            db,
            Message(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                direction=direction,
                sender_type=sender,
                body=body,
                status=DeliveryStatus.read,
                created_at=now - timedelta(minutes=10 - i),
            ),
        )
    ask = "Can you do any better on the villa price?"
    handoff = await insert(
        db,
        Conversation(
            tenant_id=tenant.id,
            contact_id=contacts[3].id,
            mode=ConversationMode.human,
            unread_count=1,
            last_message_at=now,
            last_direction=Direction.inbound,
            last_message=ask,
        ),
    )
    await insert(
        db,
        Message(
            tenant_id=tenant.id,
            conversation_id=handoff.id,
            direction=Direction.inbound,
            sender_type=SenderType.contact,
            body=ask,
        ),
    )
    if embed:
        for p in props:
            await index_property(db, p.id, tenant.currency)
    print("Seeded. Log in as demo@estateflow.dev / demo12345")


async def _run() -> None:
    try:
        await main(embed="--no-embed" not in sys.argv)
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(_run())
