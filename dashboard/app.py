import streamlit as st
import pandas as pd
from data.polymarket import get_iran_markets
from data.news import get_latest_headlines
from model.edge import get_trade_signals, calc_edge
from model.estimator import MARKET_PRIORS
from tracker.positions import get_calibration_summary
from config import EDGE_THRESHOLD

st.set_page_config(page_title="PolyEdge", layout="wide")
st.title("PolyEdge — Iran Signal Dashboard")

# ── Live markets ──────────────────────────────────────────────
st.header("Live Edge Signals")
with st.spinner("Fetching markets..."):
    markets = get_iran_markets()
    signals = get_trade_signals(markets, MARKET_PRIORS, EDGE_THRESHOLD)

if signals:
    df = pd.DataFrame(signals)
    df["edge_%"] = (df["edge"] * 100).round(1)
    st.dataframe(df[["question","side","market_prob","your_prob",
                      "edge_%","bet_size","volume","end_date"]],
                 use_container_width=True)
else:
    st.info("No edges above threshold right now.")

# ── News feed ─────────────────────────────────────────────────
st.header("Latest News Signals")
with st.spinner("Fetching news..."):
    articles = get_latest_headlines()
for a in articles[:15]:
    st.markdown(f"**[{a['title']}]({a['url']})** — *{a['source']}* ({a['published'][:10]})")

# ── Calibration ───────────────────────────────────────────────
st.header("Your Calibration")
cal = get_calibration_summary()
st.metric("Resolved Trades", cal["trades"])
if cal["trades"] > 0:
    st.metric("Avg Brier Score", cal["avg_brier"],
              help="Lower = better. Perfect = 0, Random = 0.25")
