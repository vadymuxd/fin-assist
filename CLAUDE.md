# Fin Assist — Claude Instructions

## At the start of every session, fetch these two pages:

1. **Agent Config** — your identity, current phase, safety rules, scripts, and what to update where
   → https://www.notion.so/33f416f27566811aa994e1a3561adac7

2. **Memory Index** — decision log of everything meaningful that's been decided or built
   → https://www.notion.so/33f416f27566812a8b25fea944567cab

Agent Config tells you when to fetch reference pages (User Profile, Architecture, Credentials, Sheet Structure, Sessions) — only load those when the topic requires it.

## After every meaningful decision or outcome

Add a detailed summary to the Sessions DB in Notion, then add a one-liner entry to Memory Index pointing to it. Update Agent Config if anything structural changed. Full instructions are in Agent Config.

## Safety rules (always apply, even if Notion is unavailable)

- **Never touch** these Google Sheet tabs: `Inv25+`, `Summary (+)`, `Money Flow (+)`, `Joint Spendings (+)`, `Personal Spendings (+)`, `Savings (+)`, `Accounts (+)`, `Legend`, `Inv22-24`, `Earnings 2025`
- Scripts may only read/write: `Inv26`, `InvTransactions`, `Alerts Config`, `Analysis Log`
- No new scripts until Phase 3 design session is complete and real holdings data is in the sheet
