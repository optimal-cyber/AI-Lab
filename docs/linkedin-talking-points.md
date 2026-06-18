# LinkedIn talking points

Bullet ammunition for the lab announcement — **not a draft post**. Pick three to
four hook + substantive points and write the post in your own voice; this file
exists so you don't have to invent the framing under deadline.

---

## Hook angles (pick one)

- **"A credible Zero Trust AI posture without enterprise vendor pricing."**
  ~$75–85/month at idle. Cloudflare Zero Trust + AWS + Okta + open source.
- **"What does a Cloudflare-and-OSS counterpart to Will Grana's Zscaler reference
  lab look like?"** (Tag Will if you reference his post.)
- **"Compliance teams should be running MCP against their own evidence stores,
  not vendor APIs."** Lead with the SAM.gov + POA&M + CMMC tools.
- **"The part most cloud teams skip: workload egress allowlisting."** Lead with
  the proxy + SG design that *forces* HTTP/HTTPS through a default-deny list.
- **"Two-pattern SSO: trusted-header for chat, direct OIDC for admin."** Match
  the auth mechanism to the blast radius.

## Substantive points (pick a few to defend)

- The **controls** (no public ingress, identity-aware access with MFA, default-
  deny egress, inline AI guardrails, scoped IAM, no SSH) are **the same
  regardless of vendor.** Demonstrating them in OSS is the point.
- **Open source is production-credible** for these controls when wired correctly
  — Cloudflare Access in front of `cloudflared`, NeMo Guardrails as DaaS, a
  hardened Squid allowlist, Okta as the IdP.
- The **MCP server is the real differentiator.** Generic "wrapped Open WebUI"
  demos don't have a live SAM.gov lookup, a NIST 800-53 catalog, POA&M and CMMC
  L2 tools — all read-only by design, and all auditable in one log line.
- **Read-only first.** Write-mode is a separate security project — documented
  in `docs/mcp-write-mode.md` with eight prerequisites.
- **DaaS guardrails fail closed.** If the guardrail service is unreachable, the
  request is blocked. Killing the guard must not be a bypass.
- **Workload egress is the part most teams haven't caught up on.** The control
  here is structural — the security group blocks direct 80/443, so HTTP/HTTPS
  *cannot* leave except through the default-deny domain allowlist. The list is
  diff-able Terraform code.
- **One prompt → four correlated audit records** (Okta → Cloudflare Access →
  Open WebUI → LiteLLM + MCP) tied by email and `litellm_call_id`. Pull this
  off and your audit-trail story is done.
- **3PAO mindset:** every design decision lives in an ADR with the context,
  alternatives, and consequences a fellow assessor would actually press on.

## Things to NOT claim

- **Not CMMC-compliant.** Reference design, not an assessment boundary or
  attestation. The CMMC L2 dashboard is illustrative seed data.
- **No client data.** Lab runs on personal AWS / personal Cloudflare / personal
  Okta tenant; nothing touches DDC / Motorola / Ignyte / any client engagement.
- **Not a Zscaler replacement for enterprises that already have it.** This is
  for SBIR/STTR-stage teams and small DIB shops who cannot afford ZPA + ZIA.
- **Not an attestation of NIST 800-53 / 800-171.** It demonstrates how the
  controls would *evidence*, not that the lab itself is in scope.

## Visual assets — capture exactly these 8 from the test plan

| # | Test ID | What it shows |
|---|---|---|
| 1 | T-SSO-1 | Cloudflare Access redirect → Okta + MFA → Open WebUI signed in |
| 2 | T-SSO-2 | `lab-users` user blocked at the gateway admin app |
| 3 | T-SSO-3/4 | Strict gateway policy denying on geo / WARP posture |
| 4 | T-GR-1 | Prompt-injection blocked by NeMo + the JSON `decisions.log` line |
| 5 | T-GR-2 | Fake `ghp_` PAT blocked, redacted finding in the log |
| 6 | T-MCP-2 | **The money shot** — "Look up Optimal, LLC by CAGE 14HQ0" returning a real SAM.gov entity inside your own gateway, POC fields `[REDACTED]` |
| 7 | T-MCP-3 | The CMMC L2 dashboard with the disclaimer visible |
| 8 | T-AUDIT-1 | Side-by-side: Okta log, Access log, Open WebUI session, LiteLLM row + MCP structlog line — same email, same minute |

## Architecture diagram

The single-file SVG at `landing/index.html` is portable — screenshot it for the
post if you want one image. Or use the Mermaid in `README.md`.

## Tags worth considering

`#ZeroTrust #CMMC #SBIR #FedRAMP #CloudSecurity #AISecurity #MCP #OpenSource
#Cloudflare #DIB #VOSB`

## Disclosure footer (drop this verbatim)

> *Reference design built by Optimal, LLC (CAGE 14HQ0) on personal time and
> personal infrastructure. No client data; not a CMMC assessment boundary; not a
> claim of compliance. Source + ADRs: github.com/optimal-cyber/AI-Gateway*

## If you reference Will Grana

Tag him; credit the inspiration in one line, then state your delta in one line
(e.g. "Cloudflare + open source counterpart; ~$80/mo; MCP against compliance
evidence"). Don't position it as a critique of his version — it's a parallel
take.
