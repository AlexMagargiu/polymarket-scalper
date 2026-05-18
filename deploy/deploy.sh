#!/usr/bin/env bash
set -euo pipefail

VPS_HOST="${VPS_HOST:-root@89.167.90.189}"
REMOTE_DIR="/root/polymarket-scalper"
VENV_DIR="${REMOTE_DIR}/venv"

echo "==> Deploying Polymarket Scalper to ${VPS_HOST}:${REMOTE_DIR}"

echo "==> Syncing code..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude 'dashboard/' \
    --exclude '.next/' \
    --exclude 'node_modules/' \
    --exclude '*.db' \
    --exclude '.env' \
    --exclude '.env.local' \
    ./ "${VPS_HOST}:${REMOTE_DIR}/"

echo "==> Installing dependencies..."
ssh "${VPS_HOST}" "cd ${REMOTE_DIR} && \
    test -d ${VENV_DIR} || python3 -m venv ${VENV_DIR} && \
    ${VENV_DIR}/bin/pip install -q --upgrade pip && \
    ${VENV_DIR}/bin/pip install -q -r requirements.txt"

echo "==> Reloading systemd service..."
ssh "${VPS_HOST}" "cp ${REMOTE_DIR}/deploy/scalper.service /etc/systemd/system/scalper.service && \
    systemctl daemon-reload && \
    systemctl enable scalper && \
    systemctl restart scalper"

echo "==> Waiting for service to start..."
sleep 3

ssh "${VPS_HOST}" "systemctl is-active scalper && echo 'Service is running' || echo 'WARNING: Service failed to start'"

echo "==> Checking health endpoint..."
ssh "${VPS_HOST}" "curl -sf http://localhost:8099/api/health || echo 'WARNING: Health check failed'"

echo "==> Deploy complete!"
echo "    Logs: ssh ${VPS_HOST} journalctl -u scalper -f"
