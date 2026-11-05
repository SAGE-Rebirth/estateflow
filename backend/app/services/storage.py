"""Local-disk file storage with a public area (listing photos, served at /media) and a
private area (brochures, buyers' WhatsApp media) that is only reachable via authenticated
endpoints. Paths are stored relative to UPLOAD_DIR, prefixed with the area."""

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.models import new_id

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
DOC_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
MEDIA_EXT = {
    **IMAGE_TYPES,
    **DOC_TYPES,
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "video/mp4": ".mp4",
}


def root() -> Path:
    return Path(get_settings().upload_dir)


def public_dir() -> Path:
    return root() / "public"


def save_bytes(data: bytes, tenant_id: str, ext: str, *, private: bool) -> str:
    rel = Path("private" if private else "public") / tenant_id / f"{new_id()}{ext}"
    dest = root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return rel.as_posix()


async def save_upload(
    file: UploadFile, tenant_id: str, allowed: dict[str, str], *, private: bool
) -> str:
    s = get_settings()
    if file.content_type not in allowed:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type {file.content_type}"
        )
    limit = s.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Max {s.max_upload_mb} MB")
    return save_bytes(data, tenant_id, allowed[file.content_type], private=private)


def public_url(rel_path: str) -> str:
    return f"{get_settings().public_base_url}/media/{rel_path.removeprefix('public/')}"


def resolve(rel_path: str) -> Path:
    path = (root() / rel_path).resolve()
    if not path.is_relative_to(root().resolve()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return path


def delete_file(rel_path: str | None) -> None:
    if rel_path:
        resolve(rel_path).unlink(missing_ok=True)
