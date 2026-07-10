#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${AGENT_DIR}/runtime/agent.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "Agent is not running"
  exit 1
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" 2>/dev/null; then
  echo "Agent is running with PID ${PID}"
  ps -fp "${PID}"
else
  echo "PID file exists but process is not running"
  rm -f "${PID_FILE}"
  exit 1
fi
