from app.core.db import insert, save
from app.models import (
    ListingType,
    Media,
    MediaKind,
    Property,
    PropertyStatus,
    PropertyType,
    Tenant,
)

API = "/api/v1/market"


async def _seller(db, slug, **kw) -> Tenant:
    return await insert(
        db,
        Tenant(
            name=f"{slug.title()} Realty",
            slug=slug,
            whatsapp_display_number="+91 98765 43210",
            **kw,
        ),
    )


async def _home(db, t, ref, **kw) -> Property:
    defaults = dict(
        title=f"Home {ref}",
        listing_type=ListingType.sale,
        property_type=PropertyType.apartment,
        status=PropertyStatus.available,
        price=5_000_000,
        area_sqft=1000,
        bedrooms=2,
        city="Bengaluru",
        locality="Hebbal",
        published=True,
    )
    return await insert(db, Property(tenant_id=t.id, ref_code=ref, **{**defaults, **kw}))


async def test_listings_across_sellers_with_filters_and_sort(client, db):
    a, b = await _seller(db, "acme"), await _seller(db, "beta")
    await _home(
        db,
        a,
        "PR-1001",
        price=9_500_000,
        bedrooms=3,
        area_sqft=1650,
        media=[
            Media(url="https://x/2.jpg", path="-", sort_order=2),
            Media(url="https://x/1.jpg", path="-", sort_order=1),
            Media(url="https://x/plan.jpg", path="-", kind=MediaKind.floorplan),
        ],
    )
    await _home(db, a, "PR-1002", price=4_800_000, bedrooms=2, locality="Yelahanka")
    await _home(
        db,
        b,
        "PR-1001",
        price=32_000_000,
        bedrooms=5,
        property_type=PropertyType.villa,
        locality="Whitefield",
    )
    await _home(
        db,
        b,
        "PR-1002",
        listing_type=ListingType.rent,
        price=28_000,
        bedrooms=1,
        locality="Koramangala",
    )
    # Never shown: draft, sold, unpublished, inactive seller, opted-out seller.
    await _home(db, a, "PR-1003", status=PropertyStatus.draft)
    await _home(db, a, "PR-1004", status=PropertyStatus.sold)
    await _home(db, a, "PR-1005", published=False)
    await _home(db, await _seller(db, "gone", is_active=False), "PR-1001")
    await _home(db, await _seller(db, "private", list_on_marketplace=False), "PR-1001")

    r = (await client.get(f"{API}/listings")).json()
    assert r["total"] == 4
    # A published draft isn't reachable by URL either; a sold one keeps its page.
    assert (await client.get(f"{API}/listings/acme/PR-1003")).status_code == 404
    assert (await client.get(f"{API}/listings/acme/PR-1004")).status_code == 200
    assert {(i["slug"], i["ref_code"]) for i in r["items"]} == {
        ("acme", "PR-1001"),
        ("acme", "PR-1002"),
        ("beta", "PR-1001"),
        ("beta", "PR-1002"),
    }

    top = next(i for i in r["items"] if i["slug"] == "acme" and i["ref_code"] == "PR-1001")
    assert top["photo"] == "https://x/1.jpg" and top["photo_count"] == 2
    assert top["price_per_sqft"] == round(9_500_000 / 1650)
    assert top["seller_name"] == "Acme Realty"
    assert "PR-1001" in top["whatsapp_url"]

    async def refs(**params):
        r = (await client.get(f"{API}/listings", params=params)).json()
        return [f"{i['slug']}/{i['ref_code']}" for i in r["items"]]

    assert await refs(listing_type="sale", sort="price_asc") == [
        "acme/PR-1002",
        "acme/PR-1001",
        "beta/PR-1001",
    ]
    assert await refs(bedrooms=[4]) == ["beta/PR-1001"]  # 4 means 4+
    assert sorted(await refs(bedrooms=[2, 3])) == ["acme/PR-1001", "acme/PR-1002"]
    assert await refs(property_type=["villa"]) == ["beta/PR-1001"]
    assert await refs(max_price=5_000_000, listing_type="sale") == ["acme/PR-1002"]
    assert await refs(locality="hebbal") == ["acme/PR-1001"]
    assert await refs(q="whitefield") == ["beta/PR-1001"]
    assert sorted(await refs(seller="beta")) == ["beta/PR-1001", "beta/PR-1002"]
    assert await refs(q="(((") == []  # regex input is escaped
    page = (await client.get(f"{API}/listings", params={"limit": 2, "offset": 2})).json()
    assert page["total"] == 4 and len(page["items"]) == 2


async def test_detail_with_similar_homes(client, db):
    a, b = await _seller(db, "acme"), await _seller(db, "beta")
    await _home(
        db,
        a,
        "PR-1001",
        description="Lake-facing corner unit",
        latitude=13.03,
        longitude=77.59,
        media=[Media(url="https://x/plan.jpg", path="-", kind=MediaKind.floorplan)],
    )
    await _home(db, b, "PR-2001")  # same city + type, other seller
    await _home(db, a, "PR-1002", property_type=PropertyType.villa)  # same city, other type
    await _home(db, a, "PR-1003", city="Mumbai")
    await _home(db, a, "PR-1004", listing_type=ListingType.rent)

    d = (await client.get(f"{API}/listings/acme/pr-1001")).json()
    assert d["description"] == "Lake-facing corner unit"
    assert d["floorplans"] == ["https://x/plan.jpg"] and d["photos"] == []
    assert d["seller"] == {
        "name": "Acme Realty",
        "slug": "acme",
        "whatsapp_number": "+91 98765 43210",
    }
    assert [f"{s['slug']}/{s['ref_code']}" for s in d["similar"]] == [
        "beta/PR-2001",
        "acme/PR-1002",
    ]
    assert (await client.get(f"{API}/listings/acme/PR-9999")).status_code == 404
    assert (await client.get(f"{API}/listings/nobody/PR-1001")).status_code == 404


async def test_summary_counts(client, db):
    a = await _seller(db, "acme")
    await _home(db, a, "PR-1001")
    await _home(db, a, "PR-1002", city="Mumbai", locality="Bandra")
    await _home(db, a, "PR-1003", listing_type=ListingType.rent, property_type=PropertyType.villa)
    p = await _home(db, a, "PR-1004")
    p.status = PropertyStatus.sold
    await save(db, p, "status")
    s = (await client.get(f"{API}/summary")).json()
    assert (s["total"], s["for_sale"], s["for_rent"]) == (3, 2, 1)
    assert s["cities"] == [{"value": "Bengaluru", "count": 2}, {"value": "Mumbai", "count": 1}]
    assert {"value": "villa", "count": 1} in s["property_types"]
