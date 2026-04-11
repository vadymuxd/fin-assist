# Fin Assist — Claude Instructions

## Memory: Read This First

At the start of every session, read the memory index:
→ `memory/MEMORY.md`

Then follow links to any topic files relevant to the current task. This tells you who Vadym is, what's been built, what decisions were made, and what's in scope.

## Memory: Writing

- When significant decisions are made or new things are built, update `memory/sessions/session_NNN.md` (increment the session number)
- Update the index entry in `memory/MEMORY.md` to include the new session
- Update any relevant topic files in `memory/topics/` if facts changed (credentials, architecture, sheet structure, etc.)
- Do this at natural session end or when the memory reminder fires

## Ground Rules

- **Never touch** the following Google Sheet tabs: `Inv25+`, `Summary (+)`, `Money Flow (+)`, `Joint Spendings (+)`, `Personal Spendings (+)`, `Savings (+)`, `Accounts (+)`, `Legend`, `Inv22-24`, `Earnings 2025`
- Scripts may only read/write to: `Inv26`, `InvTransactions`, `Alerts Config`, `Analysis Log`
- No new scripts until Phase 2 design session is complete and real holdings data is in the sheet
- See `PLAN.md` for current task state before starting any work
