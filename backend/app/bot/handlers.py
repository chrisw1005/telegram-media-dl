"""Bot command handlers.

Flow summary:
  /start           → welcome + Web login deep link (if not yet logged in)
  /dl <t.me link>  → parse link, enqueue download, re-upload to Saved Messages
  forwarded msg    → pull forward source → same as /dl
  /status          → show top 10 active/queued jobs for the caller
  /cancel <id>     → cancel a queued or running job

Authorization:
  - Every inbound update is checked against ACL.is_allowed(tg_user_id).
  - If tg_user_id has no MTProto session, /start returns a login link.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.queue import DownloadJob, JobStatus

if TYPE_CHECKING:
    from app.api.deps import AppState

logger = logging.getLogger(__name__)

TME_RE = re.compile(
    r"https?://t\.me/(?:c/(?P<cid>-?\d+)|(?P<username>[A-Za-z0-9_]+))/(?P<msg>\d+(?:-\d+)?)/?"
)

BOT_DL_RANGE_MAX = 50  # cap per /dl command so nobody accidentally queues thousands

# Deep-link login tokens (bot → web). Maps short token → (tg_user_id, expires_at).
_login_deeplink: dict[str, tuple[int, float]] = {}
LOGIN_DEEPLINK_TTL = 15 * 60

# Progress-report throttling so we don't hit Telegram's edit-message rate limit.
PROGRESS_EDIT_INTERVAL_SEC = 2.0


def _format_bytes(n: int) -> str:
    if not n:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}" if i > 0 else f"{int(v)} B"


def _format_speed(bps: float) -> str:
    return f"{_format_bytes(int(bps))}/s"


def _bar(pct: int, width: int = 12) -> str:
    pct = max(0, min(100, pct))
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _format_progress_text(job: dict, speed_bps: float) -> str:
    name = job.get("filename") or f"msg-{job.get('message_id')}"
    total = int(job.get("bytes_total", 0) or 0)
    done = int(job.get("bytes_done", 0) or 0)
    pct = int(done * 100 / total) if total > 0 else 0
    bar = _bar(pct)
    status = job.get("status")

    lines = [f"`{name}`"]
    if status == "flood_wait":
        remaining = max(0, int(job.get("flood_wait_until", 0) - time.time()))
        lines.append(f"⏸ FLOOD_WAIT — {remaining}s 後恢復")
        lines.append(f"`{bar}` {pct}%")
    elif status == "pending":
        lines.append("⏳ 等待中…")
    else:
        lines.append(f"`{bar}` {pct}%")
        lines.append(
            f"{_format_bytes(done)} / {_format_bytes(total)}  •  {_format_speed(speed_bps)}"
        )
    return "\n".join(lines)


def _format_final_text(job: dict) -> str:
    status = job.get("status")
    name = job.get("filename") or f"msg-{job.get('message_id')}"
    total = int(job.get("bytes_total", 0) or 0)
    if status == "completed":
        lines = [f"✅ `{name}` 已完成", f"大小：{_format_bytes(total)}"]
        if job.get("send_to_saved"):
            lines.append("已傳到你的 Saved Messages")
        return "\n".join(lines)
    if status == "cancelled":
        return f"🚫 `{name}` 已取消"
    if status == "failed":
        err = job.get("error") or "unknown"
        return f"❌ `{name}` 失敗\n{err}"
    return f"`{name}` — {status}"


async def watch_job(
    ctx: ContextTypes.DEFAULT_TYPE,
    state: AppState,
    chat_id: int,
    reply_message_id: int,
    job_id: str,
) -> None:
    """Subscribe to queue events for a single job and keep a bot message in sync.

    Throttles edit_message_text calls to ~1 every PROGRESS_EDIT_INTERVAL_SEC
    seconds. Computes speed from byte deltas between edits.
    """
    sub = state.queue.subscribe(job_id)
    last_edit_ts = 0.0
    last_bytes = 0
    last_time = time.monotonic()
    last_text: str | None = None

    async def safe_edit(text: str) -> None:
        nonlocal last_text
        if text == last_text:
            return
        try:
            await ctx.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=reply_message_id,
                parse_mode="Markdown",
            )
            last_text = text
        except Exception:
            # Common: "message is not modified", rate limits, network blips.
            # Swallow — next tick will try again.
            pass

    try:
        while True:
            try:
                evt = await asyncio.wait_for(sub.get(), timeout=30.0)
            except TimeoutError:
                # No events for a while — re-read current state and refresh once.
                snap = state.queue.get(job_id)
                if snap is None:
                    return
                evt = {"event": "tick", "job": snap.to_dict()}

            job_dict = evt.get("job", {})
            status = job_dict.get("status")

            if status in ("completed", "failed", "cancelled"):
                await safe_edit(_format_final_text(job_dict))
                return

            now = time.monotonic()

            # Always edit on "started"/"flood_wait"/first time, or if enough time passed.
            force = status in ("flood_wait",) or last_text is None or evt.get("event") == "started"
            if not force and (now - last_edit_ts) < PROGRESS_EDIT_INTERVAL_SEC:
                continue

            bytes_now = int(job_dict.get("bytes_done", 0) or 0)
            dt = max(0.001, now - last_time)
            speed = max(0, (bytes_now - last_bytes) / dt)
            last_bytes, last_time, last_edit_ts = bytes_now, now, now

            await safe_edit(_format_progress_text(job_dict, speed))
    finally:
        state.queue.unsubscribe(sub, job_id=job_id)


def install(app: Application, state: AppState) -> None:
    """Register all handlers. Called once at startup."""
    app.bot_data["state"] = state
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("dl", on_dl))
    app.add_handler(CommandHandler("status", on_status))
    app.add_handler(CommandHandler("cancel", on_cancel))
    app.add_handler(MessageHandler(filters.FORWARDED & ~filters.COMMAND, on_forwarded))


def _state(ctx: ContextTypes.DEFAULT_TYPE) -> AppState:
    return ctx.application.bot_data["state"]


async def _deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "無存取權限。請聯絡管理員將您的 Telegram ID 加入白名單。"
        )


def issue_deeplink_token(tg_user_id: int) -> str:
    tok = secrets.token_urlsafe(24)
    _login_deeplink[tok] = (tg_user_id, time.time() + LOGIN_DEEPLINK_TTL)
    return tok


def resolve_deeplink_token(tok: str) -> int | None:
    entry = _login_deeplink.get(tok)
    if entry is None:
        return None
    uid, exp = entry
    if time.time() > exp:
        _login_deeplink.pop(tok, None)
        return None
    return uid


# ---- /start ----

async def on_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx)
    user = update.effective_user
    if user is None or update.effective_message is None:
        return

    if not state.acl.is_allowed(user.id):
        await _deny(update)
        return

    has_session = state.session_store.has_session(user.id)
    if not has_session:
        tok = issue_deeplink_token(user.id)
        base = state.config.public_base_url or "http://localhost:5173"
        login_url = f"{base.rstrip('/')}/?bot_token={tok}"
        await update.effective_message.reply_text(
            "嗨！請先用瀏覽器完成 Telegram 登入（QR 或手機號）：\n"
            f"{login_url}\n\n"
            "登入後，再回這裡傳 t.me 連結或直接轉傳媒體給我即可下載。",
            disable_web_page_preview=True,
        )
        return

    await update.effective_message.reply_text(
        "已登入 ✅\n\n"
        "用法：\n"
        "  /dl <t.me 連結>  — 下載該訊息的媒體\n"
        "  或直接轉傳含媒體的訊息給我\n"
        "  /status          — 查看下載佇列\n"
        "  /cancel <job_id> — 取消某個下載"
    )


# ---- /dl ----

async def on_dl(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx)
    user = update.effective_user
    msg = update.effective_message
    if user is None or msg is None:
        return
    if not state.acl.is_allowed(user.id):
        await _deny(update)
        return
    if not state.session_store.has_session(user.id):
        await msg.reply_text("請先用 /start 完成 Web 登入。")
        return

    args = ctx.args or []
    if not args:
        await msg.reply_text(
            "用法：\n"
            "  /dl <t.me/xxx/123>\n"
            "  /dl <link1> <link2> ...（多個一次下載）\n"
            "  /dl <t.me/xxx/10-20>（範圍，最多 "
            f"{BOT_DL_RANGE_MAX} 則）",
        )
        return

    # Parse every arg; each may expand into multiple (chat_ref, msg_id) pairs
    # when the link uses the "10-20" range syntax.
    jobs_to_queue: list[tuple[int | str, int]] = []
    parse_errors: list[str] = []
    for raw in args:
        parsed = parse_tme_link(raw)
        if parsed is None:
            parse_errors.append(raw)
            continue
        chat_ref, msg_spec = parsed
        if isinstance(msg_spec, tuple):
            start, end = msg_spec
            if end < start:
                start, end = end, start
            count = end - start + 1
            if count > BOT_DL_RANGE_MAX:
                parse_errors.append(f"{raw}（範圍超過 {BOT_DL_RANGE_MAX}）")
                continue
            for mid in range(start, end + 1):
                jobs_to_queue.append((chat_ref, mid))
        else:
            jobs_to_queue.append((chat_ref, msg_spec))

    if not jobs_to_queue:
        await msg.reply_text(
            "無法解析任何連結。支援格式：\n"
            "  https://t.me/<username>/<msg_id>\n"
            "  https://t.me/c/<chat_id>/<msg_id>\n"
            "  https://t.me/<...>/10-20（範圍）",
        )
        return

    enqueued = 0
    for chat_ref, mid in jobs_to_queue:
        try:
            resolved = await resolve_chat_ref(state, user.id, chat_ref)
        except Exception as e:
            logger.exception("resolve_chat failed")
            parse_errors.append(f"{chat_ref}：{e}")
            continue

        job = DownloadJob(
            id="",
            tg_user_id=user.id,
            chat_id=resolved,
            message_id=mid,
            kind="download",
            dest_dir=str(state.config.download_dir / str(user.id)),
            send_to_saved=True,
        )
        jid = await state.queue.enqueue(job)
        reply = await msg.reply_text(
            f"⏳ 已排入佇列 (`{jid[:8]}`) — msg `{mid}`\n準備開始下載…",
            parse_mode="Markdown",
        )
        asyncio.create_task(watch_job(ctx, state, reply.chat_id, reply.message_id, jid))
        enqueued += 1

    if parse_errors:
        await msg.reply_text("⚠️ 部分項目略過：\n" + "\n".join(f"- {e}" for e in parse_errors[:10]))
    if enqueued > 1:
        await msg.reply_text(f"📥 共排入 {enqueued} 筆同時下載")


def parse_tme_link(link: str) -> tuple[str | int, int | tuple[int, int]] | None:
    """Parse a t.me URL.

    Returns (chat_ref, msg_id) for a single message, or (chat_ref, (from, to))
    for a range like `.../10-20`. Returns None if the input is not a t.me URL.
    """
    m = TME_RE.match(link.strip())
    if not m:
        try:
            u = urlparse(link)
            if u.netloc not in ("t.me", "telegram.me"):
                return None
        except Exception:
            return None
        return None

    raw_msg = m.group("msg")
    if "-" in raw_msg:
        a, b = raw_msg.split("-", 1)
        msg_spec: int | tuple[int, int] = (int(a), int(b))
    else:
        msg_spec = int(raw_msg)

    if m.group("cid"):
        cid = int(m.group("cid"))
        # Telegram uses -100... format for channel IDs
        full_chat_id = cid if cid < 0 else -(1000000000000 + cid)
        return (full_chat_id, msg_spec)
    return (m.group("username"), msg_spec)


async def resolve_chat_ref(state: AppState, uid: int, chat_ref: int | str) -> int:
    """Resolve t.me link's chat part to a numeric chat_id that Telethon can use."""
    if isinstance(chat_ref, int):
        return chat_ref
    client = await state.client_pool.get_client(uid)
    entity = await client.get_entity(chat_ref)
    return int(entity.id)


# ---- forwarded message ----

async def on_forwarded(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx)
    user = update.effective_user
    msg = update.effective_message
    if user is None or msg is None:
        return
    if not state.acl.is_allowed(user.id):
        await _deny(update)
        return
    if not state.session_store.has_session(user.id):
        await msg.reply_text("請先用 /start 完成 Web 登入。")
        return

    source_chat_id: int | None = None
    source_msg_id: int | None = None

    if msg.forward_origin is not None:
        fo = msg.forward_origin
        if hasattr(fo, "chat") and fo.chat is not None:
            source_chat_id = int(fo.chat.id)
            source_msg_id = int(getattr(fo, "message_id", 0) or 0)
        elif hasattr(fo, "sender_chat") and fo.sender_chat is not None:
            source_chat_id = int(fo.sender_chat.id)
            source_msg_id = int(getattr(fo, "message_id", 0) or 0)

    if source_chat_id is None or not source_msg_id:
        await msg.reply_text(
            "無法取得轉傳來源。請改用 /dl <t.me/...> 連結形式，或轉傳的來源須為公開聊天。"
        )
        return

    if not (msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation):
        await msg.reply_text("此訊息不含媒體。")
        return

    job = DownloadJob(
        id="",
        tg_user_id=user.id,
        chat_id=source_chat_id,
        message_id=source_msg_id,
        kind="download",
        dest_dir=str(state.config.download_dir / str(user.id)),
        send_to_saved=True,
    )
    jid = await state.queue.enqueue(job)
    reply = await msg.reply_text(
        f"⏳ 已排入佇列 (`{jid[:8]}`)\n準備開始下載…",
        parse_mode="Markdown",
    )
    asyncio.create_task(watch_job(ctx, state, reply.chat_id, reply.message_id, jid))


# ---- /status ----

async def on_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx)
    user = update.effective_user
    msg = update.effective_message
    if user is None or msg is None:
        return
    if not state.acl.is_allowed(user.id):
        await _deny(update)
        return

    jobs = state.queue.list_jobs(tg_user_id=user.id)
    active = [j for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FLOOD_WAIT)]
    recent_done = [j for j in jobs if j.status == JobStatus.COMPLETED][:5]

    if not active and not recent_done:
        await msg.reply_text("目前沒有佇列中的下載。")
        return

    lines = []
    if active:
        lines.append("*進行中 / 排隊中：*")
        for j in active[:10]:
            pct = int((j.bytes_done / j.bytes_total) * 100) if j.bytes_total else 0
            status_label = {
                JobStatus.PENDING: "等待中",
                JobStatus.RUNNING: "下載中",
                JobStatus.FLOOD_WAIT: "FLOOD_WAIT",
            }[j.status]
            name = j.filename or f"msg-{j.message_id}"
            lines.append(f"  `{j.id[:8]}` {status_label} {pct}% — {name}")

    if recent_done:
        if lines:
            lines.append("")
        lines.append("*最近完成：*")
        for j in recent_done:
            lines.append(f"  ✅ {j.filename or f'msg-{j.message_id}'}")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


# ---- /cancel ----

async def on_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx)
    user = update.effective_user
    msg = update.effective_message
    if user is None or msg is None:
        return
    if not state.acl.is_allowed(user.id):
        await _deny(update)
        return

    args = ctx.args or []
    if not args:
        await msg.reply_text("用法：/cancel <job_id 前綴>")
        return

    prefix = args[0]
    matches = [j for j in state.queue.list_jobs(user.id) if j.id.startswith(prefix)]
    if not matches:
        await msg.reply_text(f"找不到符合的 job（prefix={prefix}）")
        return
    if len(matches) > 1:
        await msg.reply_text(f"prefix 過短，有 {len(matches)} 個符合。請提供更長的 id 前綴。")
        return
    job = matches[0]
    ok = await state.queue.cancel(job.id)
    await msg.reply_text(f"{'已取消' if ok else '無法取消'}：{job.id[:8]}")
