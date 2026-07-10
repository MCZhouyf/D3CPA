#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${AGENT_DIR}/runtime/agent.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "No PID file found"
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}" 2>/dev/null || true
  sleep 2
  if kill -0 "${PID}" 2>/dev/null; then
    kill -9 "${PID}" 2>/dev/null || true
  fi
fi

rm -f "${PID_FILE}"
pkill -f -- 'GradleWrapperMain runClient' || true
pkill -f -- 'minedojo.sim.bridge.utils.watchdog' || true

echo "Agent stopped"
