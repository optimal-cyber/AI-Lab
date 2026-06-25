#!/bin/bash
# host-deploy.sh — last-mile app deploy on an AI-Gateway EC2 host (run as root via SSM).
# Idempotent: installs git, clones/updates the repo at /opt/ai-lab/repo, installs the
# systemd units, and starts the role's docker compose stack.
#   usage: host-deploy.sh <chat|gateway>
set -euxo pipefail

ROLE="${1:?usage: host-deploy.sh <chat|gateway>}"
REPO_URL="https://github.com/optimal-cyber/AI-Gateway.git"
REPO_DIR="/opt/ai-lab/repo"

# egress is via the Squid proxy (ADR-009) — load it so dnf/git can reach the internet
if [ -f /etc/environment ]; then set -a; . /etc/environment; set +a; fi

# 1. git (not in the base user-data package set)
command -v git >/dev/null 2>&1 || dnf -y install git

# 2. clone (or fast-forward) the public repo at the path the units expect
if [ -d "${REPO_DIR}/.git" ]; then
  git -C "${REPO_DIR}" fetch --depth=1 origin main
  git -C "${REPO_DIR}" reset --hard origin/main
else
  rm -rf "${REPO_DIR}"
  git clone --depth=1 --branch main "${REPO_URL}" "${REPO_DIR}"
fi

# 3. install the systemd units + ensure the bootstrap script is executable
install -m 0644 "${REPO_DIR}/docker/_shared/ai-lab-secrets@.service" /etc/systemd/system/
install -m 0644 "${REPO_DIR}/docker/_shared/ai-lab-stack@.service"    /etc/systemd/system/
chmod +x "${REPO_DIR}/docker/_shared/secrets-bootstrap.sh"
systemctl daemon-reload

# 4. enable persistently + start without blocking (the build can take minutes; we poll)
systemctl enable "ai-lab-stack@${ROLE}"
systemctl reset-failed "ai-lab-secrets@${ROLE}" "ai-lab-stack@${ROLE}" 2>/dev/null || true
systemctl start --no-block "ai-lab-stack@${ROLE}"

echo "HOST_DEPLOY_KICKED role=${ROLE} repo=$(git -C ${REPO_DIR} rev-parse --short HEAD)"
