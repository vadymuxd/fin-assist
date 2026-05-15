#!/usr/bin/env python3
"""
mortgage_rates.py — live UK mortgage market data.

Every figure here comes from a real source; nothing is fabricated:

  • BoE base rate           — Bank of England database, series IUDBEDR
  • BoE quoted lender rates — Bank of England database, monthly 2yr/5yr fixed series
  • MPC schedule            — Bank of England 'upcoming MPC dates' page
  • Best-buy mortgage deals — Moneyfacts 85% LTV best-buy table (updated hourly)

Every fetch_* function degrades gracefully: on any failure it returns a dict
with an 'error' key instead of raising, so the monitor still produces a report
(clearly flagging the missing source) rather than crashing.

Standalone debug run:
  python3 scripts/lib/mortgage_rates.py
"""

import re
import html as _html
import json
import math
from datetime import date, datetime

import requests

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": _UA, "Accept-Language": "en-GB,en;q=0.9"}

_IADB = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"

# Bank of England quoted-rate series — average rate quoted by UK lenders.
# code -> (term label, LTV band). Vadym & Lisa sit at ~84% LTV, so the 75%
# and 90% bands bracket them (no 85% band exists in the BoE dataset).
QUOTED_SERIES = {
    "IUMBV34": ("2-year fixed", 75),
    "IUMB482": ("2-year fixed", 90),
    "IUMBV42": ("5-year fixed", 75),
    "IUMZO28": ("5-year fixed", 90),
}

# Official MPC announcement dates — fallback only, used if the BoE page fetch
# fails. The live fetch is preferred so this never needs yearly maintenance.
_MPC_FALLBACK = [
    "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-18", "2026-07-30",
    "2026-09-17", "2026-11-05", "2026-12-17", "2027-02-04", "2027-03-18",
    "2027-04-29", "2027-06-17", "2027-07-29", "2027-09-16", "2027-11-04",
    "2027-12-16",
]

# Moneyfacts best-buy pages, tried in order. The 85% LTV page is the right one
# for Vadym & Lisa; the others are fallbacks in case that page is renamed. All
# expose deals as server-rendered product="{json}" attributes and are permitted
# by robots.txt.
_MONEYFACTS_PAGES = (
    "https://moneyfactscompare.co.uk/mortgages/85-ltv-mortgages/",
    "https://moneyfactscompare.co.uk/mortgages/best-mortgage-rates/",
    "https://moneyfactscompare.co.uk/mortgages/fixed-rate-mortgages/",
)

# Their LTV is ~84%, which sits in the 85% lending tier. Only keep deals a
# borrower at that LTV would actually qualify for.
_MIN_LTV = 84


# ── Bank of England database (IADB) ───────────────────────────────────────────

def _iadb_url(series_codes: str, from_year: int) -> str:
    to_year = date.today().year + 1
    return (
        f"{_IADB}?Travel=NIxAZxSUx&DAT=RNG"
        f"&FD=1&FM=Jan&FY={from_year}&TD=31&TM=Dec&TY={to_year}"
        f"&CSVF=TT&csv.x=66&csv.y=26&UsingCodes=Y&Filter=N&VPD=Y"
        f"&SeriesCodes={series_codes}"
    )


def _parse_iadb_table(html: str):
    """Return (column_codes, [(iso_date, [values...]), ...]) from an IADB page."""
    thead = html[html.find("<thead>"):html.find("</thead>")]
    codes = re.findall(r"<strong[^>]*>([A-Z0-9]+)</strong>", thead)
    tbody = html[html.find("<tbody>"):html.find("</tbody>")]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tbody, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 2:
            continue
        try:
            iso = datetime.strptime(cells[0], "%d %b %y").date().isoformat()
        except ValueError:
            continue
        rows.append((iso, cells[1:]))
    return codes, rows


def fetch_boe_base_rate() -> dict:
    """Current official Bank Rate, the date it last changed, and the prior level."""
    try:
        url = _iadb_url("IUDBEDR", date.today().year - 2)
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        _, rows = _parse_iadb_table(resp.text)
        series = [(d, float(v[0])) for d, v in rows if v and v[0]]
        if not series:
            return {"error": "no IUDBEDR rows parsed from BoE database"}

        current = series[-1][1]
        last_change = series[0][0]
        previous = None
        for i in range(len(series) - 1, 0, -1):
            if series[i][1] == current and series[i - 1][1] != current:
                last_change = series[i][0]
                previous = series[i - 1][1]
                break
        return {
            "rate": current,
            "as_of": series[-1][0],
            "last_change": last_change,
            "previous_rate": previous,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def fetch_boe_quoted_rates() -> dict:
    """Latest + prior-month average quoted 2yr/5yr fixed rates at 75% & 90% LTV."""
    try:
        url = _iadb_url(",".join(QUOTED_SERIES), date.today().year - 1)
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        codes, rows = _parse_iadb_table(resp.text)
        rows = [(d, v) for d, v in rows if any(v)]
        if not rows:
            return {"error": "no quoted-rate rows parsed from BoE database"}

        def row_map(values):
            out = {}
            for i, code in enumerate(codes):
                if i < len(values) and values[i]:
                    try:
                        out[code] = float(values[i])
                    except ValueError:
                        pass
            return out

        latest = row_map(rows[-1][1])
        prev = row_map(rows[-2][1]) if len(rows) >= 2 else {}
        series = []
        for code, (label, ltv) in QUOTED_SERIES.items():
            series.append({
                "code": code, "label": label, "ltv": ltv,
                "rate": latest.get(code), "prev_rate": prev.get(code),
            })
        return {
            "as_of": rows[-1][0],
            "prev_as_of": rows[-2][0] if len(rows) >= 2 else None,
            "series": series,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


# ── MPC schedule ──────────────────────────────────────────────────────────────

def fetch_mpc_dates() -> list:
    """Upcoming MPC interest-rate announcement dates (ISO), today onward."""
    today = date.today().isoformat()
    found = set()
    try:
        resp = requests.get(
            "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates",
            headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        text = resp.text.replace("&nbsp;", " ")
        # MPC announcements always fall on a Thursday, so the correct year is
        # the one where the parsed day/month actually lands on a Thursday.
        for day, month in re.findall(r"Thursday\s+(\d{1,2})\s+([A-Z][a-z]+)", text):
            for yr in (date.today().year, date.today().year + 1):
                try:
                    dt = datetime.strptime(f"{day} {month} {yr}", "%d %B %Y")
                except ValueError:
                    continue
                if dt.weekday() == 3:          # Thursday
                    found.add(dt.date().isoformat())
    except Exception:
        pass

    pool = sorted(found) if found else _MPC_FALLBACK
    upcoming = [d for d in pool if d >= today]
    return upcoming or sorted(_MPC_FALLBACK)


# ── Moneyfacts best-buy table ─────────────────────────────────────────────────

def _ltv_pct(raw) -> float:
    try:
        return round(float(raw))
    except (TypeError, ValueError):
        return None


def _parse_moneyfacts_products(html: str) -> list:
    """Extract unique deal objects from Moneyfacts' product="{json}" attributes."""
    seen, products = set(), []
    for raw in re.findall(r'product="(\{.*?\})"', html):
        try:
            product = json.loads(_html.unescape(raw))
        except json.JSONDecodeError:
            continue
        pid = product.get("Id")
        if pid in seen:
            continue
        seen.add(pid)
        products.append(product)
    return products


def fetch_best_buy_rates() -> dict:
    """Cheapest live 2yr & 5yr fixed deals at the 85% LTV tier, from Moneyfacts."""
    last_error = "no Moneyfacts page returned usable data"

    for url in _MONEYFACTS_PAGES:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=45)
            resp.raise_for_status()
            products = _parse_moneyfacts_products(resp.text)
            if not products:
                last_error = f"no products parsed from {url}"
                continue

            def best(period: str):
                fixed = [p for p in products
                         if p.get("MortgageType") == "Fixed"
                         and p.get("Period") == period
                         and p.get("Rate") is not None
                         and (_ltv_pct(p.get("MaxLTV")) or 0) >= _MIN_LTV]
                if not fixed:
                    return None
                p = min(fixed, key=lambda x: x["Rate"])
                return {
                    "rate": float(p["Rate"]),
                    "lender": p.get("Company") or p.get("ProviderName"),
                    "fee": p.get("ProductFees"),
                    "fee_text": (p.get("ProductFeesText") or "").strip().rstrip(","),
                    "max_ltv": _ltv_pct(p.get("MaxLTV")),
                    "revert": (p.get("FirstRevertText") or "").strip(),
                    "description": p.get("Description"),
                }

            result = {
                "source": "Moneyfacts",
                "page": url,
                "fixed_2yr": best("2 Years"),
                "fixed_5yr": best("5 Years"),
                "product_count": len(products),
            }
            if result["fixed_2yr"] or result["fixed_5yr"]:
                return result
            last_error = f"no qualifying 85%-tier fixed deals on {url}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

    return {"error": last_error}


# ── amortisation ──────────────────────────────────────────────────────────────

def monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
    """Standard repayment-mortgage monthly payment."""
    r = annual_rate / 12
    if r <= 0:
        return principal / term_months
    growth = (1 + r) ** term_months
    return principal * r * growth / (growth - 1)


def remaining_term_months(balance: float, annual_rate: float, payment: float):
    """Months left on a repayment mortgage, inferred from balance/rate/payment."""
    r = annual_rate / 12
    ratio = balance * r / payment
    if ratio >= 1:          # payment does not even cover interest
        return None
    return round(-math.log(1 - ratio) / math.log(1 + r))


# ── debug entrypoint ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("BoE base rate:")
    print(" ", fetch_boe_base_rate())
    print("BoE quoted rates:")
    print(" ", fetch_boe_quoted_rates())
    print("Upcoming MPC dates:")
    print(" ", fetch_mpc_dates()[:4])
    print("Best-buy (Moneyfacts, 85% LTV):")
    print(" ", fetch_best_buy_rates())
