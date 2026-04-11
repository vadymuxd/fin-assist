# Fin Assist

Personal AI chief of staff for finances. Tracks investments, monitors prices, scores holdings with Claude, and delivers alerts via Telegram.

---

## Architecture

Three layers running on GitHub Actions — no always-on Mac required.

| Layer | What it does | Technology |
|-------|-------------|------------|
| **Data** | Portfolio, live prices, sentiment, expenses | Google Sheets + yfinance + Emma |
| **Brain** | Scoring, recommendations, analysis | Claude API |
| **Interface** | Alerts, weekly digest, conversation | Telegram + claude.ai |

Runs twice daily (8am + 3:30pm weekdays) via GitHub Actions cron.

---

## Memory

Claude remembers context across all surfaces via **Notion**:

- **Mac (Claude Code)** — reads `CLAUDE.md` → fetches Agent Config + Memory Index from Notion
- **Mobile (claude.ai)** — Fin Assist Claude Project fetches same Notion pages on startup
- **Sessions DB** — structured log of every meaningful decision or outcome

Notion is the single source of truth. Local `memory/` folder was removed in Phase 2.

---

## Project Structure

```
fin-assist/
├── scripts/
│   ├── price_monitor.py        # Fetches prices, detects spikes/drops (built, placeholder tickers)
│   ├── memory_reminder.sh      # Stop hook: reminds Claude to update Notion every 5 turns
│   └── ...                     # remaining scripts — built in Phase 5
├── config/
│   ├── service_account.json    # Google Sheets access (gitignored)
│   └── thresholds.json         # Per-stock alert thresholds
├── .github/workflows/          # GitHub Actions cron jobs (Phase 5)
├── CLAUDE.md                   # Claude Code session instructions
├── PLAN.md                     # Full phase-by-phase build plan
└── .env                        # Secrets (gitignored) — see .env.example
```

---

## Setup

```bash
# Clone and install dependencies
git clone https://github.com/vadymuxd/fin-assist
cd fin-assist
pip install -r requirements.txt

# Copy and fill in secrets
cp .env.example .env
```

Required secrets in `.env`:
- `CLAUDE_API_KEY`
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
- `PORTFOLIO_SHEET_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` (path to service account JSON)

---

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundations & Infrastructure | ✅ Complete |
| 2 | Memory & Assistant Continuity | ✅ Complete |
| 3 | Data Import & Sheet Scaffolding | ❌ Not started |
| 4 | Design Session | ❌ Not started |
| 5 | Scripts & Automation | ⏳ In progress |
| 6 | App & UI | ❌ Not started |
| 7–10 | Savings, Pensions, Mortgage, Budgeting | ❌ Not started |

See [PLAN.md](PLAN.md) for full detail.
