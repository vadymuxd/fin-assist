# /log-trades — Log investment trades to all stores

The user has provided one or more trades. Parse them, look up any unknown tickers, confirm, then write to InvTransactions (Sheets), Investments tab (Sheets), Supabase, and Notion Investments Context.

The script auto-manages the Investments tab structure:
- BUY of an unknown ticker → inserts a new row in the stocks section
- SELL that takes Qty to 0 → automatically deletes the row (no zero-qty ghosts)
- After every batch → rewrites stock-section aggregate formulas (G11 SUM, Total T212 SUMIF, Total Freetrade SUMIF) so they're always correct

You don't need to manually trigger row removal or formula updates. The skill must just hand the script accurate JSON.

---

## 1. Look up unknown tickers (web search)

For any ticker NOT in the known list below, use WebSearch to find:
- Full official name
- Exchange / currency (needed for `price_formula`)
- **Sector** — one of: Technology, Communication Services, Financial Services, Industrials, Basic Materials, Healthcare, Consumer Cyclical, Consumer Defensive, Energy, Real Estate, Utilities, ETF
- **Market** — one of: US, LSE, EU, CA (or other exchange code)

Search examples: `<TICKER> ISIN <ISIN> full name exchange sector`, `<TICKER> stock exchange currency`.

Sector/market are required for new BUYs so the Allocation chart classifies the holding correctly. Without them, the ticker shows as "Unknown" until the `sectors` table is patched manually.

**Known positions:**
GOOG (Alphabet Class C, T212, USD/NASDAQ, Communication Services/US), NVDA (Nvidia, T212, USD/NASDAQ, Technology/US), RTX (RTX Corp, T212, USD/NYSE, Industrials/US), RIO (Rio Tinto, T212, GBX/LON, Basic Materials/LSE), TECK.B (Teck Resources Class B, T212, CAD/TSE, Basic Materials/CA), INRG (iShares Global Clean Energy, T212, GBX/LON, ETF/LSE), SGLN (iShares Physical Gold, T212, GBX/LON — manual price, ETF/LSE), IITU (iShares S&P 500 IT Sector, T212, GBX/LON, ETF/LSE), BRK.B (Berkshire Hathaway Class B, Freetrade, USD/NYSE, Financial Services/US), RHM (Rheinmetall, T212, EUR/ETR, Industrials/EU), SWMR (Swarmer Inc, T212, USD/NASDAQ, Industrials/US), KYIV (Kyivstar Group Ltd, T212, USD/NASDAQ, Communication Services/US), UKRN (HANetf Ukraine Reconstruction UCITS ETF, T212, GBP/LON — manual price, ETF/LSE)

---

## 2. Build the price formula for new tickers

The Investments tab col F holds a GOOGLEFINANCE formula that returns the **GBP price per share**. Pattern by exchange:

| Exchange / currency | Formula |
|---|---|
| USD on NASDAQ/NYSE | `=GOOGLEFINANCE("TICKER")/GOOGLEFINANCE("CURRENCY:GBPUSD")` |
| GBX on LSE (pence) | `=GOOGLEFINANCE("LON:TICKER")/100` |
| GBP on LSE (pounds) | `=GOOGLEFINANCE("LON:TICKER")` |
| EUR on Xetra | `=GOOGLEFINANCE("ETR:TICKER")/GOOGLEFINANCE("CURRENCY:GBPEUR")` |
| CAD on TSE | `=GOOGLEFINANCE("TSE:TICKER")/GOOGLEFINANCE("CURRENCY:GBPCAD")` |

If GOOGLEFINANCE coverage is uncertain (some ETFs aren't indexed), omit `price_formula` — the script will write the trade's GBP price as a static value.

**For tickers with no `price_formula`:** also add them to `MANUAL_TICKERS` in `scripts/update_manual_prices.py` so they get picked up in the daily price refresh. The entry format is:
```python
'TICKER': ('TICKER.LON', True),   # True = GBX→GBP (÷100); False = already GBP
```
After editing the script, confirm the addition in the report (step 6).

---

## 3. Parse the trades

Map each trade to JSON. **All prices in GBP**:

```json
{
  "date": "YYYY-MM-DD",
  "ticker": "SWMR",
  "name": "Swarmer, Inc",
  "action": "BUY" | "SELL" | "DEPOSIT" | "WITHDRAWAL" | "TRANSFER_IN" | "TRANSFER_OUT",
  "qty": 8.14461219,
  "price": 24.56,
  "total": 200.00,
  "platform": "T212" | "Freetrade" | "Nutmeg" | ...,
  "notes": "optional",
  "price_formula": "=GOOGLEFINANCE(...)",
  "sector": "Industrials",
  "market": "US"
}
```

`sector` and `market` are **required for BUYs of new tickers** (and ignored for known tickers, SELLs, or cash actions). They're upserted into Supabase `sectors`, which the web app joins to drive the Allocation chart.

**From broker statements:** when USD/EUR price is given with a GBP VALUE column, use GBP:
`price = VALUE_GBP / qty`, `total = VALUE_GBP`.

If price × qty ≠ total, trust `total` and recalculate `price`.

---

## 4. Show confirmation table

Display before writing anything:

```
Action | Ticker | Name | Qty | Price £ | Total £ | Platform | Date
```

State exactly what will happen (referencing current rows). Include for each trade:
- Existing ticker → "row N: Qty x→y, Avg Buy £a→£b"
- New ticker → "new row inserted after last stock"
- SELL → 0 → "row N deleted (full exit)"

And summarise:
- Net cash change
- Aggregate formulas to be rewritten: stocks total (G11), Total T212, Total Freetrade
- Tickers without `price_formula` that will be added to `update_manual_prices.py`
- New tickers with their `sector`/`market` that will be upserted into Supabase `sectors`
- Supabase transactions to insert (DEPOSIT/WITHDRAWAL only)
- Notion Investments Context rebuild

Wait for user confirmation.

---

## 5. Execute

Working directory: `/Users/vadymshcherbakov/Documents/Claude/Fin Assist`

### 5a. If any new ticker has no `price_formula`, add it to `update_manual_prices.py`

Edit `MANUAL_TICKERS` in `scripts/update_manual_prices.py` to include the new ticker before running the trade logger. Use `True` for GBX (LSE pence-quoted), `False` for GBP.

### 5b. Run the trade logger
```
python3 scripts/log_trades.py --json '<json_array>'
```

The script handles InvTransactions, Investments tab inserts/updates/deletes, cash adjustments, aggregate formula rewrites, and Supabase transactions inserts in one pass.

### 5c. Refresh Supabase portfolio snapshot
```
python3 scripts/snapshot_worker.py --domain portfolio
```

### 5d. Rebuild Notion Investments Context
```
python3 scripts/sheets_updater.py --snapshot
```

Run 5c and 5d only if 5b succeeds.

---

## 6. Report results

Summarise:
- InvTransactions rows appended
- Investments changes: rows updated / inserted / deleted, with row numbers (run a quick sheet read if needed to confirm)
- Cash old → new
- Aggregate formulas rewritten (mention the new last_stock_row)
- Manual price tickers added to `update_manual_prices.py` (if any)
- Supabase `sectors` upserts for new tickers (sector/market)
- Supabase `holdings` deletes for full SELLs (so the ticker drops off Allocation/holdings immediately)
- Supabase transactions inserted (cash flow events only)
- Notion snapshot refresh status

If any step errored, surface the message and tell the user what to retry.
