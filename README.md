# Telegram Website Paper Trader

A safety-first Python prototype for a Telegram-controlled **paper-trading** workflow against a website you provide.

Public repository: https://github.com/opeyemiolami486-creator/telegram-paper-trader

> **Important:** This repository does not place live trades, allocate real credits, bypass authentication, or collect passwords/OTPs in Telegram. It opens the supplied website in a visible browser and asks the operator to type credentials and OTPs directly into that browser. The default execution mode is simulation only.

## What it does

- Asks for an authorized test website URL through Telegram with `/site`, validates it, and allowlists only its exact hostname.
- Restricts navigation to an explicit host allowlist.
- Uses a visible Playwright browser so the operator can complete login and OTP manually.
- Provides Telegram commands for status, pause/resume, and a paper-trading cycle.
- Randomizes the order of eight configured pairs.
- Supports `UP` and `DOWN` paper decisions.
- Uses a conservative **abstain-by-default** strategy: it only selects the side with the lower supplied probability when both probabilities are present and within bounds; it never guesses probabilities from page appearance.
- Waits for a simulated settlement in paper mode and records an audit log.
- Enforces per-round credits, daily credits, and stop-loss limits.

The reference interaction model is inspired by [Cade Market](https://cade.market/), whose public page shows eight short-round markets with Up/Down percentages and settlement clocks. This repository uses that only as a UI concept reference; it does not automate Cade Market.

## What it intentionally does not do

- No live credit allocation or live trading.
- No Telegram collection or storage of passwords, OTPs, recovery codes, or API secrets.
- No arbitrary backend/API access.
- No automatic discovery of hidden endpoints or unrelated domains.
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
- `/site` — enter the authorized test website URL when the judge provides it.
- `/login` — open the selected website in a visible browser. Enter username, password, and OTP **in the browser only**.
- `/inspect` — read up to eight visible market cards from an authorized test page.
- `/pairs` — show the eight configured paper pairs.
- `/run` — run one randomized paper cycle.
- `/pause` and `/resume` — control cycles.
- `/stop` — emergency stop and close the browser.

The bot accepts commands only from `TELEGRAM_ALLOWED_USER_ID`; all other users are rejected.

## Website adaptation

Every site has different selectors and settlement behavior. The bot asks for the site at runtime, but URL adaptability is not the same as trade adaptability: this project deliberately does not guess selectors, discover private endpoints, or attempt to defeat protections. The reference adapter recognizes visible cards marked `data-market-card` or `data-testid="market-card"`; a paper-only click requires the page to explicitly mark itself with `data-paper-trading="true"` or `data-mode="paper"`. To adapt other markup, implement a site-specific `SiteAdapter` using documented/public selectors authorized by the test owner.

The generic adapter only opens the page and reports that manual login is required. It does not click a real trade button.

## Environment variables

See `.env.example`. Never commit `.env` or secrets. Use a local machine or a properly secured private host for a long-running bot; the default Manus sandbox is not a reliable always-on service.

## Testing

```bash
pytest -q
```

## Railway deployment

The repository includes `railway.toml` and a `Procfile`. Railway will install Python dependencies, install the Chromium runtime required by Playwright, and start the worker with `python -m bot`.

Set all variables from `.env.example` in Railway’s Variables panel. For a headless Railway worker, set `BROWSER_HEADLESS=true`. The Telegram polling loop can run on Railway, but Railway does not provide an interactive desktop, so manual username/password/OTP entry and visible-browser inspection must be performed on a local machine or an authorized remote desktop. Do not deploy credentials in source control.

The build was validated locally in a clean Python virtual environment: dependencies installed, all tests passed, and all Python modules compiled successfully. A live Railway deployment cannot be verified from this session because no Railway project or authenticated Railway CLI is connected.

## Judge testing

Testing against a real website requires the website owner’s permission, a test account or sandbox, and site-specific selectors or an official API. A judge can send `/site`, provide the authorized test URL, then use `/login` and complete login/OTP directly in the visible browser. The generic adapter intentionally refuses to click live trade controls; it demonstrates secure site selection and paper-trading orchestration instead.

## License

MIT for the prototype code. You are responsible for complying with the website's terms, applicable laws, and hackathon rules.
