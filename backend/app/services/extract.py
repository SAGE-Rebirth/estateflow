"""Smart paste: turn free text copied from elsewhere (a WhatsApp forward, a portal listing,
an email) into form fields, using Gemini's structured output."""

import re
from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.models import LeadSource, ListingType, PropertyStatus, PropertyType
from app.services.gemini import gemini_client

FormKind = Literal["property", "contact"]


class PropertyFields(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    listing_type: ListingType | None = None
    property_type: PropertyType | None = None
    status: PropertyStatus | None = None
    price: float | None = Field(None, ge=0)
    area_sqft: float | None = Field(None, ge=0)
    bedrooms: int | None = Field(None, ge=0, le=50)
    bathrooms: int | None = Field(None, ge=0, le=50)
    locality: str | None = Field(None, max_length=120)
    city: str | None = Field(None, max_length=120)
    address: str | None = Field(None, max_length=300)
    amenities: list[str] | None = None


class ContactFields(BaseModel):
    name: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=30)
    email: str | None = Field(None, max_length=200)
    source: LeadSource | None = None


SCHEMAS: dict[str, type[BaseModel]] = {"property": PropertyFields, "contact": ContactFields}

INSTRUCTIONS = {
    "property": (
        "Extract a real estate listing from the text for an Indian property CRM form. "
        "Fill only what the text states; leave everything else null. Rules: price is the full "
        "amount in rupees as a plain number (95 lakh = 9500000, 1.2 crore = 12000000; for "
        "rentals the monthly rent). area_sqft in square feet (convert sq m × 10.764, sq yd × 9). "
        "'3BHK' means bedrooms 3. title: a short listing headline (max 80 chars) built from the "
        "text, e.g. '3BHK lake-facing apartment in Hebbal'. description: the useful details "
        "in clean prose (floor, facing, possession, parking, furnishing), not repeating price. "
        "city: the official current name (Bengaluru, Mumbai, Gurugram). amenities: short "
        "lowercase names like 'gym', 'pool', 'covered parking'. status only if the text says "
        "sold, rented, under offer or similar."
    ),
    "contact": (
        "Extract one sales lead's contact details for an Indian real estate CRM. Fill only "
        "what the text states. phone: keep the digits and leading + as written. source: "
        "'referral' if someone referred them, 'website' if they came from a site or portal, "
        "'whatsapp' if it's a WhatsApp chat, 'walk_in' if they visited the office."
    ),
}


# Sellers paste in English, Hindi (Devanagari) or Hinglish (Hindi in Latin letters).
LANGUAGE_NOTE = (
    " The text may be in English, Hindi or Hinglish (e.g. 'do BHK flat kiraye pe, 25 hazaar'):"
    " understand all three. Numbers and choices are always normalised (25 hazaar = 25000,"
    " kiraya = rent, bechna = sale). city, locality and amenities are always in English"
    " letters so search works (पुणे = Pune, हिंजेवाडी = Hinjewadi, पार्किंग = parking). Keep"
    " people's names and addresses as written. Write title and description in the language"
    " the text is mostly in."
)


class ExtractionError(Exception):
    pass


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def _ground_contact(fields: dict[str, Any], text: str) -> dict[str, Any]:
    """Emails and phone numbers must be copied exactly, and small models sometimes garble
    them. Keep the model's value only if it's literally in the text; else take it from there."""
    emails = EMAIL.findall(text)
    if (email := fields.get("email")) and email.lower() not in text.lower():
        fields.pop("email")
    if "email" not in fields and emails:
        fields["email"] = emails[0]
    digits = re.sub(r"\D", "", text)
    if (phone := fields.get("phone")) and re.sub(r"\D", "", phone) not in digits:
        fields.pop("phone")
    if "phone" not in fields and (phones := PHONE.findall(text)):
        fields["phone"] = phones[0].strip()
    return fields


async def extract_fields(kind: FormKind, text: str) -> dict[str, Any]:
    """Fields found in `text`, with nulls dropped. The text is untrusted: the schema limits
    the output to plain form values, which the user reviews before saving."""
    s = get_settings()
    if not s.gemini_api_key:
        raise ExtractionError("Smart paste needs GEMINI_API_KEY.")
    model = SCHEMAS[kind]
    try:
        response = await gemini_client().aio.models.generate_content(
            model=s.gemini_extract_model,
            contents=[
                f"{INSTRUCTIONS[kind]}{LANGUAGE_NOTE}\n\n<pasted_text>\n{text}\n</pasted_text>"
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=model.model_json_schema(),
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                max_output_tokens=2048,
                temperature=0,
            ),
        )
        fields = model.model_validate_json(response.text or "{}")
    except ValidationError as exc:
        raise ExtractionError("Couldn't read details from that text.") from exc
    except Exception as exc:
        raise ExtractionError("The AI service is unavailable right now.") from exc
    found = fields.model_dump(mode="json", exclude_none=True)
    return _ground_contact(found, text) if kind == "contact" else found
