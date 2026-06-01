from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Search", page_icon="🔎", layout="wide")
st.title("🔎 Symbol Search")
st.caption("분석 결과, 빠른 필터, 감시군에서 종목명/티커를 검색합니다. 결과에 없어도 티커를 직접 입력하면 간단 차트를 불러옵니다.")

OUTPUT = Path("outputs")


def read(path):
    try:
        p = Path(path)
        return pd.read_csv(p) if p.exists() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def is_kr(symbol):
    s = str(symbol).upper()
    return s.endswith(".KS") or s.endswith(".KQ")


def price_fmt(value, symbol):
    v = num(value)
    if v <= 0:
        return "-"
    return f"₩{v:,.0f}" if is_kr(symbol) else f"${v:,.2f}"


def load_all():
    frames = []
    sources = [
        ("정밀분석", OUTPUT / "similar_scan.csv"),
        ("빠른필터", OUTPUT / "fast_scan.csv"),
        ("데이터상태", OUTPUT / "data_status.csv"),
        ("기본감시군", "universe_core.csv"),
        ("확장감시군", "universe_extended.csv"),
    ]
    for source, path in sources:
        df = read(path)
        if not df.empty:
            df = df.copy()
            df["source"] = source
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def norm_text(x):
    return str(x).lower().strip()


def search_df(df, q):
    if df.empty or not q:
        return pd.DataFrame()
    q = norm_text(q)
    mask = pd.Series(False, index=df.index)
    for col in ["symbol", "ticker", "name", "종목", "theme", "market", "asset_type"]:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(q, na=False)
    return df[mask].copy()


@st.cache_data(ttl=1800, show_spinner=False)
def chart_data(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        need = ["open", "high", "low", "close", "volume"]
        if any(c not in df.columns for c in need):
            return pd.DataFrame()
        df = df[need].dropna().copy()
        df.index = pd.to_datetime(df.index)
        df["ma20"] = df["close"].rolling(20).mean()
        df["ma60"] = df["close"].rolling(60).mean()
        df["ma120"] = df["close"].rolling(120).mean()
        return df.tail(180)
    except Exception:
        return pd.DataFrame()


def render_chart(symbol):
    df = chart_data(symbol)
    if df.empty:
        st.warning("차트 데이터를 불러오지 못했습니다. 국내 종목은 .KS 또는 .KQ를 붙여보세요. 예: 005930.KS")
        return
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="price"))
    for ma in ["ma20", "ma60", "ma120"]:
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode="lines", name=ma.upper()))
    fig.update_layout(title=f"{symbol} 1Y chart", height=520, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)


all_df = load_all()
query = st.text_input("종목명 또는 티커 검색", placeholder="예: 삼성전기, 하이닉스, NVDA, 005930.KS, QQQ")

if query:
    result = search_df(all_df, query)
    st.subheader("검색 결과")
    if result.empty:
        st.info("분석 결과/감시군 안에서는 못 찾았습니다. 아래 직접 티커 차트를 확인하세요.")
    else:
        preferred = [
            "source", "final_verdict", "symbol", "name", "asset_type", "market", "theme", "fast_score", "pattern",
            "close", "stop", "target", "rr", "pullback_entry", "win_rate20", "avg_ret20", "similar_case_count",
            "decision_reason",
        ]
        cols = [c for c in preferred if c in result.columns]
        extra = [c for c in result.columns if c not in cols]
        st.dataframe(result[cols + extra[:5]], use_container_width=True, hide_index=True)

        symbols = []
        if "symbol" in result.columns:
            symbols = result["symbol"].dropna().astype(str).unique().tolist()
        if symbols:
            selected = st.selectbox("차트 볼 종목", symbols)
            render_chart(selected)

st.divider()
st.subheader("직접 티커 차트")
direct = st.text_input("직접 티커 입력", placeholder="예: NVDA, TSLA, MU, 005930.KS, 000660.KS", key="direct_symbol")
if direct:
    render_chart(direct.strip())

with st.expander("티커 입력 예시"):
    st.markdown(
        """
- 한국 코스피: `005930.KS`, `000660.KS`
- 한국 코스닥: `039030.KQ`, `247540.KQ`
- 미국 주식: `NVDA`, `TSLA`, `MU`, `AAPL`
- 미국 ETF: `QQQ`, `SPY`, `SMH`
        """
    )
