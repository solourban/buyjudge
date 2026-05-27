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
import streamlit as st

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
    .small-muted {color:#9aa4b2; font-size:.9rem;}
    .big-action {font-size:1.15rem; font-weight:800; margin:.4rem 0 .8rem 0;}
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


def action_text(row: pd.Series) -> str:
    verdict = str(row.get("final_verdict", ""))
    symbol = str(row.get("symbol", ""))
    if verdict == "매수후보":
        return "지금 가격대에서 검토 가능. 단, 분할매수와 손절 기준은 반드시 같이 봐야 함."
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

    if verdict == "눌림대기" or n(row.get("pullback_entry")) > 0:
        q1, q2, q3 = st.columns(3)
        q1.metric("눌림 진입가", price_fmt(row.get("pullback_entry"), symbol))
        q2.metric("눌림 손익비", f"{n(row.get('pullback_rr')):.2f}")
        q3.metric("현재가 대비 눌림폭", pct_fmt(row.get("pullback_gap_pct")))

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
    period = st.selectbox("데이터 기간", ["2y", "5y", "10y", "max"], index=1)
    refresh_cache = st.checkbox("캐시 무시하고 새로 받기", value=False)
    run = st.button("분석 실행", type="primary", use_container_width=True)

    st.divider()
    st.write("개발 루틴")
    st.caption("GitHub 반영 → 앱 새로고침 → 분석 실행 → 화면 검토")

if run:
    args = [sys.executable, "main.py", "similar", "--period", period]
    if refresh_cache:
        args.append("--refresh-cache")

    with st.spinner("분석 중입니다. 처음 실행은 데이터 다운로드 때문에 시간이 걸릴 수 있습니다."):
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
            for _, row in lower.head(20).iterrows():
                render_card(row)

    st.divider()
    st.subheader("전체 요약표")
    show_cols = [
        "final_verdict", "symbol", "name", "fast_score", "pattern", "close", "stop", "target",
        "rr", "pullback_entry", "pullback_rr", "pullback_gap_pct",
        "similar_case_count", "avg_similarity", "win_rate20", "avg_ret20", "direction", "decision_reason",
    ]
    show_cols = [c for c in show_cols if c in similar.columns]
    st.dataframe(similar[show_cols], use_container_width=True, hide_index=True)

with st.expander("빠른 필터 원본", expanded=False):
    if fast.empty:
        st.caption("fast_scan.csv 없음")
    else:
        st.dataframe(fast, use_container_width=True, hide_index=True)

with st.expander("데이터 상태", expanded=False):
    if status.empty:
        st.caption("data_status.csv 없음")
    else:
        st.dataframe(status, use_container_width=True, hide_index=True)
