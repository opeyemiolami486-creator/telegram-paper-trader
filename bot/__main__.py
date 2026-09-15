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

    def reset_day(self) -> None:
        if date.today() != self.today:
            self.today = date.today()
            self.spent_today = 0
            self.losses_today = 0

    async def send(self, chat_id: int, text: str) -> None:
        await self.client.post(f"{self.base}/sendMessage", data={"chat_id": chat_id, "text": text})

    def authorized(self, update: dict) -> bool:
        sender = update.get("message", {}).get("from", {}).get("id")
        return sender == self.config.allowed_user_id

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
        if text == "/start":
            await self.send(chat_id, "Safety-first paper trader. OTPs and passwords must be entered only in the visible browser.\nCommands: /site /login /inspect /status /pairs /run /pause /resume /stop")
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
            await self.send(chat_id, await asyncio.to_thread(self.adapter.open_for_manual_login))
        elif text == "/status":
            await self.send(chat_id, f"mode={'PAPER' if self.config.paper_mode else 'BLOCKED'} site={self.config.target_url} paused={self.paused} browser_open={self.adapter.is_open()} spent_today={self.spent_today}/{self.config.daily_credit_limit} losses_today={self.losses_today}/{self.config.stop_loss_credits}")
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
            if self.losses_today >= self.config.stop_loss_credits:
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
                await asyncio.sleep(self.config.settlement_seconds)
            await self.send(chat_id, f"Cycle settled. Credits used today: {self.spent_today}/{self.config.daily_credit_limit}")

    async def run(self) -> None:
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


def main() -> None:
    config = Config.from_env()
    asyncio.run(TelegramBot(config).run())


if __name__ == "__main__":
    main()
