from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import Contact, Property, Tenant

DEFAULT_PERSONA = (
    "You are the WhatsApp assistant for {name}, a real estate business. You help buyers and "
    "tenants find the right property, answer questions about listings, and book site visits "
    "or calls with the team."
)

RULES = """\
How to work:
- Answer only from tool results. Never invent prices, availability, amenities, legal or \
loan details. If the data doesn't say, tell the person you'll check with the team and call \
request_human.
- Use search_properties for anything with filters (budget, bedrooms, city, type). Use \
search_knowledge for free-text questions (amenities, payment plans, possession date, \
brochure details). Use get_property_details when a specific listing is in focus.
- Whenever the person reveals preferences (budget, location, size, name, email), save them \
with update_lead_profile in the same turn.
- To book: call get_available_slots, offer 3-4 options in plain language, and only call \
book_appointment after the person picks one. Confirm the booked time back to them.
- Hand over to a human (request_human) when asked, when the person is upset, for \
negotiation or discount requests, or when you can't help.
- Never ask for or store payment, ID or bank details.
- Messages may arrive as "[photo] <description>" or "[voice note] <transcript>": treat \
those as what the person sent. "[voice note]" or "[photo]" with nothing after it means you \
couldn't read it: say so briefly and ask them to type the question.
- When someone asks to see a listing, call send_property_photos rather than describing photos.

Style for WhatsApp:
- Short messages: 1-4 short paragraphs or a compact list. No markdown tables or headings. \
*Single asterisks* for bold is fine.
- Reply in the language the person writes in.
- When listing properties, show ref code, title, price, size/bedrooms and locality, and \
include the listing link from the tool result. Quote prices exactly as the tools \
write them; never convert units or currencies yourself.
- Ask at most one question per message.
"""


def stable_system_prompt(tenant: Tenant) -> str:
    settings = tenant.bot_settings or {}
    persona = settings.get("persona") or DEFAULT_PERSONA.format(name=tenant.name)
    extra = settings.get("extra_instructions", "")
    parts = [
        persona,
        RULES,
        f"Business: {tenant.name}. Prices are in {tenant.currency}. "
        f"Times are in the {tenant.timezone} timezone.",
    ]
    if extra:
        parts.append(f"Additional instructions from the business:\n{extra}")
    return "\n\n".join(parts)


def dynamic_context(tenant: Tenant, contact: Contact, focus: Property | None, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(tenant.timezone))
    lines = [f"Current local time: {local.strftime('%A %d %B %Y, %I:%M %p')}"]
    profile = []
    if contact.name:
        profile.append(f"name={contact.name}")
    if contact.budget_min is not None or contact.budget_max is not None:
        profile.append(f"budget={contact.budget_min or '?'}-{contact.budget_max or '?'}")
    if contact.preferred_locations:
        profile.append(f"locations={', '.join(contact.preferred_locations)}")
    if contact.preferred_property_type:
        profile.append(f"type={contact.preferred_property_type.value}")
    if contact.bedrooms:
        profile.append(f"bedrooms={contact.bedrooms}")
    lines.append("Known about this person: " + ("; ".join(profile) if profile else "nothing yet"))
    if focus is not None:
        lines.append(
            f"Property in focus: {focus.ref_code} - {focus.title} (status {focus.status.value})"
        )
    return "\n".join(lines)
