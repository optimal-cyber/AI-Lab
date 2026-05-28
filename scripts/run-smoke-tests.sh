#!/usr/bin/env bash
# =============================================================================
# run-smoke-tests.sh — egress + container health checks (host shell)
# =============================================================================
# Run from an SSM Session Manager shell on chat-host or gateway-host. The script
# inspects /etc/environment for the proxy IP and detects the host's role by
# which compose dir is present. Each check degrades to SKIP rather than fail
# when a precondition is missing, so it is safe to run at any phase.
#
# Mapped to docs/test-plan.md: T-EG-1..4 (egress) + container healthchecks.
# Does NOT perform identity-plane checks — that is scripts/test-sso.sh.
# =============================================================================
set -uo pipefail

# load proxy from /etc/environment if present
if [[ -f /etc/environment ]]; then
  # shellcheck disable=SC1091
  set -a; . /etc/environment; set +a
fi
PROXY="${HTTP_PROXY:-${http_proxy:-}}"
PROXY_HOST="${PROXY#http://}"; PROXY_HOST="${PROXY_HOST%%:*}"

pass=0 fail=0 skip=0
ok()   { printf '  \033[32m✓ PASS\033[0m  %s\n' "$*"; pass=$((pass+1)); }
no()   { printf '  \033[31m✗ FAIL\033[0m  %s\n' "$*"; fail=$((fail+1)); }
sk()   { printf '  \033[33m- SKIP\033[0m  %s\n' "$*"; skip=$((skip+1)); }

echo "== AI Lab smoke tests =="
echo "HTTP_PROXY=${PROXY:-<unset>}"
echo

# --- T-EG-1: direct egress to a non-allowlisted domain should fail ----------
echo "[T-EG-1] direct https://example.com (no proxy) — expect failure"
if out=$(curl -sS --max-time 6 -o /dev/null -w '%{http_code}' --noproxy '*' https://example.com 2>&1); then
  if [[ "${out}" == "000" ]]; then
    ok "blocked (no connection — SG drops direct 443)"
  else
    no "got HTTP ${out} — direct 443 should NOT succeed (egress invariant broken)"
  fi
else
  ok "blocked (curl error: $(printf '%s' "${out}" | tail -1))"
fi

# --- T-EG-2: via proxy, denied domain should return 403 from squid -----------
echo "[T-EG-2] via proxy to https://example.com — expect Squid 403"
if [[ -z "${PROXY}" ]]; then
  sk "no proxy env (set HTTP_PROXY or run on a configured host)"
else
  code=$(curl -sS --max-time 8 -x "${PROXY}" -o /dev/null -w '%{http_code}' https://example.com 2>/dev/null || echo "000")
  if [[ "${code}" == "403" ]]; then
    ok "Squid denied: HTTP 403 (not in allowlist)"
  else
    no "expected 403 from Squid, got ${code}"
  fi
fi

# --- T-EG-3: via proxy, allowlisted provider should connect ------------------
echo "[T-EG-3] via proxy to https://api.openai.com/v1/models — expect TLS OK"
if [[ -z "${PROXY}" ]]; then
  sk "no proxy env"
else
  code=$(curl -sS --max-time 8 -x "${PROXY}" -o /dev/null -w '%{http_code}' https://api.openai.com/v1/models 2>/dev/null || echo "000")
  # 401 (no key) or 200 (with key) both prove the path is allowed
  if [[ "${code}" == "401" || "${code}" == "200" ]]; then
    ok "allowlist path open (HTTP ${code} — 401 with no key is expected)"
  else
    no "expected 200/401, got ${code} — provider domain may not be allowlisted"
  fi
fi

# --- T-EG-4: direct port 7844 should NOT reach an arbitrary host -------------
echo "[T-EG-4] direct tcp/7844 to example.com — expect timeout/refused"
if timeout 4 bash -c "echo > /dev/tcp/example.com/7844" 2>/dev/null; then
  no "7844 reachable to example.com — SG egress on 7844 is too broad"
else
  ok "blocked / no route (SG allows 7844 only conceptually for Cloudflare edge)"
fi

# --- container healthchecks (gateway-host only) ------------------------------
echo
echo "[containers] docker compose health"
if [[ -d /opt/ai-lab/repo/docker/gateway-host ]]; then
  cd /opt/ai-lab/repo/docker/gateway-host
  ROLE="gateway"
elif [[ -d /opt/ai-lab/repo/docker/chat-host ]]; then
  cd /opt/ai-lab/repo/docker/chat-host
  ROLE="chat"
else
  sk "no compose dir at /opt/ai-lab/repo/docker/{chat,gateway}-host"
  ROLE=""
fi

if [[ -n "${ROLE}" ]] && command -v docker >/dev/null; then
  if ! docker compose ps --status running --format '{{.Service}}' >/tmp/_svcs 2>/dev/null; then
    sk "docker compose not reachable here"
  else
    running=$(wc -l </tmp/_svcs)
    if [[ "${running}" -gt 0 ]]; then
      ok "${ROLE}: ${running} container(s) running: $(tr '\n' ' ' </tmp/_svcs)"
    else
      no "${ROLE}: no containers running"
    fi
    if [[ "${ROLE}" == "gateway" ]]; then
      for svc in nemo-guardrails compliance-mcp; do
        if docker compose exec -T "${svc}" python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)" >/dev/null 2>&1; then
          ok "${svc} /health 200"
        else
          # fall back to the --health CLI form (works without HTTP)
          if docker compose exec -T "${svc}" python -m src.server --health >/dev/null 2>&1 || \
             docker compose exec -T "${svc}" python server.py --health >/dev/null 2>&1; then
            ok "${svc} --health ok"
          else
            no "${svc} healthcheck failed"
          fi
        fi
      done
      if docker compose exec -T postgres pg_isready -U litellm >/dev/null 2>&1; then
        ok "postgres pg_isready"
      else
        no "postgres pg_isready failed"
      fi
    fi
  fi
fi

echo
printf '== summary: \033[32m%d pass\033[0m, \033[31m%d fail\033[0m, \033[33m%d skip\033[0m ==\n' "$pass" "$fail" "$skip"
[[ "$fail" -eq 0 ]]
