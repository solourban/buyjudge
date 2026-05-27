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

st.title("📈 BuyJudge")
st.caption("주식/ETF 매수후보 분석기 · Python 엔진 + 웹 화면")

st.warning("투자 추천이 아니라 분석 보조 도구입니다. 실전 주문 전에는 반드시 가상매매 검증이 필요합니다.")


def run_command(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def read_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


with st.sidebar:
    st.header("실행")
    period = st.selectbox("데이터 기간", ["2y", "5y", "10y", "max"], index=1)
    refresh_cache = st.checkbox("캐시 무시하고 새로 받기", value=False)
    run = st.button("분석 실행", type="primary", use_container_width=True)

    st.divider()
    st.write("결과 파일")
    st.code("outputs/fast_scan.csv\noutputs/similar_scan.csv\noutputs/similar_cases_raw.csv")

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

similar = read_csv("similar_scan.csv")
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

    st.subheader("최종 판정")
    show_cols = [
        "final_verdict", "symbol", "name", "fast_score", "pattern", "close", "stop", "target",
        "rr", "pullback_entry", "pullback_rr", "pullback_gap_pct",
        "similar_case_count", "avg_similarity", "win_rate20", "avg_ret20", "direction", "decision_reason",
    ]
    show_cols = [c for c in show_cols if c in similar.columns]
    st.dataframe(similar[show_cols], use_container_width=True, hide_index=True)

    with st.expander("카드형 요약"):
        for _, r in similar.head(20).iterrows():
            verdict = str(r.get("final_verdict", ""))
            title = f"{verdict} · {r.get('name', '')} ({r.get('symbol', '')})"
            with st.container(border=True):
                st.markdown(f"### {title}")
                a, b, c, d = st.columns(4)
                a.metric("점수", r.get("fast_score", 0))
                b.metric("상승확률", f"{r.get('win_rate20', 0)}%")
                c.metric("평균수익", f"{r.get('avg_ret20', 0)}%")
                d.metric("손익비", r.get("rr", 0))
                st.write(r.get("decision_reason", ""))
                st.caption(str(r.get("top_cases", "")))

st.subheader("빠른 필터")
if fast.empty:
    st.caption("fast_scan.csv 없음")
else:
    st.dataframe(fast, use_container_width=True, hide_index=True)

st.subheader("데이터 상태")
if status.empty:
    st.caption("data_status.csv 없음")
else:
    st.dataframe(status, use_container_width=True, hide_index=True)
