# Telegram Website Paper Trader

A safety-first Python prototype for a Telegram-controlled **paper-trading** workflow against a website you provide.

Public repository: https://github.com/opeyemiolami486-creator/telegram-paper-trader

> **Important:** This repository does not place live trades, allocate real credits, bypass authentication, or collect passwords/OTPs in Telegram. It opens the supplied website in a visible browser and asks the operator to type credentials and OTPs directly into that browser. The default execution mode is simulation only.

## What it does

- Accepts a website URL through configuration.
- Restricts navigation to an explicit host allowlist.
- Uses a visible Playwright browser so the operator can complete login and OTP manually.
- Provides Telegram commands for status, pause/resume, and a paper-trading cycle.
- Randomizes the order of eight configured pairs.
- Supports `UP` and `DOWN` paper decisions.
- Uses a conservative **abstain-by-default** strategy: it only selects the side with the lower supplied probability when both probabilities are present and within bounds; it never guesses probabilities from page appearance.
- Waits for a simulated settlement in paper mode and records an audit log.
- Enforces per-round credits, daily credits, and stop-loss limits.

## What it intentionally does not do

- No live credit allocation or live trading.
- No Telegram collection or storage of passwords, OTPs, recovery codes, or API secrets.
- No arbitrary backend/API access.
- No CAPTCHA solving, anti-bot bypass, stealth mode, or hidden browser.
- No claim that a lower probability means a better trade. The “lowest probability” rule is included only as a configurable hackathon strategy and defaults to abstention unless a trusted probability feed is provided.

## Setup

1. Create a Telegram bot with BotFather and keep the token private.
2. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and your Telegram user ID.
3. Add only the website hostnames you are authorized to automate to `ALLOWED_HOSTS`.
4. Install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

5. Run:

```bash
python -m bot
```

## Telegram commands

- `/start` — show the safety notice and available commands.
- `/status` — show current mode, pause state, and limits.
- `/login` — open the configured website in a visible browser. Enter username, password, and OTP **in the browser only**.
- `/pairs` — show the eight configured paper pairs.
- `/run` — run one randomized paper cycle.
- `/pause` and `/resume` — control cycles.
- `/stop` — emergency stop and close the browser.

The bot accepts commands only from `TELEGRAM_ALLOWED_USER_ID`; all other users are rejected.

## Website adaptation

Every site has different selectors and settlement behavior. This project deliberately does not guess selectors or attempt to defeat protections. To adapt it, implement a site-specific `SiteAdapter` in `bot/site_adapter.py` using the website's documented/public interface or selectors you are authorized to use. Keep live execution disabled until the site owner explicitly permits automation and the adapter has been tested against a sandbox.

The generic adapter only opens the page and reports that manual login is required. It does not click a real trade button.

## Environment variables

See `.env.example`. Never commit `.env` or secrets. Use a local machine or a properly secured private host for a long-running bot; the default Manus sandbox is not a reliable always-on service.

## Testing

```bash
pytest -q
```

## Judge demo

Judges can run a deterministic local demonstration without Telegram credentials or a real website:

```bash
python demo.py
```

The demo creates eight local mock pairs, randomizes their order, selects the lower **supplied** probability, waits for simulated settlement, and prints an audit trail. It never opens a real browser and never allocates credits. This is the supported way to test the project when no authorized sandbox or documented API has been provided.

Testing against a real website requires the website owner’s permission, a test account or sandbox, and site-specific selectors or an official API. The generic adapter intentionally refuses to click live trade controls.

## License

MIT for the prototype code. You are responsible for complying with the website's terms, applicable laws, and hackathon rules.
