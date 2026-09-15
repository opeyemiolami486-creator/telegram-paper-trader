from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import date
from urllib.parse import urlparse

import httpx

from .config import Config
from .site_adapter import SiteAdapter
from .strategy import Side, choose_lowest_probability

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.base = f"https://api.telegram.org/bot{config.telegram_token}"
        self.client = httpx.AsyncClient(timeout=40)
        self.adapter = SiteAdapter(config)
        self.paused = True
        self.spent_today = 0
        self.losses_today = 0
        self.today = date.today()
        self.offset = 0
        self.lock = asyncio.Lock()
        self.awaiting_site = False
        self.awaiting_username: set[int] = set()
        self.pending_usernames: dict[int, str] = {}

    def reset_day(self) -> None:
        if date.today() != self.today:
            self.today = date.today()
            self.spent_today = 0
            self.losses_today = 0

    async def send(self, chat_id: int, text: str) -> None:
        await self.client.post(f"{self.base}/sendMessage", data={"chat_id": chat_id, "text": text})

    def authorized(self, update: dict) -> bool:
        sender = update.get("message", {}).get("from", {}).get("id")
        return self.config.public_access or sender in self.config.allowed_user_ids

    async def handle(self, update: dict) -> None:
        if not self.authorized(update):
            LOG.warning("Rejected Telegram user")
            return
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        raw_text = (message.get("text") or "").strip()
        text = raw_text.lower()
        if not chat_id:
            return
        self.reset_day()
        if self.awaiting_site and not text.startswith("/"):
            self.awaiting_site = False
            try:
                self.config = self.config.with_target_url(raw_text)
                self.adapter.config = self.config
                await self.send(chat_id, f"Test site saved: {self.config.target_url}\nHost allowlist updated for this exact host. Use /login to open it in a visible browser. Live trading remains disabled.")
            except ValueError as exc:
                await self.send(chat_id, f"Site rejected: {exc}\nSend a full http(s) URL, or use /site to try again.")
            return
        if chat_id in self.awaiting_username and not text.startswith("/"):
            self.awaiting_username.discard(chat_id)
            if _looks_like_secret(raw_text):
                await self.send(chat_id, "For your protection, do not send passwords, OTPs, recovery codes, or API secrets to Telegram. Use /login and enter them only in the browser.")
                return
            self.pending_usernames[chat_id] = raw_text[:200]
            await self.send(chat_id, "Username saved in memory for this login attempt only. Opening the authorized site now; enter your password and OTP in the browser only.")
            await self.send(chat_id, await self.login_message(raw_text[:200]))
            self.pending_usernames.pop(chat_id, None)
            return
        if text == "/start":
            access = "public judge mode" if self.config.public_access else "private allowlist mode"
            await self.send(chat_id, f"Safety-first paper trader ({access}). /login asks for an optional username, then opens the authorized site. Passwords and OTPs must be entered only in the browser.\nCommands: /site /login /cancel /inspect /status /pairs /run /pause /resume /stop")
        elif text == "/site":
            self.awaiting_site = True
            await self.send(chat_id, "Send the full http(s) URL of the authorized test website. I will allowlist only its exact hostname and open only that URL; I will not access arbitrary backend endpoints.")
        elif text.startswith("/site "):
            self.awaiting_site = False
            try:
                self.config = self.config.with_target_url(raw_text[6:].strip())
                self.adapter.config = self.config
                await self.send(chat_id, f"Test site saved: {self.config.target_url}\nUse /login to open it in a visible browser. Live trading remains disabled.")
            except ValueError as exc:
                await self.send(chat_id, f"Site rejected: {exc}")
        elif text == "/login":
            self.awaiting_username.add(chat_id)
            await self.send(chat_id, "Optional: send your username only to prefill the browser. Never send a password, OTP, recovery code, or API secret here. Or use /cancel to open without a username.")
        elif text.startswith("/login "):
            username = raw_text[7:].strip()
            if _looks_like_secret(username):
                await self.send(chat_id, "Login details rejected. Do not send passwords, OTPs, recovery codes, or API secrets to Telegram.")
            else:
                await self.send(chat_id, await self.login_message(username[:200]))
        elif text == "/cancel":
            self.awaiting_username.discard(chat_id)
            self.pending_usernames.pop(chat_id, None)
            await self.send(chat_id, await self.login_message())
        elif text == "/status":
            loss_limit = self.config.stop_loss_credits if self.config.stop_loss_credits is not None else "unlimited"
            await self.send(chat_id, f"mode={'PAPER' if self.config.paper_mode else 'BLOCKED'} site={self.config.target_url} paused={self.paused} browser_open={self.adapter.is_open()} spent_today={self.spent_today}/{self.config.daily_credit_limit} losses_today={self.losses_today}/{loss_limit}")
        elif text == "/inspect":
            try:
                markets = await asyncio.to_thread(self.adapter.inspect_visible_markets)
                if not markets:
                    await self.send(chat_id, "No supported visible market cards found. Expected data-market-card or data-testid=market-card.")
                else:
                    await self.send(chat_id, "\n".join(f"{i + 1}. {m.name} | Up={m.up_percent}% Down={m.down_percent}%" for i, m in enumerate(markets)))
            except Exception as exc:
                await self.send(chat_id, f"Inspection stopped safely: {exc}")
        elif text == "/pairs":
            await self.send(chat_id, "Configured pairs:\n" + "\n".join(f"- {p}" for p in self.config.pairs))
        elif text == "/pause":
            self.paused = True
            await self.send(chat_id, "Paused. No cycle will run until /resume.")
        elif text == "/resume":
            self.paused = False
            await self.send(chat_id, "Resumed, but this prototype remains paper-trading only.")
        elif text == "/stop":
            self.paused = True
            await asyncio.to_thread(self.adapter.close)
            await self.send(chat_id, "Emergency stop complete; browser closed and bot paused.")
        elif text == "/run":
            await self.run_cycle(chat_id)
        else:
            await self.send(chat_id, "Unknown command. Use /start for help.")

    async def run_cycle(self, chat_id: int) -> None:
        async with self.lock:
            self.reset_day()
            if not self.config.paper_mode:
                await self.send(chat_id, "Blocked: PAPER_MODE must remain true in this prototype.")
                return
            if self.paused:
                await self.send(chat_id, "Paused. Use /resume before /run.")
                return
            if self.spent_today + self.config.round_credits > self.config.daily_credit_limit:
                await self.send(chat_id, "Daily credit limit reached; refusing to continue.")
                return
            if self.config.stop_loss_credits is not None and self.losses_today >= self.config.stop_loss_credits:
                await self.send(chat_id, "Stop-loss limit reached; refusing to continue.")
                return
            order = list(self.config.pairs)
            random.SystemRandom().shuffle(order)
            await self.send(chat_id, "Paper cycle order:\n" + " -> ".join(order))
            visible = []
            if self.adapter.is_open():
                try:
                    visible = await asyncio.to_thread(self.adapter.inspect_visible_markets)
                except Exception as exc:
                    await self.send(chat_id, f"Visible-market inspection failed safely: {exc}")
            for index, pair in enumerate(order):
                probabilities = None
                if index < len(visible) and visible[index].up_percent is not None and visible[index].down_percent is not None:
                    probabilities = {
                        Side.UP: visible[index].up_percent / 100,
                        Side.DOWN: visible[index].down_percent / 100,
                    }
                decision = choose_lowest_probability(probabilities)
                if decision.side is None:
                    await self.send(chat_id, f"{pair}: ABSTAIN — {decision.reason}")
                    continue
                self.spent_today += self.config.round_credits
                try:
                    if self.adapter.is_open():
                        await asyncio.to_thread(self.adapter.paper_click, index, decision.side.value)
                    else:
                        raise RuntimeError("no visible browser session")
                    await self.send(chat_id, f"{pair}: PAPER {decision.side.value}; click recorded, waiting for settlement")
                except Exception as exc:
                    self.spent_today -= self.config.round_credits
                    await self.send(chat_id, f"{pair}: REFUSED — {exc}")
                    continue
                settlement_seconds = random.SystemRandom().randint(
                    self.config.settlement_min_seconds,
                    self.config.settlement_max_seconds,
                )
                await self.send(chat_id, f"{pair}: simulated settlement delay selected: {settlement_seconds}s")
                await asyncio.sleep(settlement_seconds)
            await self.send(chat_id, f"Cycle settled. Credits used today: {self.spent_today}/{self.config.daily_credit_limit}")

    async def login_message(self, username: str | None = None) -> str:
        try:
            return await asyncio.to_thread(self.adapter.open_for_manual_login, username)
        except Exception as exc:
            LOG.warning("Login handoff failed safely: %s", exc)
            return "Login handoff failed safely. Check the hosted relay URL, shared secret, and target allowlist, then try /login again."

    async def run(self) -> None:
        if self.config.allowed_user_id is not None:
            await self.send(self.config.allowed_user_id, "Bot online in PAPER mode. Use /start.")
        try:
            while True:
                response = await self.client.get(f"{self.base}/getUpdates", params={"timeout": 25, "offset": self.offset})
                response.raise_for_status()
                for update in response.json().get("result", []):
                    self.offset = update["update_id"] + 1
                    await self.handle(update)
        finally:
            await self.client.aclose()
            await asyncio.to_thread(self.adapter.close)


def _looks_like_secret(value: str) -> bool:
    """Conservative guard against accidentally accepting common secret-shaped input."""
    compact = value.replace(" ", "")
    lowered = value.lower()
    return (
        len(value) > 200
        or "otp" in lowered
        or "password" in lowered
        or "recovery" in lowered
        or (compact.isdigit() and len(compact) in {4, 5, 6, 7, 8})
    )


def main() -> None:
    config = Config.from_env()
    asyncio.run(TelegramBot(config).run())


if __name__ == "__main__":
    main()
