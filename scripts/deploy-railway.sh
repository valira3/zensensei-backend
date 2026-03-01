#!/usr/bin/env bash
# ZenSensei Railway Deployment Helper
# Usage: ./scripts/deploy-railway.sh <command> [options]
#
# Commands:
#   setup   -- Create Railway project + all 7 services + Redis plugin
#   deploy  -- Deploy all services (or a single service with --service flag)
#   status  -- Show deployment status for all services
#   logs    -- Stream logs from a specific service (-s <service-name>)
#   env     -- Set environment variables for a service from a .env file
#   open    -- Open the Railway dashboard in your browser

set -euo pipefail

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

declare -A DOCKERFILE_PATHS=(
  ["gateway"]="gateway/Dockerfile"
  ["user-service"]="services/user_service/Dockerfile"
  ["graph-query-service"]="services/graph_query_service/Dockerfile"
  ["ai-reasoning-service"]="services/ai_reasoning_service/Dockerfile"
  ["integration-service"]="services/integration_service/Dockerfile"
  ["notification-service"]="services/notification_service/Dockerfile"
  ["analytics-service"]="services/analytics_service/Dockerfile"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${BLUE}[zensensei]${NC} $*"; }
ok()     { echo -e "${GREEN}[ok]${NC} $*"; }
warn()   { echo -e "${YELLOW}[warn]${NC} $*"; }
err()    { echo -e "${RED}[error]${NC} $*" >&2; }
header() { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}"; }

require_cmd() {
  if ! command -v "$1" &>/dev/null; then
    err "Required command not found: $1"
    exit 1
  fi
}

require_railway_auth() {
  if ! railway whoami &>/dev/null 2>&1; then
    err "Not authenticated with Railway. Run: railway login"
    exit 1
  fi
}

cmd_setup() {
  header "Setting up Railway project: $PROJECT_NAME"
  require_cmd railway
  require_railway_auth
  log "Creating project..."
  railway init --name "$PROJECT_NAME" || warn "Project may already exist"
  log "Adding Redis plugin..."
  railway add --plugin redis || warn "Redis plugin may already exist"
  header "Creating services"
  for svc in "${SERVICES[@]}"; do
    log "Creating service: $svc"
    railway service create "$svc" || warn "Service $svc may already exist"
  done
  header "Setup complete"
  echo "Next: Set environment variables and run deploy"
}

cmd_deploy() {
  local target_service=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --service|-s) target_service="$2"; shift 2 ;;
      *) err "Unknown option: $1"; exit 1 ;;
    esac
  done
  require_cmd railway
  require_railway_auth
  if [[ -n "$target_service" ]]; then
    header "Deploying service: $target_service"
    railway up --service "$target_service" --detach
    ok "Triggered deployment for $target_service"
  else
    header "Deploying all services"
    for svc in "${SERVICES[@]}"; do
      log "Deploying: $svc"
      railway up --service "$svc" --detach
      ok "Triggered: $svc"
    done
    ok "All deployments triggered."
  fi
}

cmd_status() {
  require_cmd railway
  require_railway_auth
  header "Deployment status: $PROJECT_NAME"
  for svc in "${SERVICES[@]}"; do
    status=$(railway status --service "$svc" 2>/dev/null | grep -i "status" | head -1 || echo "unknown")
    echo "$svc: $status"
  done
}

cmd_logs() {
  local target_service=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --service|-s) target_service="$2"; shift 2 ;;
      *) err "Unknown option: $1"; exit 1 ;;
    esac
  done
  require_cmd railway
  require_railway_auth
  if [[ -z "$target_service" ]]; then
    err "Specify a service with --service <name>"
    exit 1
  fi
  header "Streaming logs: $target_service"
  railway logs --service "$target_service"
}

cmd_open() {
  require_cmd railway
  railway open
}

usage() {
  cat <<EOF
ZenSensei Railway Deployment Helper

Usage: $(basename "$0") <command> [options]

Commands:
  setup                     Create Railway project, services, and Redis plugin
  deploy [--service NAME]   Deploy all services, or a single one
  status                    Show deployment status for all services
  logs --service NAME       Stream logs from a specific service
  open                      Open Railway dashboard in browser

Service names:
$(printf "  - %s\n" "${SERVICES[@]}")
EOF
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
  setup)   cmd_setup "$@" ;;
  deploy)  cmd_deploy "$@" ;;
  status)  cmd_status "$@" ;;
  logs)    cmd_logs "$@" ;;
  open)    cmd_open "$@" ;;
  help|-h|--help) usage ;;
  *) err "Unknown command: $COMMAND"; usage; exit 1 ;;
esac
