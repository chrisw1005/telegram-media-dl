#!/usr/bin/env bash
#
# setup.sh — 一鍵首次安裝。
# - backend：uv sync 建立 .venv 並裝依賴
# - frontend：pnpm install 裝 node_modules
# - .env：若不存在則從 .env.example 複製，並自動產生 SESSION_ENCRYPTION_KEY
# - 最後提示使用者填入 TG_API_ID / TG_API_HASH
#
# 用法：
#   ./scripts/setup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

c_red=$'\033[31m'; c_yel=$'\033[33m'; c_grn=$'\033[32m'; c_cya=$'\033[36m'; c_off=$'\033[0m'

log()  { echo "${c_cya}[setup]${c_off} $*"; }
warn() { echo "${c_yel}[setup]${c_off} $*"; }
ok()   { echo "${c_grn}[setup]${c_off} $*"; }
err()  { echo "${c_red}[setup]${c_off} $*" >&2; }

# ---- prerequisites ----
if ! command -v uv >/dev/null 2>&1; then
    err "uv not installed"
    echo "  安裝方式：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
    if command -v corepack >/dev/null 2>&1; then
        log "pnpm not found; trying corepack activate"
        corepack prepare pnpm@9 --activate || {
            err "corepack failed; please install pnpm manually: npm install -g pnpm"
            exit 1
        }
    else
        err "pnpm not installed and corepack unavailable"
        echo "  安裝方式：npm install -g pnpm  (或啟用 corepack)"
        exit 1
    fi
fi

if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found (uv bundles it, but host python3 is also needed for key generation)"
    exit 1
fi

# ---- backend ----
log "installing backend dependencies (uv sync)…"
(cd "$PROJECT_ROOT/backend" && uv sync) || { err "uv sync failed"; exit 1; }
ok "backend deps ready (backend/.venv)"

# ---- frontend ----
log "installing frontend dependencies (pnpm install)…"
(cd "$PROJECT_ROOT/frontend" && pnpm install) || { err "pnpm install failed"; exit 1; }
ok "frontend deps ready (frontend/node_modules)"

# ---- .env ----
ENV_FILE="$PROJECT_ROOT/backend/.env"
ENV_EXAMPLE="$PROJECT_ROOT/backend/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
    log "creating backend/.env from template…"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    KEY=$(cd "$PROJECT_ROOT/backend" && uv run python -c \
        "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null | tail -1)
    if [[ -n "$KEY" ]]; then
        # macOS/BSD sed and GNU sed differ on -i; use a portable form
        python3 -c "
import re, sys
p = '$ENV_FILE'
s = open(p).read()
s = re.sub(r'^SESSION_ENCRYPTION_KEY=.*$', 'SESSION_ENCRYPTION_KEY=' + '$KEY', s, flags=re.M)
open(p, 'w').write(s)
"
        ok "generated SESSION_ENCRYPTION_KEY into backend/.env"
    else
        warn "could not auto-generate SESSION_ENCRYPTION_KEY; fill it manually"
    fi
else
    log "backend/.env already exists — leaving untouched"
fi

# ---- summary ----
echo
ok "setup complete ✓"
echo
echo "  下一步："
echo "    1. 編輯 $ENV_FILE 填入你的 Telegram API 憑證："
echo "         TG_API_ID   ← 到 https://my.telegram.org/apps 申請"
echo "         TG_API_HASH ← 同上"
echo "         BOT_TOKEN   ← 如需 Bot 功能，到 @BotFather 建 bot 取得"
echo "    2. 啟動 dev server："
echo "         ./scripts/dev.sh"
echo "    3. 開瀏覽器：http://localhost:5373/"
echo
