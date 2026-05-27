"""
BuyJudge Streamlit web app.

Run locally:
  streamlit run app.py

Deploy target:
  Streamlit Community Cloud / Railway / Render 등에서 app.py를 entrypoint로 사용.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

OUTPUT_DIR = Path("outputs")

st.set_page_config(page_title="BuyJudge", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    .bj-title {font-size: 2.4rem; font-weight: 900; margin-bottom: .2rem;}
    .bj-sub {color:#9aa4b2; margin-bottom: 1.2rem;}
    .decision-buy {border-left: 6px solid #28d17c; padding: 1rem; border-radius: 14px; background: rgba(40,209,124,.08);}
    .decision-pullback {border-left: 6px solid #60a5fa; padding: 1rem; border-radius: 14px; background: rgba(96,165,250,.08);}
    .decision-watch {border-left: 6px solid #ffd166; padding: 1rem; border-radius: 14px; background: rgba(255,209,102,.08);}
    .decision-block {border-left: 6px solid #ff6b6b; padding: 1rem; border-radius: 14px; background: rgba(255,107,107,.06);}
    .decision-weak {border-left: 6px solid #a78bfa; padding: 1rem; border-radius: 14px; background: rgba(167,139,250,.06);}
    .big-action {font-size:1.15rem; font-weight:800; margin:.4rem 0 .8rem 0;}
    .plan-box {padding: .9rem; border-radius: 12px; border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.04); margin-top: .6rem;}
    .plan-title {font-weight: 900; font-size: 1.05rem; margin-bottom: .35rem;}
    .plan-line {color:#cbd5e1; line-height:1.7;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="bj-title">📈 BuyJudge</div>', unsafe_allow_html=True)
st.markdown('<div class="bj-sub">주식/ETF 매수후보 분석기 · Python 엔진 + 웹 화면</div>', unsafe_allow_html=True)
st.warning("투자 추천이 아니라 분석 보조 도구입니다. 실전 주문 전에는 반드시 가상매매 검증이 필요합니다.")


def run_command(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def read_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def n(x, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def is_kr_symbol(symbol: str) -> bool:
    s = str(symbol).upper()
    return s.endswith(".KS") or s.endswith(".KQ")


def price_fmt(value, symbol: str) -> str:
    v = n(value)
    if v <= 0:
        return "-"
    if is_kr_symbol(symbol):
        return f"₩{v:,.0f}"
    return f"${v:,.2f}"


def pct_fmt(value, signed: bool = False) -> str:
    v = n(value)
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.2f}%"


@st.cache_data(ttl=60 * 30, show_spinner=False)
def load_chart_data(symbol: str, period: str) -> pd.DataFrame:
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
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["ma120"] = df["close"].rolling(120).mean()
    return df.tail(180)


def render_chart(row: pd.Series) -> None:
    symbol = str(row.get("symbol", ""))
    name = str(row.get("name", ""))
    if not symbol:
        return

    with st.expander("차트 보기", expanded=False):
        df = load_chart_data(symbol, "1y")
        if df.empty:
            st.caption("차트 데이터를 불러오지 못했습니다.")
            return

        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="일봉",
            )
        )
        for ma in ["ma20", "ma60", "ma120"]:
            if ma in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df[ma], mode="lines", name=ma.upper()))

        close = n(row.get("close"))
        stop = n(row.get("stop"))
        target = n(row.get("target"))
        pullback = n(row.get("pullback_entry"))

        if close > 0:
            fig.add_hline(y=close, line_dash="dot", annotation_text="현재가", annotation_position="top left")
        if stop > 0:
            fig.add_hline(y=stop, line_dash="dash", annotation_text="손절가", annotation_position="bottom left")
        if target > 0:
            fig.add_hline(y=target, line_dash="dash", annotation_text="목표가", annotation_position="top right")
        if str(row.get("final_verdict", "")) == "눌림대기" and pullback > 0:
            fig.add_hline(y=pullback, line_dash="dot", annotation_text="눌림 진입가", annotation_position="bottom right")

        fig.update_layout(
            title=f"{name} ({symbol}) · 최근 1년 일봉",
            height=520,
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=55, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("캔들 + 20/60/120일선 + 현재가/손절가/목표가 기준선입니다. 차트는 판단 보조용입니다.")


def action_text(row: pd.Series) -> str:
    verdict = str(row.get("final_verdict", ""))
    symbol = str(row.get("symbol", ""))
    if verdict == "매수후보":
        return "현재가 기준 조건 통과. 단, 몰빵 금지. 분할매수·손절가를 같이 봐야 함."
    if verdict == "눌림대기":
        return f"현재가 추격금지. {price_fmt(row.get('pullback_entry'), symbol)} 부근까지 눌리면 다시 관심."
    if verdict == "조건부관망":
        return "조건 일부 미달. 지금은 관망, 거래대금·추세·유사통계가 더 붙는지 확인."
    if verdict == "위험차단":
        return "현재 조건에서는 매수 제외. 손절폭·손익비·과열 조건 중 하나가 위험."
    return "유사사례 부족. 데이터가 더 쌓이거나 비교군을 넓힌 뒤 판단."


def card_class(verdict: str) -> str:
    if verdict == "매수후보":
        return "decision-buy"
    if verdict == "눌림대기":
        return "decision-pullback"
    if verdict == "조건부관망":
        return "decision-watch"
    if verdict == "위험차단":
        return "decision-block"
    return "decision-weak"


def build_trade_plan(row: pd.Series) -> dict:
    symbol = str(row.get("symbol", ""))
    verdict = str(row.get("final_verdict", ""))
    close = n(row.get("close"))
    stop = n(row.get("stop"))
    target = n(row.get("target"))
    pullback = n(row.get("pullback_entry"))

    if close <= 0 or stop <= 0 or target <= 0:
        return {"valid": False, "reason": "가격 데이터 부족"}

    if verdict == "매수후보":
        entry1 = close
        entry2 = close * 0.97 if close * 0.97 > stop * 1.02 else 0
        entry3 = close * 0.94 if close * 0.94 > stop * 1.02 else 0
        headline = "현재가 기준 분할 진입 검토"
        condition = "현재가보다 3% 이상 급등해 출발하면 추격하지 말고 다음 신호까지 대기."
    elif verdict == "눌림대기" and pullback > 0:
        entry1 = pullback
        entry2 = (pullback + stop) / 2 if (pullback + stop) / 2 > stop * 1.02 else 0
        entry3 = 0
        headline = "눌림 가격 도달 전까지 매수 금지"
        condition = f"{price_fmt(pullback, symbol)} 부근 도달 후 반등/거래대금 확인 시에만 검토."
    elif verdict == "조건부관망":
        entry1 = close
        entry2 = close * 0.96 if close * 0.96 > stop * 1.02 else 0
        entry3 = 0
        headline = "관망 우선, 조건 개선 시 소액 검토"
        condition = "거래대금 20일비, 유사사례, 추세 중 하나라도 개선될 때까지 비중 낮게 접근."
    else:
        return {"valid": False, "reason": "매매 플랜 생성 대상 아님"}

    entries = [("1차", entry1, "40%"), ("2차", entry2, "30%"), ("3차", entry3, "30%")]
    active = [(label, price, ratio) for label, price, ratio in entries if price > 0]
    avg_entry = sum(price * float(ratio.replace("%", "")) for _, price, ratio in active) / sum(float(ratio.replace("%", "")) for _, _, ratio in active)
    target1 = avg_entry + (target - avg_entry) * 0.5
    risk_pct = (avg_entry - stop) / avg_entry * 100 if avg_entry > stop else 0
    reward_pct = (target - avg_entry) / avg_entry * 100 if target > avg_entry else 0
    rr = reward_pct / risk_pct if risk_pct > 0 else 0

    return {
        "valid": True,
        "symbol": symbol,
        "headline": headline,
        "condition": condition,
        "entries": active,
        "avg_entry": avg_entry,
        "stop": stop,
        "target1": target1,
        "target2": target,
        "risk_pct": risk_pct,
        "reward_pct": reward_pct,
        "rr": rr,
    }


def render_trade_plan(row: pd.Series) -> None:
    plan = build_trade_plan(row)
    if not plan.get("valid"):
        return
    symbol = plan["symbol"]

    with st.expander("분할매수·손절·익절 플랜", expanded=True):
        st.markdown(f"<div class='plan-box'><div class='plan-title'>{plan['headline']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='plan-line'>조건: {plan['condition']}</div>", unsafe_allow_html=True)
        for label, price, ratio in plan["entries"]:
            st.markdown(f"<div class='plan-line'>{label} 진입: {price_fmt(price, symbol)} · 비중 {ratio}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='plan-line'>평균단가 기준: {price_fmt(plan['avg_entry'], symbol)} · 손절 {price_fmt(plan['stop'], symbol)} · 1차 익절 {price_fmt(plan['target1'], symbol)} · 2차 익절 {price_fmt(plan['target2'], symbol)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='plan-line'>예상 손실폭 {plan['risk_pct']:.2f}% · 목표수익 {plan['reward_pct']:.2f}% · 플랜 손익비 {plan['rr']:.2f}</div></div>",
            unsafe_allow_html=True,
        )
        st.caption("이 플랜은 자동 주문이 아니라 판단 보조용입니다. 실제 진입 전 호가·체결강도·당일 시장 흐름 확인 필요.")


def render_card(row: pd.Series) -> None:
    symbol = str(row.get("symbol", ""))
    name = str(row.get("name", ""))
    verdict = str(row.get("final_verdict", ""))
    klass = card_class(verdict)

    st.markdown(f"<div class='{klass}'>", unsafe_allow_html=True)
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
    render_trade_plan(row)

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
    if "fast_score" in out.columns:
        out["fast_score"] = pd.to_numeric(out["fast_score"], errors="coerce").fillna(0)
        out = out.sort_values(["_order", "fast_score"], ascending=[True, False])
    else:
        out = out.sort_values(["_order"])
    return out.drop(columns=["_order"])


with st.sidebar:
    st.header("실행")
    universe_map = {
        "기본 감시군 · 빠름": "universe_core.csv",
        "확장 감시군 · 느림": "universe_extended.csv",
    }
    universe_label = st.selectbox("감시군", list(universe_map.keys()), index=0)
    universe_file = universe_map[universe_label]
    st.caption(f"사용 파일: {universe_file}")

    period = st.selectbox("데이터 기간", ["2y", "5y", "10y", "max"], index=1)
    max_candidates = st.selectbox("정밀분석 대상 수", [10, 15, 30, 50], index=2)
    st.caption("최종 판정표는 전체 감시군이 아니라, 빠른 필터를 통과한 정밀분석 대상만 보여줍니다. 전체 목록은 하단 '빠른 필터 원본'에서 확인합니다.")

    refresh_cache = st.checkbox("캐시 무시하고 새로 받기", value=False)
    run = st.button("분석 실행", type="primary", use_container_width=True)

    st.divider()
    st.write("개발 루틴")
    st.caption("GitHub 반영 → 앱 새로고침 → 분석 실행 → 화면 검토")

if run:
    args = [
        sys.executable,
        "main.py",
        "similar",
        "--period",
        period,
        "--universe",
        universe_file,
        "--max-candidates",
        str(max_candidates),
    ]
    if refresh_cache:
        args.append("--refresh-cache")

    with st.spinner("분석 중입니다. 확장 감시군이나 5y 이상은 시간이 걸릴 수 있습니다."):
        code, log = run_command(args)

    if code == 0:
        st.success("분석 완료")
    else:
        st.error("분석 중 오류 발생")

    with st.expander("실행 로그"):
        st.code(log)

similar = prepare_df(read_csv("similar_scan.csv"))
fast = read_csv("fast_scan.csv")
status = read_csv("data_status.csv")

if similar.empty:
    st.info("아직 분석 결과가 없습니다. 왼쪽의 '분석 실행' 버튼을 누르세요.")
else:
    if "final_verdict" in similar.columns:
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
    show_cols = [
        "final_verdict", "symbol", "name", "fast_score", "pattern", "close", "stop", "target",
        "rr", "pullback_entry", "pullback_rr", "pullback_gap_pct",
        "similar_case_count", "avg_similarity", "win_rate20", "avg_ret20", "direction", "decision_reason",
    ]
    show_cols = [c for c in show_cols if c in similar.columns]
    st.dataframe(similar[show_cols], use_container_width=True, hide_index=True)

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
