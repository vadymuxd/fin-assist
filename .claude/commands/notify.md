# /notify — Ping Vadym on Telegram when done OR blocked waiting on him

Trigger this any time Vadym asks to be notified — phrases like "notify me
when done", "tell me when you're finished", "message me when it's ready",
"let me know on Telegram", etc. This applies for the rest of the session (or
until he says otherwise), even across multiple tasks in the same
conversation.

Once active, it covers **two distinct moments**, not just completion:

1. **Done** — the task (or everything requested) is finished.
2. **Blocked** — you are about to end your turn while waiting on Vadym,
   because he's away from his Mac and won't see it otherwise. This includes:
   - Asking a clarifying question (`AskUserQuestion`) he needs to answer
     before you can continue.
   - Asking for plain-text confirmation before a risky/destructive action
     (git push, force operations, deleting things, sending messages on his
     behalf, etc. — anything the system prompt already tells you to confirm
     before doing).
   - Any tool call that is about to trigger a permission-approval prompt he
     needs to act on (e.g. a Bash command outside what's pre-approved).

## What to do

**On a blocker** (right before the message/tool call that will pause and
wait for his response — i.e. as part of the same turn, not after):
```
python3 scripts/notify_telegram.py "⏸️ Need you: <one line — what you're asking/what needs approval>"
```
Then proceed with asking the question / making the tool call as normal. Do
this every time you hit a new blocker in the session, not just the first —
each one is a separate reason to come back to the Mac.

**On done** (as the very last step, before ending your turn):
```
python3 scripts/notify_telegram.py "✅ Done: <one or two sentence summary>"
```
- Say what was done (or that it failed, with the reason) — not "I'm done",
  actual content Vadym can act on without reopening the session.
- Keep it under ~300 characters.

In both cases, don't wait for confirmation the message sent before
proceeding/ending your turn — just report success/failure of the send in
your next reply.

## Notes

- Uses `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from `.env` (same bot,
  `@finassist_do_bot`, used by all monitor scripts).
- If Vadym asks to be notified for a single specific task only ("just this
  one"), apply both triggers for that task and don't repeat them for
  unrelated later requests in the same session.
- Don't send a "blocked" ping for routine, expected confirmations that
  aren't really a wait (e.g. don't spam one per line of a multi-part
  question) — one ping per distinct point where you'd otherwise sit idle.
