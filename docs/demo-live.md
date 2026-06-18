# Demo the live gateway

How to demo the **live private gateway** end-to-end with the current config
(through G1–G5). There is **no public demo URL** by design — the gateway has zero
public ingress (ADR-002); it is reached only through Cloudflare Access + Okta, or
from an SSM shell on the host. This runbook covers pushing the latest config to
the running stack, then the two demo surfaces: the **Admin control plane** and the
**OpenAI-compatible endpoint**.

> Assumes the stack is already deployed (README Deploy order, Phases 0–6). This is
> a redeploy-of-config + demo, not a from-scratch deploy. Reference design — no
> client data; the gov tiers are config-ready, not live (no gov-cloud creds).

## Prerequisites

- AWS CLI + SSM access to the lab account (no SSH — ADR-006).
- Provider keys seeded in Secrets Manager (`lab/*`): `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY` (for live completions), `SAM_GOV_API_KEY` (for the SAM.gov
  demo). Seeded into the tmpfs `.env` by `secrets-bootstrap.sh`.
- An admin Okta user in `lab-admins` (for the Admin UI), with MFA + WARP.

## Part A — push the G1–G5 config to the running stack

The repo lives on the host at `/opt/ai-lab/repo`. `litellm` is an image with the
config **mounted** (recreate to reload); `compliance-mcp` and `nemo` are **built**
on the host (the Federal Register tool is a code change → rebuild).

```bash
# SSM into gateway-host, then:
sudo git -C /opt/ai-lab/repo pull           # GitHub redirects the old AI-Lab URL
cd /opt/ai-lab/repo/docker/gateway-host

# Rebuild the MCP image (new federal_register_search tool) + recreate it:
sudo docker compose up -d --build compliance-mcp
# Recreate LiteLLM so it re-reads the mounted litellm-config.yaml (new model_list
# posture tiers, gov entries, router_settings, alerting):
sudo docker compose up -d --force-recreate litellm
# (nemo-guardrails unchanged in G1–G5; no rebuild needed.)
```

**Egress for `federal_register_search`** (optional — only if you'll demo it): add
`.federalregister.gov` to the live Squid allowlist. Quick path (no instance
replace) — SSM into the **proxy** host:

```bash
echo ".federalregister.gov" | sudo tee -a /etc/squid/allowlist.txt
sudo squid -k reconfigure          # hot-reload the ACL, no restart
```

The durable path is `terraform apply` (the allowlist is rendered into the proxy
user-data; note an apply may replace the proxy instance). The G2 gov endpoints
(`.aiplatform.googleapis.com`, `.openai.azure.us`, GovCloud Bedrock) are inert
without creds, so skip them for the demo.

**Verify health** before demoing:

```bash
cd /opt/ai-lab/repo && ./scripts/run-smoke-tests.sh   # containers + egress all green
```

## Part B — demo the control plane (the screen that *is* the gateway)

> **Branding note.** The off-brand LiteLLM Swagger/ReDoc pages at `/` and `/redoc`
> are disabled (`NO_DOCS`/`NO_REDOC` on the litellm container), and the Admin UI
> carries the Optimal Horizon logo (`ui_theme_config`). To make the bare root land
> on the control plane, add a **Cloudflare Single Redirect** (Rules → Redirect
> Rules) on `gateway.optimallabs.io`: when URI path equals `/`, 302 to `/ui`.
> (The OSS UI still shows the "LiteLLM" wordmark in places — removing it entirely
> is a LiteLLM Enterprise feature.)

1. Browser → **`https://gateway.optimallabs.io/ui`**.
2. Cloudflare Access → Okta + MFA (must be `lab-admins`, US geo, WARP).
3. Walk the LiteLLM Admin:
   - **Models** — the `dev` tier (`gpt-4o`, `claude-*`) and the `gov` tier
     (`gov/claude-opus-4-8`, `gov/gpt-4o`) both registered, with posture
     (`model_info`).
   - **Virtual keys / Teams** — per-team budgets + live spend.
   - **Logs** — every call with identity, model, cost, tokens; guardrail blocks
     show as `$0` / `0-token` **Failure** rows (the provider was never called).

This — not the chat window — is the screen to present as "the gateway."

## Part C — demo the OpenAI-compatible endpoint (the API *is* the gateway)

From an SSM shell on **gateway-host** (the endpoint is private, on `:4000`):

```bash
# Read the master key from the tmpfs .env (or use a virtual key):
export LITELLM_KEY=$(sudo grep -oP 'LITELLM_MASTER_KEY=\K.*' /run/ai-lab/gateway.env)
export GATEWAY_URL=http://127.0.0.1:4000

cd /opt/ai-lab/repo && ./scripts/run-smoke-tests.sh
```

`T-GW-1..5` are the live proof: one key reaches `gpt-4o` **and**
`claude-opus-4-8` (T-GW-1/2), an injection is **blocked pre-call** (T-GW-3, no
spend), a **SAM.gov** lookup routes through `/v1` (T-GW-4), and a `gov`-tier model
is **registered** (T-GW-5; the gov *call* SKIPs — no gov-cloud creds, as expected).
For the bare "only the base_url changed" curl, see the README gateway section.

## Part D — (optional) demo tenancy

```bash
export LITELLM_MASTER_KEY=$(sudo grep -oP 'LITELLM_MASTER_KEY=\K.*' /run/ai-lab/gateway.env)

# dry-run, then apply — a dev tenant and a gov tenant (gov needs an approver):
./scripts/provision-org.sh --org "Demo Co" --tier dev --budget 50 --apply
./scripts/provision-org.sh --org "Acme Defense" --tier gov --approved-by "ryan" --apply
```

Show the two teams + keys in the Admin UI, then prove tier gating (T-TEN-1 /
T-GOV-1): the gov key reaches `gov/*` only; a `dev` model call with it is rejected.

## Part E — cleanup

Revoke the demo keys/teams in the Admin UI (or `POST /key/delete`,
`/team/delete`). Spend history stays in the audit log.

## What you will NOT see (by design)

- **No public URL.** The gateway is private; only an approved Okta user (Admin UI)
  or an in-VPC/SSM caller (endpoint) reaches it.
- **No gov-tier completions.** The gov boundaries are config-ready, not live —
  `gov/*` models register and carry posture, but a live call needs gov-cloud
  credentials (roadmap go-live). T-GW-5's call SKIPs; that's the expected result.
