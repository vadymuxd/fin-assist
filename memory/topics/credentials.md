# Credentials & Config

## What exists (never store actual values here — just locations)

| Credential | Location | Status |
|-----------|----------|--------|
| Claude API key | `.env` → `CLAUDE_API_KEY` | ✅ Set |
| Telegram bot token | `.env` → `TELEGRAM_BOT_TOKEN` | ✅ Set |
| Telegram chat ID | `.env` → `TELEGRAM_CHAT_ID` | ✅ Set (8673222152) |
| Google service account JSON | `config/service_account.json` | ✅ In place |
| Google Sheet ID | `.env` → `PORTFOLIO_SHEET_ID` | ✅ Set |
| GitHub repo secrets | GitHub → Settings → Secrets | ❌ Not added yet |

## Key references
- Telegram bot: `@finassist_do_bot`
- Service account email: `fin-assist@fin-assist-492923.iam.gserviceaccount.com`
- Google Cloud project: `fin-assist` (fin-assist-492923)
- GitHub repo: https://github.com/vadymuxd/fin-assist
- Google Sheet: `1IwBSuAzlP0xt0_9pQbztovmfy4Ng1BVCwUuhDurJhsI`

## GitHub Actions secrets still to add
When GitHub Actions workflows are created, add these secrets to the repo
(GitHub → Settings → Secrets and variables → Actions):
- `CLAUDE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOOGLE_SHEETS_CREDS` (paste full contents of service_account.json)
- `PORTFOLIO_SHEET_ID`

## .gitignore rules
- `.env` — excluded
- `config/service_account.json` — excluded (via `*.json` rule, except `config/thresholds.json`)
