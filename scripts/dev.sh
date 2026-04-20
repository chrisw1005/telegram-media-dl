#!/usr/bin/env bash
#
# dev.sh — 啟動 backend (uvicorn :8000) + frontend (vite :5173) dev server。
# 若 port 被其他 process 佔用，會主動 kill 後再啟動。
# Ctrl-C 會同時停掉兩邊。
#
# 用法：
#   ./scripts/dev.sh              # 預設 port
#   BACKEND_PORT=8001 ./scripts/dev.sh
#   ./scripts/dev.sh --backend-only
#   ./scripts/dev.sh --frontend-only
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 預設避開 Django/FastAPI 8000、Vite 5173 等容易撞到的 port
BACKEND_PORT="${BACKEND_PORT:-8787}"
FRONTEND_PORT="${FRONTEND_PORT:-5373}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"

START_BACKEND=1
START_FRONTEND=1
for arg in "$@"; do
    case "$arg" in
        --backend-only) START_FRONTEND=0 ;;
        --frontend-only) START_BACKEND=0 ;;
        -h|--help)
            sed -n '2,15p' "${BASH_SOURCE[0]}"
            exit 0 ;;
        *) echo "[x] unknown arg: $arg" >&2; exit 2 ;;
    esac
done

c_red=$'\033[31m'; c_yel=$'\033[33m'; c_grn=$'\033[32m'; c_cya=$'\033[36m'; c_off=$'\033[0m'

log()  { echo "${c_cya}[dev]${c_off} $*"; }
warn() { echo "${c_yel}[dev]${c_off} $*"; }
err()  { echo "${c_red}[dev]${c_off} $*" >&2; }
ok()   { echo "${c_grn}[dev]${c_off} $*"; }

port_pids() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti ":$port" -sTCP:LISTEN 2>/dev/null || true
    else
        fuser -n tcp "$port" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
    fi
}

pid_cmdline() {
    local pid=$1
    if [[ -r "/proc/$pid/comm" ]]; then
        local comm
        comm=$(cat "/proc/$pid/comm" 2>/dev/null || echo "?")
        local cmd
        cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | head -c 80)
        echo "$comm ($cmd)"
    else
        echo "?"
    fi
}

free_port() {
    local port=$1 label=$2
    local pids
    pids=$(port_pids "$port")
    if [[ -z "$pids" ]]; then
        log "port $port ($label) is free"
        return
    fi
    warn "port $port ($label) occupied by:"
    for pid in $pids; do
        warn "  pid $pid — $(pid_cmdline "$pid")"
    done
    warn "killing (SIGTERM)…"
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    for _ in 1 2 3; do
        sleep 1
        pids=$(port_pids "$port")
        [[ -z "$pids" ]] && { ok "port $port freed"; return; }
    done
    warn "still held — sending SIGKILL"
    # shellcheck disable=SC2086
    kill -KILL $pids 2>/dev/null || true
    sleep 1
    pids=$(port_pids "$port")
    if [[ -n "$pids" ]]; then
        err "port $port could not be freed; aborting"
        exit 1
    fi
    ok "port $port freed"
}

# ---- pre-flight: free the needed ports ----
[[ $START_BACKEND  -eq 1 ]] && free_port "$BACKEND_PORT"  backend
[[ $START_FRONTEND -eq 1 ]] && free_port "$FRONTEND_PORT" frontend

# ---- sanity checks ----
if [[ $START_BACKEND -eq 1 ]]; then
    [[ -f "$PROJECT_ROOT/backend/.env" ]] || warn "backend/.env missing — copy backend/.env.example first"
    command -v uv >/dev/null 2>&1 || { err "uv not installed"; exit 1; }
fi
if [[ $START_FRONTEND -eq 1 ]]; then
    command -v pnpm >/dev/null 2>&1 || { err "pnpm not installed (try: corepack prepare pnpm@9 --activate)"; exit 1; }
    [[ -d "$PROJECT_ROOT/frontend/node_modules" ]] || { log "frontend deps missing; running pnpm install"; (cd "$PROJECT_ROOT/frontend" && pnpm install); }
fi

# ---- start children ----
PIDS=()
cleanup() {
    log "shutting down…"
    for pid in "${PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    # give them a moment to exit
    sleep 0.5
    for pid in "${PIDS[@]}"; do
        kill -KILL "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT INT TERM

if [[ $START_BACKEND -eq 1 ]]; then
    log "starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
    (cd "$PROJECT_ROOT/backend" && exec uv run uvicorn app.main:app \
        --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload) &
    PIDS+=($!)
fi

if [[ $START_FRONTEND -eq 1 ]]; then
    log "starting frontend on ${FRONTEND_HOST}:${FRONTEND_PORT}"
    (cd "$PROJECT_ROOT/frontend" \
        && BACKEND_PORT="$BACKEND_PORT" \
           FRONTEND_PORT="$FRONTEND_PORT" \
           BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}" \
           exec pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT") &
    PIDS+=($!)
fi

ok "running. open http://${FRONTEND_HOST}:${FRONTEND_PORT}/ (Ctrl-C stops all)"

# wait for any child to exit; then cleanup trap fires.
wait -n "${PIDS[@]}" 2>/dev/null || true
# If we got here, one died — kill the rest and exit.
