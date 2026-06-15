from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="BuyJudge Instant", page_icon="⚡", layout="wide")
st.title("⚡ Instant Analysis")
st.caption("검색만 하지 말고, 원하는 티커를 임시 감시군으로 만들어 즉석 정밀분석합니다.")

OUTPUT = Path("outputs")
TEMP_UNIVERSE = Path("manual_universe.csv")
MANUAL_SCAN = OUTPUT / "manual_scan.csv"
RUN_TIMEOUT_SECONDS = 240


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


def parse_lines(text):
    rows = []
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", ",").split(",") if p.strip()]
        symbol = parts[0].upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        name = parts[1] if len(parts) >= 2 else symbol
        market = "KR" if is_kr(symbol) else "US"
        rows.append({
            "enabled": True,
            "symbol": symbol,
            "name": name,
            "asset_type": "STOCK",
            "market": market,
            "theme": "MANUAL",
        })
    return rows


def backup_outputs():
    OUTPUT.mkdir(exist_ok=True)
    targets = ["similar_scan.csv", "similar_cases_raw.csv", "fast_scan.csv", "data_status.csv"]
    backed = []
    for name in targets:
        p = OUTPUT / name
        b = OUTPUT / f".{name}.bak"
        if p.exists():
            shutil.copy2(p, b)
            backed.append((p, b))
    return backed


def restore_outputs(backed):
    for p, b in backed:
        if b.exists():
            shutil.copy2(b, p)
            b.unlink(missing_ok=True)


def run_manual_analysis(rows, period, max_candidates, top_n, min_similarity, min_cases):
    df = pd.DataFrame(rows)
    df.to_csv(TEMP_UNIVERSE, index=False, encoding="utf-8-sig")
    backed = backup_outputs()
    args = [
        sys.executable, "main.py", "similar",
        "--universe", str(TEMP_UNIVERSE),
        "--period", period,
        "--max-candidates", str(max_candidates),
        "--top-n", str(top_n),
        "--min-similarity", str(min_similarity),
        "--min-cases", str(min_cases),
    ]

    manual = pd.DataFrame()
    code = 1
    log = ""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT_SECONDS,
        )
        code = proc.returncode
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if (OUTPUT / "similar_scan.csv").exists():
            manual = pd.read_csv(OUTPUT / "similar_scan.csv")
            manual.to_csv(MANUAL_SCAN, index=False, encoding="utf-8-sig")
    except subprocess.TimeoutExpired as exc:
        code = 124
        partial_out = exc.stdout if isinstance(exc.stdout, str) else ""
        partial_err = exc.stderr if isinstance(exc.stderr, str) else ""
        log = partial_out + "\n" + partial_err + f"\n[TIMEOUT] {RUN_TIMEOUT_SECONDS}초를 초과해 즉석 분석을 중단했습니다. 종목 수/기간/유사사례 수를 줄여보세요."
    except Exception as exc:
        code = 1
        log = f"[ERROR] {type(exc).__name__}: {exc}"
    finally:
        restore_outputs(backed)
        TEMP_UNIVERSE.unlink(missing_ok=True)
    return code, log, manual


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


def add_expected(fig, row, df):
    cases = int(num(row.get("similar_case_count")))
    base = num(row.get("close")) or num(df["close"].iloc[-1])
    if cases <= 0 or base <= 0 or df.empty:
        return False
    last = df.index[-1]
    future = pd.bdate_range(last, periods=22)[1:]
    if len(future) == 0:
        return False
    end = future[-1]
    avg = num(row.get("avg_ret20"))
    up = num(row.get("avg_max_up20"))
    down = num(row.get("avg_max_down20"))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg / 100)], mode="lines+markers", name="20일 예상 평균", line=dict(dash="dash", width=3)))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + up / 100)], mode="lines", name="상단", line=dict(dash="dot")))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + down / 100)], mode="lines", name="하단", line=dict(dash="dot")))
    fig.add_vrect(x0=last, x1=end, fillcolor="rgba(120,120,120,.08)", line_width=0)
    return True


def render_chart(row, period):
    symbol = str(row.get("symbol", ""))
    df = chart_data(symbol, period)
    if df.empty:
        st.warning(f"{symbol} 차트 데이터를 불러오지 못했습니다.")
        return
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="일봉"))
    for ma in ["ma20", "ma60", "ma120", "ma240"]:
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode="lines", name=ma.upper()))
    for key, label in [("close", "현재가"), ("stop", "손절가"), ("target", "목표가"), ("pullback_entry", "눌림가")]:
        v = num(row.get(key))
        if v > 0:
            fig.add_hline(y=v, line_dash="dash" if key in ["stop", "target"] else "dot", annotation_text=label)
    add_expected(fig, row, df)
    fig.update_layout(title=f"{row.get('name', symbol)} ({symbol}) · 즉석분석 차트", height=560, xaxis_rangeslider_visible=True, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)


with st.sidebar:
    st.header("설정")
    period = st.selectbox("분석/차트 기간", ["2y", "5y", "10y", "max"], index=1)
    top_n = st.selectbox("유사사례 수", [20, 30, 50], index=1)
    min_similarity = st.slider("최소 유사도", 45, 70, 55, 1)
    min_cases = st.slider("최소 유사사례", 3, 15, 8, 1)

text = st.text_area(
    "분석할 티커 입력",
    value="NVDA,NVIDIA\nTSLA,Tesla\n000660.KS,SK하이닉스\n009150.KS,삼성전기",
    height=150,
    help="한 줄에 하나씩 입력. 형식: 티커 또는 티커,이름",
)

rows = parse_lines(text)
st.caption(f"분석 대상: {len(rows)}개 / 즉석 분석 제한시간: {RUN_TIMEOUT_SECONDS}초")
run = st.button("즉석 정밀분석 실행", type="primary")

if run:
    if not rows:
        st.warning("분석할 티커를 입력하세요.")
        st.stop()
    with st.spinner("즉석 분석 중입니다. 입력 종목 수와 기간에 따라 시간이 걸립니다."):
        code, log, manual = run_manual_analysis(rows, period, len(rows), top_n, min_similarity, min_cases)
    st.success("즉석 분석 완료") if code == 0 else st.error("즉석 분석 중 오류 발생")
    with st.expander("실행 로그"):
        st.code(log)
    st.session_state["manual_result"] = manual

manual = st.session_state.get("manual_result")
if manual is None and MANUAL_SCAN.exists():
    manual = pd.read_csv(MANUAL_SCAN)

if manual is not None and not manual.empty:
    st.subheader("즉석 분석 결과")
    cols = ["final_verdict", "symbol", "name", "fast_score", "pattern", "close", "stop", "target", "rr", "pullback_entry", "pullback_rr", "similar_case_count", "avg_similarity", "win_rate20", "avg_ret20", "avg_max_up20", "avg_max_down20", "decision_reason"]
    cols = [c for c in cols if c in manual.columns]
    st.dataframe(manual[cols], use_container_width=True, hide_index=True)

    st.subheader("차트 + 예상 경로")
    selected = st.selectbox("차트 볼 종목", manual["symbol"].astype(str).tolist())
    row = manual[manual["symbol"].astype(str) == selected].iloc[0]
    render_chart(row, period)
else:
    st.info("아직 즉석 분석 결과가 없습니다.")

with st.expander("주의"):
    st.markdown("""
- 이 페이지는 입력한 티커만 임시 감시군으로 만들어 `main.py similar`를 실행합니다.
- 실행 중 오류가 나도 메인 분석 결과를 복구하도록 `try/finally`로 보호합니다.
- 즉석 결과는 `outputs/manual_scan.csv`에 따로 저장합니다.
- 예상 경로는 즉석 유사사례 통계를 기준으로 그립니다.
- 뉴스/공시/실적은 아직 반영하지 않습니다.
    """)
