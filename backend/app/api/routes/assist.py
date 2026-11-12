from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal
from app.core.ratelimit import hit
from app.services.extract import ExtractionError, FormKind, extract_fields

router = APIRouter(tags=["assist"])


class ExtractIn(BaseModel):
    form: FormKind
    text: str = Field(min_length=10, max_length=8000)


class ExtractOut(BaseModel):
    fields: dict[str, Any]


@router.post("/assist/extract", response_model=ExtractOut)
async def extract(body: ExtractIn, p: CurrentPrincipal) -> ExtractOut:
    """Smart paste: fill a form from text copied from another source."""
    # Each call is a paid model request; a person pasting won't come near this.
    await hit("assist_extract", p.user.id, 60, 3600)
    try:
        return ExtractOut(fields=await extract_fields(body.form, body.text))
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
