from bot.__main__ import _looks_like_secret
from bot.site_adapter import BrowserSession, SiteAdapter
from tests.test_config import config


def test_secret_guard_rejects_common_credential_shapes():
    assert _looks_like_secret("password=not-for-telegram")
    assert _looks_like_secret("123456")
    assert _looks_like_secret("my OTP is 123456")
    assert not _looks_like_secret("judge@example.com")


def test_login_explains_when_no_visible_desktop(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    adapter = SiteAdapter(config())
    message = adapter.open_for_manual_login("judge@example.com")
    assert "No visible desktop" in message
    assert "password" in message.lower()
    assert not adapter.is_open()


def test_dead_browser_session_is_not_alive():
    class DeadBrowser:
        def is_connected(self):
            return False

    class Page:
        def is_closed(self):
            return False

    adapter = SiteAdapter(config())
    adapter.session = BrowserSession(object(), DeadBrowser(), Page())
    assert not adapter._session_is_alive()
