"""Customer portal — per-tenant self-service login. Every read/write is scoped to
the portal token's tenant; a token can never see or touch another tenant's data."""

M = "sk-master"
MSG = [{"role": "user", "content": "hi"}]


def _tenant_with_token(app, name="Acme", tier="dev"):
    store = app.state.store
    tenant = store.create_tenant(name=name, tier=tier)
    team = store.create_team(alias=name, tier=tier, tenant_id=tenant["id"])
    tok = store.create_portal_token(tenant_id=tenant["id"])["token"]
    return tenant, team, tok


def _h(tok):
    return {"Authorization": "Bearer " + tok}


# -- auth --------------------------------------------------------------------

def test_portal_requires_valid_token(make_client):
    c, _ = make_client(control_plane=True, master_key=M)
    assert c.get("/portal/me").status_code == 401
    assert c.get("/portal/me", headers=_h("pt-nope")).status_code == 401


def test_portal_me_scoped_to_token_tenant(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    tenant, _, tok = _tenant_with_token(app, "Acme")
    r = c.get("/portal/me", headers=_h(tok))
    assert r.status_code == 200 and r.json()["id"] == tenant["id"] and r.json()["name"] == "Acme"


def test_revoked_portal_token_rejected(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    tenant, _, tok = _tenant_with_token(app)
    ptid = app.state.store.list_portal_tokens(tenant["id"])[0]["id"]
    app.state.store.revoke_portal_token(ptid)
    assert c.get("/portal/me", headers=_h(tok)).status_code == 401


# -- isolation (the security-critical part) ----------------------------------

def test_portal_keys_isolated_to_tenant(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    store = app.state.store
    _, teama, toka = _tenant_with_token(app, "A")
    _, teamb, _ = _tenant_with_token(app, "B")
    ka = store.create_key(team_id=teama["id"])
    kb = store.create_key(team_id=teamb["id"])

    a_keys = c.get("/portal/keys", headers=_h(toka)).json()["data"]
    assert [k["id"] for k in a_keys] == [ka["id"]]            # A sees only A's key

    # A cannot revoke B's key — 404 (don't even reveal it exists)
    assert c.delete(f"/portal/keys/{kb['id']}", headers=_h(toka)).status_code == 404
    assert store.get_key(kb["id"])["active"] is True          # untouched


# -- self-service keys -------------------------------------------------------

def test_portal_self_service_mint_and_revoke(make_client):
    c, app = make_client(control_plane=True, master_key=M, upstream_key="sk-up")
    tenant, _, tok = _tenant_with_token(app, "Acme")
    k = c.post("/portal/keys", headers=_h(tok), json={"alias": "my-ci", "rpm_limit": 30}).json()
    assert k["key"].startswith("sk-") and k["tenant_id"] == tenant["id"]
    # the self-minted key actually works through the gateway
    assert c.post("/v1/chat/completions", headers=_h(k["key"]),
                  json={"model": "claude-opus-4-8", "messages": MSG}).status_code == 200
    # and the customer can revoke it themselves
    assert c.delete(f"/portal/keys/{k['id']}", headers=_h(tok)).status_code == 200
    assert app.state.store.get_key(k["id"])["active"] is False


def test_portal_minted_key_cannot_exceed_team_tier(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    store = app.state.store
    tenant = store.create_tenant(name="Gov", tier="gov")
    store.create_team(alias="Gov", tier="gov", tenant_id=tenant["id"],
                      models=["gov/claude-opus-4-8"])
    tok = store.create_portal_token(tenant_id=tenant["id"])["token"]
    k = c.post("/portal/keys", headers=_h(tok), json={"alias": "x"}).json()
    assert k["models"] == ["gov/claude-opus-4-8"]            # inherits team's allow-list


def test_suspended_tenant_cannot_mint(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    tenant, _, tok = _tenant_with_token(app)
    app.state.store.set_tenant_status(tenant["id"], "suspended")
    r = c.post("/portal/keys", headers=_h(tok), json={"alias": "x"})
    assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "tenant_suspended"


# -- usage + invoice, scoped to the token's tenant ---------------------------

def test_portal_usage_and_invoice_scoped(make_client):
    c, app = make_client(control_plane=True, master_key=M, upstream_key="sk-up")
    store = app.state.store
    tenant, team, tok = _tenant_with_token(app, "Acme")
    key = store.create_key(team_id=team["id"])
    c.post("/v1/chat/completions", headers=_h(key["key"]),
           json={"model": "claude-opus-4-8", "messages": MSG})    # $0.09
    u = c.get("/portal/usage", headers=_h(tok)).json()
    assert u["tenant_id"] == tenant["id"] and u["total_cost"] == 0.09
    inv = c.get("/portal/invoice", headers=_h(tok)).json()
    assert inv["tenant_id"] == tenant["id"] and inv["subtotal_usage_raw"] == 0.09


# -- admin issues portal tokens ----------------------------------------------

def test_admin_issues_and_lists_portal_tokens(make_client):
    c, app = make_client(control_plane=True, master_key=M)
    h = {"Authorization": "Bearer " + M}
    t = app.state.store.create_tenant(name="Acme")
    r = c.post(f"/admin/tenants/{t['id']}/portal-tokens", headers=h)
    assert r.status_code == 200 and r.json()["token"].startswith("pt-")
    lst = c.get(f"/admin/tenants/{t['id']}/portal-tokens", headers=h).json()["data"]
    assert len(lst) == 1 and "token_hash" not in lst[0] and "token" not in lst[0]
