import os
import json
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

THRESHOLDS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'thresholds.json')

# Placeholder tickers — replace with your actual holdings
TICKERS = ['AAPL', 'RHM.DE', 'BAESF']


def load_thresholds():
    with open(THRESHOLDS_PATH) as f:
        return json.load(f)


def get_price_data():
    hist = yf.download(TICKERS, period='2d', auto_adjust=True, progress=False)
    if hist.empty or len(hist) < 2:
        return []

    results = []
    for ticker in TICKERS:
        try:
            closes = hist['Close'][ticker].dropna()
            if len(closes) < 2:
                print(f"⚠️  Not enough data for {ticker}")
                continue
            prev_close = float(closes.iloc[-2])
            current = float(closes.iloc[-1])
            change_pct = ((current - prev_close) / prev_close) * 100
            results.append({
                'ticker': ticker,
                'prev_close': round(prev_close, 2),
                'current': round(current, 2),
                'change_pct': round(change_pct, 2),
            })
        except Exception as e:
            print(f"⚠️  No data for {ticker}: {e}")
    return results


def check_alerts(price_data, thresholds):
    overrides = thresholds.get('overrides', {})
    default = thresholds['default']
    ticker = price_data['ticker']
    limits = overrides.get(ticker, default)
    alerts = []
    if price_data['change_pct'] >= limits['spike_pct']:
        alerts.append(f"🚀 SPIKE: {ticker} +{price_data['change_pct']}% (threshold: +{limits['spike_pct']}%)")
    elif price_data['change_pct'] <= -limits['drop_pct']:
        alerts.append(f"🔻 DROP: {ticker} {price_data['change_pct']}% (threshold: -{limits['drop_pct']}%)")
    return alerts


def run():
    thresholds = load_thresholds()
    alerts = []

    results = get_price_data()
    for data in results:
        alerts.extend(check_alerts(data, thresholds))
        print(f"{data['ticker']}: {data['current']} ({'+' if data['change_pct'] >= 0 else ''}{data['change_pct']}%)")

    if alerts:
        print("\nALERTS:")
        for a in alerts:
            print(a)
    else:
        print("\nNo alerts triggered.")

    return results, alerts


if __name__ == '__main__':
    run()
