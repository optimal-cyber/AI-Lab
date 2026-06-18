# Control mapping & evidence (G5 / ADR-019)

How the gateway's controls map to **NIST SP 800-53 Rev 5** and **CMMC L2 /
NIST 800-171** practices, what **evidence** proves each one, and how a **tenant's**
evidence is assembled. This is the control-inheritance / SSP-shaped artifact a 3PAO
would read.

> **This evidences how the controls map and where the evidence lives — it is NOT
> an SSP, an attestation, or an authorization.** The lab holds no client data /
> CUI and is not an assessment boundary. Control IDs and the structured-JSON
> evidence shapes are real; the *authorization* is out of scope. A real engagement
> extends this with its own boundary, scoping, and continuous-monitoring evidence.

## 1. Control-inheritance model

Every control is one of three layers (the customer-responsibility matrix shape):

- **Inherited** — the FedRAMP-authorized gov boundary (AWS GovCloud, Azure
  Government, GCP Assured Workloads) provides the underlying datacenter, physical,
  hypervisor, and crypto-module baseline. The gateway *inherits* these.
- **Implemented** — the gateway provides the access, guardrail, egress, audit, and
  tenancy controls (the rows below). This is what the lab demonstrates.
- **Tenant responsibility** — the approved org owns its own data classification,
  user vetting, and acceptable-use. The gateway gives the org the scoped key,
  budget, tier, and audit; the org governs what it sends.

## 2. Control mapping

| Gateway component | NIST 800-53 Rev 5 | CMMC L2 (800-171) | Evidence (artifact · field) | Layer | Ref |
|---|---|---|---|---|---|
| Cloudflare Access + Okta — identity-aware access, MFA, groups | AC-2, AC-3, IA-2, IA-2(1), IA-2(2), AC-17 | AC.L2-3.1.1, AC.L2-3.1.2, IA.L2-3.5.3 | Okta System Log (auth + MFA factor) · Cloudflare Access log (Allow/Block, policy name) | Implemented (+ IdP inherited) | ADR-002/007 |
| No public ingress · Cloudflare Tunnel (outbound-only) | SC-7, AC-17 | SC.L2-3.13.1, SC.L2-3.13.2 | Terraform: zero inbound SG rules · tunnel `HEALTHY` in CF dashboard | Implemented | ADR-002 |
| NeMo guardrails — input/output, fail-closed, secret/PII/injection detection | SI-4, AC-4, SI-10, SC-7 | SI.L2-3.14.6, AC.L2-3.1.3 | NeMo `decisions.log` · `{blocked, findings[redacted], request_id, duration_ms}` | Implemented | ADR-003 |
| Squid egress allowlist — default-deny, allow-by-exception | SC-7, SC-7(5), AC-4 | SC.L2-3.13.1, SC.L2-3.13.6 | Terraform `egress_allowlist_domains` · Squid `403 TCP_DENIED` on non-allowlisted (T-EG-2) | Implemented | ADR-009 |
| Read-only MCP — least privilege / least functionality | AC-6, CM-7, AC-3 | AC.L2-3.1.5, CM.L2-3.4.6 | SQLite `mode=ro`; MCP structlog · `{tool_name, status, redacted_args}` | Implemented | ADR-005 |
| SSM-only access · no SSH · IMDSv2 | AC-17, AC-6, CM-7, IA-2 | AC.L2-3.1.5, CM.L2-3.4.6 | Terraform: no SSH keys on instances · SSM session log | Implemented | ADR-006 |
| Scoped IAM — least privilege | AC-6, AC-6(1) | AC.L2-3.1.5 | Terraform instance-role policy (`secretsmanager:GetSecretValue` on `lab/*`, no wildcards) | Implemented | — |
| Secrets in tmpfs (0600, RAM) + Secrets Manager | IA-5, SC-12, SC-28 | IA.L2-3.5.10, SC.L2-3.13.16 | `secrets-bootstrap.sh` (tmpfs `/run/ai-lab/*.env`); Secrets Manager `lab/*` | Implemented (+ KMS inherited) | — |
| LiteLLM virtual keys · per-team budgets · model allow-lists (tenancy + tiers) | AC-2, AC-3, AC-4, AC-6 | AC.L2-3.1.1, AC.L2-3.1.2 | `LiteLLM_SpendLogs` · `{key, team, model, end_user}`; team `metadata{tier, approved_by}` | Implemented | ADR-014/016/018 |
| Posture tiers + residency policy (gov tenant → `gov/*` only) | AC-4, CA-3, SA-9 | AC.L2-3.1.3, SC.L2-3.13.1 | `model_info{tier, boundary}`; SpendLogs `model` → boundary (gov rows never on a commercial endpoint) | Implemented (+ boundary inherited) | ADR-014/015/018 |
| Structured audit (NeMo + LiteLLM + MCP) · `request_id` join · CloudWatch · TLS | AU-2, AU-3, AU-6, AU-9, AU-12, SC-8 | AU.L2-3.3.1, AU.L2-3.3.2, SC.L2-3.13.8 | the three logs joined by `request_id`; CloudWatch retention (`log_retention_days`) | Implemented | ADR-003/016 |
| Gov boundary — FedRAMP-authorized cloud (datacenter/physical/crypto baseline) | (baseline families) | (inherited baseline) | the boundary's FedRAMP package | **Inherited** | ADR-014/015 |

## 3. Per-tenant evidence assembly

A single tenant request produces a correlated bundle, joined by **`request_id`**
(`litellm_call_id`) and segregable by **team** (org). For one request:

| Source | Key fields | Joined by | Evidences |
|---|---|---|---|
| **Okta System Log** | `user.authentication.sso`, MFA factor | email + timestamp | AC-2, IA-2 / IA.L2-3.5.3 |
| **Cloudflare Access log** | Allow/Block, policy, email | email + timestamp | AC-3, AC-17 / AC.L2-3.1.1 |
| **NeMo `decisions.log`** | `blocked`, `findings[redacted]`, `request_id` | `request_id` | SI-4, AC-4 / SI.L2-3.14.6 |
| **LiteLLM `LiteLLM_SpendLogs`** | `request_id`, `model`→boundary, `team`, `end_user`, `spend`, `status` | `request_id` | AC-2/3/4, AU-2/3 / AU.L2-3.3.2 |
| **compliance-MCP structlog** | `caller_virtual_key_hash`, `caller_role`, `tool_name`, `status` | `caller_virtual_key_hash` ↔ team key | AC-6, AU-2 / AC.L2-3.1.5 |

Filtering `LiteLLM_SpendLogs` by `team` yields **one org's evidence**; the MCP
line's `caller_virtual_key_hash` ties tool calls back to that org's key. For a gov
tenant, the `model`→boundary mapping shows every row on a gov boundary and none on
a commercial endpoint — the **residency policy, evidenced** (ADR-018). Matched
secrets/PII are pre-redacted in every log, so the evidence never carries the raw
sensitive value (SI-4 / AU-9). This is the bundle behind test-plan **T-EVID-1**
(and the `request_id` join first shown in [`sso-role-mapping.md`](sso-role-mapping.md)).

## 4. What this is not

- **Not an SSP and not an attestation.** No System Security Plan boundary diagram,
  no POA&M-of-record, no continuous-monitoring program, no 3PAO assessment.
- **No CUI / client data.** The lab runs on personal AWS / Cloudflare / Okta and
  processes no controlled data; the CMMC L2 dashboard is illustrative seed data.
- **Authorization is out of scope.** A `gov` boundary's FedRAMP authorization is
  the *cloud operator's*, inherited — the lab claims none of its own.
- **How a real engagement extends this:** add the authorization boundary + data-flow
  diagram, a customer-responsibility matrix per gov boundary, the POA&M and SPRS
  scoring of record, and the continuous-monitoring evidence pipeline (ship the same
  structured logs to the engagement's SIEM).
