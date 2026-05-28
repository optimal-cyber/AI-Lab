# Google Cloud DNS — the three `lab.` CNAMEs (Phase 4)

> ## ⚠️ DO NOT TOUCH ANY EXISTING `gooptimal.io` RECORDS
> `gooptimal.io` stays authoritative on **Google Cloud DNS** (ADR-008). You are
> adding **exactly three** new record sets under the `lab.` namespace. Do **not**
> modify, delete, or re-delegate: `outpost.gooptimal.io`, the apex `A`/`AAAA`, the
> `MX` records, or any `SPF`/`DKIM`/`DMARC` `TXT` records, or anything else.
> Adding `lab.*` records cannot affect production email or the newsletter — but
> only if you add, never edit. A DNS mistake here should be contained to
> `*.lab.gooptimal.io`.

## The three records

| Name | Type | Value | TTL |
|---|---|---|---|
| `lab.gooptimal.io` | CNAME | `<pages-project>.pages.dev` | 300 |
| `chat.lab.gooptimal.io` | CNAME | `<chat-tunnel-uuid>.cfargotunnel.com` | 300 |
| `gateway.lab.gooptimal.io` | CNAME | `<gateway-tunnel-uuid>.cfargotunnel.com` | 300 |

Where the values come from:
- `<pages-project>.pages.dev` — the Cloudflare Pages project (Phase 4.5,
  `landing/README.md`), e.g. `ai-lab-landing.pages.dev`.
- `<chat-tunnel-uuid>` / `<gateway-tunnel-uuid>` — the tunnel IDs from Phase 4
  (Cloudflare dashboard → Zero Trust → Networks → Tunnels, or the Terraform
  outputs `chat_tunnel_cname` / `gateway_tunnel_cname` in
  `terraform/modules/cloudflare/outputs.tf`).

> Note on `lab.gooptimal.io` itself: a CNAME at a name that also needs other
> records is fine here because `lab` has no other records. Cloudflare Pages may
> alternatively give you an apex-style target; follow whatever the Pages "custom
> domain" screen shows for `lab.gooptimal.io` if it differs from the `.pages.dev`
> CNAME above.

## Add them in Google Cloud DNS

1. Google Cloud Console → **Network Services → Cloud DNS** → select the
   **`gooptimal.io`** managed zone.
2. **Add Standard / Add record set** — once per row above:
   - **DNS name:** `lab` (Cloud DNS appends `.gooptimal.io.`), then `chat.lab`,
     then `gateway.lab`.
   - **Resource record type:** `CNAME`
   - **TTL:** `300` seconds
   - **Canonical name / data:** the Value from the table (include the trailing
     `.` if the console requires FQDN form, e.g. `<uuid>.cfargotunnel.com.`).
3. Save each. Do not batch-edit the zone file; add discrete record sets so you
   cannot accidentally alter a neighboring record.

### gcloud CLI equivalent (optional)

```bash
ZONE=gooptimal-io          # your Cloud DNS managed-zone name (not the domain)
gcloud dns record-sets create chat.lab.gooptimal.io.    --zone="$ZONE" --type=CNAME --ttl=300 --rrdatas="<chat-tunnel-uuid>.cfargotunnel.com."
gcloud dns record-sets create gateway.lab.gooptimal.io. --zone="$ZONE" --type=CNAME --ttl=300 --rrdatas="<gateway-tunnel-uuid>.cfargotunnel.com."
gcloud dns record-sets create lab.gooptimal.io.         --zone="$ZONE" --type=CNAME --ttl=300 --rrdatas="<pages-project>.pages.dev."
```
`create` (not `update`/`transaction`) only adds; it errors rather than clobbering
an existing record — the safe choice here.

## Verify (does not require the apps to be up)

```bash
dig +short CNAME chat.lab.gooptimal.io @8.8.8.8
# -> <chat-tunnel-uuid>.cfargotunnel.com.
dig +short CNAME gateway.lab.gooptimal.io @8.8.8.8
# -> <gateway-tunnel-uuid>.cfargotunnel.com.
dig +short CNAME lab.gooptimal.io @8.8.8.8
# -> <pages-project>.pages.dev.

# sanity: confirm you did NOT disturb production
dig +short MX gooptimal.io @8.8.8.8        # unchanged
dig +short TXT gooptimal.io @8.8.8.8       # SPF/DMARC unchanged
dig +short outpost.gooptimal.io @8.8.8.8   # unchanged
```

Once the CNAMEs resolve and the tunnels/Pages project are live, browse to
`https://chat.lab.gooptimal.io` → you should be redirected to Cloudflare Access →
Okta. Run `scripts/test-sso.sh` for the structural checks.
