# Fin Assist — Build Plan
**Personal Finance AI Assistant**
Last updated: April 2026

---

## Architecture

Cloud-hosted automation pipeline running on **GitHub Actions** (no Mac required to be always-on). Three layers:

| Layer | What it does | Technology |
|-------|-------------|------------|
| Data | Portfolio + live prices + news + sentiment + fundamentals | Google Sheets + Finnhub (primary) + yfinance (fallback) |
| Brain | Analysis, scoring, recommendations | Claude API (called by scripts — FAS scoring only, not per-headline) |
| Interface | Alerts + weekly digest + conversational assistant | Telegram + Claude Project (claude.ai) |

**Key decision:** Checks run 3× daily (09:30 / 13:00 / 16:30 BST, weekdays) + Sunday digest via GitHub Actions cron. No always-on server needed.

**Data routing:** Finnhub free tier (60 req/min, 60+ exchanges incl. LSE) for US stocks + news sentiment + analyst data. yfinance as fallback for tickers Finnhub doesn't fully cover on free tier (some LSE endpoints). Script checks `Exchange` field and routes accordingly.

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
- [x] ~~`price_monitor.py`~~ (deprecated in Phase 5C — event-driven monitoring replaced threshold-based alerts)

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
> **Scripts may only read/write to:** `Inv26 - Summary`, `Inv26 - Trend`, `InvTransactions`, `Alerts Config`, `Analysis Log`
> **JP Morgan** = Nutmeg Alpha (product was renamed)

- [x] **3.1** Sheet exists and is shared with service account as Editor
- [x] **3.2** Sheet ID added to `.env` → `PORTFOLIO_SHEET_ID`
- [x] **3.3** T212 + Freetrade CSVs exported and dropped into `data/` (gitignored)
  - `data/Trading212_export_2025-04-11_to_2026-04-11.csv` — 8 stocks (NVDA, RIO, SGLN, INRG, RTX, TECK/B, GOOG, FIG→sold)
  - `data/freetrade-export_2022-2026.csv` — 6 stocks (HOp/HO, RHMd/RHM, VGER, BRK.B, LGEN, GENM)
  - Moneyfarm + JP Morgan/Nutmeg Alpha: managed funds — no trade-level CSV; values entered manually
- [x] **3.4** Exports reviewed — T212 columns understood, Freetrade ticker mapping built (`FT_TICKER_MAP`)
- [x] **3.5** `InvTransactions` tab created and populated — all buys/sells from T212 + Freetrade with normalised columns (Date, Ticker, Action, Qty, Price Per Share £, Total £, Platform)
- [x] **3.6** `Inv26 - Summary` tab built from real holdings with three sections:
  - **Summary row** (row 5): Stocks Total Value, Stocks P&L £/%, Managed Funds Total, Grand Total (incl. cash)
  - **Self-Managed Stocks** (rows 9–19): 11 live positions, current prices via `GOOGLEFINANCE`, P&L from purchase; SGLN priced via `update_manual_prices.py` (Yahoo Finance fallback)
  - **Managed Funds** (rows 23–24): Nutmeg Alpha (£1,000 invested / £1,257 current), Moneyfarm (£1,000 invested / £1,238 current) — manually maintained, updated monthly from app
  - **Cash**: manually added to sheet, included in Grand Total via formula `=B4+E4+Q4`
  - **Grand Total as at April 2026: ~£20,507**
  - **5 benchmarks added**: S&P 500 (6816.89), FTSE 100 (10600.53), NASDAQ 100 (25116.34), MSCI World (132.23), Gold via SGLN (68.80 — references F18 from `update_manual_prices.py`)
- [x] **3.7** `Alerts Config` tab placeholder created (to be filled in Phase 4 design session)
- [x] **3.8** `Analysis Log` tab created — empty, ready for `claude_analyst.py`
- [x] **3B** `Inv26 - Trend` tab created — 20-column schema (A–T). April 13 baseline hardcoded in row 17 (all % = 0). May 2026 template in row 18 with formulas locked to row 17. Benchmarks stored as raw index values; % vs start computed by formula. Tracking start: **April 13, 2026**.
- [x] **3B** `InvTransactions` extended — Notes column (col I) added. New action types: `DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, `TRANSFER_OUT`. Total Invested = `SUMIF(Action=DEPOSIT)` — P&L stays clean when new cash arrives.

### Scripts built in Phase 3
| Script | Purpose |
|--------|---------|
| `scripts/build_portfolio_sheet.py` | Parses T212 + Freetrade CSVs, builds InvTransactions + Inv26 tabs from scratch, applies formatting |
| `scripts/update_manual_prices.py` | Fetches SGLN price from Yahoo Finance (yfinance), writes to Inv26 - Summary col F + timestamp col M. ⚠️ Phase 5: rename worksheet lookup from `'Inv26'` → `'Inv26 - Summary'` |

### Key technical decisions
| Issue | Solution |
|-------|---------|
| GOOGLEFINANCE currency conversion (`USDGBP` returns array) | Use `/GOOGLEFINANCE("CURRENCY:GBPUSD")` — scalar, reliable |
| SGLN not in Google Finance | Yahoo Finance via `yfinance` (`SGLN.L`), MANUAL_TICKERS dict (extensible) |
| LON:VGER returns GBP not GBX | `FT_TICKER_MAP` maps VGER as `currency='GBP'` — no divide by 100 |
| Service account 403 on first run | Reshared sheet as Editor (fin-assist@fin-assist-492923.iam.gserviceaccount.com) |

> **Note:** All P&L = Google Sheet formulas. Scripts write only to `Inv26` (price, Score, Recommendation, Last Updated) and `Analysis Log`.

---

## Phase 4 — Design Session ✅ COMPLETE

> All 5 design questions answered and locked. Decisions documented in Notion Sessions 012–014.

### Decisions locked

| Question | Decision |
|----------|---------|
| **Q1 — News & data source** | Finnhub free tier (primary) — 60 req/min, 60+ exchanges, news with sentiment built-in, analyst upgrades/price targets. yfinance as fallback for tickers Finnhub doesn't fully cover on free tier (some LSE). Script routes by `Exchange` field. |
| **Q2 — Market universe** | Global — any market, gated by: (1) T212 UK can buy it, (2) live price fetchable. Practical scope: LSE, NYSE, NASDAQ, XETRA, Euronext. Asian markets deprioritised (generally not on T212 UK). |
| **Q3 — Run frequency** | 3× daily weekdays: 09:30 / 13:00 / 16:30 BST. Mirrors market structure (open, mid, power hour close). Sunday 09:00 BST digest + full fundamental refresh. Alert dedup: same ticker can't re-alert within 6 hours. |
| **Q4 — Fundamental data** | Weekly only (Sunday). P/E, revenue/EPS trend, analyst price targets — quarterly data, no point refreshing daily. Exception: if Finnhub news detects an earnings release, that ticker gets an ad-hoc fundamental refresh on the next run. |
| **Q5 — Portfolio Snapshot** | Daily update after close run (16:30 BST). `sheets_updater.py` writes to Notion. Token cost ~$0.02/day. For portfolio changes: `build_portfolio_sheet.py --update-snapshot` triggers immediate refresh. No always-on worker needed. |

### Run schedule detail

| Run | UTC | London | Purpose |
|-----|-----|--------|---------|
| Morning | 08:30 | 09:30 BST | Just after LSE opens — overnight news, pre-market gaps |
| Midday | 12:00 | 13:00 BST | US pre-market live, EU mid-session |
| Close | 15:30 | 16:30 BST | Just after LSE closes — end-of-day signal confirmation |
| Sunday digest | 08:00 | 09:00 BST | Weekly summary + full fundamental refresh |

---

## Phase 5 — Scripts & Automation ⏳ NEXT

> Build order below. All design decisions are locked (see Phase 4).
> Reference Notion Sessions 012–014 for full spec.

### Task list (9 tasks)

- [x] **5.1** Patch `build_portfolio_sheet.py` — rename worksheet lookup `'Inv26'` → `'Inv26 - Summary'`
- [x] **5.2** Patch `update_manual_prices.py` — same rename
- [x] **5.3** ~~Build `claude_analyst.py`~~ — superseded by `holdings_monitor.py` in Phase 5C
- [x] **5.4** ~~Build `alert_sender.py`~~ — superseded by event-driven alerts in Phase 5C (consolidated brief replaced)
- [x] **5.5** Build `sheets_updater.py` — write Analysis Log rows to sheet + daily Notion Portfolio Snapshot update after 15:30 UTC run
- [x] **5.6** ~~Build `prospect_scanner.py`~~ — superseded by `prospect_discovery.py` in Phase 5C (static watchlist replaced with dynamic discovery)
- [x] **5.7** Build `snapshot_trend.py` — append monthly row to `Inv26 - Trend`. Reads Grand Total + all 5 benchmark values from `Inv26 - Summary`. GitHub Actions cron: `0 16 28-31 * 1-5` (covers last few days of month, weekdays); script checks if it's actually the last weekday before running, exits silently if not. Manual dispatch always available.
- [x] **5.8** Build `weekly_digest.py` — Sunday Telegram summary (portfolio performance, top signals, fundamental snapshot)
- [x] **5.9** GitHub Actions workflows created:
  - `daily_monitor.yml` — 3× daily cron: `30 8 * * 1-5`, `0 12 * * 1-5`, `30 15 * * 1-5`
  - `weekly_digest.yml` — Sunday: `0 8 * * 0`
  - `monthly_trend.yml` — last weekday of month: `0 16 28-31 * 1-5`
- [x] **5.10** Sheet tabs created: `Analysis Log` (headers + ready), `Watchlist` (headers, add tickers), `Alerts Config` (all 17 held tickers pre-populated with 5%/5% thresholds)
- [ ] Add all secrets to GitHub repo (Settings → Secrets)
- [ ] End-to-end test: trigger workflow manually, confirm Telegram message received

---

## Phase 5B — Telegram Bot Interactive Layer ⏳ PLANNED

> Extends the bot from output-only (alerts + digests) to interactive: send commands or questions, get Claude-powered replies.
> Design decisions locked in conversation — April 2026. Build after Phase 5 end-to-end test passes.

### Architecture

```
You → Telegram message
         ↓
   Cloudflare Worker (webhook receiver, free tier, ~instant)
         ↓
   /command? ──yes──→ GitHub Actions workflow_dispatch
                             ↓ runs script (Finnhub + Sheets + Claude API)
                             ↓ posts result to Telegram
         ↓
   free text? ──yes──→ Claude API (your credits)
                         context: Notion memory system (Agent Config + Memory Index
                         + User Profile + Sessions DB + latest portfolio snapshot)
                         ↓ posts reply to Telegram
```

### Commands

| Command | Script triggered via GHA | Response |
|---------|--------------------------|----------|
| `/holdings` (alias `/analyse`) | `holdings_monitor.py --bot` | Full status per holding + 24h event detection |
| `/discover` (alias `/scan`) | `prospect_discovery.py --bot` | Today's top discoveries ranked + rationale |
| `/digest` | `weekly_digest.py --bot` | Weekly summary on demand |
| `/snapshot` | `sheets_updater.py --snapshot` | Refreshes Notion portfolio snapshot |

### Conversational mode

Free-text messages go directly to Claude API (no GHA needed). The Cloudflare Worker fetches fresh context from Notion before each call:
- **Agent Config** — identity, rules, current phase
- **Memory Index** — full decision log
- **User Profile** — investment style, goals, risk profile
- **Latest portfolio snapshot** — from Sessions DB (written by `sheets_updater.py` after each run)
- **Recent Analysis Log entries** — signals fired, FAS scores

This makes Claude fully context-aware across sessions, identical to how it operates in Claude Code and the claude.ai Project — one memory system, all surfaces.

### Task list

- [ ] **5B.1** Create Cloudflare Worker — receives Telegram webhook, routes commands vs free text
- [ ] **5B.2** Command dispatcher — calls GitHub API `workflow_dispatch` for each `/command`, returns "Running…" acknowledgement immediately
- [ ] **5B.3** Conversational handler — fetches Notion context pages, calls Claude API, posts reply
- [ ] **5B.4** Extend each script (5.3–5.8) to post its own formatted Telegram reply when triggered via bot (vs scheduled run)
- [ ] **5B.5** Register Cloudflare Worker URL as Telegram webhook (`setWebhook`)
- [ ] **5B.6** Add new secrets: `NOTION_API_KEY` (Worker env), `GH_PAT` (for workflow_dispatch), `CF_WORKER_URL`
- [ ] **5B.7** End-to-end test: send each command + a free-text question, confirm correct responses

### Key decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Webhook receiver | Cloudflare Worker (free tier) | No always-on server; 100k req/day free; ~instant response |
| Conversational context | Notion memory system | Already the memory backbone for Claude Code + claude.ai; always fresh; no KV cache to maintain |
| Heavy scripts | GitHub Actions (workflow_dispatch) | Scripts need Finnhub + Sheets credentials + Python deps — GHA already has all of these |
| Light responses | Claude API direct from Worker | No need to spin up GHA for a text question; faster and cheaper |
| New secrets | `NOTION_API_KEY`, `GH_PAT`, `CF_WORKER_URL` | Worker needs Notion read access + ability to trigger GHA |

---

## Phase 5C — Insights Engine Redesign ✅ COMPLETE (April 2026)

> Motivation: 3× daily consolidated briefs were noise — identical messages, score-based not event-based, no actionable insights. User redirected: don't send unless genuinely worth acting on, and insights must come from real market events + trader signal sources, not abstract scores.

### Architecture change

**Before (Phase 5):** `claude_analyst.py` → `alert_sender.py` → consolidated brief every run, regardless of signal strength. Static manual `Watchlist` tab.

**After (Phase 5C):** Two event-driven scripts, each with `--auto` (silent unless actionable) and `--bot` (always replies) modes. Discovery is dynamic — no manual watchlist upkeep.

### New scripts

| Script | Purpose |
|--------|---------|
| `scripts/lib/market_sources.py` | Shared library: Reddit/Finnhub news/Yahoo trending fetchers, ticker extractor with Finnhub-cached symbol universe for validation |
| `scripts/holdings_monitor.py` | Scans last 24h news per holding, Claude identifies concrete events (earnings, regulatory, leadership, macro), classifies `NONE/WATCH/ACT`. `--auto`: silent unless `ACT`. `--bot`: full status table. Writes `data/holdings_alerts.json` + legacy-format `data/analysis_results.json` for sheet score updates. |
| `scripts/prospect_discovery.py` | Dynamic discovery: aggregates ticker mentions across Reddit (r/wallstreetbets, r/stocks, r/investing, r/ValueInvesting), Finnhub market news, Yahoo trending. Applies exclusion filters, ranks by mention count, scores top candidates via Claude (exploratory tone). Journals every discovery to `Watchlist` tab. `--auto`: silent unless new BUY (score ≥ 6). `--bot`: full scan reply. |

### Config

`config/discovery_filters.json` — exclude keywords (crypto, SPAC, meme), tickers (GME, AMC), country codes (CN, HK, KY), min market cap, min source mentions, Reddit subs, ticker stopwords. Editable without code changes.

### Watchlist tab (new schema — auto-migrated on first run)

Journal of every discovery: `Date Added | Ticker | Name | Exchange | Source(s) | First Score | Latest Score | Recommendation | Rationale | Status`. Status values: `Active / Purchased / Ignored / Stale`. Existing rows update Latest Score + Rationale; new tickers append.

### Alerting rules

| Mode | Holdings | Discovery |
|------|---------|-----------|
| `--auto` (cron) | Silent unless ≥1 ACT-level event | Silent unless ≥1 new BUY (score ≥ 6, not previously on Watchlist) |
| `--bot` (Telegram) | Always replies with full holdings status ranked by alert level | Always replies with full scan results ranked by score |

### Deprecated (deleted)

`scripts/alert_sender.py`, `scripts/prospect_scanner.py`, `scripts/claude_analyst.py`, `scripts/price_monitor.py`.

### Telegram commands

`/holdings` (alias `/analyse`) → `holdings_monitor.py --bot`
`/discover` (alias `/scan`) → `prospect_discovery.py --bot`
Legacy commands kept as aliases so existing muscle memory works.

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

1. **Phase 5** — Build all 9 tasks in order (see Phase 5 task list above). Start with patches 5.1 + 5.2, then core scripts.
2. **Ongoing** — Run `update_manual_prices.py` manually until added to GitHub Actions schedule
3. **Ongoing** — Update managed fund values (Nutmeg Alpha, Moneyfarm) monthly from app → `Inv26 - Summary`
