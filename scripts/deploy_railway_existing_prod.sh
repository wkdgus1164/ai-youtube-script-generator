#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ID="${RAILWAY_WORKSPACE_ID_OVERRIDE:-9f20ba1c-43d7-48e8-9429-9e8a00619449}"
PROJECT_ID="${RAILWAY_PROJECT_ID_OVERRIDE:-5da695c1-a3cd-4d61-b454-2724ec3bbed4}"
ENVIRONMENT_NAME="${RAILWAY_ENVIRONMENT_OVERRIDE:-production}"
BACKEND_SERVICE="${RAILWAY_BACKEND_SERVICE:-workflow-api}"
CONSOLE_SERVICE="${RAILWAY_CONSOLE_SERVICE:-workflow-console}"
CONSOLE_VOLUME_MOUNT_PATH="/app/backend/data"
BACKEND_PROMPT_STORE_PATH="/data/script_writer_prompts.json"
export BACKEND_SERVICE CONSOLE_SERVICE

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  echo "Missing ${ROOT_DIR}/.env" >&2
  exit 1
fi

set -a
source "${ROOT_DIR}/.env"
set +a

for required in OPENAI_API_KEY API_KEY DEFAULT_LLM_MODEL EXTRA_MODELS WEBUI_SECRET_KEY WEBUI_AUTH; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing required env var in .env: ${required}" >&2
    exit 1
  fi
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

link_project() {
  local workdir="$1"
  mkdir -p "${workdir}"
  (
    cd "${workdir}"
    railway link -w "${WORKSPACE_ID}" -p "${PROJECT_ID}" -e "${ENVIRONMENT_NAME}" >/dev/null
  )
}

run_linked() {
  local workdir="$1"
  shift
  (
    cd "${workdir}"
    "$@"
  )
}

json_query() {
  local expr="$1"
  python3 -c "import json,sys; data=json.load(sys.stdin); print(${expr})"
}

PROJECT_LINK_DIR="${TMP_DIR}/project"
link_project "${PROJECT_LINK_DIR}"

STATUS_JSON="$(run_linked "${PROJECT_LINK_DIR}" railway status --json)"

BACKEND_PUBLIC_DOMAIN="$(
  STATUS_JSON="${STATUS_JSON}" BACKEND_SERVICE="${BACKEND_SERVICE}" python3 - <<'PY'
import json
import os

service_name = os.environ["BACKEND_SERVICE"]
status = json.loads(os.environ["STATUS_JSON"])
for env_edge in status["environments"]["edges"]:
    for svc_edge in env_edge["node"]["serviceInstances"]["edges"]:
        node = svc_edge["node"]
        if node["serviceName"] == service_name:
            domains = node["domains"]["serviceDomains"]
            if domains:
                print(domains[0]["domain"])
                raise SystemExit
raise SystemExit(f"Missing public domain for {service_name}")
PY
)"

CONSOLE_PUBLIC_DOMAIN="$(
  STATUS_JSON="${STATUS_JSON}" CONSOLE_SERVICE="${CONSOLE_SERVICE}" python3 - <<'PY'
import json
import os

service_name = os.environ["CONSOLE_SERVICE"]
status = json.loads(os.environ["STATUS_JSON"])
for env_edge in status["environments"]["edges"]:
    for svc_edge in env_edge["node"]["serviceInstances"]["edges"]:
        node = svc_edge["node"]
        if node["serviceName"] == service_name:
            domains = node["domains"]["serviceDomains"]
            if domains:
                print(domains[0]["domain"])
                raise SystemExit
raise SystemExit(f"Missing public domain for {service_name}")
PY
)"

CONSOLE_HAS_VOLUME="$(
  STATUS_JSON="${STATUS_JSON}" CONSOLE_SERVICE="${CONSOLE_SERVICE}" python3 - <<'PY'
import json
import os

service_name = os.environ["CONSOLE_SERVICE"]
status = json.loads(os.environ["STATUS_JSON"])
service_id = None
env_node = status["environments"]["edges"][0]["node"]
for svc_edge in status["services"]["edges"]:
    node = svc_edge["node"]
    if node["name"] == service_name:
        service_id = node["id"]
        break

if service_id is None:
    raise SystemExit(f"Missing service: {service_name}")

has_volume = any(
    volume_edge["node"]["serviceId"] == service_id
    for volume_edge in env_node["volumeInstances"]["edges"]
)
print("1" if has_volume else "0")
PY
)"

echo "Backend public domain: ${BACKEND_PUBLIC_DOMAIN}"

railway_set() {
  local service="$1"
  shift
  run_linked "${PROJECT_LINK_DIR}" railway variable set -s "${service}" -e "${ENVIRONMENT_NAME}" --skip-deploys "$@"
}

railway_delete() {
  local service="$1"
  local key="$2"
  run_linked "${PROJECT_LINK_DIR}" railway variable delete -s "${service}" -e "${ENVIRONMENT_NAME}" "${key}" >/dev/null 2>&1 || true
}

service_status_json() {
  local service="$1"
  run_linked "${PROJECT_LINK_DIR}" railway service status -s "${service}" -e "${ENVIRONMENT_NAME}" --json
}

service_deployment_id() {
  local service="$1"
  service_status_json "${service}" | json_query 'data["deploymentId"]'
}

service_deployment_status() {
  local service="$1"
  service_status_json "${service}" | json_query 'data["status"]'
}

wait_for_new_deployment() {
  local service="$1"
  local previous_id="$2"
  local attempts="${3:-60}"
  local sleep_seconds="${4:-10}"

  for ((i = 1; i <= attempts; i++)); do
    local payload
    payload="$(service_status_json "${service}")"
    local deployment_id
    local status
    deployment_id="$(printf '%s' "${payload}" | json_query 'data["deploymentId"]')"
    status="$(printf '%s' "${payload}" | json_query 'data["status"]')"
    echo "[${service}] poll ${i}: deployment=${deployment_id} status=${status}"

    if [[ "${deployment_id}" != "${previous_id}" && "${status}" == "SUCCESS" ]]; then
      return 0
    fi

    if [[ "${status}" == "FAILED" || "${status}" == "CRASHED" || "${status}" == "REMOVED" ]]; then
      echo "Deployment failed for ${service}" >&2
      return 1
    fi

    sleep "${sleep_seconds}"
  done

  echo "Timed out waiting for ${service} deployment" >&2
  return 1
}

echo "Applying workflow-api variables"
railway_set "${BACKEND_SERVICE}" "OPENAI_API_KEY=${OPENAI_API_KEY}"
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  railway_set "${BACKEND_SERVICE}" "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"
fi
if [[ -n "${LANGSMITH_API_KEY:-}" ]]; then
  railway_set "${BACKEND_SERVICE}" "LANGCHAIN_API_KEY=${LANGSMITH_API_KEY}"
fi
if [[ -n "${TAVILY_API_KEY:-}" ]]; then
  railway_set "${BACKEND_SERVICE}" "TAVILY_API_KEY=${TAVILY_API_KEY}"
fi
railway_set "${BACKEND_SERVICE}" "DEFAULT_LLM_MODEL=${DEFAULT_LLM_MODEL}"
railway_set "${BACKEND_SERVICE}" "API_KEY=${API_KEY}"
railway_set "${BACKEND_SERVICE}" "EXTRA_MODELS=${EXTRA_MODELS}"
railway_set "${BACKEND_SERVICE}" "OPENWEBUI_VISIBLE_MODELS=${OPENWEBUI_VISIBLE_MODELS:-youtube-script-writer}"
railway_set "${BACKEND_SERVICE}" "LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2:-false}"
railway_set "${BACKEND_SERVICE}" "LANGCHAIN_PROJECT=${LANGCHAIN_PROJECT:-langgraph-openwebui}"
railway_set "${BACKEND_SERVICE}" "SCRIPT_WRITER_PROMPT_STORE_PATH=${BACKEND_PROMPT_STORE_PATH}"
railway_delete "${BACKEND_SERVICE}" "REQUEST_TIMEOUT"

echo "Applying workflow-console variables"
railway_set "${CONSOLE_SERVICE}" "ENABLE_OLLAMA_API=false"
railway_set "${CONSOLE_SERVICE}" "OPENAI_API_BASE_URL=https://${BACKEND_PUBLIC_DOMAIN}/v1"
railway_set "${CONSOLE_SERVICE}" "OPENAI_API_KEY=${API_KEY}"
railway_set "${CONSOLE_SERVICE}" "WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}"
railway_set "${CONSOLE_SERVICE}" "WEBUI_AUTH=${WEBUI_AUTH}"
railway_set "${CONSOLE_SERVICE}" "DATA_DIR=${CONSOLE_VOLUME_MOUNT_PATH}"
railway_set "${CONSOLE_SERVICE}" "SCRIPT_WRITER_BACKEND_PUBLIC_URL=https://${BACKEND_PUBLIC_DOMAIN}"

if [[ "${CONSOLE_HAS_VOLUME}" != "1" ]]; then
  echo "Attaching new persistent volume to ${CONSOLE_SERVICE}"
  CONSOLE_LINK_DIR="${TMP_DIR}/console-service"
  mkdir -p "${CONSOLE_LINK_DIR}"
  (
    cd "${CONSOLE_LINK_DIR}"
    railway link -w "${WORKSPACE_ID}" -p "${PROJECT_ID}" -e "${ENVIRONMENT_NAME}" -s "${CONSOLE_SERVICE}" >/dev/null
    railway volume add -m "${CONSOLE_VOLUME_MOUNT_PATH}" >/dev/null
  )
fi

BACKEND_PREVIOUS_DEPLOYMENT="$(service_deployment_id "${BACKEND_SERVICE}")"
echo "Deploying ${BACKEND_SERVICE} from ${ROOT_DIR}/backend"
railway up "${ROOT_DIR}/backend" \
  --path-as-root \
  -p "${PROJECT_ID}" \
  -e "${ENVIRONMENT_NAME}" \
  -s "${BACKEND_SERVICE}" \
  -d \
  -m "Deploy workflow-api from ai-youtube-script-generator"
wait_for_new_deployment "${BACKEND_SERVICE}" "${BACKEND_PREVIOUS_DEPLOYMENT}"

echo "Verifying backend public health"
curl -fsS "https://${BACKEND_PUBLIC_DOMAIN}/health" >/dev/null
curl -fsS -H "Authorization: Bearer ${API_KEY}" "https://${BACKEND_PUBLIC_DOMAIN}/v1/models" | grep -q '"youtube-script-writer"'

CONSOLE_PREVIOUS_DEPLOYMENT="$(service_deployment_id "${CONSOLE_SERVICE}")"
echo "Deploying ${CONSOLE_SERVICE} from ${ROOT_DIR}/openwebui"
railway up "${ROOT_DIR}/openwebui" \
  --path-as-root \
  -p "${PROJECT_ID}" \
  -e "${ENVIRONMENT_NAME}" \
  -s "${CONSOLE_SERVICE}" \
  -d \
  -m "Deploy OpenWebUI console from ai-youtube-script-generator"
wait_for_new_deployment "${CONSOLE_SERVICE}" "${CONSOLE_PREVIOUS_DEPLOYMENT}"

echo "Verifying OpenWebUI public endpoint"
curl -fsS "https://${CONSOLE_PUBLIC_DOMAIN}" | grep -q "Open WebUI"

echo "Deployment complete."
echo "OpenWebUI: https://${CONSOLE_PUBLIC_DOMAIN}"
echo "Backend: https://${BACKEND_PUBLIC_DOMAIN}"
