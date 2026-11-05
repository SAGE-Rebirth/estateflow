from typing import Annotated

import structlog
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from app.core.config import get_settings
from app.core.queue import enqueue
from app.services.whatsapp.client import verify_signature
from app.services.whatsapp.webhook import parse_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger()


@router.get("/whatsapp")
async def verify(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta's subscription handshake."""
    if mode == "subscribe" and token == get_settings().whatsapp_verify_token and challenge:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")


@router.post("/whatsapp")
async def receive(
    request: Request,
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, str]:
    """Verify, enqueue, return 200 fast. Meta retries on slow or failed responses."""
    raw = await request.body()
    if not verify_signature(raw, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    payload = await request.json()
    messages, statuses = parse_webhook(payload)
    for m in messages:
        # job_id = wamid: arq drops duplicate enqueues while the job is known.
        await enqueue(
            "process_inbound_message",
            m.phone_number_id,
            m.raw,
            m.profile_name,
            job_id=f"wa:{m.wa_message_id}",
        )
    for s in statuses:
        await enqueue("process_status_update", s.wa_message_id, s.status, s.error)
    log.info("whatsapp_webhook", messages=len(messages), statuses=len(statuses))
    return {"status": "ok"}
