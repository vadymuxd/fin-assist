# Session 001 — Foundations & Infrastructure
**Date:** April 2026
**Status:** Complete

---

## What was discussed

- Reviewed the original build plan (`fin_assist_plan.docx`) which assumed an always-on 2016 MacBook Pro
- Decided the Mac can't run as a server — explored alternatives
- Chose **GitHub Actions** as the automation host (free, no server needed)
- Chose **Telegram** as the only notification channel (both alerts and weekly digest)
- Decided on **twice-daily checks** (8am + 3:30pm weekdays) instead of 30-min continuous monitoring
- Phase 5 (dashboard) deferred — not in MVP
- Updated `fin_assist_plan.docx` to reflect all amendments

## Key decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Automation host | GitHub Actions | Free, no always-on Mac needed |
| Notification | Telegram only | Instant, Android-native, free |
| Check frequency | 8am + 3:30pm weekdays | Sufficient without VPS cost |
| Dashboard | Deferred (Phase 5) | Not needed for MVP |
| Sheet | Use existing sheet, add new tabs only | Don't disrupt existing data |
| Script-writable tabs | `Inv26`, `InvTransactions` only | Protect existing tabs |
| Pensions/savings | Excluded from scope for now | Can't act on them anyway |

## What was built

- GitHub repo: https://github.com/vadymuxd/fin-assist
- Folder structure: `scripts/`, `config/`, `.github/workflows/`
- `requirements.txt` + dependencies installed
- `.gitignore`, `.env.example`
- Telegram bot: `@finassist_do_bot`
- Google Cloud project `fin-assist`, Sheets API enabled, service account created
- `config/service_account.json` in place
- `config/thresholds.json` (placeholder thresholds, needs real holdings)
- `scripts/price_monitor.py` — working, tested with AAPL + BAESF (placeholder tickers)
- `PLAN.md` created in repo root
- `memory/` system created

## What was NOT done (do next session)

- Phase 2: Create Claude Project on claude.ai (Fin Assist conversational agent for mobile)
- Phase 2: Design session — define actual stock thresholds, scoring model
- Phase 3: Export holdings CSVs from T212 + Freetrade
- Phase 3: Create `Inv26` and `InvTransactions` tabs in existing sheet
- Phase 3: Populate with real holdings data
- Phase 4: All remaining scripts (`alert_sender.py`, `sheets_updater.py`, `claude_analyst.py`, etc.)
- Phase 4: GitHub Actions workflows

## Mistake made this session

Jumped into building `price_monitor.py` before completing the Phase 2 design session. Used placeholder tickers instead of waiting for real holdings data. **Rule going forward:** no scripts until design session + real holdings are in the sheet.

---

## References
- Plan: `PLAN.md`
- Architecture decisions: `memory/topics/architecture.md`
- Credentials: `memory/topics/credentials.md`
- Sheet structure: `memory/topics/sheet_structure.md`
