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

## Phase 3 — Design Session ❌ NOT STARTED

> ⚠️ Requires Phase 2 complete. Do this inside the **Fin Assist Claude Project** on claude.ai.

- [ ] **3.1** Export holdings CSVs from T212 (Account → History → Export CSV) and Freetrade (Account → Statements → Download)
- [ ] **3.2** Design scoring model: Buy/Sell/Hold on scale -100 to +100
- [ ] **3.3** Define alert thresholds per stock (e.g. RHM: ±4%, others: ±6%)
- [ ] **3.4** Define Google Sheet schema: tabs, columns, what auto-updates vs manual
- [ ] **3.5** Define weekly digest format
- [ ] **3.6** Document all decisions back into the Project system prompt + Notion memory

### Scoring Framework (starting point — adjust in session)
| Signal | Suggested Weight |
|--------|----------------|
| Price momentum (% vs 30-day avg, RSI) | 20% |
| News sentiment (headlines, last 7 days) | 20% |
| Analyst consensus (upgrades/targets) | 25% |
| Trader discussion (Reddit/StockTwits) | 15% |
| Thesis alignment (why you bought) | 20% |

### Alert Threshold Starting Point
| Stock type | Spike alert | Drop alert |
|-----------|------------|-----------|
| High volatility (defence/tech) | +4% | -4% |
| Mid volatility (diversified) | +6% | -6% |
| Index trackers | +3% | -3% |

---

## Phase 4 — Google Sheet ⏳ IN PROGRESS

> **Use existing sheet** `1IwBSuAzlP0xt0_9pQbztovmfy4Ng1BVCwUuhDurJhsI` — do NOT create a new one.
> Already shared with service account. Sheet ID added to `.env`.
>
> **Existing tabs — DO NOT TOUCH:** `Inv25+`, `Summary (+)`, `Money Flow (+)`, `Joint Spendings (+)`, `Personal Spendings (+)`, `Savings (+)`, `Accounts (+)`, `Legend`, `Inv22-24`, `Earnings 2025`
>
> **Scripts may only read/write to:** `Inv26` and `InvTransactions` (new tabs created below)
>
> **Scope:** Stocks only (T212 + Freetrade). Pensions, savings, CMC Invest excluded for now.
> **JP Morgan** = Nutmeg Alpha (product was renamed)

- [x] **4.1** Sheet exists and is shared with service account
- [x] **4.2** Sheet ID added to `.env` → `PORTFOLIO_SHEET_ID`
- [ ] **4.3** Create `Inv26` tab — single tab with stocks + managed funds, visually grouped:

  **Section 1: Summary (top, pinned)**
  - Stocks total value, Stocks total P&L, Managed funds total, Grand total, Last updated by script

  **Section 2: Self-Managed Stocks** (auto-updated via GOOGLEFINANCE + script)
  | Column | Source |
  |--------|--------|
  | Ticker, Name, Platform (T212/Freetrade) | Static |
  | Qty, Avg Buy Price | Calculated from `InvTransactions` |
  | Current Price | `=GOOGLEFINANCE(ticker,"price")` |
  | P&L Today £/% | Formula |
  | P&L This Week £ | Formula using `GOOGLEFINANCE` historical |
  | P&L This Month £ | Formula |
  | P&L This Year £ | Formula |
  | P&L From Purchase £/% | Formula vs avg buy price |
  | Score, Recommendation | Written by `claude_analyst.py` |
  | Last Updated | Written by `sheets_updater.py` |

  **Section 3: Managed Funds** (manual value entry, updated monthly)
  - JP Morgan / Nutmeg Alpha, Moneyfarm
  | Column | Source |
  |--------|--------|
  | Name, Provider | Static |
  | Invested £ | Manual |
  | Current Value £ | Manual (update monthly from app) |
  | P&L £, P&L % | Formula |
  | Last Updated | Manual |

- [ ] **4.4** Create `InvTransactions` tab — full buy/sell history for individual stocks:
  | Column | Notes |
  |--------|-------|
  | Date | Trade date |
  | Ticker | e.g. AAPL, RHM.DE |
  | Action | Buy / Sell |
  | Qty | Number of shares |
  | Price Per Share £ | At time of trade |
  | Total Value £ | Qty × Price |
  | Platform | T212 / Freetrade |
  | Notes | Optional |
  - Import from T212 + Freetrade CSVs as starting point
  - Source of truth for avg buy price calculations in `Inv26`

- [ ] **4.5** Create `Alerts Config` tab (Ticker, Spike %, Drop %, Active Y/N) — read by `price_monitor.py`
- [ ] **4.6** Create `Analysis Log` tab (Date, Ticker, Score, Confidence, Reason) — written by `claude_analyst.py`
- [ ] **4.7** Export CSVs from T212 + Freetrade and populate `InvTransactions`
- [ ] **4.8** Populate `Inv26` stocks section from transaction data; add Nutmeg + Moneyfarm to managed funds section

> **Note:** All P&L = Google Sheet formulas. Scripts write only to `Inv26` (Score, Recommendation, Last Updated) and `Analysis Log`.

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
| `PORTFOLIO_SHEET_ID` in `.env` | ❌ Empty — needs sheet to be created |
| GitHub repo secrets | ❌ Not added yet (needed for GitHub Actions) |

---

## Immediate Next Steps

1. **Phase 3** — Design session from Mac (export holdings from T212 + Freetrade first)
2. **Phase 4** — Create Google Sheet tabs with real holdings
3. **Phase 5** — Build remaining scripts with real data
