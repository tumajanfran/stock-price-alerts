import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import yfinance as yf

ALERTS_FILE = Path("alerts.json")


def fetch_price(ticker):
    t = yf.Ticker(ticker)
    try:
        price = t.fast_info.get("last_price")
        if price is not None:
            return float(price)
    except Exception:
        pass
    hist = t.history(period="1d")
    if hist.empty:
        raise ValueError(f"No price data for {ticker}")
    return float(hist["Close"].iloc[-1])


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.environ["SENDER_EMAIL"]
    msg["To"] = os.environ["RECIPIENT_EMAIL"]
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(os.environ["SENDER_EMAIL"], os.environ["APP_PASSWORD"])
        server.send_message(msg)


def normalize(alerts):
    for a in alerts:
        a["ticker"] = a["ticker"].strip().upper()
        a["direction"] = a.get("direction", "above").strip().lower()
        a["target"] = float(a["target"])
        a.setdefault("triggered", False)
    return alerts


def main():
    if not ALERTS_FILE.exists():
        print("No alerts.json found.")
        return

    alerts = normalize(json.loads(ALERTS_FILE.read_text() or "[]"))
    active = [a for a in alerts if not a.get("triggered")]
    if not active:
        print("No active alerts.")
        ALERTS_FILE.write_text(json.dumps(alerts, indent=2))
        return

    tickers = sorted({a["ticker"] for a in active})
    prices = {}
    for t in tickers:
        try:
            prices[t] = fetch_price(t)
            print(f"{t}: {prices[t]:.2f}")
        except Exception as e:
            print(f"Failed to fetch {t}: {e}", file=sys.stderr)

    for alert in alerts:
        if alert.get("triggered"):
            continue
        price = prices.get(alert["ticker"])
        if price is None:
            continue
        hit = (
            (alert["direction"] == "above" and price >= alert["target"]) or
            (alert["direction"] == "below" and price <= alert["target"])
        )
        if not hit:
            continue
        subject = f"Stock alert: {alert['ticker']} {alert['direction']} {alert['target']}"
        body = (
            f"{alert['ticker']} is at {price:.2f}, "
            f"which is {alert['direction']} your target of {alert['target']}.\n\n"
            f"Sent by Stock Alerts (GitHub Actions)."
        )
        try:
            send_email(subject, body)
            alert["triggered"] = True
            alert["triggered_price"] = round(price, 2)
            print(f"ALERT SENT: {alert['ticker']} at {price:.2f}")
        except Exception as e:
            print(f"Email failed for {alert['ticker']}: {e}", file=sys.stderr)

    ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


if __name__ == "__main__":
    main()
