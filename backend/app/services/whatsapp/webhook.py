"""Parse Meta WhatsApp Cloud API webhook payloads into flat events."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    phone_number_id: str
    wa_message_id: str
    wa_id: str  # sender's WhatsApp id (their number without "+")
    profile_name: str | None
    timestamp: datetime
    type: str
    text: str
    raw: dict[str, Any]
    media_id: str | None = None
    media_mime: str | None = None


@dataclass(frozen=True)
class StatusUpdate:
    phone_number_id: str
    wa_message_id: str
    status: str
    error: str | None


def _text_of(msg: dict[str, Any]) -> str:
    kind = msg.get("type")
    if kind == "text":
        return msg.get("text", {}).get("body", "")
    if kind == "button":
        return msg.get("button", {}).get("text", "")
    if kind == "interactive":
        inter = msg.get("interactive", {})
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return reply.get("title", "")
    if kind in ("image", "video", "document"):
        caption = msg.get(kind, {}).get("caption")
        return f"[{kind}] {caption}" if caption else f"[{kind} received]"
    if kind == "location":
        loc = msg.get("location", {})
        name = loc.get("name") or loc.get("address") or ""
        return f"[location] {name} ({loc.get('latitude')}, {loc.get('longitude')})".strip()
    if kind == "audio":
        return "[voice note]"
    return f"[{kind} message]"


MEDIA_TYPES = ("image", "audio", "document", "video", "sticker")


def _media(msg: dict[str, Any]) -> dict[str, Any]:
    kind = msg.get("type")
    return msg.get(kind, {}) if kind in MEDIA_TYPES else {}


def parse_webhook(payload: dict[str, Any]) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
            names = {
                c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])
            }
            for msg in value.get("messages", []):
                messages.append(
                    InboundMessage(
                        phone_number_id=phone_number_id,
                        wa_message_id=msg["id"],
                        wa_id=msg["from"],
                        profile_name=names.get(msg["from"]),
                        timestamp=datetime.fromtimestamp(int(msg.get("timestamp", 0)), UTC),
                        type=msg.get("type", "unknown"),
                        text=_text_of(msg),
                        raw=msg,
                        media_id=_media(msg).get("id"),
                        media_mime=_media(msg).get("mime_type"),
                    )
                )
            for st in value.get("statuses", []):
                errors = st.get("errors") or []
                statuses.append(
                    StatusUpdate(
                        phone_number_id=phone_number_id,
                        wa_message_id=st["id"],
                        status=st.get("status", ""),
                        error=errors[0].get("title") if errors else None,
                    )
                )
    return messages, statuses
