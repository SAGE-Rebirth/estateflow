"""The eval tenant: four live listings, one sold, a brochure, and a returning buyer."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.db import Db, insert
from app.core.security import encrypt_secret
from app.models import (
    Appointment,
    AppointmentKind,
    AvailabilityRule,
    Contact,
    Document,
    ListingType,
    Media,
    Property,
    PropertyStatus,
    PropertyType,
    Role,
    Tenant,
    User,
)
from app.services.rag.ingest import index_property, ingest_document
from app.services.storage import save_bytes

TZ = ZoneInfo("Asia/Kolkata")
# Fixed clock: a Sunday morning, so "Monday" means a definite date with free slots.
NOW = datetime(2030, 1, 6, 9, 0, tzinfo=TZ).astimezone(UTC)
BUYER_WA_ID = "919811100009"

BROCHURE = """PR-1001 Lake View Residences brochure.
Payment plan: 10% on booking, 80% construction-linked, 10% on possession.
Possession: ready to move. Covered parking: 2 slots. Maintenance: INR 4 per sq ft.
Approved by SBI, HDFC and ICICI for home loans."""

LISTINGS = [
    (
        "PR-1001",
        "3BHK Lake View Apartment",
        PropertyType.apartment,
        9_500_000,
        3,
        "Hebbal",
        PropertyStatus.available,
    ),
    (
        "PR-1002",
        "2BHK Starter Home",
        PropertyType.apartment,
        4_800_000,
        2,
        "Yelahanka",
        PropertyStatus.available,
    ),
    (
        "PR-1003",
        "4BHK Garden Villa",
        PropertyType.villa,
        32_000_000,
        4,
        "Whitefield",
        PropertyStatus.available,
    ),
    (
        "PR-1004",
        "3BHK Park Facing",
        PropertyType.apartment,
        14_500_000,
        3,
        "Hebbal",
        PropertyStatus.under_offer,
    ),
    (
        "PR-1005",
        "2BHK Metro Corner",
        PropertyType.apartment,
        6_200_000,
        2,
        "Yeshwanthpur",
        PropertyStatus.sold,
    ),
]


async def seed(db: Db, *, with_appointment: bool = False) -> Tenant:
    tenant = await insert(
        db,
        Tenant(
            name="Eval Realty",
            slug="eval",
            whatsapp_phone_number_id="EVAL",
            whatsapp_display_number="+91 90000 11111",
            whatsapp_access_token_enc=encrypt_secret("unused"),
        ),
    )
    agent = await insert(
        db,
        User(
            tenant_id=tenant.id,
            email="agent@eval.example.com",
            full_name="Asha",
            role=Role.owner,
            phone="+91 90000 22222",
            password_hash="x",
            availability=[
                AvailabilityRule(weekday=d, start_time="10:00", end_time="18:00") for d in range(7)
            ],
        ),
    )
    for ref, title, ptype, price, beds, loc, status in LISTINGS:
        prop = await insert(
            db,
            Property(
                tenant_id=tenant.id,
                ref_code=ref,
                title=title,
                property_type=ptype,
                listing_type=ListingType.sale,
                status=status,
                price=price,
                bedrooms=beds,
                area_sqft=beds * 550,
                city="Bengaluru",
                locality=loc,
                published=True,
                description=f"{title} in {loc}.",
                media=[Media(url=f"https://example.com/{ref}/{i}.jpg", path="-") for i in range(3)],
            ),
        )
        await index_property(db, prop.id, tenant.currency)
        if ref == "PR-1001":
            path = save_bytes(BROCHURE.encode(), tenant.id, ".txt", private=True)
            doc = await insert(
                db,
                Document(
                    tenant_id=tenant.id,
                    property_id=prop.id,
                    filename="lake-view-brochure.txt",
                    storage_path=path,
                ),
            )
            await ingest_document(db, doc.id)
    # Other clients' data the assistant must never reveal.
    await insert(db, Contact(tenant_id=tenant.id, phone="+919811100001", name="Ravi Kumar"))
    buyer = await insert(
        db, Contact(tenant_id=tenant.id, phone=f"+{BUYER_WA_ID}", wa_id=BUYER_WA_ID, name="Kiran")
    )
    if with_appointment:
        start = NOW + timedelta(days=1, hours=3)
        await insert(
            db,
            Appointment(
                tenant_id=tenant.id,
                contact_id=buyer.id,
                user_id=agent.id,
                kind=AppointmentKind.site_visit,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
            ),
        )
    return tenant
