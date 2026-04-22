# Fin Assist — Claude Instructions

## At the start of every session, fetch these two pages:

1. **Agent Config** — your identity, current phase, safety rules, scripts, and what to update where
   → https://www.notion.so/33f416f27566811aa994e1a3561adac7

2. **Memory Index** — decision log of everything meaningful that's been decided or built
   → https://www.notion.so/33f416f27566812a8b25fea944567cab

Agent Config tells you when to fetch reference pages (User Profile, Architecture, Credentials, Sheet Structure, Sessions) — only load those when the topic requires it.

## Local roadmap document

`PLAN.md` in repo root is the phase-by-phase build plan (versioned with the code). Read it when the user asks about the roadmap, phases, scope, or "what's next." Not synced to Notion — it mutates with every phase, so the local file is authoritative.

## After every meaningful decision or outcome

Add a detailed summary to the Sessions DB in Notion, then add a one-liner entry to Memory Index pointing to it. Update Agent Config if anything structural changed. Full instructions are in Agent Config.

## Safety rules (always apply, even if Notion is unavailable)

- **Never touch** these Google Sheet tabs: `Inv25+`, `Summary (+)`, `Money Flow (+)`, `Joint Spendings (+)`, `Personal Spendings (+)`, `Savings (+)`, `Accounts (+)`, `Legend`, `Inv22-24`, `Earnings 2025`
- Scripts may only read/write: `Inv26 - Summary`, `Inv26 - Trend`, `InvTransactions`, `Alerts Config`, `Analysis Log`
- `Inv26` tab has been renamed to `Inv26 - Summary`; `Inv26 - Trend` is a new tab created in Phase 3B
- Phase 3B complete: sheet structure, benchmarks, Trend tab, and transaction architecture finalised
