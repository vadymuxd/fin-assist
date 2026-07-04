# /notify — Ping Vadym on Telegram when work is done

Trigger this any time Vadym asks to be notified when the current task finishes —
phrases like "notify me when done", "tell me when you're finished", "message me
when it's ready", "let me know on Telegram", etc. This applies for the rest of
the session (or until he says otherwise), even across multiple tasks in the
same conversation.

## What to do

1. Finish the requested work as normal.
2. As the very last step, before ending your turn, send a short Telegram
   message summarizing the outcome:
   ```
   python3 scripts/notify_telegram.py "<one or two sentence summary>"
   ```
   - Say what was done (or that it failed, with the reason) — not "I'm done",
     actual content Vadym can act on without reopening the session.
   - Keep it under ~300 characters.
3. Don't wait for confirmation the message sent before ending your turn —
   just report success/failure of the send in your final reply.

## Notes

- Uses `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from `.env` (same bot,
  `@finassist_do_bot`, used by all monitor scripts).
- If Vadym asks to be notified for a single specific task only ("just this
  one"), send the message and don't repeat it for unrelated later requests
  in the same session.
