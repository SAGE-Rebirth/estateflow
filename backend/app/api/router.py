from fastapi import APIRouter

from app.api.routes import (
    assist,
    auth,
    crm,
    dashboard,
    market,
    properties,
    public,
    scheduling,
    webhooks,
)

api_router = APIRouter()
for module in (auth, properties, crm, scheduling, dashboard, public, market, webhooks, assist):
    api_router.include_router(module.router)
