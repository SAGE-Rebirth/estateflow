from pydantic import BaseModel, EmailStr, Field

from app.models import Role
from app.schemas.common import Out


class SignupIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{1,78}[a-z0-9])$")
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    timezone: str = "Asia/Kolkata"
    currency: str = Field(default="INR", min_length=3, max_length=3)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str | None = None


class SessionOut(BaseModel):
    """Tokens are only included for API clients that request token mode."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(Out):
    id: str
    email: str
    full_name: str
    phone: str | None
    role: Role
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = None
    role: Role = Role.agent


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role: Role | None = None
    is_active: bool | None = None


class TenantOut(Out):
    id: str
    name: str
    slug: str
    timezone: str
    currency: str
    contact_email: str | None
    whatsapp_phone_number_id: str | None
    whatsapp_display_number: str | None
    bot_settings: dict
    list_on_marketplace: bool


class TenantUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contact_email: EmailStr | None = None
    bot_settings: dict | None = None
    list_on_marketplace: bool | None = None


class WhatsAppConfigIn(BaseModel):
    phone_number_id: str
    display_number: str
    access_token: str


class MeOut(BaseModel):
    user: UserOut
    tenant: TenantOut
