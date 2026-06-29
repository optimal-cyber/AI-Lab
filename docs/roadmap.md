# Roadmap — from single-tenant lab to a government-ready multi-cloud AI access layer

**North star:** one secure API / access layer that lets **approved
organizations** connect to **government-ready AI models and services** across
**multiple cloud providers**.

This document is the strategic arc *past* the built lab (Phases 0–6 in the
[README](../README.md#build-status)). It is sequencing + scope, not
implementation. Every phase lands behind one or more ADRs in
[`decisions.md`](decisions.md).

> **Status (config-ready):** G1–G5 have all landed as ADRs 014–019 +
> [`control-mapping.md`](control-mapping.md). The gov boundaries are wired but not
> live (no gov-cloud credentials in this lab) and remote TF state is not yet
> migrated — both are the gates that open before a first real tenant. The *design*
> is complete end-to-end; *going live* is provisioning, not more design. The
> concrete GovCloud provisioning path (account → creds → egress → flip) is in
> [`govcloud-go-live.md`](govcloud-go-live.md).

> **Honesty guardrail (applies to every phase, non-negotiable):** this stays a
> **reference architecture / pattern**. "Government-ready" describes a model
> *deployment posture* (served from a compliant boundary, with documented
> residency/retention), **not** a certification. The lab is not a FedRAMP/CMMC
> assessment boundary, holds no client data, and claims no attestation. Present
> "government-ready *design*," never "this lab is authorized."

---

## Where the lab is today (baseline)

| Axis | Today |
|---|---|
| Access layer | LiteLLM gateway — OpenAI-compatible `/v1` + SSO-gated Admin control plane ✅ |
| Tenancy | **Single operator** — one team (`AI-Lab`), one virtual key (`open-webui`) |
| Models | Commercial **OpenAI + Anthropic direct** (frontier lineup), one cloud's worth of creds |
| Cloud providers | **AWS only**; provider calls egress through the Squid allowlist |
| Services | 6 read-only compliance MCP tools (SAM.gov, Federal Register, NIST 800-53, POA&M, CMMC) ✅ |
| Controls | Cloudflare Access + Okta, NeMo guardrails (fail-closed), default-deny egress, structured audit ✅ |

The control architecture is already the right shape. The roadmap extends it along
three axes — **tenancy**, **multi-cloud**, **government-ready curation** — without
changing that shape.

---

## Phase G1 — Government-ready model catalog + posture metadata

*Foundational. The cheapest high-signal move, and a prerequisite for honestly
adding more clouds or gating tenants by tier.*

- **Goal:** every model the gateway exposes carries a machine-readable
  **compliance posture**, and "government-ready" becomes a defined tier rather
  than a vibe.
- **Scope / key components:**
  - A posture tag schema on each `model_list` entry (LiteLLM `model_info`):
    `{ boundary, cloud, region, fedramp, residency, retention, il }` —
    e.g. `gov` vs `dev/commercial`.
  - Add **Claude Platform on AWS** (Anthropic-operated, SigV4 + AWS IAM, US,
    **full API parity**) as the first government-ready Claude path — the
    strongest single move because it's full-parity and AWS-native, unlike the
    partner-operated boundaries below.
  - Keep commercial OpenAI/Anthropic-direct as an explicitly-labeled `dev` tier
    (non-gov boundary), so the distinction is visible, not implied.
- **Decisions (ADR):** the posture tag schema; what counts as a "government-ready
  boundary" and the evidence required to tag a model `gov`.
- **Done when:** the Admin UI / `litellm-config` shows a `gov` vs `dev` tier per
  model with documented posture, and a smoke test asserts a `gov`-tagged model is
  reachable through `/v1`.

## Phase G2 — Multi-cloud broker

*Depends on G1 (need the posture schema before adding boundaries honestly).*

- **Goal:** the gateway brokers across clouds; provider creds stay central; a
  logical model name resolves to the best government-ready deployment with
  failover.
- **Scope / key components:**
  - Wire additional providers in LiteLLM, each with creds in Secrets Manager,
    egress-allowlist entries, and a G1 posture tag:
    - **Amazon Bedrock** (GovCloud region for the gov boundary; `anthropic.`- and
      `openai.`-prefixed IDs — OpenAI GPT/GPT-OSS gained FedRAMP High + IL-4/5 there 2026-06-25),
    - **Azure OpenAI / Microsoft Foundry** (Azure Government),
    - **Google Vertex AI** (Assured Workloads).
  - A routing/failover policy: e.g. a logical `gov/claude-opus` that resolves
    across deployments by posture + health.
  - **Parity caveat to document, not hide:** Anthropic server-side tools and
    Managed Agents run only on Anthropic-direct and Claude Platform on AWS — *not*
    Bedrock/Vertex/Foundry. The gateway's MCP/government-service tool-routing is
    LiteLLM-side, so the *services* stay available cross-cloud even where
    provider-native agent features don't.
- **Decisions (ADR):** the provider set + per-cloud regions/boundaries; the
  routing/failover policy; per-cloud egress (revisit Squid vs the identity-aware
  Cloudflare Gateway path in [`phase2.md`](phase2.md)).
- **Done when:** one logical gov model resolves across ≥2 clouds with failover,
  each call attributed to its serving boundary in the audit row.

## Phase G3 — Multi-tenancy: approved organizations

*Can start once G1 defines the tiers an org's allow-list references.*

- **Goal:** each **approved organization** is an isolated tenant with its own
  keys, budgets, and model-tier allow-list, provisioned through a documented
  approval flow.
- **Scope / key components:**
  - **Org = LiteLLM team.** Per-org virtual keys, budgets, rate limits, and a
    model allow-list that selects which G1 posture tiers the org may reach.
  - **Identity:** Okta group → team mapping to start; document the B2B
    federation upgrade path (org brings its own IdP) as a later option.
  - **Onboarding/approval flow:** an "approved organization" runbook — vet →
    provision team + scoped keys + allowed tiers → issue credentials.
    IaC-first: model an org as a Terraform module so provisioning is a diff.
  - **Tenant isolation in audit:** add the team/org dimension to every log line;
    per-tenant log/spend views in the Admin UI.
- **Decisions (ADR):** the tenancy model + IdP federation strategy;
  **remote Terraform state (S3 + DynamoDB)** becomes mandatory here — supersede
  [ADR-001](decisions.md) before real orgs exist.
- **Done when:** two distinct orgs reach the gateway with isolated keys/budgets,
  each can reach only its allowed tiers, and audit rows segregate cleanly by org.

## Phase G4 — Tenant-scoped governance

*Depends on G3.*

- **Goal:** governance policy attaches to the tenant/tier, not just globally.
- **Scope:** per-tier guardrail policy (gov tenants get stricter egress +
  mandatory output rail + residency enforcement); per-tenant spend caps +
  alerting; approval gates for sensitive tiers.
- **Done when:** a gov-tier tenant demonstrably gets stricter enforcement than a
  dev-tier tenant, shown in the decision logs.

## Phase G5 — Evidence & attestation-readiness

*Continuous; matures alongside G1–G4.*

- **Goal:** the gateway's control story is documented and evidenced per tenant —
  the artifact a 3PAO would actually read.
- **Scope:** map controls to NIST 800-53 / CMMC / FedRAMP; produce the
  per-tenant evidence shapes (audit logs joined by `request_id`); SSP-style
  control-inheritance write-up.
- **Honesty:** "evidences how the controls *would* map," not "authorized."

---

## Sequencing

```
G1 (catalog + posture, incl. Claude Platform on AWS)   ← start here (foundational, quick win)
 ├── G2 (multi-cloud broker)        depends on G1
 └── G3 (approved-org tenancy)      depends on G1 tiers; can run parallel to G2
          └── G4 (tenant governance)   depends on G3
G5 (evidence/attestation-readiness)  continuous across all
```

**Recommended first build:** the thinnest valuable vertical slice of **G1** —
the posture-tag schema plus **Claude Platform on AWS** as the first
government-ready Claude path, with commercial endpoints relabeled `dev`. It's
mostly config + metadata + one ADR, it makes "government-ready" concrete, and it
unblocks both G2 and G3.

## Cross-cutting guardrails (every phase)

- Reference architecture / pattern — **not** an attestation or assessment
  boundary; no client data.
- "Government-ready" = served from a documented compliant boundary; the tag is a
  claim about the **deployment**, not a certification.
- Remote TF state is a hard prerequisite for multi-tenant (G3) — supersede
  [ADR-001](decisions.md).
- Egress grows per cloud — revisit Squid vs identity-aware Cloudflare Gateway
  ([`phase2.md`](phase2.md)) as boundaries multiply.
