"""Verify Telegram Mini App `initData`.

Algorithm (per Telegram docs):
  1. Parse `initData` as URL-encoded key=value pairs.
  2. Remove the `hash` field; keep the rest and join sorted by key as
     `key=value\nkey=value...` (data_check_string).
  3. secret_key = HMAC_SHA256(key="WebAppData", data=bot_token)
  4. expected_hash = HMAC_SHA256(key=secret_key, data=data_check_string)
  5. Compare with the provided `hash` (hex) in constant time.

Return a parsed payload {user: {id, ...}, auth_date, query_id, ...} on success.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

AUTH_DATA_MAX_AGE_SECONDS = 24 * 3600


@dataclass
class InitDataUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


@dataclass
class VerifiedInitData:
    user: InitDataUser
    auth_date: int
    raw: dict[str, Any]


class InitDataError(Exception):
    pass


def verify_init_data(init_data: str, bot_token: str) -> VerifiedInitData:
    if not init_data:
        raise InitDataError("empty init_data")

    pairs = dict(parse_qsl(init_data, strict_parsing=False, keep_blank_values=True))
    provided_hash = pairs.pop("hash", "")
    if not provided_hash:
        raise InitDataError("missing_hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, provided_hash):
        raise InitDataError("invalid_hash")

    auth_date_raw = pairs.get("auth_date")
    try:
        auth_date = int(auth_date_raw) if auth_date_raw else 0
    except ValueError as e:
        raise InitDataError("bad_auth_date") from e

    if auth_date and (time.time() - auth_date) > AUTH_DATA_MAX_AGE_SECONDS:
        raise InitDataError("expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataError("missing_user")
    try:
        user_dict = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise InitDataError("bad_user_json") from e

    user = InitDataUser(
        id=int(user_dict["id"]),
        first_name=user_dict.get("first_name"),
        last_name=user_dict.get("last_name"),
        username=user_dict.get("username"),
        language_code=user_dict.get("language_code"),
    )
    return VerifiedInitData(user=user, auth_date=auth_date, raw=pairs)
