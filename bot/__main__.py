from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import date

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
        text = (message.get("text") or "").strip().lower()
        if not chat_id:
            return
        self.reset_day()
        if text == "/start":
            await self.send(chat_id, "Safety-first paper trader. OTPs and passwords must be entered only in the visible browser.\nCommands: /login /status /pairs /run /pause /resume /stop")
        elif text == "/login":
            await self.send(chat_id, await asyncio.to_thread(self.adapter.open_for_manual_login))
        elif text == "/status":
            await self.send(chat_id, f"mode={'PAPER' if self.config.paper_mode else 'BLOCKED'} paused={self.paused} browser_open={self.adapter.is_open()} spent_today={self.spent_today}/{self.config.daily_credit_limit} losses_today={self.losses_today}/{self.config.stop_loss_credits}")
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
            for pair in order:
                # No odds source is connected by default. This safely abstains.
                decision = choose_lowest_probability(None)
                if decision.side is None:
                    await self.send(chat_id, f"{pair}: ABSTAIN — {decision.reason}")
                    continue
                self.spent_today += self.config.round_credits
                await self.send(chat_id, f"{pair}: PAPER {decision.side.value}; waiting for settlement")
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
