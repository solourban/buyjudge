from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Search", page_icon="🔎", layout="wide")
st.title("🔎 Symbol Search")
st.caption("종목명/티커 검색, 장기 차트, 분석 결과가 있는 종목의 예상 경로를 같이 확인합니다.")

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
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def search_df(df, q):
    if df.empty or not q:
        return pd.DataFrame()
    q = str(q).lower().strip()
    mask = pd.Series(False, index=df.index)
    for col in ["symbol", "ticker", "name", "종목", "theme", "market", "asset_type"]:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(q, na=False)
    return df[mask].copy()


@st.cache_data(ttl=1800, show_spinner=False)
def chart_data(symbol, period):
    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
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
        df = df.sort_index()
        df["ma20"] = df["close"].rolling(20).mean()
        df["ma60"] = df["close"].rolling(60).mean()
        df["ma120"] = df["close"].rolling(120).mean()
        df["ma240"] = df["close"].rolling(240).mean()
        return df
    except Exception:
        return pd.DataFrame()


def add_expected_path(fig, row, df):
    if row is None or df.empty:
        return False
    cases = int(num(row.get("similar_case_count")))
    base = num(row.get("close")) or num(df["close"].iloc[-1])
    if cases <= 0 or base <= 0:
        return False

    last = df.index[-1]
    future = pd.bdate_range(last, periods=22)[1:]
    if len(future) == 0:
        return False
    end = future[-1]

    avg_ret = num(row.get("avg_ret20"))
    avg_up = num(row.get("avg_max_up20"))
    avg_down = num(row.get("avg_max_down20"))

    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_ret / 100)], mode="lines+markers", name="20일 예상 평균", line=dict(dash="dash", width=3)))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_up / 100)], mode="lines", name="20일 상단", line=dict(dash="dot")))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_down / 100)], mode="lines", name="20일 하단", line=dict(dash="dot")))
    fig.add_vrect(x0=last, x1=end, fillcolor="rgba(120,120,120,.08)", line_width=0, annotation_text="예상구간", annotation_position="top left")
    return True


def find_similar_row(symbol):
    sim = read(OUTPUT / "similar_scan.csv")
    if sim.empty or "symbol" not in sim.columns:
        return None
    m = sim[sim["symbol"].astype(str).str.upper() == str(symbol).upper()]
    if m.empty:
        return None
    return m.iloc[0]


def render_chart(symbol, period, row=None):
    df = chart_data(symbol, period)
    if df.empty:
        st.warning("차트 데이터를 불러오지 못했습니다. 국내 종목은 .KS 또는 .KQ를 붙여보세요. 예: 005930.KS")
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="일봉"))
    for ma in ["ma20", "ma60", "ma120", "ma240"]:
        if ma in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode="lines", name=ma.upper()))

    if row is not None:
        close = num(row.get("close"))
        stop = num(row.get("stop"))
        target = num(row.get("target"))
        pullback = num(row.get("pullback_entry"))
        if close > 0:
            fig.add_hline(y=close, line_dash="dot", annotation_text="분석 현재가", annotation_position="top left")
        if stop > 0:
            fig.add_hline(y=stop, line_dash="dash", annotation_text="손절가", annotation_position="bottom left")
        if target > 0:
            fig.add_hline(y=target, line_dash="dash", annotation_text="목표가", annotation_position="top right")
        if pullback > 0:
            fig.add_hline(y=pullback, line_dash="dot", annotation_text="눌림가", annotation_position="bottom right")

    has_expected = add_expected_path(fig, row, df)
    fig.update_layout(title=f"{symbol} · {period} chart", height=560, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

    if has_expected:
        st.caption("예상 경로는 정밀분석 결과의 유사사례 20거래일 평균/상단/하단 시나리오입니다.")
    else:
        st.caption("예상 경로 없음: 이 종목이 정밀분석 결과(similar_scan.csv)에 없거나 유사사례 통계가 부족합니다.")


all_df = load_all()
period = st.selectbox("차트 기간", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3)
query = st.text_input("종목명 또는 티커 검색", placeholder="예: 삼성전기, 하이닉스, NVDA, 005930.KS, QQQ")

if query:
    result = search_df(all_df, query)
    st.subheader("검색 결과")
    if result.empty:
        st.info("분석 결과/감시군 안에서는 못 찾았습니다. 아래 직접 티커 차트를 확인하세요.")
    else:
        preferred = [
            "source", "final_verdict", "symbol", "name", "asset_type", "market", "theme", "fast_score", "pattern",
            "close", "stop", "target", "rr", "pullback_entry", "win_rate20", "avg_ret20", "avg_max_up20", "avg_max_down20", "similar_case_count",
            "decision_reason",
        ]
        cols = [c for c in preferred if c in result.columns]
        extra = [c for c in result.columns if c not in cols]
        st.dataframe(result[cols + extra[:5]], use_container_width=True, hide_index=True)

        symbols = result["symbol"].dropna().astype(str).unique().tolist() if "symbol" in result.columns else []
        if symbols:
            selected = st.selectbox("차트 볼 종목", symbols)
            row = find_similar_row(selected)
            render_chart(selected, period, row)

st.divider()
st.subheader("직접 티커 차트")
direct = st.text_input("직접 티커 입력", placeholder="예: NVDA, TSLA, MU, 005930.KS, 000660.KS", key="direct_symbol")
if direct:
    sym = direct.strip()
    row = find_similar_row(sym)
    render_chart(sym, period, row)

with st.expander("왜 예상 경로가 안 나올 수 있나?"):
    st.markdown(
        """
- 검색 차트는 기본적으로 yfinance 가격 차트입니다.
- **예상 경로는 정밀분석 결과에 있는 종목만** 표시됩니다.
- 즉, 메인에서 분석 실행 → `similar_scan.csv`에 포함 → 유사사례 통계 존재 순서가 필요합니다.
- 감시군에는 있지만 정밀분석 대상이 아니었던 종목은 가격 차트만 표시됩니다.
- 차트 기간은 위의 `차트 기간`에서 6개월~최대 기간까지 바꿀 수 있습니다.
        """
    )

with st.expander("티커 입력 예시"):
    st.markdown(
        """
- 한국 코스피: `005930.KS`, `000660.KS`
- 한국 코스닥: `039030.KQ`, `247540.KQ`
- 미국 주식: `NVDA`, `TSLA`, `MU`, `AAPL`
- 미국 ETF: `QQQ`, `SPY`, `SMH`
        """
    )
