# GovCloud go-live — the path from "registered" to "live"

The honest answer to *"how far is this from real?"* for the **government-ready
(`gov`) tier** — and specifically the OpenAI GPT / GPT-OSS models on Amazon Bedrock
in AWS GovCloud (US), [authorized at FedRAMP High + DoD IL-4/5 on
2026-06-25](https://aws.amazon.com/about-aws/whats-new/2026/06/addl-bedrock-model-fedramp-il-5-govcloud/).

> **Status:** the `gov` tier is **registered, not live**. The models appear in
> `/v1/models` tagged `access_tier=gov, fedramp=high, il="IL4/IL5"` and a `gov`
> tenant can be issued a scoped key — but a *live call* fails until a GovCloud
> account, credentials, and egress exist. This stays a **deployment-posture** claim,
> never an authorization or attestation (see [`roadmap.md`](roadmap.md) honesty
> guardrail).

## Where we are

- **Today's boundary:** commercial AWS, `us-east-1` — a defensible **FedRAMP
  Moderate-aligned** posture. All live inference in the demo runs here.
- **The gap:** AWS GovCloud (US) is a *separate partition*. A commercial account and
  its IAM roles **cannot reach GovCloud** — it needs its own GovCloud account and
  GovCloud IAM credentials.
- **Access blocker (real):** self-serve GovCloud signup is **denied** ("did not meet
  one or more of the prerequisites"). This is expected, not a misconfiguration —
  GovCloud is gated by eligibility, not a checkbox.

## Step 1 — get a GovCloud account (the gating item; weeks, not days)

GovCloud access requires meeting **three eligibility requirements** and signing two
agreements. You then provide documentation to AWS rather than self-provisioning.

| Requirement | What it means for Optimal, LLC |
|---|---|
| **U.S. entity** | Incorporated to do business in the U.S., based on U.S. soil — Optimal, LLC qualifies (CAGE 14HQ0). |
| **U.S. Person account holder** | U.S. citizen or active green-card holder — Ryan qualifies. |
| **Able to handle ITAR export-controlled data** | Attest capability to handle ITAR data under [AWS GovCloud ITAR terms](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-itar.html). |

**Action:** don't retry the self-serve form — go through the qualified path. Submit
the [AWS GovCloud (US) Contact Us form](https://aws.amazon.com/govcloud-us/contact-us/)
(or engage an AWS Public Sector rep), be ready to evidence the three items above, and
sign the customer agreement + the GovCloud-specific agreement. Realistic timeline:
**~2–6 weeks**, depending on AWS review. This is the only step that can't be
compressed — start it now, in parallel with everything else.

## Step 2 — stand up Bedrock in GovCloud

Once the GovCloud account exists:

1. In the GovCloud account, enable **Amazon Bedrock** in `us-gov-west-1` and request
   **model access** for the gov models (`openai.gpt-oss-120b`, `openai.gpt-oss-20b`,
   the proprietary `openai.gpt-5.5`, and `anthropic.claude-opus-4-8`). Confirm exact
   IDs with `aws bedrock list-foundation-models --region us-gov-west-1`.
2. Create a **GovCloud IAM** principal scoped to `bedrock:InvokeModel*` on those
   model ARNs (least privilege — mirror the commercial instance role's discipline).

## Step 3 — wire creds + egress into the gateway

The gov entries in
[`docker/gateway-host/litellm-config.yaml`](docker/gateway-host/litellm-config.yaml)
are already shaped for this; going live is a **creds + allowlist** change, not an
integration:

1. **Secrets:** store the GovCloud IAM access key / secret in AWS Secrets Manager
   under `lab/*` (e.g. `lab/aws_gov_access_key_id`, `lab/aws_gov_secret_access_key`),
   seed them through `scripts/seed-secrets.sh`, and surface them to the `litellm`
   container so it authenticates SigV4 against GovCloud Bedrock. (Cross-partition, so
   it's IAM *keys*, not the commercial instance profile.)
2. **Egress:** add the GovCloud Bedrock endpoint
   (`bedrock-runtime.us-gov-west-1.amazonaws.com`) to the **Squid allowlist**
   (`terraform apply`, or hot-reload: append to `/etc/squid/allowlist.txt` +
   `squid -k reconfigure` on `ai-lab-proxy`). Until then the call routes but Squid
   403s it — by design.
3. **Flip:** add the cred refs to each `gov/*` entry's `litellm_params`, then
   `docker compose up -d --force-recreate litellm` on gateway-host.

## Step 4 — prove it

Extend the smoke tests: a live `gov/gpt-oss-120b` (or `gov/claude-opus-4-8`)
completion returns 200, and the audit row attributes it to the **AWS GovCloud
(Bedrock)** boundary. At that point `T-GW-5` upgrades from "registered" to "live."

## The 30/60/90 you can say out loud

- **Now (demo):** live FedRAMP-Moderate-aligned posture in commercial AWS; the IL-5
  GovCloud OpenAI boundary registered, tagged, and one config flip from live.
- **~30–60 days:** GovCloud account approved (Step 1 is the long pole).
- **+1 week after access:** Steps 2–4 — gov tier live, first real `gov` completion
  served from an IL-4/5 boundary.

**Sources:**
[AWS GovCloud (US) sign-up](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/getting-started-sign-up.html) ·
[GovCloud FAQs](https://aws.amazon.com/govcloud-us/faqs/) ·
[ITAR compliance](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-itar.html) ·
[Bedrock models — FedRAMP High + IL-4/5 in GovCloud](https://aws.amazon.com/about-aws/whats-new/2026/06/addl-bedrock-model-fedramp-il-5-govcloud/)
