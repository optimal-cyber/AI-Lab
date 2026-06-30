"""Customer portal (Phase 2) — per-tenant self-service, scoped to ONE tenant.

This is the "multiple customer logins" surface: a customer authenticates with a
PORTAL TOKEN (pt-…, distinct from an API key) and reaches a view limited to their
own tenant — their usage, invoices, and their own scoped API keys (which they can
mint/revoke themselves, within their tenant's tier). Every read/write is scoped to
the token's tenant_id; a token can never see or touch another tenant's data.

The operator master-key console (/admin) still sees everything; this is the
narrower, customer-facing door. True per-customer SSO / B2B IdP federation (each
org bringing its own Okta) is the next layer (roadmap G3) — this is the app-layer
multi-customer login it builds on.
"""

from __future__ import annotations

from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .store import Store


class PortalKeyCreate(BaseModel):
    alias: Optional[str] = None
    max_budget: Optional[float] = None
    rpm_limit: Optional[int] = None


def _unauth(msg: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"error": {
        "message": msg, "type": "authentication_error", "code": "portal_unauthorized"}})


def _ctx(request: Request) -> Tuple[Store, dict]:
    """Resolve (store, tenant) from the Bearer portal token, or raise 401."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"error": {
            "message": "Portal unavailable (control plane off).",
            "type": "service_unavailable"}})
    auth = request.headers.get("authorization", "")
    tok = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not tok:
        raise _unauth("Portal token required.")
    row = store.get_portal_token_by_plaintext(tok)
    if not row or not row["active"]:
        raise _unauth("Invalid or revoked portal token.")
    tenant = store.get_tenant(row["tenant_id"])
    if not tenant:
        raise _unauth("Portal token's tenant no longer exists.")
    return store, tenant


def build_router() -> APIRouter:
    r = APIRouter(prefix="/portal", tags=["portal"])

    @r.get("/me")
    async def me(request: Request):
        _, tenant = _ctx(request)
        return {"id": tenant["id"], "name": tenant["name"], "tier": tenant["tier"],
                "plan": tenant.get("plan"), "status": tenant["status"]}

    @r.get("/keys")
    async def keys(request: Request):
        store, tenant = _ctx(request)
        return {"data": store.list_keys(tenant_id=tenant["id"])}

    @r.post("/keys")
    async def create_key(body: PortalKeyCreate, request: Request):
        store, tenant = _ctx(request)
        if tenant["status"] != "active":
            raise HTTPException(status_code=403, detail={"error": {
                "message": "Organization is suspended; cannot mint keys.",
                "type": "permission_error", "code": "tenant_suspended"}})
        # Attach to the tenant's (default) team so the key inherits that team's
        # model allow-list — a customer can NEVER mint a key beyond their tier.
        teams = store.list_teams(tenant_id=tenant["id"])
        team = teams[0] if teams else store.create_team(
            alias=tenant["name"], tier=tenant["tier"], tenant_id=tenant["id"])
        key = store.create_key(team_id=team["id"], tenant_id=tenant["id"],
                               alias=body.alias, models=team["models"],
                               max_budget=body.max_budget, rpm_limit=body.rpm_limit)
        return key  # plaintext returned ONCE

    @r.delete("/keys/{key_id}")
    async def revoke_key(key_id: str, request: Request):
        store, tenant = _ctx(request)
        key = store.get_key(key_id)
        # Ownership check: a portal token may only revoke ITS OWN tenant's keys.
        # 404 (not 403) so a token can't even probe another tenant's key ids.
        if not key or key.get("tenant_id") != tenant["id"]:
            raise HTTPException(status_code=404, detail={"error": {
                "message": "key not found", "type": "invalid_request_error"}})
        store.revoke_key(key_id)
        return {"id": key_id, "revoked": True}

    @r.get("/usage")
    async def usage(request: Request, period: Optional[str] = None):
        store, tenant = _ctx(request)
        from . import billing
        try:
            since, until = billing.month_window(period)
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": {
                "message": "period must be 'YYYY-MM'", "type": "invalid_request_error"}})
        return store.tenant_usage(tenant["id"], since=since, until=until)

    @r.get("/invoice")
    async def invoice(request: Request, period: Optional[str] = None):
        store, tenant = _ctx(request)
        from . import billing
        try:
            since, until = billing.month_window(period)
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": {
                "message": "period must be 'YYYY-MM'", "type": "invalid_request_error"}})
        usage = store.tenant_usage(tenant["id"], since=since, until=until)
        plan = billing.resolve_plan(tenant.get("plan"))
        return billing.build_invoice(tenant=tenant, usage=usage, plan=plan,
                                     since=since, until=until)

    return r
