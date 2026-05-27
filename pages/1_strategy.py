from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="BuyJudge Strategy", page_icon="🧭", layout="wide")
st.title("🧭 Strategy View")

path = Path("outputs") / "similar_scan.csv"
if not path.exists():
    st.info("Run analysis on the main page first.")
    st.stop()

df = pd.read_csv(path)
if df.empty:
    st.info("No result yet.")
    st.stop()

def num(row, key):
    try:
        v = row.get(key, 0)
        if pd.isna(v):
            return 0.0
        return float(v)
    except Exception:
        return 0.0

def is_index_style(row):
    text = f"{row.get('symbol','')} {row.get('name','')}".upper()
    return any(k in text for k in ["ETF", "KODEX", "TIGER", "QQQ", "SPY", "VOO", "IVV", "S&P", "NASDAQ", "나스닥"])

def classify(row):
    verdict = str(row.get("final_verdict", ""))
    pattern = str(row.get("pattern", ""))
    score = num(row, "fast_score")
    win = num(row, "win_rate20")
    avg = num(row, "avg_ret20")
    up = num(row, "avg_max_up20")
    rr = num(row, "rr")
    tv = num(row, "trading_value_ratio20")
    cases = int(num(row, "similar_case_count"))

    if verdict in ["위험차단", "통계부족"]:
        return "exclude", "none", "not ready"
    if is_index_style(row):
        return "stable", "2-8 weeks", "index style"
    if tv >= 1.5 and score >= 65 and win >= 55 and avg >= 2 and up >= 8:
        return "short swing", "3-20 days", "momentum + volume"
    if cases >= 8 and rr >= 1.2 and win >= 50 and (avg >= 4 or up >= 15) and score >= 55:
        return "mid growth swing", "1-4 months", "stats + upside"
    if cases >= 8 and rr >= 1.4 and up >= 25 and any(k in pattern for k in ["정배열", "재상승", "회복", "돌파"]):
        return "long trend watch", "3-12 months", "large upside watch"
    return "watch", "wait", "needs better conditions"

classified = df.apply(lambda r: classify(r), axis=1)
df["strategy_type"] = [x[0] for x in classified]
df["timeframe"] = [x[1] for x in classified]
df["strategy_reason"] = [x[2] for x in classified]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("short", int((df["strategy_type"] == "short swing").sum()))
c2.metric("mid", int((df["strategy_type"] == "mid growth swing").sum()))
c3.metric("long", int((df["strategy_type"] == "long trend watch").sum()))
c4.metric("stable", int((df["strategy_type"] == "stable").sum()))
c5.metric("watch/exclude", int(df["strategy_type"].isin(["watch", "exclude"]).sum()))

choices = sorted(df["strategy_type"].dropna().unique().tolist())
selected = st.multiselect("strategy", choices, default=choices)
view = df[df["strategy_type"].isin(selected)]
cols = ["strategy_type", "timeframe", "strategy_reason", "final_verdict", "symbol", "name", "fast_score", "win_rate20", "avg_ret20", "avg_max_up20", "avg_max_down20", "rr", "trading_value_ratio20", "similar_case_count", "decision_reason"]
cols = [c for c in cols if c in view.columns]
st.dataframe(view[cols], use_container_width=True, hide_index=True)
