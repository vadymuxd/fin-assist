# Google Sheet Structure

**Sheet ID:** `1IwBSuAzlP0xt0_9pQbztovmfy4Ng1BVCwUuhDurJhsI`
**Shared with service account:** `fin-assist@fin-assist-492923.iam.gserviceaccount.com`

---

## EXISTING TABS — DO NOT TOUCH

Scripts must never read from or write to these tabs.

| Tab | Purpose |
|-----|---------|
| `Inv25+` | Platform-level portfolio tracking (Freetrade, T212, Nutmeg, Moneyfarm, Pensions) — monthly snapshots |
| `Inv22-24` | Historical performance Jul 2022 – Mar 2025 |
| `Summary (+)` | Monthly budget summary (income, joint/personal expenses, savings) |
| `Money Flow (+)` | Money flow tracking |
| `Joint Spendings (+)` | Joint expenses |
| `Personal Spendings (+)` | Personal expenses |
| `Savings (+)` | Savings breakdown (joint + personal) |
| `Accounts (+)` | All financial accounts overview |
| `Legend` | Reference/legend |
| `Earnings 2025` | 2025 earnings |

---

## NEW TABS — Scripts read/write here only

### `Inv26`
Single portfolio view: stocks + managed funds on one tab, visually grouped.

**Section 1: Summary (top)**
- Stocks total value, P&L, Managed funds total, Grand total, Last updated

**Section 2: Self-Managed Stocks**
Columns: Ticker | Name | Platform | Qty | Avg Buy Price | Current Price | P&L Today £/% | P&L This Week £ | P&L This Month £ | P&L This Year £ | P&L From Purchase £/% | Score | Recommendation | Last Updated

- Current Price → `=GOOGLEFINANCE(ticker,"price")`
- P&L Today % → `=GOOGLEFINANCE(ticker,"changepct")`
- Historical P&L → `GOOGLEFINANCE` historical price formulas
- Score + Recommendation → written by `claude_analyst.py`
- Last Updated → written by `sheets_updater.py`

**Section 3: Managed Funds**
JP Morgan/Nutmeg Alpha + Moneyfarm — manual value entry monthly
Columns: Name | Provider | Invested £ | Current Value £ | P&L £ | P&L % | Last Updated (manual)

### `InvTransactions`
Full buy/sell history for individual stocks.
Columns: Date | Ticker | Action (Buy/Sell) | Qty | Price Per Share £ | Total Value £ | Platform | Notes

- Populated from T212 + Freetrade CSV exports
- Source of truth for avg buy price in `Inv26`

### `Alerts Config`
Per-stock alert thresholds read by `price_monitor.py`.
Columns: Ticker | Spike % | Drop % | Active (Y/N)

### `Analysis Log`
History of Claude's recommendations, written by `claude_analyst.py`.
Columns: Date | Ticker | Score | Confidence | Reason
