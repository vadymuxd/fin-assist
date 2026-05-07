# Fin Assist — Build Plan
**Personal Finance AI Assistant**
Last updated: May 2026

> **Authoritative version is in Notion:** https://www.notion.so/34f416f2756681c48b99ef184aa3c5c3
> This file is a git mirror. Notion is updated first; PLAN.md synced after.

---

## Architecture

Cloud-hosted automation on **GitHub Actions** (no always-on Mac needed). Three stores, one purpose each:

| Store | Purpose | Written by |
|-------|---------|------------|
| **Google Sheets** | Confirmed balances + account metadata (rates, names, owners). Investment source of truth (live formulas). | Human (bulk updates) |
| **Notion** | Individual transactions + Claude's memory. Entry point for Claude mobile and NL updates. | Claude mobile, sync_worker |
| **Supabase** | App database — derived from Sheets and Notion. Workers write here. App reads here. | Workers only |

**Schedule:** 3× daily weekdays (09:30 / 13:00 / 16:30 BST) + Monday 08:00 BST digest + Sunday 09:00 BST mortgage monitor.

**Web app:** fin-assist-web.vercel.app — Next.js on Vercel, Supabase read cache, 5 tabs (Investments / Savings / Pensions / Net Worth / Insights + Mortgage)

**Transaction input paths — 5 paths, one destination (Supabase → Web App)**
```
PATH 1: Cash Flow Sheet → sync_worker.py (1st of month) → Notion Transactions DB → sync_worker.py (daily close) → Supabase
PATH 2: Claude mobile NL → Notion Transactions DB → sync_worker.py (daily close) → Supabase
PATH 3: Bank API (future, Phase 19) → Supabase direct + Notion summary
PATH 4: market_worker.py + snapshot_worker.py → Supabase (investments, unchanged)
PATH 5: Web app "+" manual entry → Supabase (instant) → sync_worker.py backfills Notion Transactions DB
```

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
> **Scripts may only read/write to:** `Inv26 - Summary`, `InvTransactions`, `Alerts Config`, `Analysis Log`
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
- [x] **3B** `Inv26 - Trend` tab created (later removed — trend data now lives in app via Supabase `portfolio_snapshots`)
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
| **Q3 — Run frequency** | 3× daily weekdays: 09:30 / 13:00 / 16:30 BST. Mirrors market structure (open, mid, power hour close). Monday 08:00 BST weekly digest. Alert dedup: same ticker can't re-alert within 6 hours. |
| **Q4 — Fundamental data** | Rolled into weekly digest via `holdings_monitor.py` (Finnhub + AV sentiment, bullish/bearish%) and yfinance-based 7-day returns. Analyst targets surface through holdings_monitor's per-ticker context. |
| **Q5 — Portfolio Snapshot** | Daily update after close run (16:30 BST). `sheets_updater.py` writes to Notion. Token cost ~$0.02/day. For portfolio changes: `build_portfolio_sheet.py --update-snapshot` triggers immediate refresh. No always-on worker needed. |

### Run schedule detail

| Run | UTC | London | Purpose |
|-----|-----|--------|---------|
| Morning | 08:30 | 09:30 BST | Just after LSE opens — overnight news, pre-market gaps |
| Midday | 12:00 | 13:00 BST | US pre-market live, EU mid-session |
| Close | 15:30 | 16:30 BST | Just after LSE closes — end-of-day signal confirmation |
| Monday digest | 07:00 | 08:00 BST | Weekly summary — portfolio WoW, benchmarks (yfinance 7d), holdings grouped 🚀 BUY MORE / ⚠️ CONSIDER SELL / 👀 WATCH, sector ETFs, discovery top 3, Sonnet 4.6 recommendation |

---

## Phase 5 — Scripts & Automation ✅ COMPLETE

> Build order below. All design decisions are locked (see Phase 4).
> Reference Notion Sessions 012–014 for full spec.

### Task list (9 tasks)

- [x] **5.1** Patch `build_portfolio_sheet.py` — rename worksheet lookup `'Inv26'` → `'Inv26 - Summary'`
- [x] **5.2** Patch `update_manual_prices.py` — same rename
- [x] **5.3** ~~Build `claude_analyst.py`~~ — superseded by `holdings_monitor.py` in Phase 5C
- [x] **5.4** ~~Build `alert_sender.py`~~ — superseded by event-driven alerts in Phase 5C (consolidated brief replaced)
- [x] **5.5** Build `sheets_updater.py` — write Analysis Log rows to sheet + daily Notion Portfolio Snapshot update after 15:30 UTC run
- [x] **5.6** ~~Build `prospect_scanner.py`~~ — superseded by `prospect_discovery.py` in Phase 5C (static watchlist replaced with dynamic discovery)
- [x] **5.7** ~~Build `snapshot_trend.py`~~ — removed (sheet removed; trend data lives in app via `portfolio_snapshots`)
- [x] **5.8** Build `weekly_digest.py` — Monday 08:00 BST Telegram summary. v2 (Apr 2026): portfolio WoW (yfinance-weighted), 7d benchmarks with beat markers, holdings grouped 🚀/⚠️/👀 with bullish/bearish% badges, sector ETFs + concentration warn, discovery top 3, Sonnet 4.6 recommendation paragraph
- [x] **5.9** GitHub Actions workflows created:
  - `daily_monitor.yml` — 3× daily cron: `30 8 * * 1-5`, `0 12 * * 1-5`, `30 15 * * 1-5`
  - `weekly_digest.yml` — Monday: `0 7 * * 1` (runs holdings_monitor + prospect_discovery first)
  - ~~`monthly_trend.yml`~~ — removed (Inv26 - Trend sheet removed)
- [x] **5.10** Sheet tabs created: `Analysis Log` (headers + ready), `Watchlist` (headers, add tickers), `Alerts Config` (all 17 held tickers pre-populated with 5%/5% thresholds)
- [x] Add all secrets to GitHub repo (Settings → Secrets) — 8 secrets set incl. MARKETAUX_API_KEY
- [x] End-to-end test: trigger workflow manually, confirm Telegram message received

---

## Phase 5B — Telegram Bot Interactive Layer ✅ COMPLETE

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
| `/holdings` | `holdings_monitor.py --bot` | Full status per holding + 24h event detection |
| `/discover` | `prospect_discovery.py --bot` | Today's top discoveries ranked + rationale |
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

- [x] **5B.1** Cloudflare Worker live at `fin-assist-bot.vadym-uxd.workers.dev` — routes commands vs free text
- [x] **5B.2** Command dispatcher — calls GitHub API `workflow_dispatch` for each `/command`
- [x] **5B.3** Conversational handler — fetches Notion context, calls Claude Opus 4.7, posts reply
- [x] **5B.4** Each script has `--bot` flag that posts its own formatted Telegram reply
- [x] **5B.5** Cloudflare Worker URL registered as Telegram webhook
- [x] **5B.6** All 5 Worker secrets set: `NOTION_API_KEY`, `CLAUDE_API_KEY`, `GH_PAT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [x] **5B.7** End-to-end tested — all commands + free-text replies working

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

## Pre-Phase-6 — Housekeeping ⏳ DO FIRST

> Two cleanup items to finish before starting Phase 6A. Blockers / data hygiene.

- [x] **PH.1 Telegram dedup audit** — root cause: `holdings_monitor.py` used `(ticker, headlines_hash)` as dedup key; rolling 24h news window shifted the hash between runs even for the same event → re-fired. Fixed to time-based dedup: key=`ticker`, 6-hour window via Alerts Log `Run Time (UTC)` column. `prospect_discovery.py` latent bug fixed too: Watchlist snapshot now read *before* upsert so same-day re-runs don't re-announce a ticker first discovered that morning.
- [x] **PH.4 Fix Notion snapshot cron-drift bug** — `sheets_updater.py --snapshot` was never firing from cron because `daily_monitor.yml` checked exact minute (`MINUTE = "30"`) but GHA drifts 20–30 min. Fixed to `HOUR -ge "15"` — robust to drift. Notion Portfolio Snapshot had been frozen since 2026-04-16; refreshed and live as of 2026-04-22 22:51 UTC.
- [x] **PH.2 Record Rheinmetall (RHM / RHMd) transaction** — broker migration on 2026-04-22: sold 1 share on Freetrade (£1,229.87 proceeds, order `H6O22V1E6SKC`), rebought 1.1430181 shares on T212 (£1,420.60 all-in, order `EO49951315617`). Both rows appended to `InvTransactions`. `Inv26 - Summary` RHM row updated: Platform→T212, Qty→1.1430181, Avg Buy £→£1,047.25 (cost basis £1,197.03 = original £1,006.29 + £190.73 extra cash on rebuy). Tracking Started Value bumped by £190.73 (£1,276.09 → £1,466.82) to prevent the cash injection being counted as tracking-period P&L.
- [x] **PH.3 Retire Phase 3 bootstrap artefacts** — `scripts/build_portfolio_sheet.py` and the two broker export CSVs (`data/Trading212_export_*.csv`, `data/freetrade-export_*.csv`) deleted. They were one-shot bootstrap tooling from Phase 3.5 and have been stale since — `InvTransactions` is now the authoritative source. Only PLAN.md Phase 3 history still references them as historical context.

---

## Phase 6 — App & UI ⏳ READY TO BUILD

> Design session complete (Sessions 026–027). Two-tab responsive web app on Vercel, no auth, data via Supabase, Android via Expo later.
> **Gated on Pre-Phase-6 housekeeping (PH.1 + PH.2) completing first.**

### Design decisions (locked)

| Q | Decision |
|---|---------|
| **Q1 — UI scope** | Two tabs. Tab 1 Portfolio Dashboard (bird's-eye, charts, breakdowns by sector/stock/market, trend lines D/W/M, benchmark overlays). Tab 2 Insights Feed (discoveries including filtered-out with emphasis, news with images grouped by date, visual Analysis Log + Watchlist, historical browse). |
| **Q2 — Audience** | Personal only. No PII / account credentials shown — only analytics. No auth needed. |
| **Q3 — Platform** | Next.js on Vercel, responsive mobile + desktop. Android via Expo WebView wrapper later. No iOS, no Telegram mini-app. |
| **Q4a — Data source** | Supabase (user already has account). Scripts dual-write to Supabase alongside Sheets. |
| **Q4b — Value scope** | All values including absolute £ are OK to display on the public URL. |
| **Repo layout** | Monorepo — `web/` alongside `scripts/` + `worker/`. |
| **Charts** | Tremor (`@tremor/react`). |
| **Supabase access** | Public read, service-role write. Anon SELECT allowed on all tables; INSERT/UPDATE/DELETE require service-role key (stored in GitHub Secrets). |

### 6A — Data foundation (Supabase) ✅ COMPLETE

> Supabase becomes the read source for the web app. Existing Python scripts dual-write to Supabase alongside Sheets. Sheets remains source of truth for humans.

- [x] **6A.1** Create Supabase project (free tier). Add `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` to `.env`, GitHub Actions secrets, and Vercel env.
- [x] **6A.2** Schema migration `supabase/migrations/0001_init.sql` — 7 tables: holdings, portfolio_snapshots, trend_snapshots, discoveries, holdings_alerts, news_items, sectors.
- [x] **6A.3** Build `scripts/lib/supabase_sink.py` — shared client + writer helpers. Fails open.
- [x] **6A.4** Dual-write wiring: sheets_updater → holdings, prospect_discovery → discoveries, holdings_monitor → holdings_alerts, market_sources → news_items. (snapshot_trend → trend_snapshots removed)
- [x] **6A.5** `scripts/daily_portfolio_snapshot.py` — reads Inv26-Summary totals + benchmarks, upserts to `portfolio_snapshots`. Called from `daily_monitor.yml` close run (HOUR ≥ 15).
- [x] **6A.6** `market_sources.py` extended with `image_url` capture from Marketaux + Alpha Vantage.
- [x] **Migration 0002** — `holdings.value_gbp` column added (GBP-denominated value from sheet col G). Applied via Supabase CLI. Backfill complete (11 rows).

### 6B — Next.js scaffolding ✅ COMPLETE

- [x] **6B.1** Next.js 16 App Router + TypeScript + Tailwind v4 bootstrapped in `web/`.
- [x] **6B.2** `@supabase/supabase-js` installed, `web/lib/supabase.ts` anon read-only client. RLS: public SELECT, service-role writes only.
- [x] **6B.3** Vercel project created, GitHub repo connected (Root Dir=`web`, skip-on-no-web-change). Live at https://fin-assist-web.vercel.app. `.npmrc` with `legacy-peer-deps=true` for Tremor/React 19 compat.
- [x] **6B.4** Shared layout: desktop top nav, mobile bottom tab bar (fixed, `pb-[safe-area-inset-bottom]`).
- [x] **6B.5** `@tremor/react` installed. Tailwind v4 `@source` directive added for Tremor class scanning.

### 6C — Tab 1: Portfolio Dashboard ✅ COMPLETE

- [x] **6C.1** KPI cards — Grand Total (£), WoW/MoM/YTD % with adaptive delta logic (shows "—" when not enough history).
- [x] **6C.2** Portfolio line chart — Tremor AreaChart, D/W/M toggle, 5 benchmark overlays normalised to 100 at baseline (Apr 13).
- [x] **6C.3** Allocation donut — sector/market/platform toggle, `value_gbp`-based for accurate cross-currency breakdown.
- [x] **6C.4** Holdings table — sortable on desktop, card list on mobile, links to drill-down.
- [x] **6C.5** Per-holding drill-down `/holdings/[ticker]` — name/platform/sector/market chips, P&L, latest alert badge + rationale, recent news with images + sentiment.

### 6D — Tab 2: Insights Feed ✅ COMPLETE

- [x] **6D.1** "Today's Discoveries" — latest run ranked by score. Emphasis marker on items that hit Telegram; muted styling on filtered-out.
- [x] **6D.2** "Recent Holdings Alerts" — latest ACT/WATCH events; each card links to triggering article(s).
- [x] **6D.3** Sector news stream — `news_items` grouped by day, image thumbnails, ticker/sector chip tags.
- [x] **6D.4** Historical browse — date picker; past day's discoveries + alerts + news.
- [x] **6D.5** Empty state + error handling — friendly message if Supabase returns nothing or fails.

### 6E — Savings & Net Worth UI ✅ COMPLETE

> Extends the app to 4 tabs: Investments | Savings | Net Worth | Insights. Builds on Phase 7 data layer.

- [x] **6E.0** Rename "Dashboard" → "Investments" in nav + page heading. Add Ticker dimension to Allocation chart.
- [x] **6E.1** Add Savings + Net Worth tabs to nav (`PiggyBank` / `TrendingUp` icons, lucide-react).
- [x] **6E.2** Savings page `/savings` — KPI cards (total/personal/joint + deltas), growth line chart, allocation donut, accounts table.
- [x] **6E.3** Net Worth page `/net-worth` — KPI cards, combined line chart (net worth + savings + investments), savings-vs-investments donut.
- [x] **6E.4** `getSavingsSnapshots()`, `getSavingsAccounts()`, `computeSavingsDeltas()`, `getNetWorthData()` in `web/lib/queries.ts`.

### 6F — Testing & validation (web) ✅ COMPLETE

- [x] **6F.1** Data freshness — scripts run, Supabase rows + Vercel URL reflect latest data.
- [x] **6F.2** E2E smoke per tab — all components verified, no console errors.
- [x] **6F.3** Responsive on real devices — iOS Safari, Android Chrome, desktop verified.
- [x] **6F.4** Chart interactions — D/W/M toggle, benchmark overlays, drill-downs working.
- [x] **6F.5** News image rendering + sector icon fallback verified.
- [x] **6F.6** Supabase RLS — anon INSERT blocked, SELECT works.
- [x] **6F.7** Performance budget met.
- [x] **6F.8** Empty-state + error paths handled.
- [x] **6F.9** Dogfood complete — web app is sufficient; Android deferred to Phase 11.

---

## Phase 7 — Savings Data Layer ✅ COMPLETE

> Track savings accounts (Monzo, Chase, Starling, Revolut pots, ISAs). Source: `Savings Balance` sheet tab (wide time-series: Bank | Account | Type | Owner | [Month Year Balance] …). UI built in Phase 6E.

### Architecture
- Sheet `Savings Balance` → `savings_snapshot.py` → Supabase (`savings_accounts` + `savings_snapshots`) → web app
- Mirrors investments pipeline exactly: sheet is source of truth, Supabase is read cache for the web app

### 7A — Notion: Savings Context page ✅ COMPLETE
- [x] **7A.1** Savings Context page created under Reference. Account registry, data pipeline, goals, sheet column notes. Moved out of Agent Config. Config reference table updated.

### 7B — Google Sheet: `Savings Balance` tab ✅ COMPLETE
- [x] **7B.1** Wide-format tab exists: Bank | Account | Type | Owner | April 2026 Balance | May 2026 Balance | …

### 7C — Supabase: migration `0004_savings.sql` ✅ COMPLETE
- [x] **7C.1** `savings_accounts` + `savings_snapshots` tables created with RLS. Migration at `supabase/migrations/0004_savings.sql`.

### 7D — Python script: `scripts/savings_snapshot.py` ✅ COMPLETE
- [x] **7D.1** Reads `Savings Balance` tab, parses month column headers → dates (last day of month), pivots wide-format → per-account-per-date rows
- [x] **7D.2** Upserts `savings_accounts` on `(date, bank, account_name)`; aggregates → upserts `savings_snapshots` on `date`
- [x] **7D.3** Triggers Vercel ISR revalidation after write
- ~~**7D.4**~~ Wiring into `daily_monitor.yml` dropped — superseded by Phase 11 unified sync script that covers all domains consistently

### 7E — `supabase_sink.py` additions ✅ COMPLETE
- [x] **7E.1** `write_savings_accounts(rows)` and `write_savings_snapshot(date, total, personal, joint)` in `scripts/lib/supabase_sink.py`

### 7F — Live bank API ← DEFERRED
> Revolut Open Banking / TrueLayer / Plaid auto-refresh. No direct personal Revolut API exists — requires Open Banking aggregator (TrueLayer/Plaid), both paid in production. Revisit after Phase 12 natural language update layer is in place.

---

## Phase 8 — Pensions ✅ COMPLETE

Add pension tracking. Read-only monitoring — can't trade but want visibility.

### 8A — Notion Reference page ✅
- [x] Pensions Context page created under Reference. Provider registry, pipeline, goals, sheet column notes.

### 8B — Google Sheet ✅
- [x] Wide-format `Pension Balance` tab: Provider | Account | Type | monthly balance columns

### 8C — Supabase ✅
- [x] Migration `0005_pensions.sql`: `pension_accounts` + `pension_snapshots` tables with RLS

### 8D — `pension_snapshot.py` ✅
- [x] Reads sheet, pivots wide→long, upserts both tables, triggers Vercel ISR

### 8E — Web app ✅
- [x] `/pensions` tab (amber theme): KPI cards, trend chart, allocation donut (by provider/account/type), accounts table
- [x] Nav updated to 5 tabs: Investments | Savings | Pensions | Net Worth | Insights
- [x] Net Worth updated: 3-way split (Investments + Savings + Pensions), allocation chart + KPI chips

---

## Phase 9 — Mortgage ✅ COMPLETE

Mortgage dashboard live (chart, metrics, KPI). Net worth gains mortgage equity. `mortgage_monitor.py` running Sunday 09:00 BST. `mortgage_snapshot.py` seeds amortisation history.

---

## Phase 10 — Architecture Review & Alignment

**Why:** Confirm Architecture reference page reflects actual current state before any new build starts.

- [ ] **10.1** Run architecture review interview session
- [ ] **10.2** Update Architecture reference page with all corrections ← *in progress (2026-05-05)*
- [ ] **10.3** Review and adjust Phase 11–16 task lists if anything changed
- [ ] **10.4** Confirm Phase 11 is ready to start

---

## Phase 11 — Clean Up the Engine Room ✅ COMPLETE

**Why:** Consolidate ~12 scripts into 4 clean workers before building anything new on top.

| New worker | Replaces | Responsibility |
|---|---|---|
| `market_worker.py` | `news_fetcher.py`, `stock_assessor.py`, `alert_dispatcher.py` | Full investment pipeline: fetch → assess → dispatch. `--mode` flag. |
| `snapshot_worker.py` | `daily_portfolio_snapshot.py`, `savings_snapshot.py`, `pension_snapshot.py`, `mortgage_snapshot.py`, scores from `sheets_updater.py` | Single owner of all Supabase snapshot writes. `--domain` flag. Note: `mortgage_snapshot.py` currently has no GHA trigger — snapshot_worker fixes this. |
| `sync_worker.py` | *(new)* | Reconciles Notion Transactions DB ↔ Supabase. Cash Flow sheet → Notion on 1st of month. |
| `digest_worker.py` | `weekly_digest.py` | Reads Supabase directly. No duplicate Monday pipeline calls. |

**Kept as-is:** `holdings_monitor.py --bot`, `prospect_discovery.py --bot`, `update_manual_prices.py`, `mortgage_monitor.py`, `sheets_updater.py` (Notion snapshot only — Analysis Log write retired)

- [x] **eng.1** Write `market_worker.py` — absorbs `news_fetcher` + `stock_assessor` + `alert_dispatcher` via `--mode fetch|assess|dispatch`. Originals deleted. `daily_monitor.yml` updated.
- [x] **eng.2** Write `snapshot_worker.py` — absorbs `savings_snapshot.py`, `pension_snapshot.py`, `daily_portfolio_snapshot.py` via `--domain portfolio|savings|pensions|all`. Originals deleted. `daily_monitor.yml` updated (close-run calls `snapshot_worker --domain all` then `sheets_updater --snapshot`).
- [x] **eng.3** Write `digest_worker.py` — remove pre-run pipeline, read from Supabase directly. Update `weekly_digest.yml`.
- [x] **eng.4** Retire `snapshot_trend.py` + `monthly_trend.yml`. `Inv26 - Trend` tab removed. `trend_snapshots` Supabase table dropped (migration 0007). `write_trend_snapshot` removed from `supabase_sink.py`. Trend/history data lives in app via `portfolio_snapshots`.
- [x] **eng.5** Update Architecture reference page — replaced old scripts inventory with 4-worker model, updated GHA workflows table, retired deprecated scripts list.
- [x] **eng.6** Smoke test all GHA workflows.
- [x] **eng.7** Add `/mortgage` Telegram bot command — wired in Cloudflare Worker COMMANDS map → `mortgage_monitor.yml`.
- ~~[ ] **eng.8**~~ ~~Investigate 4 May cron failure~~ — resolved.
- [x] **eng.9** Add weekend portfolio snapshot — `weekend_snapshot.yml` Saturday 09:00 BST, runs `snapshot_worker.py --domain portfolio` only.
- [x] **eng.10** Fix `mortgage_monitor.py` Telegram 400 error — `build_telegram_summary()` extracts rates + BoE + recommendation into ~800 char plain-text message. Full report still saved to repo.
- ~~**eng.11**~~ ~~Fix "Updated" date on Savings / Pensions / House pages~~ **Deprecated** — updated_at column approach removed (2026-05-05).

---

## Phase 12 — Lock the Data Model

**Why:** Lock every schema and sheet decision before writing transaction code.

### Sheet audit
- [x] **data.1** Open Sheet — audit every tab, document actual current purpose
- [x] **data.2** Classify each tab: Active-scripts / Active-manual / Archive / Redundant
- [x] **data.3** Rename tabs: `Summary (+)`→`Income`, `Money Flow (+)`→`Cash Flow`, `Joint Spendings (+)`→`Joint Spendings`, `Personal Spendings (+)`→`Personal Spendings`, `Inv26 - Summary`→`Investments`. Removed: `Inv25+`, `Inv22-24`, `Earnings 2025`, `Legend`, `Accounts (+)`, `Alerts Config`, `Alerts Log`, `Watchlist`, `Analysis Log`.
- [x] **data.4** Retire `Alerts Log`, `Watchlist`, `Analysis Log` — data already in Supabase; Sheets writes stripped from scripts
- [x] **data.5** `Pensions` and `Cash Flow` tabs documented in Sheet Structure reference page
- [x] **data.6** Safety rules removed — no tab restrictions. Scripts updated to use new tab names.
- [x] **data.7** Agent Config updated — safety rules section replaced with simple sheet access note
- [x] **data.8** `(+)` tabs renamed. `update_manual_prices.py` expanded to all 17 tickers + FX conversion + A2 timestamp. `price_refresh.yml` added (21:30 BST weekdays, US/CA close).

### Architecture decisions to lock
- [x] **data.9** Cash Flow tab mapped: `Date (day) | From | To | Description | Amount £` — monthly routing template (salary in, account transfers, pot top-ups). 25 rows. `sync_worker` reads on 1st of month to pre-populate expected transactions.
- [x] **data.10** All 9 tabs retained: `Income`, `Cash Flow`, `Investments`, `Joint Spendings`, `Personal Spendings`, `Saving Transfers`, `Savings Balance`, `Pensions`, `InvTransactions`. Nothing removed in Phase 13. `InvTransactions` retires in Phase 16 when `sync_worker` is live.
- [x] **data.11** `transactions` table migration written → `supabase/migrations/0010_transactions.sql`. Apply to Supabase before Phase 13 build starts.

**`transactions` table schema:**
`id (uuid) | date | domain | account_name | amount_gbp | type | notes | source | synced_to_notion (bool) | created_at`

---

## Phase 13 — Add Transaction Entry to the App

**Why:** Web app becomes the primary way to log financial events — "+" button opens a modal, pick domain, fill fields, hit submit. Supabase updates instantly, charts revalidate.

- [ ] **entry.1** Write migration `0008_transactions.sql` — create `transactions` table with RLS.
- [ ] **entry.2** Add `write_transaction()` helper to `supabase_sink.py`
- [ ] **entry.3** Build `/api/transactions` POST route — validates payload, inserts to Supabase, triggers ISR
- [ ] **entry.4** Build `TransactionModal` component — domain picker step → contextual field step → confirm
- [ ] **entry.5** Wire "+" button into header (persistent across all tabs)
- [ ] **entry.6** Connect domain dropdowns to live Supabase account lists (`savings_accounts`, `pension_accounts`)
- [ ] **entry.7** Verify charts revalidate correctly after insert
- [ ] **entry.8** One-time backfill: push historical Savings Balance + Pension Balance sheet data → Supabase `transactions`

---

## Phase 14 — Investments Comparison Chart

**Why:** Frontend-only. Answers: how is my custom stock portfolio performing vs market and managed funds?

- [ ] **chart.1** Confirm `portfolio_snapshots` has enough history to isolate custom-stocks baseline
- [ ] **chart.2** Confirm pension + managed fund monthly snapshots have consistent cadence for overlay
- [ ] **chart.3** Build `ComparisonChart` component — normalised % from first data point, 4 lines, Recharts
- [ ] **chart.4** Add to Investments tab (below existing dashboard or as toggle)

---

## Phase 15 — Tell Claude What Changed (NL Entry)

**Why:** For ad-hoc updates — "moved £2k from Chase to Moneybox" — tell Claude mobile, it writes to Notion Transactions DB. sync_worker picks it up at daily close.

- [ ] **nl.1** Create Notion Transactions DB — columns: Date | Domain | Account | Amount £ | Type | Notes | Source | Synced
- [ ] **nl.2** Create Expenses Context reference page
- [ ] **nl.3** Confirm Mortgage + Pensions Context pages complete
- [ ] **nl.4** Update Fin Assist system prompt — detect financial update mentions, extract fields, write to Notion Transactions DB
- [ ] **nl.5** Test all domains end-to-end
- [ ] **nl.6** Verify sync picks up NL entries and routes correctly within 24h

---

## Phase 16 — Close the Loop (Bidirectional Sync)

**Why:** Two transaction stores (Supabase from app, Notion from Claude) need to stay in sync automatically.

**Reconciliation logic:**
- Notion `Synced=false` → write to Supabase, mark Synced
- Supabase `synced_to_notion=false` → write to Notion, mark synced
- Dedup key: `date + domain + account_name + amount_gbp + type`

- [ ] **sync.1** Map Cash Flow sheet layout (confirm in data.9 before building)
- [ ] **sync.2** Build `sync_worker.py` — Cash Flow read + Notion write (1st of month) + bidirectional reconciliation (daily close)
- [ ] **sync.3** Add `monthly_sync.yml` GHA workflow (1st of month trigger)
- [ ] **sync.4** Add `sync_worker.py` to `daily_monitor.yml` close run

---

## Phase 17 — Android App

**Why:** Build when native UX (push notifications, home screen icon, offline) is actually needed.

- [ ] **android.1** Pick approach: WebView wrapper or react-native-web
- [ ] **android.2** Scaffold in `mobile/` — single WebView screen pointing at Vercel URL
- [ ] **android.3** Icon + splash + app name via `app.json`
- [ ] **android.4** EAS Build → APK/AAB, install on personal Android
- [ ] **android.5** Distribution: sideload or EAS Submit to Play Store

---

## Phase 18 — In-App Chat Interface

**Why:** Collapse Telegram + claude.ai into the Fin Assist app — native chat UI, push notifications, full financial context.

- [ ] **chat.1** Design session — lock push notification approach, chat backend, context loading, message persistence
- [ ] **chat.2** Expo push notification setup
- [ ] **chat.3** Migrate alert delivery to Expo push
- [ ] **chat.4** Build `/chat` route — message thread, input, streaming response
- [ ] **chat.5** Chat API endpoint — financial context + Claude API + streaming
- [ ] **chat.6** Message history in Supabase (`chat_messages` table)
- [ ] **chat.7** Android WebView default landing → `/chat`
- [ ] **chat.8** Deprecate Telegram bot + Claude mobile Project once stable

---

## Phase 19 — Budgeting & Expenses ⚠️ OPTIONAL / DEFERRED

> **Status:** Parked indefinitely. Expenses tracked in Emma app. Only build if Open Banking / Plaid / TrueLayer MCP integration becomes viable for automatic transaction import.

---

## Immediate Next Steps

1. **Phase 10** — Complete architecture review, update docs (in progress)
2. **Phase 11** — Script consolidation + operational fixes (cron drift, mortgage Telegram, weekend snapshot)
3. **Phase 12** — Sheet audit, schema decisions, safety rules rewrite
4. **Phase 13** — "+" modal, instant Supabase write (highest immediate user value)
5. **Phase 14** — Investments comparison chart (parallel-safe after Phase 12)
6. **Phase 15** — NL entry via Claude mobile → Notion
7. **Phase 16** — `sync_worker.py` bidirectional reconciliation
8. **Phase 17** — Android app (when native UX needed)
9. **Phase 18** — In-app chat (long-term, replaces Telegram + claude.ai)
10. **Ongoing** — Update managed fund values (Nutmeg Alpha, JP Morgan) monthly in `Inv26 - Summary`
