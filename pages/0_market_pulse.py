from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Market Pulse", page_icon="🌐", layout="wide")
st.title("🌐 Market Pulse")
st.caption("후보 종목을 보기 전에 시장 전체 분위기를 먼저 확인합니다. 데이터가 없으면 가짜 숫자를 넣지 않습니다.")

MARKETS = [
    {"group": "미국 지수", "name": "S&P 500", "symbol": "^GSPC"},
    {"group": "미국 지수", "name": "Nasdaq", "symbol": "^IXIC"},
    {"group": "미국 지수", "name": "Dow", "symbol": "^DJI"},
    {"group": "변동성", "name": "VIX", "symbol": "^VIX"},
    {"group": "금리", "name": "미국 10년물", "symbol": "^TNX"},
    {"group": "환율", "name": "달러/원", "symbol": "KRW=X"},
    {"group": "원자재", "name": "WTI", "symbol": "CL=F"},
    {"group": "원자재", "name": "Gold", "symbol": "GC=F"},
    {"group": "크립토", "name": "Bitcoin", "symbol": "BTC-USD"},
]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    if "close" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["close"]).copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


@st.cache_data(ttl=300, show_spinner=False)
def load_one(symbol: str, period: str = "6mo") -> tuple[pd.DataFrame, str]:
    try:
        raw = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        df = normalize(raw)
        if df.empty:
            return pd.DataFrame(), "데이터 없음"
        return df, "지연/공개 데이터"
    except Exception as e:
        return pd.DataFrame(), f"불러오기 실패: {type(e).__name__}"


def fmt_value(symbol: str, value: float) -> str:
    if pd.isna(value):
        return "데이터 없음"
    if symbol == "^TNX":
        return f"{value:.2f}"
    if symbol == "KRW=X":
        return f"₩{value:,.2f}"
    if symbol in ["CL=F", "GC=F", "BTC-USD"]:
        return f"${value:,.2f}"
    return f"{value:,.2f}"


def classify_regime(rows: pd.DataFrame) -> tuple[str, str]:
    if rows.empty:
        return "판단 불가", "시장 데이터가 없습니다."
    lookup = rows.set_index("symbol").to_dict("index")
    spx = lookup.get("^GSPC", {})
    nas = lookup.get("^IXIC", {})
    vix = lookup.get("^VIX", {})
    tnx = lookup.get("^TNX", {})
    score = 0
    reasons = []
    if spx.get("change_pct", 0) > 0:
        score += 1
        reasons.append("S&P500 상승")
    if nas.get("change_pct", 0) > 0:
        score += 1
        reasons.append("Nasdaq 상승")
    if vix.get("last", 99) < 18:
        score += 1
        reasons.append("VIX 안정")
    elif vix.get("last", 0) > 25:
        score -= 2
        reasons.append("VIX 고위험")
    if tnx.get("change_pct", 0) > 1.0:
        score -= 1
        reasons.append("10년물 금리 상승 압력")
    if score >= 2:
        return "Risk-On 우세", " / ".join(reasons)
    if score <= -1:
        return "Risk-Off 주의", " / ".join(reasons)
    return "중립/혼조", " / ".join(reasons) if reasons else "뚜렷한 방향성 부족"


period = st.selectbox("차트 기간", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=2)
rows = []
series = {}

with st.spinner("시장 데이터 확인 중입니다."):
    for item in MARKETS:
        df, status = load_one(item["symbol"], period)
        if df.empty or len(df) < 2:
            rows.append({
                "group": item["group"], "name": item["name"], "symbol": item["symbol"],
                "last": None, "prev": None, "change_pct": None, "status": status,
            })
            continue
        last = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-2])
        change_pct = (last / prev - 1) * 100 if prev else 0
        rows.append({
            "group": item["group"], "name": item["name"], "symbol": item["symbol"],
            "last": last, "prev": prev, "change_pct": change_pct, "status": status,
        })
        series[item["symbol"]] = df

summary = pd.DataFrame(rows)
regime, regime_reason = classify_regime(summary.dropna(subset=["last"]))
st.subheader(f"시장 상태: {regime}")
st.caption(regime_reason)

cols = st.columns(3)
for idx, r in summary.iterrows():
    delta = None if pd.isna(r["change_pct"]) else f"{r['change_pct']:+.2f}%"
    cols[idx % 3].metric(f"{r['name']} ({r['symbol']})", fmt_value(r["symbol"], r["last"]), delta)

st.divider()
st.subheader("시장 차트")
chart_symbols = st.multiselect(
    "표시할 항목",
    [f"{m['name']} ({m['symbol']})" for m in MARKETS],
    default=["S&P 500 (^GSPC)", "Nasdaq (^IXIC)", "VIX (^VIX)", "미국 10년물 (^TNX)"]
)

fig = go.Figure()
for label in chart_symbols:
    symbol = label.split("(")[-1].replace(")", "")
    df = series.get(symbol)
    if df is None or df.empty:
        continue
    base = float(df["close"].iloc[0])
    if base <= 0:
        continue
    fig.add_trace(go.Scatter(x=df.index, y=(df["close"] / base - 1) * 100, mode="lines", name=label))
fig.update_layout(height=520, title="선택 항목 기간 수익률 비교(%)", yaxis_title="기간 수익률(%)", margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig, use_container_width=True)

st.subheader("데이터 상태")
view = summary.copy()
view["last"] = view.apply(lambda r: fmt_value(r["symbol"], r["last"]), axis=1)
view["change_pct"] = view["change_pct"].apply(lambda x: "데이터 없음" if pd.isna(x) else f"{x:+.2f}%")
st.dataframe(view[["group", "name", "symbol", "last", "change_pct", "status"]], use_container_width=True, hide_index=True)

st.caption(f"마지막 새로고침: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} / yfinance 공개·지연 데이터 기준. 실시간 보장은 API 연동 전까지 하지 않습니다.")
