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


@dataclass(frozen=True)
class VisibleMarket:
    name: str
    up_percent: int | None
    down_percent: int | None
    settlement_text: str


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
        if self.config.browser_headless:
            return (
                "A headless browser session started, but it is not visible on Railway. "
                "For manual username/password/OTP entry, run the bot locally with "
                "BROWSER_HEADLESS=false or use an authorized judge test account without OTP. "
                "Do not send credentials or OTPs to Telegram."
            )
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

    def inspect_visible_markets(self) -> list[VisibleMarket]:
        """Read visible Cade-style cards; never calls a private API."""
        if not self.session:
            raise RuntimeError("Open the site with /login first")
        cards = self.session.page.locator("[data-market-card], [data-testid='market-card']")
        markets: list[VisibleMarket] = []
        for i in range(min(cards.count(), 8)):
            card = cards.nth(i)
            text = card.inner_text()
            markets.append(VisibleMarket(
                name=text.splitlines()[0][:80] or f"market-{i + 1}",
                up_percent=_percent_after(text, "up"),
                down_percent=_percent_after(text, "down"),
                settlement_text=text[:240],
            ))
        return markets

    def paper_click(self, market_index: int, side: str) -> None:
        """Click only an explicitly marked paper/demo control on an authorized site."""
        if not self.config.paper_mode:
            raise RuntimeError("Live mode is disabled")
        if not self.session:
            raise RuntimeError("Open the site with /login first")
        marker = self.session.page.locator("[data-paper-trading='true'], [data-mode='paper']")
        if marker.count() == 0:
            raise RuntimeError("Refusing to click: page does not identify itself as paper/demo mode")
        if side not in {"UP", "DOWN"} or not 0 <= market_index < 8:
            raise ValueError("Invalid market index or side")
        card = self.session.page.locator("[data-market-card], [data-testid='market-card']").nth(market_index)
        card.get_by_role("button", name=side, exact=True).click()

    def run_live_trade(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Live trading is disabled in this prototype")


def _percent_after(text: str, word: str) -> int | None:
    parts = text.replace("%", " % ").split()
    for i, part in enumerate(parts[:-1]):
        if part.lower() == word.lower() and parts[i + 1].isdigit():
            value = int(parts[i + 1])
            return value if 0 <= value <= 100 else None
    return None
