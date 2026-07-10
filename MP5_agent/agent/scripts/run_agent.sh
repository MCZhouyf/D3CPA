export MLLM_URL="${MLLM_URL:-}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://xiaoai.plus/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
export GPT_MODEL_NAME="${GPT_MODEL_NAME:-gpt-5.1}"
export ANSWER_METHOD="${ANSWER_METHOD:-active}"
export ANSWER_MODEL="${ANSWER_MODEL:-mllm}"
export TASK_FILE="${TASK_FILE:-tasks/creative/diamond.json}"
export MP5_DISABLE_MEMORY="${MP5_DISABLE_MEMORY:-0}"
export MINEDOJO_VGL_DEVICE="${MINEDOJO_VGL_DEVICE:-/dev/dri/card4}"
export MINEDOJO_WINDOW_WIDTH="${MINEDOJO_WINDOW_WIDTH:-1600}"
export MINEDOJO_WINDOW_HEIGHT="${MINEDOJO_WINDOW_HEIGHT:-900}"

python -u run_agent.py \
  --mllm_url "${MLLM_URL}" \
  --openai_key "${OPENAI_API_KEY}" \
  --gpt_model_name "${GPT_MODEL_NAME}" \
  --answer_method "${ANSWER_METHOD}" \
  --answer_model "${ANSWER_MODEL}" \
  --task "${TASK_FILE}"
