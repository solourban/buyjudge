from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

OUTPUT_DIR = Path("outputs")
CACHE_DIR = Path("data_cache")

st.set_page_config(page_title="BuyJudge", page_icon="📈", layout="wide")
st.markdown(
    """
    <style>
    .bj-title{font-size:2.4rem;font-weight:900;margin-bottom:.2rem}.bj-sub{color:#9aa4b2;margin-bottom:1.2rem}
    .decision-buy{border-left:6px solid #28d17c;padding:1rem;border-radius:14px;background:rgba(40,209,124,.08)}
    .decision-pullback{border-left:6px solid #60a5fa;padding:1rem;border-radius:14px;background:rgba(96,165,250,.08)}
    .decision-watch{border-left:6px solid #ffd166;padding:1rem;border-radius:14px;background:rgba(255,209,102,.08)}
    .decision-block{border-left:6px solid #ff6b6b;padding:1rem;border-radius:14px;background:rgba(255,107,107,.06)}
    .decision-weak{border-left:6px solid #a78bfa;padding:1rem;border-radius:14px;background:rgba(167,139,250,.06)}
    .big-action{font-size:1.15rem;font-weight:800;margin:.4rem 0 .8rem 0}.plan-box{padding:.9rem;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);margin-top:.6rem}.plan-title{font-weight:900;font-size:1.05rem;margin-bottom:.35rem}.plan-line{color:#cbd5e1;line-height:1.7}
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="bj-title">📈 BuyJudge</div>', unsafe_allow_html=True)
st.markdown('<div class="bj-sub">주식/ETF 후보 분석기 · Python 엔진 + 웹 화면</div>', unsafe_allow_html=True)
st.warning("분석 보조 도구입니다. 실제 매매 전에는 가상매매 검증이 필요합니다.")


def run_command(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def read_csv(name: str) -> pd.DataFrame:
    p = OUTPUT_DIR / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def n(x, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def is_kr(symbol: str) -> bool:
    s = str(symbol).upper()
    return s.endswith(".KS") or s.endswith(".KQ")


def price_fmt(value, symbol: str) -> str:
    v = n(value)
    if v <= 0:
        return "-"
    return f"₩{v:,.0f}" if is_kr(symbol) else f"${v:,.2f}"


def pct_fmt(value, signed: bool = False) -> str:
    v = n(value)
    return f"{'+' if signed and v > 0 else ''}{v:.2f}%"


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
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
    return df.tail(180)


def cache_key(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(symbol))


def load_from_cache(symbol: str) -> pd.DataFrame:
    if not CACHE_DIR.exists():
        return pd.DataFrame()
    files = sorted(CACHE_DIR.glob(f"{cache_key(symbol)}_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        try:
            out = normalize_ohlcv(pd.read_csv(f, index_col=0, parse_dates=True))
            if not out.empty:
                return out
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def load_chart_data(symbol: str, period: str = "1y") -> tuple[pd.DataFrame, str]:
    cached = load_from_cache(symbol)
    if not cached.empty:
        return cached, "분석 캐시"
    try:
        raw = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        out = normalize_ohlcv(raw)
        if not out.empty:
            return out, "yfinance"
    except Exception:
        pass
    return pd.DataFrame(), "실패"


def add_expected_path(fig: go.Figure, row: pd.Series, df: pd.DataFrame) -> None:
    if df.empty:
        return
    case_count = int(n(row.get("similar_case_count")))
    base = n(row.get("close")) or n(df["close"].iloc[-1])
    if case_count <= 0 or base <= 0:
        return
    last = df.index[-1]
    future = pd.bdate_range(last, periods=22)[1:]
    if len(future) == 0:
        return
    end = future[-1]
    avg_ret = n(row.get("avg_ret20"))
    avg_up = n(row.get("avg_max_up20"))
    avg_down = n(row.get("avg_max_down20"))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_ret / 100)], mode="lines+markers", name="20일 예상 평균경로", line=dict(dash="dash", width=3)))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_up / 100)], mode="lines", name="20일 상단 시나리오", line=dict(dash="dot")))
    fig.add_trace(go.Scatter(x=[last, end], y=[base, base * (1 + avg_down / 100)], mode="lines", name="20일 하단 시나리오", line=dict(dash="dot")))
    fig.add_vrect(x0=last, x1=end, fillcolor="rgba(120,120,120,.08)", line_width=0, annotation_text="예상구간", annotation_position="top left")


def render_chart(row: pd.Series) -> None:
    symbol = str(row.get("symbol", ""))
    name = str(row.get("name", ""))
    if not symbol:
        return
    with st.expander("차트 보기", expanded=False):
        df, source = load_chart_data(symbol)
        if df.empty:
            st.caption("차트 데이터를 불러오지 못했습니다. 분석 실행 후 다시 펼쳐보세요.")
            return
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="일봉"))
        for ma in ["ma20", "ma60", "ma120"]:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode="lines", name=ma.upper()))
        close, stop, target, pull = n(row.get("close")), n(row.get("stop")), n(row.get("target")), n(row.get("pullback_entry"))
        if close > 0:
            fig.add_hline(y=close, line_dash="dot", annotation_text="현재가", annotation_position="top left")
        if stop > 0:
            fig.add_hline(y=stop, line_dash="dash", annotation_text="손절가", annotation_position="bottom left")
        if target > 0:
            fig.add_hline(y=target, line_dash="dash", annotation_text="목표가", annotation_position="top right")
        if str(row.get("final_verdict", "")) == "눌림대기" and pull > 0:
            fig.add_hline(y=pull, line_dash="dot", annotation_text="눌림 진입가", annotation_position="bottom right")
        add_expected_path(fig, row, df)
        fig.update_layout(title=f"{name} ({symbol}) · 차트 + 20거래일 예상 경로", height=560, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=55, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"데이터 소스: {source}. 예상 경로는 유사사례의 20거래일 평균/상단/하단 시나리오입니다.")


def action_text(row: pd.Series) -> str:
    v = str(row.get("final_verdict", ""))
    s = str(row.get("symbol", ""))
    if v == "매수후보":
        return "현재가 기준 조건 통과. 단, 몰빵 금지. 분할매수·손절가를 같이 봐야 함."
    if v == "눌림대기":
        return f"현재가 추격금지. {price_fmt(row.get('pullback_entry'), s)} 부근까지 눌리면 다시 관심."
    if v == "조건부관망":
        return "조건 일부 미달. 지금은 관망, 거래대금·추세·유사통계가 더 붙는지 확인."
    if v == "위험차단":
        return "현재 조건에서는 제외. 손절폭·손익비·과열 조건 중 하나가 위험."
    return "유사사례 부족. 데이터가 더 쌓이거나 비교군을 넓힌 뒤 판단."


def card_class(v: str) -> str:
    return {"매수후보": "decision-buy", "눌림대기": "decision-pullback", "조건부관망": "decision-watch", "위험차단": "decision-block"}.get(v, "decision-weak")


def build_plan(row: pd.Series) -> dict:
    symbol, verdict = str(row.get("symbol", "")), str(row.get("final_verdict", ""))
    close, stop, target, pull = n(row.get("close")), n(row.get("stop")), n(row.get("target")), n(row.get("pullback_entry"))
    if close <= 0 or stop <= 0 or target <= 0:
        return {"valid": False}
    if verdict == "매수후보":
        entries = [("1차", close, 40), ("2차", close * 0.97, 30), ("3차", close * 0.94, 30)]
        title = "현재가 기준 분할 진입 검토"
        cond = "현재가보다 3% 이상 급등해 출발하면 추격하지 말고 다음 신호까지 대기."
    elif verdict == "눌림대기" and pull > 0:
        entries = [("1차", pull, 40), ("2차", (pull + stop) / 2, 30)]
        title = "눌림 가격 도달 전까지 매수 금지"
        cond = f"{price_fmt(pull, symbol)} 부근 도달 후 반등/거래대금 확인 시에만 검토."
    elif verdict == "조건부관망":
        entries = [("1차", close, 40), ("2차", close * 0.96, 30)]
        title = "관망 우선, 조건 개선 시 소액 검토"
        cond = "거래대금 20일비, 유사사례, 추세 중 하나라도 개선될 때까지 낮은 비중."
    else:
        return {"valid": False}
    active = [(a, p, r) for a, p, r in entries if p > stop * 1.02]
    if not active:
        return {"valid": False}
    avg = sum(p * r for _, p, r in active) / sum(r for _, _, r in active)
    t1 = avg + (target - avg) * 0.5
    risk = (avg - stop) / avg * 100 if avg > stop else 0
    reward = (target - avg) / avg * 100 if target > avg else 0
    rr = reward / risk if risk > 0 else 0
    return {"valid": True, "symbol": symbol, "title": title, "cond": cond, "entries": active, "avg": avg, "stop": stop, "t1": t1, "t2": target, "risk": risk, "reward": reward, "rr": rr}


def render_plan(row: pd.Series) -> None:
    p = build_plan(row)
    if not p.get("valid"):
        return
    s = p["symbol"]
    with st.expander("분할매수·손절·익절 플랜", expanded=True):
        st.markdown(f"<div class='plan-box'><div class='plan-title'>{p['title']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='plan-line'>조건: {p['cond']}</div>", unsafe_allow_html=True)
        for label, price, ratio in p["entries"]:
            st.markdown(f"<div class='plan-line'>{label} 진입: {price_fmt(price, s)} · 비중 {ratio}%</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='plan-line'>평균단가: {price_fmt(p['avg'], s)} · 손절 {price_fmt(p['stop'], s)} · 1차 익절 {price_fmt(p['t1'], s)} · 2차 익절 {price_fmt(p['t2'], s)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='plan-line'>예상 손실폭 {p['risk']:.2f}% · 목표수익 {p['reward']:.2f}% · 플랜 손익비 {p['rr']:.2f}</div></div>", unsafe_allow_html=True)
        st.caption("판단 보조용 플랜입니다. 실제 진입 전 당일 시장 흐름 확인 필요.")


def render_card(row: pd.Series) -> None:
    symbol, name, verdict = str(row.get("symbol", "")), str(row.get("name", "")), str(row.get("final_verdict", ""))
    st.markdown(f"<div class='{card_class(verdict)}'>", unsafe_allow_html=True)
    st.markdown(f"### {verdict} · {name} ({symbol})")
    st.markdown(f"<div class='big-action'>{action_text(row)}</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("점수", f"{n(row.get('fast_score')):.0f}")
    c2.metric("상승확률", pct_fmt(row.get("win_rate20")))
    c3.metric("평균수익", pct_fmt(row.get("avg_ret20"), signed=True))
    c4.metric("현재 손익비", f"{n(row.get('rr')):.2f}")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("현재가", price_fmt(row.get("close"), symbol))
    p2.metric("손절가", price_fmt(row.get("stop"), symbol))
    p3.metric("목표가", price_fmt(row.get("target"), symbol))
    p4.metric("거래대금 20일비", f"{n(row.get('trading_value_ratio20')):.2f}배")
    if verdict == "눌림대기":
        q1, q2, q3 = st.columns(3)
        q1.metric("눌림 진입가", price_fmt(row.get("pullback_entry"), symbol))
        q2.metric("눌림 손익비", f"{n(row.get('pullback_rr')):.2f}")
        q3.metric("현재가 대비 눌림폭", pct_fmt(row.get("pullback_gap_pct")))
    render_chart(row)
    render_plan(row)
    st.caption(str(row.get("decision_reason", "")))
    with st.expander("대표 유사사례 / 차단사유"):
        st.write(str(row.get("top_cases", "")) or "대표 유사사례 없음")
        blockers = str(row.get("blockers", ""))
        if blockers and blockers.lower() != "nan":
            st.write("차단사유:", blockers)
    st.markdown("</div>", unsafe_allow_html=True)


def prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "final_verdict" not in df.columns:
        return df
    order = {"매수후보": 0, "눌림대기": 1, "조건부관망": 2, "위험차단": 3, "통계부족": 4}
    out = df.copy()
    out["_order"] = out["final_verdict"].map(order).fillna(9)
    out["fast_score"] = pd.to_numeric(out.get("fast_score", 0), errors="coerce").fillna(0)
    return out.sort_values(["_order", "fast_score"], ascending=[True, False]).drop(columns=["_order"])


with st.sidebar:
    st.header("실행")
    universe_map = {"기본 감시군 · 빠름": "universe_core.csv", "확장 감시군 · 느림": "universe_extended.csv"}
    universe_label = st.selectbox("감시군", list(universe_map.keys()), index=0)
    universe_file = universe_map[universe_label]
    st.caption(f"사용 파일: {universe_file}")
    period = st.selectbox("데이터 기간", ["2y", "5y", "10y", "max"], index=1)
    max_candidates = st.selectbox("정밀분석 대상 수", [10, 15, 30, 50], index=2)
    st.caption("최종 판정표는 빠른 필터를 통과한 정밀분석 대상만 보여줍니다. 전체 목록은 하단 빠른 필터 원본에서 확인합니다.")
    refresh_cache = st.checkbox("캐시 무시하고 새로 받기", value=False)
    run = st.button("분석 실행", type="primary", use_container_width=True)
    st.divider()
    st.write("개발 루틴")
    st.caption("GitHub 반영 → 앱 새로고침 → 분석 실행 → 화면 검토")

if run:
    args = [sys.executable, "main.py", "similar", "--period", period, "--universe", universe_file, "--max-candidates", str(max_candidates)]
    if refresh_cache:
        args.append("--refresh-cache")
    with st.spinner("분석 중입니다. 확장 감시군이나 5y 이상은 시간이 걸릴 수 있습니다."):
        code, log = run_command(args)
    st.success("분석 완료") if code == 0 else st.error("분석 중 오류 발생")
    with st.expander("실행 로그"):
        st.code(log)

similar = prepare_df(read_csv("similar_scan.csv"))
fast = read_csv("fast_scan.csv")
status = read_csv("data_status.csv")

if similar.empty:
    st.info("아직 분석 결과가 없습니다. 왼쪽의 '분석 실행' 버튼을 누르세요.")
else:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("매수후보", int((similar["final_verdict"] == "매수후보").sum()))
    c2.metric("눌림대기", int((similar["final_verdict"] == "눌림대기").sum()))
    c3.metric("조건부관망", int((similar["final_verdict"] == "조건부관망").sum()))
    c4.metric("위험차단", int((similar["final_verdict"] == "위험차단").sum()))
    c5.metric("통계부족", int((similar["final_verdict"] == "통계부족").sum()))
    st.divider()
    st.subheader("오늘 볼 후보")
    focus = similar[similar["final_verdict"].isin(["매수후보", "눌림대기", "조건부관망"])]
    if focus.empty:
        st.caption("오늘 우선 검토할 후보 없음")
    else:
        for _, row in focus.iterrows():
            render_card(row)
    with st.expander("위험차단 / 통계부족", expanded=False):
        lower = similar[similar["final_verdict"].isin(["위험차단", "통계부족"])]
        if lower.empty:
            st.caption("위험차단/통계부족 없음")
        else:
            for _, row in lower.head(50).iterrows():
                render_card(row)
    st.divider()
    st.subheader("전체 요약표")
    st.caption(f"현재 표시: 정밀분석 결과 {len(similar)}개. 전체 감시군 수는 하단 빠른 필터 원본에서 확인.")
    show_cols = ["final_verdict", "symbol", "name", "fast_score", "pattern", "close", "stop", "target", "rr", "pullback_entry", "pullback_rr", "pullback_gap_pct", "similar_case_count", "avg_similarity", "win_rate20", "avg_ret20", "avg_max_up20", "avg_max_down20", "direction", "decision_reason"]
    st.dataframe(similar[[c for c in show_cols if c in similar.columns]], use_container_width=True, hide_index=True)

with st.expander("빠른 필터 원본 · 전체 감시군", expanded=False):
    if fast.empty:
        st.caption("fast_scan.csv 없음")
    else:
        st.caption(f"전체 빠른 필터 결과 {len(fast)}개. 여기에는 감시군 전체가 표시됩니다.")
        st.dataframe(fast, use_container_width=True, hide_index=True)

with st.expander("데이터 상태", expanded=False):
    if status.empty:
        st.caption("data_status.csv 없음")
    else:
        st.dataframe(status, use_container_width=True, hide_index=True)
