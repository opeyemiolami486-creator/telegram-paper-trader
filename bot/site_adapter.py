from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import Browser, Page, sync_playwright

from .config import Config


@dataclass
class BrowserSession:
    playwright: object
    browser: Browser
    page: Page


class SiteAdapter:
    """Generic adapter: open and observe only; no live trade clicks."""

    def __init__(self, config: Config, notify: Callable[[str], None] | None = None):
        self.config = config
        self.notify = notify or (lambda _: None)
        self.session: BrowserSession | None = None

    def open_for_manual_login(self) -> str:
        if self.session:
            return "A browser session is already open. Enter credentials and OTP in the browser window."
        if not self.config.is_allowed_url(self.config.target_url):
            raise ValueError("Target URL is not allowlisted")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=self.config.browser_headless)
        page = browser.new_page()
        page.goto(self.config.target_url, wait_until="domcontentloaded")
        self.session = BrowserSession(pw, browser, page)
        return (
            "Browser opened. Enter username, password, and OTP directly in that browser window. "
            "Do not send credentials or OTPs to Telegram. When finished, use /status."
        )

    def close(self) -> None:
        if self.session:
            self.session.browser.close()
            self.session.playwright.stop()
            self.session = None

    def is_open(self) -> bool:
        return self.session is not None

    def run_live_trade(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Live trading is disabled in this prototype")
