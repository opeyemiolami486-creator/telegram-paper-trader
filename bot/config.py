from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_user_id: int
    target_url: str
    allowed_hosts: frozenset[str]
    pairs: tuple[str, ...]
    paper_mode: bool
    round_credits: int
    daily_credit_limit: int
    stop_loss_credits: int
    settlement_seconds: int
    browser_headless: bool

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        user_id = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
        target = os.environ.get("TARGET_URL", "").strip()
        hosts = frozenset(x.strip().lower() for x in os.environ.get("ALLOWED_HOSTS", "").split(",") if x.strip())
        pairs = tuple(x.strip() for x in os.environ.get("PAIR_NAMES", "").split(",") if x.strip())
        if not token or not user_id or not target or not hosts:
            raise ValueError("TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID, TARGET_URL, and ALLOWED_HOSTS are required")
        if len(pairs) != 8:
            raise ValueError("PAIR_NAMES must contain exactly 8 comma-separated names")
        parsed = urlparse(target)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("TARGET_URL must be an http(s) URL")
        if parsed.hostname.lower() not in hosts:
            raise ValueError("TARGET_URL hostname must be present in ALLOWED_HOSTS")
        return cls(
            telegram_token=token,
            allowed_user_id=int(user_id),
            target_url=target,
            allowed_hosts=hosts,
            pairs=pairs,
            paper_mode=os.environ.get("PAPER_MODE", "true").lower() == "true",
            round_credits=max(1, int(os.environ.get("ROUND_CREDITS", "1"))),
            daily_credit_limit=max(1, int(os.environ.get("DAILY_CREDIT_LIMIT", "10"))),
            stop_loss_credits=max(0, int(os.environ.get("STOP_LOSS_CREDITS", "3"))),
            settlement_seconds=max(0, int(os.environ.get("SETTLEMENT_SECONDS", "10"))),
            browser_headless=os.environ.get("BROWSER_HEADLESS", "false").lower() == "true",
        )

    def is_allowed_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host in self.allowed_hosts
