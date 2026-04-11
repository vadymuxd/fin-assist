# Fin Assist — Build Plan
**Personal Finance AI Assistant**
Last updated: April 2026

---

## Architecture

Cloud-hosted automation pipeline running on **GitHub Actions** (no Mac required to be always-on). Three layers:

| Layer | What it does | Technology |
|-------|-------------|------------|
| Data | Portfolio + live prices + sentiment + expenses + budget | Google Sheets + Yahoo Finance (yfinance) + Emma Live Export |
| Brain | Analysis, scoring, recommendations, budget monitoring | Claude API (called by scripts) |
| Interface | Alerts + weekly digest + conversational assistant | Telegram + Claude Project (claude.ai) |

**Key decision:** Checks run twice daily (8am + 3:30pm weekdays) via GitHub Actions cron. No always-on server needed.

**Notification channel:** Telegram (both urgent alerts and weekly digest)

---

## Phase 1 — Foundations ✅ COMPLETE

- [x] Python 3.13.4 confirmed
- [x] GitHub repo created: https://github.com/vadymuxd/fin-assist
- [x] Repo cloned to `/Users/vadymshcherbakov/Documents/Claude/Fin Assist/`
- [x] Folder structure created (`scripts/`, `config/`, `.github/workflows/`)
- [x] `requirements.txt` created and dependencies installed
- [x] `.gitignore` configured (excludes `.env`, service account JSON)
- [x] `.env.example` created
- [x] Telegram bot created: `@finassist_do_bot`
- [x] Telegram bot token + chat ID added to `.env`
- [x] Claude API key added to `.env`
- [x] Google Cloud project `fin-assist` created
- [x] Google Sheets API enabled
- [x] Service account created + JSON key saved to `config/service_account.json`
- [x] `price_monitor.py` written and tested (placeholder tickers — needs real holdings)

---

## Phase 2 — Memory & Assistant Continuity ✅ COMPLETE

Goal: Claude remembers context across all surfaces — Mac (Claude Code), mobile (claude.ai).

### What's built
- [x] `CLAUDE.md` in repo root — Claude Code fetches Agent Config + Memory Index from Notion on startup
- [x] `scripts/memory_reminder.sh` + Stop hook — reminds Claude to update Notion every 5 turns
- [x] Notion as memory backbone: Agent Config, Memory Index, Sessions DB, Reference pages
- [x] `~/.claude/projects/.../memory/MEMORY.md` — redirect pointer to Notion (local `memory/` folder removed)
- [x] **2.1** Notion pages: User Profile, Architecture, Credentials, Sheet Structure
- [x] **2.2** Notion "Sessions" database for session logs
- [x] **2.3** Stop hook updated to prompt Notion sync after every 5 turns
- [x] **2.4** Notion MCP configured in claude.ai (Connectors tab)
- [x] **2.5** Claude Project created on claude.ai: `Fin Assist`
- [x] **2.6** Claude Project system prompt written — fetches Agent Config + Memory Index from Notion on startup
- [x] **2.7** Mobile session verified — Claude Project reads from Notion and introduces itself correctly (Session 004)

### Memory architecture decisions
| Decision | Choice | Reason |
|----------|--------|--------|
| Shared memory store | Notion | Only option where both Claude Code + claude.ai can read AND write |
| Google Drive MCP | Not used for memory | Read-only MCP — no write tools available |
| Google Sheets access (scripts) | Service account JSON | Already works; not MCP |
| Google Sheets access (Claude interactive) | Deferred — custom MCP later | No reliable read/write Google Sheets MCP exists yet; will build custom wrapper around service account when needed |

---

## Phase 3 — Data Import & Sheet Scaffolding ✅ COMPLETE

> Goal: get real holdings into the sheet first. Schema emerges from actual data, not upfront design.

> **Sheet:** `1IwBSuAzlP0xt0_9pQbztovmfy4Ng1BVCwUuhDurJhsI`
> **Scripts may only read/write to:** `Inv26`, `InvTransactions`, `Alerts Config`, `Analysis Log`
> **JP Morgan** = Nutmeg Alpha (product was renamed)

- [x] **3.1** Sheet exists and is shared with service account as Editor
- [x] **3.2** Sheet ID added to `.env` → `PORTFOLIO_SHEET_ID`
- [x] **3.3** T212 + Freetrade CSVs exported and dropped into `data/` (gitignored)
  - `data/Trading212_export_2025-04-11_to_2026-04-11.csv` — 8 stocks (NVDA, RIO, SGLN, INRG, RTX, TECK/B, GOOG, FIG→sold)
  - `data/freetrade-export_2022-2026.csv` — 6 stocks (HOp/HO, RHMd/RHM, VGER, BRK.B, LGEN, GENM)
  - Moneyfarm + JP Morgan/Nutmeg Alpha: managed funds — no trade-level CSV; values entered manually
- [x] **3.4** Exports reviewed — T212 columns understood, Freetrade ticker mapping built (`FT_TICKER_MAP`)
- [x] **3.5** `InvTransactions` tab created and populated — all buys/sells from T212 + Freetrade with normalised columns (Date, Ticker, Action, Qty, Price Per Share £, Total £, Platform)
- [x] **3.6** `Inv26` tab built from real holdings with three sections:
  - **Summary row** (row 5): Stocks Total Value, Stocks P&L £/%, Managed Funds Total, Grand Total (incl. cash)
  - **Self-Managed Stocks** (rows 9–19): 11 live positions, current prices via `GOOGLEFINANCE`, P&L from purchase; SGLN priced via `update_manual_prices.py` (Yahoo Finance fallback)
  - **Managed Funds** (rows 23–24): Nutmeg Alpha (£1,000 invested / £1,257 current), Moneyfarm (£1,000 invested / £1,238 current) — manually maintained, updated monthly from app
  - **Cash**: manually added to sheet, included in Grand Total via formula `=B4+E4+Q4`
  - **Grand Total as at April 2026: ~£20,507**
- [x] **3.7** `Alerts Config` tab placeholder created (to be filled in Phase 4 design session)
- [x] **3.8** `Analysis Log` tab created — empty, ready for `claude_analyst.py`

### Scripts built in Phase 3
| Script | Purpose |
|--------|---------|
| `scripts/build_portfolio_sheet.py` | Parses T212 + Freetrade CSVs, builds InvTransactions + Inv26 tabs from scratch, applies formatting |
| `scripts/update_manual_prices.py` | Fetches SGLN price from Yahoo Finance (yfinance), writes to Inv26 col F + timestamp col M |

### Key technical decisions
| Issue | Solution |
|-------|---------|
| GOOGLEFINANCE currency conversion (`USDGBP` returns array) | Use `/GOOGLEFINANCE("CURRENCY:GBPUSD")` — scalar, reliable |
| SGLN not in Google Finance | Yahoo Finance via `yfinance` (`SGLN.L`), MANUAL_TICKERS dict (extensible) |
| LON:VGER returns GBP not GBX | `FT_TICKER_MAP` maps VGER as `currency='GBP'` — no divide by 100 |
| Service account 403 on first run | Reshared sheet as Editor (fin-assist@fin-assist-492923.iam.gserviceaccount.com) |

> **Note:** All P&L = Google Sheet formulas. Scripts write only to `Inv26` (price, Score, Recommendation, Last Updated) and `Analysis Log`.

---

## Phase 4 — Design Session ❌ NOT STARTED

> Phase 3 is now complete — real holdings are in the sheet. Ready to start.
> Requires real holdings visible in sheet ✅ done.
> Do this inside the **Fin Assist Claude Project** on claude.ai (or Mac Claude Code).
> Goal: define the intelligence layer with actual positions in front of you.

- [ ] **4.1** Review `Inv26` — confirm all holdings are correct, tickers resolve, P&L looks right
- [ ] **4.2** For each stock: write a one-line investment thesis and assign an alert threshold (fills `Alerts Config`)
- [ ] **4.3** Define scoring model: Buy/Hold/Sell on scale -100 to +100

  ### Scoring Framework (starting point — adjust in session)
  | Signal | Suggested Weight |
  |--------|----------------|
  | Price momentum (% vs 30-day avg, RSI) | 20% |
  | News sentiment (headlines, last 7 days) | 20% |
  | Analyst consensus (upgrades/targets) | 25% |
  | Trader discussion (Reddit/StockTwits) | 15% |
  | Thesis alignment (why you bought) | 20% |

  ### Alert Threshold Starting Point (per stock in 4.2)
  | Stock type | Spike alert | Drop alert |
  |-----------|------------|-----------|
  | High volatility (defence/tech) | +4% | -4% |
  | Mid volatility (diversified) | +6% | -6% |
  | Index trackers | +3% | -3% |

- [ ] **4.4** Define weekly digest format (what sections, what data, what cadence)
- [ ] **4.5** Document all decisions to Notion (Agent Config if structural, Memory Index one-liner, Reference pages if schema changed)

---

## Phase 5 — Scripts & Automation ⏳ IN PROGRESS

- [x] `price_monitor.py` — fetches prices, detects spikes/drops (placeholder tickers, needs real data)
- [ ] `alert_sender.py` — sends Telegram message when threshold breached
- [ ] `sheets_updater.py` — writes Claude analysis scores + Last Updated timestamp to sheet (P&L is handled by sheet formulas, not this script)
- [ ] `claude_analyst.py` — sends portfolio data to Claude API, returns scored recommendations
- [ ] `sentiment_fetch.py` — pulls headlines for tickers, scores sentiment
- [ ] `weekly_digest.py` — compiles weekly report, sends via Telegram every Sunday
- [ ] `main_runner.py` — orchestrates all scripts in sequence
- [ ] `.github/workflows/daily_monitor.yml` — cron: weekdays 8am + 3:30pm UTC
- [ ] `.github/workflows/weekly_digest.yml` — cron: Sunday 6pm UTC
- [ ] Add all secrets to GitHub repo (Settings → Secrets)
- [ ] End-to-end test: trigger workflow manually, confirm Telegram message received
- [ ] Update `config/thresholds.json` with real per-stock thresholds

---

## Phase 6 — App & UI

Before building: define why a dedicated app or UI is needed on top of Telegram + Claude Project. Design session should answer:
- What does the UI do that Telegram and claude.ai don't?
- Who is it for — personal only, or shareable?
- Native mobile app vs web app vs Telegram mini-app?
- What data does it surface, and how is it organised?

Then build based on those answers.

---

## Phase 7 — Savings

Extend the system to track savings accounts (Monzo, Chase, Starling, Revolut pots). Goals, interest rates, balances, progress toward targets.

---

## Phase 8 — Pensions

Add pension tracking. Nutmeg, workplace pension, projected retirement value. Read-only monitoring — can't trade, but want visibility.

---

## Phase 9 — Mortgage

Track mortgage balance, remaining term, overpayment opportunities, rate review dates.

---

## Phase 10 — Budgeting & Expenses

Full budgeting layer: income, fixed costs, discretionary spending, joint vs personal. Regular ceremonies (monthly review, annual planning). Integrate Emma Live Export data.

---

## Credentials & Config (current state)

| Item | Status |
|------|--------|
| `.env` | ✅ Complete (Claude API key, Telegram token + chat ID) |
| `config/service_account.json` | ✅ In place |
| `PORTFOLIO_SHEET_ID` in `.env` | ✅ Set |
| GitHub repo secrets | ❌ Not added yet (needed for GitHub Actions) |

---

## Immediate Next Steps

1. **Phase 4** — Design session: scoring model, per-stock alert thresholds, weekly digest format (sheet is ready)
2. **Phase 5** — Build remaining scripts against real data and defined rules
3. **Ongoing** — Run `update_manual_prices.py` manually until added to GitHub Actions schedule
