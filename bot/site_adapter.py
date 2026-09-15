from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import httpx
from playwright.sync_api import Browser, Page, sync_playwright

from .config import Config


@dataclass
class BrowserSession:
    playwright: object
    browser: Browser
    page: Page


@dataclass(frozen=True)
class VisibleMarket:
    name: str
    up_percent: int | None
    down_percent: int | None
    settlement_text: str


class SiteAdapter:
    """Paper-only site adapter with optional hosted phone login relay."""

    def __init__(self, config: Config, notify: Callable[[str], None] | None = None):
        self.config = config
        self.notify = notify or (lambda _: None)
        self.session: BrowserSession | None = None
        self.remote_token: str | None = None
        self.remote_client = httpx.Client(timeout=25)

    def open_for_manual_login(self, username: str | None = None) -> str:
        if self.config.remote_login_url:
            return self._open_remote_login(username)
        if self.session:
            if not self._session_is_alive():
                self.close()
            else:
                self.session.page.bring_to_front()
                if username:
                    self._prefill_username(username)
                return "The secure browser window is active. Enter your password and OTP in that browser window only."
        if not self.config.is_allowed_url(self.config.target_url):
            raise ValueError("Target URL is not allowlisted")
        if not self.config.browser_headless and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return (
                "No visible desktop is available in this bot process, so no browser popup can appear. "
                "Configure REMOTE_LOGIN_URL and REMOTE_BOT_SECRET for phone login, or run the bot on the "
                "tester's machine with BROWSER_HEADLESS=false.\n"
                "Do not send a password, OTP, recovery code, or API secret to Telegram."
            )
        pw = sync_playwright().start()
        try:
            launch_options = {"headless": self.config.browser_headless}
            if not self.config.browser_headless:
                launch_options["args"] = [f"--app={self.config.target_url}", "--no-first-run"]
            browser = pw.chromium.launch(**launch_options)
            page = browser.new_page()
            page.goto(self.config.target_url, wait_until="domcontentloaded")
            self.session = BrowserSession(pw, browser, page)
            page.bring_to_front()
            if username:
                self._prefill_username(username)
        except Exception:
            pw.stop()
            raise
        if self.config.browser_headless:
            return "A headless browser session started, but it has no visible window. Configure phone login or run locally with BROWSER_HEADLESS=false. Do not send credentials or OTPs to Telegram."
        return "Secure browser login window opened and focused. Enter your password and OTP directly in that browser window. Do not send credentials or OTPs to Telegram. When finished, use /status."

    def _open_remote_login(self, username: str | None = None) -> str:
        if self.remote_token and self.is_open():
            return f"Secure phone login is already active. Open this one-time link:\n{self._remote_login_link()}"
        if not self.config.remote_bot_secret:
            return "Remote login is not configured: set REMOTE_BOT_SECRET in both the bot and hosted login service."
        response = self.remote_client.post(
            f"{self.config.remote_login_url}/api/remote/sessions",
            headers={"x-remote-bot-secret": self.config.remote_bot_secret},
            json={"targetUrl": self.config.target_url, "username": username or ""},
        )
        response.raise_for_status()
        payload = response.json()
        self.remote_token = payload["token"]
        return (
            "Secure phone login is ready. Open this one-time link on the judge's phone:\n"
            f"{self._remote_login_link(payload.get('loginUrl'))}\n"
            "The link expires in 15 minutes. Enter the password and OTP only in that browser page; never send them to Telegram."
        )

    def _remote_login_link(self, path: str | None = None) -> str:
        return f"{self.config.remote_login_url}{path or f'/remote/{self.remote_token}'}"

    def _prefill_username(self, username: str) -> None:
        """Fill only a visible username-like field; never inspect or fill secrets."""
        if not self.session or not username:
            return
        for selector in ("input[autocomplete='username']", "input[type='email']", "input[name*='user' i]", "input[name*='email' i]"):
            field = self.session.page.locator(selector).first
            if field.count() and field.is_visible():
                field.fill(username)
                return

    def _session_is_alive(self) -> bool:
        if not self.session:
            return False
        try:
            return self.session.browser.is_connected() and not self.session.page.is_closed()
        except Exception:
            return False

    def close(self) -> None:
        if self.remote_token:
            try:
                self.remote_client.post(
                    f"{self.config.remote_login_url}/api/remote/sessions/{self.remote_token}/close",
                    headers={"x-remote-bot-secret": self.config.remote_bot_secret},
                )
            finally:
                self.remote_token = None
        if self.session:
            self.session.browser.close()
            self.session.playwright.stop()
            self.session = None

    def is_open(self) -> bool:
        if self.remote_token:
            try:
                response = self.remote_client.get(f"{self.config.remote_login_url}/api/remote/sessions/{self.remote_token}/state")
                if response.is_success:
                    return True
            except httpx.HTTPError:
                pass
            self.remote_token = None
            return False
        return self._session_is_alive()

    def inspect_visible_markets(self) -> list[VisibleMarket]:
        """Read visible market cards; never calls a private API."""
        if self.remote_token:
            response = self.remote_client.post(
                f"{self.config.remote_login_url}/api/remote/sessions/{self.remote_token}/inspect",
                headers={"x-remote-bot-secret": self.config.remote_bot_secret},
            )
            response.raise_for_status()
            return [VisibleMarket(m["name"], m["upPercent"], m["downPercent"], m["settlementText"]) for m in response.json()["markets"]]
        if not self.session:
            raise RuntimeError("Open the site with /login first")
        cards = self.session.page.locator("[data-market-card], [data-testid='market-card']")
        markets: list[VisibleMarket] = []
        for i in range(min(cards.count(), 8)):
            text = cards.nth(i).inner_text()
            markets.append(VisibleMarket(text.splitlines()[0][:80] or f"market-{i + 1}", _percent_after(text, "up"), _percent_after(text, "down"), text[:240]))
        return markets

    def paper_click(self, market_index: int, side: str) -> None:
        """Click only an explicitly marked paper/demo control on an authorized site."""
        if self.remote_token:
            response = self.remote_client.post(
                f"{self.config.remote_login_url}/api/remote/sessions/{self.remote_token}/paper-click",
                headers={"x-remote-bot-secret": self.config.remote_bot_secret},
                json={"index": market_index, "side": side},
            )
            response.raise_for_status()
            return
        if not self.config.paper_mode:
            raise RuntimeError("Live mode is disabled")
        if not self.session:
            raise RuntimeError("Open the site with /login first")
        if self.session.page.locator("[data-paper-trading='true'], [data-mode='paper']").count() == 0:
            raise RuntimeError("Refusing to click: page does not identify itself as paper/demo mode")
        if side not in {"UP", "DOWN"} or not 0 <= market_index < 8:
            raise ValueError("Invalid market index or side")
        self.session.page.locator("[data-market-card], [data-testid='market-card']").nth(market_index).get_by_role("button", name=side, exact=True).click()

    def run_live_trade(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Live trading is disabled in this prototype")


def _percent_after(text: str, word: str) -> int | None:
    parts = text.replace("%", " % ").split()
    for i, part in enumerate(parts[:-1]):
        if part.lower() == word.lower() and parts[i + 1].isdigit():
            value = int(parts[i + 1])
            return value if 0 <= value <= 100 else None
    return None
