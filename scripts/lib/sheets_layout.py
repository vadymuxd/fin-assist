"""
sheets_layout.py — Shared row-detection helpers for the Investments tab.

Single source of truth for locating key rows by scanning col A (labels)
and col C (broker totals). Used by snapshot_worker, sheets_updater, and
log_trades so all three stay in sync as rows are inserted/deleted.

Returned dict keys (both naming conventions kept as aliases so existing
callers don't need to be rewritten):

  Snapshot/reader names:
    vadym_total, cash, stocks_total, managed_total,
    sp500, ftse100, nasdaq100, msci_world, gold,
    lisa_total, joint_total

  Trade-writer names (log_trades):
    cash_row, stocks_total_row, first_stock_row,
    t212_total_row, freetrade_total_row, managed_funds_row
"""


def find_investment_rows(ws):
    """
    Scan the Investments tab for all key markers in one pass.

    Returns a dict with 1-based row numbers. Robust to row inserts/deletes
    in the stocks section caused by log_trades add/remove operations.
    """
    all_rows = ws.get_all_values()
    rows = {}

    for i, row in enumerate(all_rows, start=1):
        a = (row[0] if row else '').strip().upper()
        c = (row[2] if len(row) > 2 else '').strip().upper()

        if a == 'VADYM TOTAL' and 'vadym_total' not in rows:
            rows['vadym_total'] = i + 2        # label → header row → value row

        elif 'CASH FOR INVESTMENTS' in a and 'cash' not in rows:
            rows['cash']     = i + 1
            rows['cash_row'] = i + 1           # log_trades alias

        elif 'SELF-MANAGED STOCKS' in a and 'stocks_total' not in rows:
            rows['stocks_total']     = i + 1
            rows['stocks_total_row'] = i + 1   # log_trades alias
            rows['first_stock_row']  = i + 2   # log_trades: first individual stock row

        elif c.startswith('TOTAL T212') and 't212_total_row' not in rows:
            rows['t212_total_row'] = i         # log_trades only — boundary marker

        elif c.startswith('TOTAL FREE') and 'freetrade_total_row' not in rows:
            # handles "Freetrade" and the legacy "Freedtrade" typo
            rows['freetrade_total_row'] = i    # log_trades only — boundary marker

        elif 'MANAGED FUNDS' in a and 'managed_funds_row' not in rows:
            rows['managed_funds_row'] = i      # log_trades: label row itself (boundary)
            rows['managed_total']     = i + 1  # snapshot_worker: first managed fund value row

        elif 'BENCHMARK' in a and 'sp500' not in rows:
            rows['sp500']      = i + 1
            rows['ftse100']    = i + 2
            rows['nasdaq100']  = i + 3
            rows['msci_world'] = i + 4
            rows['gold']       = i + 5

        elif a == 'LISA TOTAL' and 'lisa_total' not in rows:
            rows['lisa_total'] = i + 1

        elif a == 'JOINT TOTAL' and 'joint_total' not in rows:
            rows['joint_total'] = i + 1

    return rows
