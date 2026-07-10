#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${AGENT_DIR}/runtime"
LOG_FILE="${RUNTIME_DIR}/agent.stdout.log"
PID_FILE="${RUNTIME_DIR}/agent.pid"

mkdir -p "${RUNTIME_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}")"
  if kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "Agent is already running with PID ${OLD_PID}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

source /root/miniconda3/etc/profile.d/conda.sh
conda activate MP5_agent

cd "${AGENT_DIR}"
export MINEDOJO_VGL_DEVICE="${MINEDOJO_VGL_DEVICE:-/dev/dri/card4}"
export MINEDOJO_WINDOW_WIDTH="${MINEDOJO_WINDOW_WIDTH:-1600}"
export MINEDOJO_WINDOW_HEIGHT="${MINEDOJO_WINDOW_HEIGHT:-900}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://xiaoai.plus/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
export GPT_MODEL_NAME="${GPT_MODEL_NAME:-gpt-5.1}"
export TASK_FILE="${TASK_FILE:-tasks/creative/diamond.json}"
export MP5_DISABLE_MEMORY="${MP5_DISABLE_MEMORY:-0}"

nohup setsid python -u run_agent.py \
  --mllm_url "${MLLM_URL:-}" \
  --openai_key "${OPENAI_API_KEY}" \
  --gpt_model_name "${GPT_MODEL_NAME}" \
  --answer_method "${ANSWER_METHOD:-active}" \
  --answer_model "${ANSWER_MODEL:-mllm}" \
  --task "${TASK_FILE}" \
  > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

sleep 2
if kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
  echo "Agent started with PID $(cat "${PID_FILE}")"
  echo "Log: ${LOG_FILE}"
else
  echo "Agent failed to stay running"
  exit 1
fi
