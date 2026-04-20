"""Access control: Telegram user-ID allowlist + admin check.

First login on an empty allowlist is treated as bootstrap — that user becomes admin.
Admins can add/remove allowlist entries via the Settings UI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.config import AppConfig


class ACL:
    def __init__(self, config: AppConfig, persist_path: Path | None = None) -> None:
        self._config = config
        self._path = persist_path or (config.data_dir / "acl.json")
        self._allow: set[int] = set(config.allowlist)
        self._admins: set[int] = set(config.admin_ids)
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._allow |= set(data.get("allowlist", []))
                self._admins |= set(data.get("admin_ids", []))
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "allowlist": sorted(self._allow),
                    "admin_ids": sorted(self._admins),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    def is_allowed(self, tg_user_id: int) -> bool:
        # If allowlist is empty, bootstrap mode: everyone allowed (but see bootstrap_admin).
        if not self._allow:
            return True
        return tg_user_id in self._allow

    def is_admin(self, tg_user_id: int) -> bool:
        if not self._admins and self._allow and tg_user_id in self._allow:
            # Degenerate case: no admins listed but allowlist has users. First user is admin.
            return min(self._allow) == tg_user_id
        return tg_user_id in self._admins

    def bootstrap_admin(self, tg_user_id: int) -> None:
        """If this is the first successful login and no admin is configured, promote them."""
        if not self._admins and not self._allow:
            self._allow.add(tg_user_id)
            self._admins.add(tg_user_id)
            self._save()

    def add_allowed(self, tg_user_id: int) -> None:
        self._allow.add(tg_user_id)
        self._save()

    def remove_allowed(self, tg_user_id: int) -> None:
        self._allow.discard(tg_user_id)
        self._admins.discard(tg_user_id)
        self._save()

    def add_admin(self, tg_user_id: int) -> None:
        self._allow.add(tg_user_id)
        self._admins.add(tg_user_id)
        self._save()

    def list_allowed(self) -> list[int]:
        return sorted(self._allow)

    def list_admins(self) -> list[int]:
        return sorted(self._admins)
