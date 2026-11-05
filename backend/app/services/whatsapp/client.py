import hashlib
import hmac
from typing import Any

import httpx
import structlog

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import Tenant

log = structlog.get_logger()

# WhatsApp caps a text body at 4096 characters.
MAX_TEXT = 4096


class WhatsAppError(Exception):
    pass


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


class WhatsAppClient:
    def __init__(self, tenant: Tenant, http: httpx.AsyncClient | None = None) -> None:
        if not tenant.whatsapp_phone_number_id or not tenant.whatsapp_access_token_enc:
            raise WhatsAppError(f"WhatsApp is not configured for tenant {tenant.slug}")
        s = get_settings()
        self._graph = f"{s.whatsapp_graph_base}/{s.whatsapp_api_version}"
        self._url = f"{self._graph}/{tenant.whatsapp_phone_number_id}/messages"
        self._token = decrypt_secret(tenant.whatsapp_access_token_enc)
        self._http = http

    async def _post(self, payload: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._token}"}
        body = {"messaging_product": "whatsapp", **payload}
        if self._http is not None:
            resp = await self._http.post(self._url, json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=20) as http:
                resp = await http.post(self._url, json=body, headers=headers)
        if resp.status_code >= 400:
            log.warning("whatsapp_send_failed", status=resp.status_code, body=resp.text[:500])
            raise WhatsAppError(resp.text[:500])
        data = resp.json()
        messages = data.get("messages") or [{}]
        return messages[0].get("id", "")

    async def send_text(self, to: str, body: str) -> str:
        return await self._post(
            {
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": True, "body": body[:MAX_TEXT]},
            }
        )

    async def send_template(
        self, to: str, name: str, language: str, body_params: list[str] | None = None
    ) -> str:
        """Template messages are required to message a user outside the 24h service window."""
        template: dict[str, Any] = {"name": name, "language": {"code": language}}
        if body_params:
            template["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}
            ]
        return await self._post({"to": to, "type": "template", "template": template})

    async def send_image(self, to: str, link: str, caption: str | None = None) -> str:
        """`link` must be publicly reachable by Meta's servers (our /media URLs in prod)."""
        image: dict[str, Any] = {"link": link}
        if caption:
            image["caption"] = caption[:1024]
        return await self._post({"to": to, "type": "image", "image": image})

    async def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Fetch inbound media: resolve the media id to a short-lived URL, then download."""
        limit = get_settings().max_inbound_media_mb * 1024 * 1024
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30) as http:
            meta = await (self._http or http).get(f"{self._graph}/{media_id}", headers=headers)
            if meta.status_code >= 400:
                raise WhatsAppError(f"media lookup failed: {meta.text[:200]}")
            info = meta.json()
            if int(info.get("file_size") or 0) > limit:
                raise WhatsAppError("media too large")
            resp = await (self._http or http).get(info["url"], headers=headers)
            if resp.status_code >= 400:
                raise WhatsAppError(f"media download failed: {resp.status_code}")
            return resp.content[: limit + 1], info.get("mime_type", "application/octet-stream")

    async def mark_read(self, wa_message_id: str) -> None:
        try:
            await self._post({"status": "read", "message_id": wa_message_id})
        except WhatsAppError:
            pass  # read receipts are best-effort
