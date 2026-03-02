#!/usr/bin/env bash
# =============================================================================
# ZenSensei Railway Deployment Helper
# =============================================================================
# Usage: ./scripts/deploy-railway.sh <command> [options]
#
# Commands:
#   setup   -- Create Railway project + all 7 services + Redis plugin
#   deploy  -- Deploy all services (or a single service with --service flag)
#   status  -- Show deployment status for all services
#   logs    -- Stream logs from a specific service (-s <service-name>)
#   env     -- Set environment variables for a service from a .env file
#   open    -- Open the Railway dashboard in your browser
#
# Requirements:
#   - Railway CLI installed: https://docs.railway.app/develop/cli
#   - Authenticated: run `railway login` first
#   - jq installed (for JSON parsing in status command)
#
# Examples:
#   ./scripts/deploy-railway.sh setup
#   ./scripts/deploy-railway.sh deploy
#   ./scripts/deploy-railway.sh deploy --service gateway
#   ./scripts/deploy-railway.sh status
#   ./scripts/deploy-railway.sh logs --service user-service
#   ./scripts/deploy-railway.sh env --service gateway --file .env.production
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_NAME="zensensei-backend"

SERVICES=(
  "gateway"
  "user-service"
  "graph-query-service"
  "ai-reasoning-service"
  "integration-service"
  "notification-service"
  "analytics-service"
)

# Dockerfile paths relative to repo root (build context is always repo root)
declare -A DOCKERFILE_PATHS=(
  ["gateway"]="Dockerfile"
  ["user-service"]="services/user_service/Dockerfile"
  ["graph-query-service"]="services/graph_query_service/Dockerfile"
  ["ai-reasoning-service"]="services/ai_reasoning_service/Dockerfile"
  ["integration-service"]="services/integration_service/Dockerfile"
  ["notification-service"]="services/notification_service/Dockerfile"
  ["analytics-service"]="services/analytics_service/Dockerfile"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { echo "[deploy] $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" &>/dev/null || die "'$1' is not installed. $2"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_setup() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  log "Creating Railway project: $PROJECT_NAME"
  railway init --name "$PROJECT_NAME"

  for svc in "${SERVICES[@]}"; do
    log "Adding service: $svc"
    railway service create "$svc"
  done

  log "Adding Redis plugin..."
  railway plugin add redis

  log "Setup complete. Configure env vars with: $0 env --service <name> --file <envfile>"
}

cmd_deploy() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  local target_service=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --service|-s) target_service="$2"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  if [[ -n "$target_service" ]]; then
    _deploy_service "$target_service"
  else
    for svc in "${SERVICES[@]}"; do
      _deploy_service "$svc"
    done
  fi
}

_deploy_service() {
  local svc="$1"
  local dockerfile="${DOCKERFILE_PATHS[$svc]:-}"
  [[ -n "$dockerfile" ]] || die "Unknown service: $svc"

  log "Deploying $svc (Dockerfile: $dockerfile)..."
  railway up \
    --service "$svc" \
    --dockerfile "$dockerfile" \
    --detach
  log "$svc deployment triggered."
}

cmd_status() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  require_cmd jq      "Install via: brew install jq  OR  apt-get install jq"

  log "Fetching deployment status..."
  railway status --json | jq '.deployments[] | {service: .serviceName, status: .status, url: .url}'
}

cmd_logs() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  local target_service=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --service|-s) target_service="$2"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  [[ -n "$target_service" ]] || die "--service flag required for logs command."
  log "Streaming logs for: $target_service"
  railway logs --service "$target_service"
}

cmd_env() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  local target_service=""
  local env_file=""

  while [[ $# -gt 0 ]]; do
    case $1 in
      --service|-s) target_service="$2"; shift 2 ;;
      --file|-f)    env_file="$2";       shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  [[ -n "$target_service" ]] || die "--service flag required."
  [[ -n "$env_file" ]]       || die "--file flag required."
  [[ -f "$env_file" ]]       || die "File not found: $env_file"

  log "Setting env vars for $target_service from $env_file..."
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    railway variables set "$key=$value" --service "$target_service"
  done < "$env_file"
  log "Done."
}

cmd_open() {
  require_cmd railway "Install from https://docs.railway.app/develop/cli"
  railway open
}

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  setup)  cmd_setup  "$@" ;;
  deploy) cmd_deploy "$@" ;;
  status) cmd_status "$@" ;;
  logs)   cmd_logs   "$@" ;;
  env)    cmd_env    "$@" ;;
  open)   cmd_open   "$@" ;;
  *)
    echo "Usage: $0 {setup|deploy|status|logs|env|open} [options]"
    echo "Run '$0 --help' for detailed usage."
    exit 1
    ;;
esac
