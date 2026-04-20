"""Encrypted Telethon session file storage.

Each user's Telethon session is a SQLite file. We wrap it with Fernet: the session file
is decrypted into a temp path while in use, re-encrypted on flush. Permissions are 0600.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import AppConfig


class SessionStore:
    """Per-user encrypted Telethon session files.

    Layout:
        {sessions_dir}/{tg_user_id}.session.enc  -- Fernet-encrypted SQLite session
        {sessions_dir}/live/{tg_user_id}.session -- decrypted working copy while client is open

    `live/` is recreated on startup from encrypted files; its contents are disposable.
    """

    def __init__(self, config: AppConfig, key: str) -> None:
        self._dir = config.sessions_dir
        self._live = self._dir / "live"
        self._live.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def enc_path(self, tg_user_id: int | str) -> Path:
        return self._dir / f"{tg_user_id}.session.enc"

    def live_path(self, tg_user_id: int | str) -> Path:
        return self._live / f"{tg_user_id}.session"

    def has_session(self, tg_user_id: int | str) -> bool:
        return self.enc_path(tg_user_id).exists()

    def prepare_live(self, tg_user_id: int | str) -> Path:
        """Decrypt the encrypted session into `live/` and return the live path.

        If no encrypted session exists yet, returns the live path (Telethon will create it).
        """
        live = self.live_path(tg_user_id)
        enc = self.enc_path(tg_user_id)
        if enc.exists():
            try:
                data = self._fernet.decrypt(enc.read_bytes())
            except InvalidToken as e:
                raise RuntimeError(f"Session decrypt failed for {tg_user_id}") from e
            live.write_bytes(data)
        os.chmod(live, 0o600) if live.exists() else None
        return live

    def persist(self, tg_user_id: int | str) -> None:
        """Encrypt the live session back to disk and remove the live copy."""
        live = self.live_path(tg_user_id)
        if not live.exists():
            return
        data = live.read_bytes()
        enc = self.enc_path(tg_user_id)
        tmp = enc.with_suffix(enc.suffix + ".tmp")
        tmp.write_bytes(self._fernet.encrypt(data))
        os.chmod(tmp, 0o600)
        tmp.replace(enc)

    def flush(self, tg_user_id: int | str) -> None:
        """Encrypt current live session without removing it (periodic save)."""
        live = self.live_path(tg_user_id)
        if not live.exists():
            return
        data = live.read_bytes()
        enc = self.enc_path(tg_user_id)
        tmp = enc.with_suffix(enc.suffix + ".tmp")
        tmp.write_bytes(self._fernet.encrypt(data))
        os.chmod(tmp, 0o600)
        tmp.replace(enc)

    def drop_live(self, tg_user_id: int | str) -> None:
        live = self.live_path(tg_user_id)
        if live.exists():
            live.unlink()
        # Also clean Telethon's journal file if any
        for suffix in (".session-journal", "-journal"):
            j = Path(str(live) + suffix)
            if j.exists():
                j.unlink()

    def delete(self, tg_user_id: int | str) -> None:
        """Permanent delete: encrypted + live + any temp."""
        self.drop_live(tg_user_id)
        enc = self.enc_path(tg_user_id)
        if enc.exists():
            enc.unlink()

    def cleanup_all_live(self) -> None:
        """On startup, wipe any leftover decrypted live sessions."""
        if self._live.exists():
            shutil.rmtree(self._live)
        self._live.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()

    @staticmethod
    def make_temp_workdir() -> Path:
        return Path(tempfile.mkdtemp(prefix="tgmedia-"))
