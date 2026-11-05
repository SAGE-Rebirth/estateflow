from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.db import Db, find_one, get_db
from app.core.db import get_owned as get_owned
from app.core.security import decode_token
from app.models import Role, Tenant, User

bearer = HTTPBearer(auto_error=False)

DbDep = Annotated[Db, Depends(get_db)]

ACCESS_COOKIE = "ef_access"
REFRESH_COOKIE = "ef_refresh"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Principal:
    user: User
    tenant: Tenant

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def is_admin(self) -> bool:
        return self.user.role in (Role.owner, Role.admin)


def _check_origin(request: Request) -> None:
    """CSRF defence for cookie sessions: writes must come from one of our own frontends.

    Browsers always send Origin on cross-origin and non-GET requests; SameSite=Lax cookies
    already stop most cross-site posts, this closes the rest.
    """
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")):
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in get_settings().cors_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin not allowed")


async def get_principal(
    request: Request,
    db: DbDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is not None:
        token = creds.credentials
    elif cookie := request.cookies.get(ACCESS_COOKIE):
        token = cookie
        _check_origin(request)
    else:
        raise unauthorized
    try:
        payload = decode_token(token, "access")
        user_id = str(payload["sub"])
    except (jwt.PyJWTError, KeyError):
        raise unauthorized from None
    user = await find_one(db, User, {"_id": user_id})
    if user is None or not user.is_active or payload.get("ver", 0) != user.token_version:
        raise unauthorized
    tenant = await find_one(db, Tenant, {"_id": user.tenant_id})
    if tenant is None or not tenant.is_active:
        raise unauthorized
    return Principal(user=user, tenant=tenant)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def require_admin(principal: CurrentPrincipal) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return principal


AdminPrincipal = Annotated[Principal, Depends(require_admin)]
