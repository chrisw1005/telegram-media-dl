#!/usr/bin/env bash
#
# stop.sh — 停掉佔用 backend/frontend dev port 的任何 process。
# 預設 port：8000 (backend) / 5173 (frontend)
#
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8787}"
FRONTEND_PORT="${FRONTEND_PORT:-5373}"

c_red=$'\033[31m'; c_yel=$'\033[33m'; c_grn=$'\033[32m'; c_cya=$'\033[36m'; c_off=$'\033[0m'

log()  { echo "${c_cya}[stop]${c_off} $*"; }
warn() { echo "${c_yel}[stop]${c_off} $*"; }
ok()   { echo "${c_grn}[stop]${c_off} $*"; }
err()  { echo "${c_red}[stop]${c_off} $*" >&2; }

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
        log "port $port ($label) already free"
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
        err "port $port could not be freed (pid=$pids)"
        return 1
    fi
    ok "port $port freed"
}

free_port "$BACKEND_PORT" backend
free_port "$FRONTEND_PORT" frontend
