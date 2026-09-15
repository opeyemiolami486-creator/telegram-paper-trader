import pytest

from bot.config import Config


def config():
    return Config(
        telegram_token="token",
        allowed_user_ids=frozenset({1}),
        public_access=False,
        target_url="https://example.com",
        allowed_hosts=frozenset({"example.com"}),
        pairs=tuple(f"P{i}" for i in range(8)),
        paper_mode=True,
        round_credits=1,
        daily_credit_limit=10,
        stop_loss_credits=3,
        settlement_min_seconds=0,
        settlement_max_seconds=60,
        browser_headless=False,
    )


def test_runtime_site_replaces_exact_allowlist():
    updated = config().with_target_url("https://Judge.Example/path/CaseSensitive")
    assert updated.target_url.endswith("/path/CaseSensitive")
    assert updated.allowed_hosts == frozenset({"judge.example"})


def test_public_mode_does_not_require_user_ids():
    assert config().public_access is False


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:pass@example.com", "https://example.com/#secret"])
def test_runtime_site_rejects_unsafe_url(url):
    with pytest.raises(ValueError):
        config().with_target_url(url)
