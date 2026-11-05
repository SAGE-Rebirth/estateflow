import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo.errors import DuplicateKeyError

from app.api.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    AdminPrincipal,
    CurrentPrincipal,
    DbDep,
    get_owned,
)
from app.core.config import get_settings
from app.core.db import coll, find, find_one, insert, save
from app.core.ratelimit import RateLimit, hit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.models import AvailabilityRule, Role, Tenant, User
from app.schemas.auth import (
    LoginIn,
    MeOut,
    PasswordChangeIn,
    RefreshIn,
    SessionOut,
    SignupIn,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
    WhatsAppConfigIn,
)

router = APIRouter(tags=["auth"])

TOKEN_MODE_HEADER = "x-auth-mode"


def _issue(request: Request, response: Response, user: User) -> SessionOut:
    """Start a session: httpOnly cookies for browsers; tokens in the body only for API
    clients that ask with `X-Auth-Mode: token` (so page scripts never see a credential)."""
    s = get_settings()
    access = create_access_token(user.id, user.tenant_id, user.role.value, user.token_version)
    refresh = create_refresh_token(user.id, user.tenant_id, user.token_version)
    common = {
        "httponly": True,
        "secure": s.cookie_secure,
        "samesite": "lax",
        "domain": s.cookie_domain,
    }
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=s.access_token_minutes * 60, path="/", **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=s.refresh_token_days * 86400,
        path=f"{s.api_prefix}/auth",
        **common,
    )
    if request.headers.get(TOKEN_MODE_HEADER) == "token":
        return SessionOut(access_token=access, refresh_token=refresh)
    return SessionOut()


def _clear(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=s.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE, path=f"{s.api_prefix}/auth", domain=s.cookie_domain)


def default_availability() -> list[AvailabilityRule]:
    # Mon–Sat, 10:00–18:00, hourly slots; editable from the dashboard.
    return [
        AvailabilityRule(weekday=d, start_time="10:00", end_time="18:00", slot_minutes=60)
        for d in range(6)
    ]


@router.post(
    "/auth/signup",
    response_model=SessionOut,
    status_code=201,
    dependencies=[Depends(RateLimit("signup", 5, 3600))],
)
async def signup(body: SignupIn, request: Request, response: Response, db: DbDep) -> SessionOut:
    email = body.email.lower()
    if await find_one(db, User, {"email": email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or business URL already taken")
    tenant = Tenant(
        name=body.business_name,
        slug=body.slug,
        timezone=body.timezone,
        currency=body.currency.upper(),
        contact_email=email,
    )
    try:
        await insert(db, tenant)
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or business URL already taken"
        ) from None
    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=Role.owner,
        availability=default_availability(),
    )
    try:
        await insert(db, user)
    except DuplicateKeyError:
        await coll(db, Tenant).delete_one({"_id": tenant.id})
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or business URL already taken"
        ) from None
    return _issue(request, response, user)


@router.post(
    "/auth/login",
    response_model=SessionOut,
    dependencies=[Depends(RateLimit("login_ip", 30, 900))],
)
async def login(body: LoginIn, request: Request, response: Response, db: DbDep) -> SessionOut:
    # Per-account limit stops password guessing spread across many IPs.
    await hit("login_email", body.email, 10, 900)
    user = await find_one(db, User, {"email": body.email.lower()})
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _issue(request, response, user)


@router.post(
    "/auth/refresh",
    response_model=SessionOut,
    dependencies=[Depends(RateLimit("refresh", 60, 900))],
)
async def refresh(
    request: Request, response: Response, db: DbDep, body: RefreshIn | None = None
) -> SessionOut:
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    user = None
    if token:
        try:
            payload = decode_token(token, "refresh")
            user = await find_one(db, User, {"_id": str(payload["sub"])})
            if user is not None and payload.get("ver", 0) != user.token_version:
                user = None
        except (jwt.PyJWTError, KeyError):
            user = None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return _issue(request, response, user)


@router.post("/auth/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    _clear(response)
    return response


@router.post("/auth/logout-all", status_code=204)
async def logout_everywhere(p: CurrentPrincipal, db: DbDep) -> Response:
    """Revoke every session for this user, on every device."""
    await coll(db, User).update_one({"_id": p.user.id}, {"$inc": {"token_version": 1}})
    response = Response(status_code=204)
    _clear(response)
    return response


@router.post("/auth/password", response_model=SessionOut)
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    p: CurrentPrincipal,
    db: DbDep,
) -> SessionOut:
    await hit("password_change", p.user.id, 10, 3600)
    user = p.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # signs out other devices
    await save(db, user, "password_hash", "token_version")
    return _issue(request, response, user)


@router.get("/auth/me", response_model=MeOut)
async def me(p: CurrentPrincipal) -> MeOut:
    return MeOut(user=UserOut.model_validate(p.user), tenant=TenantOut.model_validate(p.tenant))


# --- Team -------------------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut], tags=["team"])
async def list_users(p: CurrentPrincipal, db: DbDep) -> list[User]:
    return await find(db, User, {"tenant_id": p.tenant_id}, sort=[("full_name", 1)])


@router.post("/users", response_model=UserOut, status_code=201, tags=["team"])
async def create_user(body: UserCreate, p: AdminPrincipal, db: DbDep) -> User:
    if body.role == Role.owner and p.user.role != Role.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can add owners")
    user = User(
        tenant_id=p.tenant_id,
        email=body.email.lower(),
        full_name=body.full_name,
        phone=body.phone,
        role=body.role,
        password_hash=hash_password(body.password),
        availability=default_availability(),
    )
    try:
        await insert(db, user)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use") from None
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["team"])
async def update_user(user_id: str, body: UserUpdate, p: AdminPrincipal, db: DbDep) -> User:
    user = await get_owned(db, User, user_id, p.tenant_id)
    data = body.model_dump(exclude_unset=True)
    # Owner is above admin: only an owner may edit an owner or grant the owner role.
    if (user.role == Role.owner or data.get("role") == Role.owner) and p.user.role != Role.owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the owner can edit owners or grant the owner role"
        )
    if user.id == p.user.id and (data.get("is_active") is False or "role" in data):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't demote or deactivate yourself")
    for k, v in data.items():
        setattr(user, k, v)
    if data.get("is_active") is False:
        user.token_version += 1  # deactivation ends their sessions immediately
        data["token_version"] = user.token_version
    if data:
        await save(db, user, *data)
    return user


# --- Tenant settings --------------------------------------------------------------------


@router.get("/tenant", response_model=TenantOut, tags=["settings"])
async def get_tenant(p: CurrentPrincipal) -> Tenant:
    return p.tenant


@router.patch("/tenant", response_model=TenantOut, tags=["settings"])
async def update_tenant(body: TenantUpdate, p: AdminPrincipal, db: DbDep) -> Tenant:
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p.tenant, k, v.upper() if k == "currency" else v)
    if data:
        await save(db, p.tenant, *data)
    return p.tenant


@router.put("/tenant/whatsapp", response_model=TenantOut, tags=["settings"])
async def configure_whatsapp(body: WhatsAppConfigIn, p: AdminPrincipal, db: DbDep) -> Tenant:
    t = p.tenant
    t.whatsapp_phone_number_id = body.phone_number_id
    t.whatsapp_display_number = body.display_number
    t.whatsapp_access_token_enc = encrypt_secret(body.access_token)
    try:
        await save(
            db,
            t,
            "whatsapp_phone_number_id",
            "whatsapp_display_number",
            "whatsapp_access_token_enc",
        )
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This WhatsApp number is linked to another account"
        ) from None
    return t
