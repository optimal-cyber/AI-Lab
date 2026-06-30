"""Metering hardening — accurate pricing (no silent $0), estimated flagging, and
soft-budget alerts that actually fire (the stored soft_budget was previously dead)."""

from src import control, pricing

M = "sk-master"
MSG = [{"role": "user", "content": "hi"}]


# -- pricing: a table miss is priced + flagged, never silently free ----------

def test_known_model_is_authoritative():
    cost, estimated = pricing.price("gpt-4o", 1000, 1000)
    assert estimated is False
    assert cost == round(0.0025 + 0.010, 6)            # 1k in + 1k out


def test_unknown_model_uses_fallback_not_zero():
    cost, estimated = pricing.price("some-new-model-x", 1000, 1000)
    assert estimated is True
    assert cost > 0                                     # the old bug: silently $0
    assert pricing.known("some-new-model-x") is False


def test_cost_usd_backcompat_matches_price():
    assert pricing.cost_usd("claude-opus-4-8", 1000, 1000) == \
        pricing.price("claude-opus-4-8", 1000, 1000)[0]


# -- the estimated flag is persisted and summed for billing -----------------

def test_estimated_cost_summed_in_usage(store):
    t = store.create_team(alias="Acme")
    store.record_spend(request_id="r1", key_id=None, team_id=t["id"],
                       tenant_id=t["tenant_id"], model="gpt-4o",
                       prompt_tokens=0, completion_tokens=0, cost=0.10, estimated=False)
    store.record_spend(request_id="r2", key_id=None, team_id=t["id"],
                       tenant_id=t["tenant_id"], model="mystery",
                       prompt_tokens=0, completion_tokens=0, cost=0.50, estimated=True)
    u = store.tenant_usage(t["tenant_id"])
    assert u["total_cost"] == 0.60
    assert u["estimated_cost"] == 0.50                  # only the fallback-priced row


def test_unknown_model_call_flags_estimated_end_to_end(make_client):
    c, app = make_client(control_plane=True, master_key=M, upstream_key="sk-up")
    store = app.state.store
    team = store.create_team(alias="Acme")
    key = store.create_key(team_id=team["id"])          # no allow-list → any model
    c.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key["key"]},
           json={"model": "brand-new-model-9000", "messages": MSG})
    u = store.tenant_usage(team["tenant_id"])
    assert u["estimated_cost"] > 0 and u["estimated_cost"] == u["total_cost"]


# -- soft-budget alerts: fire once, on the crossing request -----------------

def test_soft_alert_fires_on_crossing_only():
    base = {"id": "team_1", "alias": "Acme", "max_budget": 1.00, "soft_budget": 0.80}
    assert control.soft_alerts({"team": {**base, "spend": 0.50}}, 0.10) == []   # below
    crossed = control.soft_alerts({"team": {**base, "spend": 0.70}}, 0.15)      # 0.70→0.85
    assert len(crossed) == 1 and crossed[0]["scope"] == "team"
    assert crossed[0]["soft_budget"] == 0.80
    assert control.soft_alerts({"team": {**base, "spend": 0.90}}, 0.05) == []   # already past


def test_soft_threshold_defaults_to_80pct_of_max():
    a = control.soft_alerts(
        {"team": {"id": "t", "alias": "A", "max_budget": 1.00, "spend": 0.79}}, 0.02)
    assert len(a) == 1 and a[0]["soft_budget"] == 0.80     # derived, no explicit soft


def test_soft_alert_emitted_end_to_end(make_client):
    c, app = make_client(control_plane=True, master_key=M, upstream_key="sk-up")
    store = app.state.store
    # cap $0.10 → soft line derived at $0.08; one opus call ($0.09) crosses it
    team = store.create_team(alias="Acme", max_budget=0.10)
    key = store.create_key(team_id=team["id"])
    c.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key["key"]},
           json={"model": "claude-opus-4-8", "messages": MSG})
    alerts = [r for r in app.state.auditor.rows if r.get("phase") == "budget_alert"]
    assert len(alerts) == 1 and alerts[0]["budget_scope"] == "team"
    assert alerts[0]["soft_budget"] == 0.08
