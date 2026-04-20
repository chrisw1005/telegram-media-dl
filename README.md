# Telegram Media DL

瀏覽、預覽並批次下載 Telegram 群組、頻道、Saved Messages 與私訊中的媒體。

- **前端**：React + TypeScript + Vite + Tailwind + shadcn/ui + framer-motion
- **後端**：FastAPI + Telethon (MTProto)，`asyncio.Queue` + JSON 快照做 crash recovery
- **三種前端共用同一後端**（分階段）：
  - P1（已完成）：Web UI
  - P2：Telegram Bot 指令（`/dl <link>`、轉傳訊息給 bot）
  - P3：Telegram Mini App（嵌入 Telegram client）

## 核心特色

- **時長自適應 keyframe 幻燈片**：縮圖 hover 400ms 自動播放影片關鍵幀幻燈片（20~120 張依時長），一眼看完整支影片內容
- **鍵盤流預覽**：開啟 Modal 後 `D`/`Enter` 加佇列 + 跳下一個、`,/.` 跳 keyframe、`J/L` ±5s、`Space` 播放
- **並發下載**：per-user semaphore（預設 4）+ 全域 rate limit（預設 20 req/s）+ `FLOOD_WAIT_X` 指數退避
- **深淺主題 + reduced motion** 完整支援、WCAG 對比度合規
- **ACL**：Telegram user ID 白名單，第一個登入者自動成為 admin

## 必備環境

- Python 3.11+ 與 [`uv`](https://docs.astral.sh/uv/)
- Node.js 22+ 與 pnpm（可透過 `corepack prepare pnpm@9 --activate`）
- Telegram API credentials：到 <https://my.telegram.org/apps> 建立一個 application 取得 `api_id` / `api_hash`

## 第一次設定

```bash
# 1. 後端環境變數
cp backend/.env.example backend/.env
# 編輯 backend/.env 填入 TG_API_ID / TG_API_HASH

# 2. 生成 session 加密 key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 把結果填到 backend/.env 的 SESSION_ENCRYPTION_KEY

# 3. （選擇性）編輯 backend/config.yaml 調整下載資料夾、並行數、白名單
```

## 啟動 dev server

兩個 terminal 分別跑：

```bash
# Terminal 1 — backend (FastAPI on :8000)
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend (Vite on :5173)
cd frontend
pnpm install
pnpm dev
```

開 <http://localhost:5173/> → 用另一台已登入的 Telegram 掃 QR 即可。

> 第一次登入的帳號會自動成為 admin（若 `config.yaml:allowlist` 未設）。之後 admin 可在 Settings 頁新增白名單。

## Production build

```bash
# Backend
cd backend && uv sync --no-dev

# Frontend
cd frontend && pnpm install && pnpm build
# 產物在 frontend/dist/
```

可用 nginx / caddy 反代 `/api` 到 uvicorn、static serve `frontend/dist/`。

## 專案結構

```
backend/
  app/
    api/     # FastAPI routers
    core/    # session、client pool、downloader、queue、keyframe extractor
    main.py  # app entrypoint
  data/      # runtime only (gitignored): sessions, cache, queue.json
  config.yaml
frontend/
  src/
    pages/     # Login, AppShell, ChatsSidebar, ChatMedia, Downloads/Settings sheets
    components/ui/  # Button, Input, Sheet, Skeleton
    components/     # MediaThumb, MediaPreviewModal, FolderPicker, ThemeToggle
    lib/            # api, ws, theme, motion, format, cn
    stores/         # zustand download store
```

## 鍵盤快捷鍵

| 場景 | 按鍵 | 行為 |
|---|---|---|
| Grid | `Cmd/Ctrl+A` | 全選目前顯示的媒體 |
| Grid | `Esc` | 取消選取 |
| Grid | `Shift+click` / `Cmd/Ctrl+click` | 加入多選 |
| Grid | 右鍵 | 加入/取消多選（不 open preview） |
| Preview Modal | `Space` | 播放/暫停 |
| Preview Modal | `D` / `Enter` | 加入下載 + 跳下一個 |
| Preview Modal | `←` / `→` | 上/下一個媒體 |
| Preview Modal | `,` / `.` | 上/下一個 keyframe |
| Preview Modal | `J` / `L` | ±5 秒 |
| Preview Modal | `Esc` | 關閉 |

## 部署模式

`config.yaml:deployment_mode`：

- `local`（預設）：檔案存到 `download_dir`（可在 UI 用 FolderPicker 切換）
- `public`：檔案透過 HTTP streaming 給瀏覽器下載；`/api/fs/*` 端點關閉

## 已知限制（P1）

- 大於 200MB 影片不自動抽 keyframe（fallback 首 5 秒 stream）——P2 規劃 Range-seek 抽幀
- Bot 功能尚未實作（P2）
- Mini App 尚未實作（P3）

## 授權

MIT
