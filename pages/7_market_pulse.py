from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Market Pulse", page_icon="🌐", layout="wide")
st.title("🌐 Market Pulse")
st.caption("후보를 보기 전에 시장 전체 상태를 먼저 확인합니다. 데이터가 없으면 가짜값 대신 데이터 없음으로 표시합니다.")

WATCH = [
    {"group": "Index", "name": "S&P 500", "symbol": "^GSPC"},
    {"group": "Index", "name": "Nasdaq", "symbol": "^IXIC"},
    {"group": "Index", "name": "Dow", "symbol": "^DJI"},
    {"group": "Risk", "name": "VIX", "symbol": "^VIX"},
    {"group": "Rates", "name": "US 10Y", "symbol": "^TNX"},
    {"group": "FX", "name": "USD/KRW", "symbol": "KRW=X"},
    {"group": "Commodity", "name": "WTI", "symbol": "CL=F"},
    {"group": "Commodity", "name": "Gold", "symbol": "GC=F"},
    {"group": "Crypto", "name": "BTC", "symbol": "BTC-USD"},
]

SECTORS = [
    ("XLK", "Technology"),
    ("SMH", "Semiconductor"),
    ("XLY", "Consumer Disc."),
    ("XLF", "Financials"),
    ("XLI", "Industrials"),
    ("XLE", "Energy"),
    ("XLV", "Healthcare"),
    ("XLU", "Utilities"),
    ("XLP", "Consumer Staples"),
    ("IWM", "Small Cap"),
]


def num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


@st.cache_data(ttl=300, show_spinner=False)
def fetch_price(symbol: str, period: str = "6mo") -> pd.DataFrame:
    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        if "close" not in df.columns:
            return pd.DataFrame()
        df = df.dropna(subset=["close"]).copy()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


def snapshot(symbol: str, period: str = "6mo") -> dict:
    df = fetch_price(symbol, period)
    if df.empty or len(df) < 2:
        return {"symbol": symbol, "status": "데이터 없음"}
    close = num(df["close"].iloc[-1])
    prev = num(df["close"].iloc[-2])
    chg = (close / prev - 1) * 100 if prev > 0 else 0
    ma20 = df["close"].rolling(20).mean().iloc[-1] if len(df) >= 20 else None
    ma60 = df["close"].rolling(60).mean().iloc[-1] if len(df) >= 60 else None
    trend = "데이터 부족"
    if ma20 is not None and ma60 is not None and not pd.isna(ma20) and not pd.isna(ma60):
        if close > ma20 > ma60:
            trend = "상승"
        elif close < ma20 < ma60:
            trend = "하락"
        else:
            trend = "혼조"
    return {
        "symbol": symbol,
        "status": "OK",
        "close": close,
        "change_pct": chg,
        "trend": trend,
        "last_date": str(df.index[-1].date()),
        "df": df,
    }


def fmt_value(name: str, value: float) -> str:
    if value is None or pd.isna(value):
        return "데이터 없음"
    if name == "USD/KRW":
        return f"₩{value:,.2f}"
    if name in ["US 10Y", "VIX"]:
        return f"{value:,.2f}"
    if name == "BTC":
        return f"${value:,.0f}"
    return f"{value:,.2f}"


def regime_text(rows: list[dict]) -> tuple[str, str]:
    by_name = {r["name"]: r for r in rows}
    score = 0
    reasons = []

    spx = by_name.get("S&P 500", {})
    ndx = by_name.get("Nasdaq", {})
    vix = by_name.get("VIX", {})
    us10 = by_name.get("US 10Y", {})
    usdkrw = by_name.get("USD/KRW", {})

    if spx.get("trend") == "상승":
        score += 2
        reasons.append("S&P500 상승 추세")
    elif spx.get("trend") == "하락":
        score -= 2
        reasons.append("S&P500 하락 추세")

    if ndx.get("trend") == "상승":
        score += 2
        reasons.append("Nasdaq 상승 추세")
    elif ndx.get("trend") == "하락":
        score -= 2
        reasons.append("Nasdaq 하락 추세")

    if num(vix.get("close")) < 16:
        score += 1
        reasons.append("VIX 낮음")
    elif num(vix.get("close")) > 22:
        score -= 2
        reasons.append("VIX 높음")

    if num(us10.get("change_pct")) > 1.5:
        score -= 1
        reasons.append("금리 상승 압박")
    elif num(us10.get("change_pct")) < -1.5:
        score += 1
        reasons.append("금리 하락 우호")

    if num(usdkrw.get("change_pct")) > 0.8:
        score -= 1
        reasons.append("달러/원 상승")

    if score >= 3:
        return "RISK-ON", " / ".join(reasons)
    if score <= -2:
        return "RISK-OFF", " / ".join(reasons)
    return "MIXED", " / ".join(reasons) if reasons else "판단 데이터 부족"


if st.button("시장 데이터 새로고침", type="primary"):
    st.cache_data.clear()

rows = []
for item in WATCH:
    s = snapshot(item["symbol"])
    s.update(item)
    rows.append(s)

regime, regime_reason = regime_text(rows)
if regime == "RISK-ON":
    st.success(f"시장 상태: {regime} · {regime_reason}")
elif regime == "RISK-OFF":
    st.error(f"시장 상태: {regime} · {regime_reason}")
else:
    st.warning(f"시장 상태: {regime} · {regime_reason}")

st.subheader("시장 스트립")
cols = st.columns(3)
for i, r in enumerate(rows):
    with cols[i % 3]:
        if r.get("status") != "OK":
            st.metric(r["name"], "데이터 없음", "API/지연 확인")
        else:
            st.metric(r["name"], fmt_value(r["name"], r["close"]), f"{r['change_pct']:+.2f}% · {r['trend']}")

st.divider()
st.subheader("차트")
select_names = [r["name"] for r in rows]
selected_name = st.selectbox("차트 선택", select_names, index=0)
selected = next(r for r in rows if r["name"] == selected_name)
if selected.get("status") != "OK":
    st.info("차트 데이터 없음")
else:
    df = selected["df"].copy()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    fig = go.Figure()
    if all(c in df.columns for c in ["open", "high", "low", "close"]):
        fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name=selected_name))
    else:
        fig.add_trace(go.Scatter(x=df.index, y=df["close"], mode="lines", name=selected_name))
    fig.add_trace(go.Scatter(x=df.index, y=df["ma20"], mode="lines", name="MA20"))
    fig.add_trace(go.Scatter(x=df.index, y=df["ma60"], mode="lines", name="MA60"))
    fig.update_layout(height=520, xaxis_rangeslider_visible=True, title=f"{selected_name} ({selected['symbol']})")
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("섹터/테마 모멘텀")
sector_rows = []
for sym, name in SECTORS:
    s = snapshot(sym, "3mo")
    if s.get("status") != "OK":
        sector_rows.append({"symbol": sym, "name": name, "1D%": None, "20D%": None, "trend": "데이터 없음"})
        continue
    df = s["df"]
    close = df["close"]
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else None
    sector_rows.append({"symbol": sym, "name": name, "1D%": round(s["change_pct"], 2), "20D%": round(ret20, 2) if ret20 is not None else None, "trend": s["trend"]})
sector_df = pd.DataFrame(sector_rows)
if not sector_df.empty:
    st.dataframe(sector_df.sort_values("20D%", ascending=False, na_position="last"), use_container_width=True, hide_index=True)

with st.expander("데이터 정책"):
    st.markdown("""
- 데이터는 yfinance에서 가져온 지연 또는 무료 데이터입니다.
- 값이 없으면 임의 숫자를 만들지 않고 `데이터 없음`으로 표시합니다.
- 이 화면은 시장 환경을 보는 보조 도구이며 매매 신호가 아닙니다.
- 실시간 호가, 체결, 주문 기능은 아직 연결하지 않습니다.
    """)
