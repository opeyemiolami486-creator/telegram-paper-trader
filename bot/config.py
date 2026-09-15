from __future__ import annotations

import os
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    public_access: bool
    target_url: str
    allowed_hosts: frozenset[str]
    pairs: tuple[str, ...]
    paper_mode: bool
    round_credits: int
    daily_credit_limit: int
    stop_loss_credits: int | None
    settlement_min_seconds: int
    settlement_max_seconds: int
    browser_headless: bool

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        user_ids = frozenset(int(x.strip()) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")).split(",") if x.strip())
        target = os.environ.get("TARGET_URL", "").strip()
        hosts = frozenset(x.strip().lower() for x in os.environ.get("ALLOWED_HOSTS", "").split(",") if x.strip())
        pairs = tuple(x.strip() for x in os.environ.get("PAIR_NAMES", "").split(",") if x.strip())
        public_access = os.environ.get("TELEGRAM_PUBLIC_ACCESS", "false").lower() == "true"
        if not token or (not user_ids and not public_access) or not target or not hosts:
            raise ValueError("TELEGRAM_BOT_TOKEN, a Telegram user ID (unless public access is enabled), TARGET_URL, and ALLOWED_HOSTS are required")
        if len(pairs) != 8:
            raise ValueError("PAIR_NAMES must contain exactly 8 comma-separated names")
        parsed = urlparse(target)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("TARGET_URL must be an http(s) URL")
        if parsed.hostname.lower() not in hosts:
            raise ValueError("TARGET_URL hostname must be present in ALLOWED_HOSTS")
        stop_loss_raw = os.environ.get("STOP_LOSS_CREDITS", "3").strip().lower()
        if stop_loss_raw in {"", "none", "unlimited", "off"}:
            stop_loss = None
        else:
            stop_loss = int(stop_loss_raw)
            if stop_loss < 0:
                raise ValueError("STOP_LOSS_CREDITS must be non-negative or unlimited")
        settlement_min = max(0, int(os.environ.get("SETTLEMENT_MIN_SECONDS", "0")))
        settlement_max = min(60, int(os.environ.get("SETTLEMENT_MAX_SECONDS", "60")))
        if settlement_min > settlement_max:
            raise ValueError("SETTLEMENT_MIN_SECONDS cannot exceed SETTLEMENT_MAX_SECONDS")
        return cls(
            telegram_token=token,
            allowed_user_ids=user_ids,
            public_access=public_access,
            target_url=target,
            allowed_hosts=hosts,
            pairs=pairs,
            paper_mode=os.environ.get("PAPER_MODE", "true").lower() == "true",
            round_credits=max(1, int(os.environ.get("ROUND_CREDITS", "1"))),
            daily_credit_limit=max(1, int(os.environ.get("DAILY_CREDIT_LIMIT", "10"))),
            stop_loss_credits=stop_loss,
            settlement_min_seconds=settlement_min,
            settlement_max_seconds=settlement_max,
            browser_headless=os.environ.get("BROWSER_HEADLESS", "false").lower() == "true",
        )

    @property
    def allowed_user_id(self) -> int | None:
        """Backward-compatible primary recipient for private mode."""
        return next(iter(self.allowed_user_ids), None)

    def is_allowed_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host in self.allowed_hosts

    def with_target_url(self, target_url: str) -> "Config":
        parsed = urlparse(target_url.strip())
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("URL must use http:// or https:// and include a hostname")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing embedded credentials are not accepted")
        if parsed.fragment:
            raise ValueError("URL fragments are not accepted")
        host = parsed.hostname.lower()
        return replace(self, target_url=target_url.strip(), allowed_hosts=frozenset({host}))
