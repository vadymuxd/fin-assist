# Architecture Decisions

## Automation host: GitHub Actions (not Mac)
- Original plan: always-on 2016 MacBook Pro in clamshell mode
- **Decision:** GitHub Actions — free, cloud-hosted, no hardware dependency
- Scripts run on cron: weekdays 8am + 3:30pm UTC
- Workflows: `daily_monitor.yml` + `weekly_digest.yml`
- Manual trigger: `workflow_dispatch` from GitHub UI

## Notifications: Telegram only
- Bot: `@finassist_do_bot`
- Both urgent alerts AND weekly digest go to Telegram
- No email

## Check frequency: twice daily
- 8am weekdays: morning check + Claude analysis
- 3:30pm weekdays: end-of-day check
- No 30-min real-time monitoring (would require VPS)

## Conversational agent: Claude Project on claude.ai
- Separate from this Claude Code session
- Accessible from Claude mobile app on Pixel 9 Pro
- System prompt contains: holdings, investment thesis, risk tolerance, scoring preferences
- NOT the same as the automation — two separate things

## Memory system: local + Notion sync (Phase 6, in progress)
- Local source of truth: `memory/` folder in repo (topics/ + sessions/)
- `CLAUDE.md` in repo root: tells Claude Code to read memory at session start
- Stop hook: `scripts/memory_reminder.sh` fires after every 5 turns, prompts memory update
- Shared memory across surfaces: **Notion** (to be set up next session)
  - Both Claude Code and claude.ai can read/write Notion via MCP
  - Google Drive MCP ruled out: read-only, no write capability
- Claude Project system prompt = stable context; Notion = dynamic/recent context

## Google access: two separate things — do not confuse
- **Scripts → Google Sheets**: service account JSON, already works, used by Python automation
- **Claude interactive → Google Sheets**: no reliable read/write MCP exists yet
  - Deferred: will build custom MCP wrapper around existing service account when needed
  - Google Drive MCP is read-only (fetch + search only) — not suitable

## Dashboard: deferred
- Phase 5, not in MVP
- All output via Telegram for now
- When built, reads directly from Google Sheet

## Data flow
```
GitHub Actions (cron)
  → price_monitor.py (fetch prices via yfinance)
  → claude_analyst.py (call Claude API for scoring)
  → alert_sender.py (Telegram if threshold breached)
  → sheets_updater.py (write scores to Inv26 tab)
  → weekly_digest.py (Sunday Telegram summary)

Google Sheet (source of truth)
  → Inv26 tab: live portfolio + P&L formulas
  → InvTransactions tab: full trade history
  → All other tabs: untouched
```
