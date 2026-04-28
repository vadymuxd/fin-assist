#!/usr/bin/env python3
"""
stock_assessor.py  —  Script B of the daily 3-step pipeline.

Reads data/news_pool.json (written by news_fetcher.py).
For each holding with news: asks Claude if the holder should sell/trim/buy more.
For each market scan prospect: asks Claude if it's worth buying.
ONLY records non-trivial findings — HOLD and PASS are discarded.

Outputs:
  data/assessments.json  —  actionable findings for alert_dispatcher.py (Script C)

Run:
  python3 scripts/stock_assessor.py
"""

import os
import json
import anthropic
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

POOL_PATH   = 'data/news_pool.json'
OUTPUT_PATH = 'data/assessments.json'
MAX_PROSPECTS = 10  # cap Claude calls for prospects per run


def build_holding_prompt(ticker, name, position, data):
    qty     = position.get('qty', 0)
    avg_buy = position.get('avg_buy', 0)
    current = position.get('current_price', 0)
    pnl_pct = ((current - avg_buy) / avg_buy * 100) if avg_buy else 0
    sign    = '+' if pnl_pct >= 0 else ''

    headlines = data.get('headlines', [])
    lines = [
        f"Review {ticker} ({name}) for a UK retail investor who HOLDS this position.",
        f"Position: {qty:.4f} shares | Avg buy £{avg_buy:.4f} | Current £{current:.4f} | P&L {sign}{pnl_pct:.1f}%",
        "",
        "Task: is there a CONCRETE, SPECIFIC reason to act on this position based on recent news?",
        "Only flag if a real event occurred — not general market sentiment, analyst opinions, or daily price moves.",
        "",
    ]

    if headlines:
        lines.append("Recent news:")
        for i, h in enumerate(headlines[:8], 1):
            title = h.get('headline') if isinstance(h, dict) else str(h)
            lines.append(f"  {i}. {title}")
    else:
        lines.append("Recent news: (none)")

    s_block = (data.get('sentiment') or {}).get('sentiment') or {}
    if s_block:
        lines.append(
            f"\nSentiment: {s_block.get('bullishPercent', 0)*100:.0f}% bullish, "
            f"{s_block.get('bearishPercent', 0)*100:.0f}% bearish"
        )

    a = data.get('analyst') or {}
    if a and any(a.get(k, 0) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')):
        lines.append(
            f"Analysts: StrongBuy {a.get('strongBuy',0)} Buy {a.get('buy',0)} "
            f"Hold {a.get('hold',0)} Sell {a.get('sell',0)} StrongSell {a.get('strongSell',0)}"
        )

    lines += [
        "",
        "Return ONLY a JSON object (no markdown):",
        '{',
        '  "action": "<SELL|EXIT|TRIM|BUY_MORE|NONE>",',
        '  "score": <integer 1-10>,',
        '  "event": "<specific event that triggered this, or empty string>",',
        '  "rationale": "<1-2 sentences: what happened and why it matters for this holder>"',
        '}',
        "",
        "action rules — be conservative, default to NONE:",
        "  NONE    = nothing concrete today, or only general noise",
        "  BUY_MORE = strong positive catalyst, score ≥ 8, thesis still intact",
        "  TRIM    = concerns building but not urgent, score ≤ 4",
        "  SELL/EXIT = concrete bad event requiring immediate attention, score ≤ 3",
        "",
        "If news is only about analyst ratings, macro mood, or daily price — return NONE.",
    ]
    return '\n'.join(lines)


def build_prospect_prompt(ticker, av_items, marketaux_items):
    lines = [
        f"Evaluate {ticker} as a potential BUY for a UK retail investor.",
        "Only recommend BUY if there is a concrete, specific investment reason today.",
        "",
        "Evidence from market sources:",
    ]
    for _, snippet in (av_items or [])[:3]:
        lines.append(f"  - {snippet}")
    for _, snippet in (marketaux_items or [])[:2]:
        lines.append(f"  - {snippet}")

    lines += [
        "",
        "Return ONLY a JSON object (no markdown):",
        '{',
        '  "recommendation": "<BUY|PASS>",',
        '  "score": <integer 1-10>,',
        '  "thesis": "<2-3 sentences: specific catalyst, why now, main risk>",',
        '  "name": "<company full name>"',
        '}',
        "",
        "recommendation rules — default to PASS:",
        "  PASS = generic buzz, no clear catalyst, or score < 7",
        "  BUY  = score ≥ 7 with a concrete thesis (specific news event, valuation trigger, catalyst)",
    ]
    return '\n'.join(lines)


def call_claude(client, prompt, ticker):
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            parts = raw.split('```')
            raw = parts[1].strip()
            if raw.startswith('json'):
                raw = raw[4:].strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"    Claude API error for {ticker}: {e}")
        return None


def main():
    print("=== Script B: Stock Assessor ===")

    if not os.path.exists(POOL_PATH):
        print(f"  {POOL_PATH} not found — run news_fetcher.py first")
        return

    with open(POOL_PATH) as f:
        pool = json.load(f)

    run_time           = pool.get('run_time', datetime.now(timezone.utc).isoformat())
    holdings           = pool.get('holdings', {})
    av_mentions        = pool.get('av_mentions', {})
    marketaux_mentions = pool.get('marketaux_mentions', {})

    client      = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    assessments = []

    # ── Assess holdings ───────────────────────────────────────────────────────
    print(f"\nAssessing {len(holdings)} holdings...")
    for ticker, data in holdings.items():
        position  = data.get('position', {})
        name      = position.get('name', ticker)
        headlines = data.get('headlines', [])

        if not headlines:
            print(f"  {ticker}: no headlines — skip")
            continue

        print(f"  {ticker} ({len(headlines)} headlines)...")
        result = call_claude(client, build_holding_prompt(ticker, name, position, data), ticker)

        if not result:
            continue

        action = result.get('action', 'NONE')
        score  = result.get('score', 5)

        if action == 'NONE':
            print(f"    → NONE (score {score}) — no action needed")
            continue

        event = result.get('event', '').strip()
        print(f"    → {action} | score {score} | {event or '(no specific event)'}")
        assessments.append({
            'type':      'holding',
            'ticker':    ticker,
            'name':      name,
            'action':    action,
            'score':     score,
            'event':     event,
            'rationale': result.get('rationale', '').strip(),
            'run_time':  run_time,
        })

    # ── Assess prospects ──────────────────────────────────────────────────────
    held_tickers     = set(holdings.keys())
    prospect_tickers = (set(av_mentions.keys()) | set(marketaux_mentions.keys())) - held_tickers

    # Rank by combined AV + Marketaux signal; take top MAX_PROSPECTS
    def signal_score(t):
        av   = sum(s for s, _ in av_mentions.get(t, []))
        mkt  = sum(s for s, _ in marketaux_mentions.get(t, []))
        return av * 3 + mkt * 2

    ranked_prospects = sorted(prospect_tickers, key=signal_score, reverse=True)[:MAX_PROSPECTS]
    # Drop anything with a negligible combined score
    ranked_prospects = [t for t in ranked_prospects if signal_score(t) >= 0.5]

    print(f"\nAssessing {len(ranked_prospects)} prospect(s)...")
    for ticker in ranked_prospects:
        av_items  = av_mentions.get(ticker, [])
        mkt_items = marketaux_mentions.get(ticker, [])
        print(f"  {ticker} (signal={signal_score(ticker):.2f})...")

        result = call_claude(client, build_prospect_prompt(ticker, av_items, mkt_items), ticker)
        if not result:
            continue

        rec   = result.get('recommendation', 'PASS')
        score = result.get('score', 5)

        if rec != 'BUY' or score < 7:
            print(f"    → {rec} (score {score}) — skip")
            continue

        print(f"    → BUY (score {score}) — logging")
        assessments.append({
            'type':      'prospect',
            'ticker':    ticker,
            'name':      result.get('name', ticker),
            'action':    'BUY',
            'score':     score,
            'event':     '',
            'rationale': result.get('thesis', '').strip(),
            'run_time':  run_time,
        })

    os.makedirs('data', exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(assessments, f, indent=2)

    print(f"\n{len(assessments)} actionable assessment(s) saved → {OUTPUT_PATH}")
    if not assessments:
        print("  All holdings are HOLD, all prospects are PASS — pipeline complete, no alerts today.")


if __name__ == '__main__':
    main()
