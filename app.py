import base64
import json
import os
from datetime import datetime

import requests
import streamlit as st
import yfinance as yf


def _secret(key, default=""):
    try:
        return st.secrets.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


REPO = _secret("GITHUB_REPO", "tumajanfran/stock-price-alerts")
TOKEN = _secret("GITHUB_TOKEN", "")
BRANCH = _secret("GITHUB_BRANCH", "master")
PATH = "alerts.json"

API = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def api_get():
    r = requests.get(API, params={"ref": BRANCH}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    body = base64.b64decode(data["content"]).decode("utf-8") or "[]"
    return json.loads(body), data["sha"]


def api_put(alerts, sha, message):
    payload = {
        "message": message,
        "content": base64.b64encode(json.dumps(alerts, indent=2).encode()).decode(),
        "branch": BRANCH,
        "sha": sha,
    }
    r = requests.put(API, json=payload, headers=HEADERS, timeout=15)
    r.raise_for_status()


def commit(mutator, message):
    alerts, sha = api_get()
    mutator(alerts)
    api_put(alerts, sha, message)


def match(alert, ticker, target, direction):
    return (
        alert["ticker"] == ticker
        and float(alert["target"]) == float(target)
        and alert["direction"] == direction
    )


@st.cache_data(ttl=60, show_spinner=False)
def current_price(ticker):
    try:
        t = yf.Ticker(ticker)
        p = t.fast_info.get("last_price")
        if p is not None:
            return float(p)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


st.set_page_config(page_title="Stock Alerts", layout="centered")
st.title("Stock Price Alerts")

if not TOKEN:
    st.error(
        "GITHUB_TOKEN is not configured. In Streamlit Cloud, open the app's "
        "**Settings → Secrets** and add a line like:\n\n"
        '`GITHUB_TOKEN = "github_pat_..."`'
    )
    st.stop()

try:
    alerts, _ = api_get()
except Exception as e:
    st.error(f"Could not load alerts from GitHub: {e}")
    st.stop()

st.caption(f"Repo: `{REPO}` — checked every ~10 min by GitHub Actions")

with st.form("add", clear_on_submit=True):
    st.subheader("Add alert")
    c1, c2, c3 = st.columns([2, 2, 1.5])
    ticker_in = c1.text_input("Ticker", placeholder="AAPL")
    target_in = c2.number_input("Target price", min_value=0.0, step=1.0, format="%.2f")
    direction_in = c3.selectbox("Direction", ["above", "below"])
    submitted = st.form_submit_button("Add", type="primary")
    if submitted:
        ticker = ticker_in.strip().upper()
        if not ticker:
            st.warning("Enter a ticker.")
        elif target_in <= 0:
            st.warning("Enter a positive target price.")
        else:
            try:
                new = {
                    "ticker": ticker,
                    "target": float(target_in),
                    "direction": direction_in,
                    "triggered": False,
                }
                commit(lambda lst: lst.append(new), f"Add {ticker} {direction_in} {target_in}")
                st.success(f"Added {ticker} {direction_in} {target_in}.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

st.subheader("Current alerts")

if not alerts:
    st.info("No alerts yet. Add one above.")
else:
    for i, a in enumerate(alerts):
        ticker = a["ticker"]
        target = float(a["target"])
        direction = a["direction"]
        triggered = bool(a.get("triggered"))

        with st.container(border=True):
            cols = st.columns([1.3, 1.3, 2, 1.8, 1, 1])
            cols[0].markdown(f"**{ticker}**")
            price = current_price(ticker)
            cols[1].write(f"{price:.2f}" if price is not None else "—")
            cols[2].write(f"Target {direction} {target:g}")
            if triggered:
                tp = a.get("triggered_price", "?")
                cols[3].markdown(f":green[**TRIGGERED**] @ {tp}")
            else:
                cols[3].markdown(":blue[active]")

            if triggered:
                if cols[4].button("Reset", key=f"reset-{i}"):
                    def reset(lst, t=ticker, tg=target, d=direction):
                        for x in lst:
                            if match(x, t, tg, d):
                                x["triggered"] = False
                                x.pop("triggered_price", None)
                                return
                    try:
                        commit(reset, f"Re-arm {ticker}")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                cols[4].write("")

            if cols[5].button("Delete", key=f"del-{i}"):
                def remove(lst, t=ticker, tg=target, d=direction):
                    for idx, x in enumerate(lst):
                        if match(x, t, tg, d):
                            del lst[idx]
                            return
                try:
                    commit(remove, f"Delete {ticker} alert")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

st.caption(f"Loaded at {datetime.now().strftime('%H:%M:%S')} — prices cached 60s")
