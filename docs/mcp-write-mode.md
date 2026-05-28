# MCP write mode — what it would take (deliberately NOT enabled)

The compliance MCP ships **read-only** (ADR-005). The SQLite store is opened
`mode=ro`, no tool mutates anything, and a prompt-injection success can at worst
*read* seeded, non-sensitive lab data. Enabling any write tool (e.g.
`poam_create` / `poam_update`) converts a prompt-injection bug into a
data-integrity incident, so write mode is treated as a **separate security
project** with its own prerequisites — all of which must be in place first.

## Why read-only is the right default

- Bounds the blast radius of AI-1/AI-4 (prompt injection / tool misuse) to reads.
- The "what it takes to safely enable writes" analysis below is itself a portfolio
  artifact — it shows the controls a write-capable agent tool actually needs.

## Prerequisites before flipping write mode on

1. **Per-call human approval.** No write executes on the model's say-so. A write
   tool returns a *pending change* (a diff/preview + a change id); a human
   approves out-of-band before it commits. No "auto-approve."
2. **Separate, narrowly-scoped identity.** Writes use a distinct IAM role / DB
   credential scoped to exactly the target rows/operations — never the read
   role. Read and write paths do not share credentials.
3. **Dedicated approver group.** A new Okta group `lab-mcp-write-approvers`
   (subset of `lab-admins`); only its members can approve a pending write. New
   Cloudflare Access + LiteLLM mappings for it.
4. **Comprehensive audit to Splunk.** Every proposed write, the prompt that
   produced it, the approver, before/after values, and the commit → Splunk HEC
   (not just stdout). Immutable, queryable, retained.
5. **Rollback procedure.** Every write is reversible: soft-delete / versioned
   rows / a documented restore from snapshot, tested before go-live.
6. **Prompt-injection regression suite.** A test corpus of injection/jailbreak
   attempts targeting the *specific* write tools, run in CI; write mode cannot
   ship while any bypass is open. (Extends the NeMo detector suite.)
7. **Guardrail coverage of tool arguments.** Write-tool args validated with strict
   Pydantic models + enums; no free-text fields that become SQL/command surface
   (extends T-MCP-E controls).
8. **Threat-model update.** New STRIDE rows for the write tools (Tampering,
   Elevation) with the mitigations above mapped to NIST AC-3/AC-6/AU-2/SI-10.

## Out of scope until the above exist

Do not add a "write mode" feature flag that toggles writes without these controls
in place. A flag is too easy to flip; the controls, not the flag, are the gate.

## Tracking

When this work is scheduled, create `terraform`/Okta artifacts for
`lab-mcp-write-approvers`, the Splunk HEC sink, and the scoped write credential,
and a `mcp-server/src/write_tools.py` behind the approval workflow — not before.
