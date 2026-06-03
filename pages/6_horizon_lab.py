from pathlib import Path
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Horizon Lab", page_icon="🧪", layout="wide")
st.title("🧪 Horizon Lab")
st.caption("선택 종목의 유사 구간을 찾아 20/60/120거래일 시나리오를 비교합니다. 기존 결과를 덮어쓰지 않는 실험용 페이지입니다.")

OUTPUT = Path("outputs")


def num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def read_csv(path):
    try:
        p = Path(path)
        return pd.read_csv(p) if p.exists() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def norm_ohlcv(df):
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
    df["trading_value"] = df["close"] * df["volume"]
    return df


def add_ind(df):
    out = df.copy()
    for p in [20, 60, 120, 240]:
        out[f"ma{p}"] = out["close"].rolling(p).mean()
    out["tv20"] = out["trading_value"].rolling(20).mean()
    out["ret5"] = out["close"].pct_change(5)
    out["ret20"] = out["close"].pct_change(20)
    out["ret60"] = out["close"].pct_change(60)
    return out.dropna().copy()


def vector_from_ind(ind, end_idx, window=60):
    if end_idx - window + 1 < 0 or end_idx >= len(ind):
        return None
    w = ind.iloc[end_idx - window + 1:end_idx + 1]
    base = w["close"].iloc[0]
    if base <= 0:
        return None
    points = np.linspace(0, len(w) - 1, 16).round().astype(int)
    price_shape = (w["close"].iloc[points].values / base) - 1
    tv = w["trading_value"].replace(0, np.nan).ffill().fillna(0)
    tv_mean = tv.mean() if tv.mean() > 0 else 1
    tv_shape = np.log((tv.iloc[points].values + 1) / (tv_mean + 1))
    last = w.iloc[-1]
    extra = np.array([
        last["ret5"], last["ret20"], last["ret60"],
        last["close"] / last["ma20"] - 1,
        last["close"] / last["ma60"] - 1,
        np.log((last["trading_value"] + 1) / (last["tv20"] + 1)) if last["tv20"] else 0,
    ])
    return np.nan_to_num(np.concatenate([price_shape, tv_shape, extra]), nan=0.0, posinf=0.0, neginf=0.0)


def similarity(a, b):
    if a is None or b is None or len(a) != len(b):
        return 0.0
    dist = float(np.sqrt(np.mean((a - b) ** 2)))
    return round(100 / (1 + dist * 3), 2)


def future(ind, end_idx, horizon):
    if end_idx + horizon >= len(ind):
        return None
    base = ind["close"].iloc[end_idx]
    fut = ind.iloc[end_idx + 1:end_idx + horizon + 1]
    if base <= 0 or fut.empty:
        return None
    return {
        f"ret{horizon}": (ind["close"].iloc[end_idx + horizon] / base - 1) * 100,
        f"up{horizon}": (fut["high"].max() / base - 1) * 100,
        f"down{horizon}": (fut["low"].min() / base - 1) * 100,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def download(symbol, period):
    try:
        raw = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        return norm_ohlcv(raw)
    except Exception:
        return pd.DataFrame()


def load_universe():
    frames = []
    for file in ["universe_core.csv", "universe_extended.csv"]:
        df = read_csv(file)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", "name", "asset_type", "market"])
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["symbol"])
    if "enabled" in df.columns:
        df = df[~df["enabled"].astype(str).str.upper().isin(["FALSE", "0", "NO", "N"])]
    return df.fillna("")


def calc_cases(target_symbol, target_row, universe, period, top_n, min_sim, step):
    target_df = download(target_symbol, period)
    target_ind = add_ind(target_df)
    if len(target_ind) < 260:
        return pd.DataFrame(), target_df
    target_vec = vector_from_ind(target_ind, len(target_ind) - 1)
    market = str(target_row.get("market", "")).upper()
    asset_type = str(target_row.get("asset_type", "STOCK")).upper()
    pool = universe.copy()
    if market and "market" in pool.columns:
        pool = pool[pool["market"].astype(str).str.upper() == market]
    if asset_type and "asset_type" in pool.columns:
        pool = pool[pool["asset_type"].astype(str).str.upper() == asset_type]
    rows = []
    for _, r in pool.iterrows():
        sym = str(r.get("symbol", "")).strip().upper()
        if not sym:
            continue
        df = target_df if sym == target_symbol else download(sym, period)
        ind = add_ind(df)
        if len(ind) < 260:
            continue
        last_end = len(ind) - 121
        for end_idx in range(60, last_end, step):
            if sym == target_symbol and end_idx > len(ind) - 181:
                continue
            vec = vector_from_ind(ind, end_idx)
            sim = similarity(target_vec, vec)
            if sim < min_sim:
                continue
            item = {
                "case_symbol": sym,
                "case_name": r.get("name", sym),
                "case_date": str(ind.index[end_idx].date()),
                "similarity": sim,
            }
            ok = True
            for h in [20, 60, 120]:
                f = future(ind, end_idx, h)
                if f is None:
                    ok = False
                    break
                item.update({k: round(v, 2) for k, v in f.items()})
            if ok:
                rows.append(item)
    out = pd.DataFrame(rows)
    if out.empty:
        return out, target_df
    return out.sort_values("similarity", ascending=False).head(top_n), target_df


def render_chart(symbol, name, df, stats, horizon):
    if df.empty:
        st.warning("차트 데이터 없음")
        return
    ind = df.copy()
    for p in [20, 60, 120, 240]:
        ind[f"ma{p}"] = ind["close"].rolling(p).mean()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=ind.index, open=ind["open"], high=ind["high"], low=ind["low"], close=ind["close"], name="일봉"))
    for ma in ["ma20", "ma60", "ma120", "ma240"]:
        fig.add_trace(go.Scatter(x=ind.index, y=ind[ma], mode="lines", name=ma.upper()))
    base = float(ind["close"].iloc[-1])
    last = ind.index[-1]
    fut = pd.bdate_range(last, periods=horizon + 2)[1:]
    if len(fut) > 0 and stats:
        end = fut[-1]
        avg = stats.get(f"ret{horizon}", 0)
        up = stats.get(f"up{horizon}", 0)
        down = stats.get(f"down{horizon}", 0)
        fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg / 100)], mode="lines+markers", name=f"{horizon}일 평균", line=dict(dash="dash", width=3)))
        fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + up / 100)], mode="lines", name=f"{horizon}일 상단", line=dict(dash="dot")))
        fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + down / 100)], mode="lines", name=f"{horizon}일 하단", line=dict(dash="dot")))
        fig.add_vrect(x0=last, x1=end, fillcolor="rgba(120,120,120,.08)", line_width=0)
    fig.update_layout(title=f"{name} ({symbol}) · {horizon}거래일 시나리오", height=620, xaxis_rangeslider_visible=True)
    st.plotly_chart(fig, use_container_width=True)


universe = load_universe()
similar = read_csv(OUTPUT / "similar_scan.csv")

if universe.empty:
    st.error("감시군 파일이 없습니다.")
    st.stop()

choices = []
if not similar.empty and "symbol" in similar.columns:
    choices = similar["symbol"].astype(str).tolist()
if not choices:
    choices = universe["symbol"].astype(str).tolist()

with st.sidebar:
    symbol = st.selectbox("대상 종목", choices)
    period = st.selectbox("데이터 기간", ["2y", "5y", "10y", "max"], index=1)
    horizon = st.selectbox("시나리오 기간", [20, 60, 120], index=1)
    top_n = st.selectbox("유사사례 수", [10, 20, 30, 50], index=2)
    min_sim = st.slider("최소 유사도", 45, 75, 55, 1)
    step = st.selectbox("탐색 간격", [5, 10, 20], index=1)

row = universe[universe["symbol"].astype(str).str.upper() == symbol.upper()]
if row.empty:
    st.warning("감시군에서 종목 정보를 찾지 못했습니다.")
    st.stop()
row = row.iloc[0]
name = str(row.get("name", symbol))

if st.button("20/60/120 시나리오 계산", type="primary"):
    with st.spinner("유사 구간 계산 중입니다. 종목 수와 기간에 따라 시간이 걸립니다."):
        cases, chart_df = calc_cases(symbol, row, universe, period, top_n, min_sim, step)
    st.session_state["horizon_cases"] = cases
    st.session_state["horizon_chart"] = chart_df
    st.session_state["horizon_symbol"] = symbol
    st.session_state["horizon_name"] = name

cases = st.session_state.get("horizon_cases", pd.DataFrame())
chart_df = st.session_state.get("horizon_chart", pd.DataFrame())

if cases.empty:
    st.info("계산 결과가 없습니다. 버튼을 누르거나 최소 유사도를 낮춰보세요.")
else:
    stats = {}
    c1, c2, c3 = st.columns(3)
    for i, h in enumerate([20, 60, 120]):
        stats[f"ret{h}"] = float(cases[f"ret{h}"].mean())
        stats[f"up{h}"] = float(cases[f"up{h}"].mean())
        stats[f"down{h}"] = float(cases[f"down{h}"].mean())
        stats[f"win{h}"] = float((cases[f"ret{h}"] > 0).mean() * 100)
        [c1, c2, c3][i].metric(f"{h}일 승률/평균", f"{stats[f'win{h}']:.1f}%", f"{stats[f'ret{h}']:+.2f}%")
    render_chart(st.session_state.get("horizon_symbol", symbol), st.session_state.get("horizon_name", name), chart_df, stats, horizon)
    st.subheader("대표 유사사례")
    st.dataframe(cases, use_container_width=True, hide_index=True)
    st.caption("이 페이지는 실험용입니다. 유사도 기반 통계일 뿐 확정 예측이 아닙니다.")
