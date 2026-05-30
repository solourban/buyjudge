from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="BuyJudge Action Board", page_icon="🎯", layout="wide")
st.title("🎯 Action Board")
st.caption("오늘 해야 할 일을 매수후보, 눌림대기, 관망, 제외로 나눠 보여줍니다. 매수 추천이 아니라 판단 보조입니다.")

RESULT_PATH = Path("outputs") / "similar_scan.csv"


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
    if is_kr(symbol):
        return f"₩{v:,.0f}"
    return f"${v:,.2f}"


def action_for(row):
    verdict = str(row.get("final_verdict", ""))
    symbol = str(row.get("symbol", ""))
    close = num(row.get("close"))
    pullback = num(row.get("pullback_entry"))
    rr = num(row.get("rr"))
    pull_rr = num(row.get("pullback_rr"))
    tv = num(row.get("trading_value_ratio20"))
    win = num(row.get("win_rate20"))
    avg = num(row.get("avg_ret20"))

    if verdict == "매수후보":
        if rr < 1.2:
            return "소액/분할 검토", "손익비가 낮아 몰빵 금지. 분할과 손절 기준이 먼저."
        if tv < 0.8:
            return "거래대금 확인", "조건은 통과했지만 거래대금이 약함. 당일 수급 확인 후 판단."
        return "우선 검토", "현재가 기준 조건 통과. 단, 분할매수와 손절가 동시 확인."

    if verdict == "눌림대기":
        if pullback > 0:
            return "가격 알림 대기", f"현재가 추격 금지. {price_fmt(pullback, symbol)} 부근 도달 시 재검토."
        return "눌림 확인", "눌림 진입가가 불명확하므로 차트와 손익비 재확인."

    if verdict == "조건부관망":
        weak = []
        if tv < 1.0:
            weak.append("거래대금")
        if win < 55:
            weak.append("승률")
        if avg < 2:
            weak.append("기대수익")
        if not weak:
            weak.append("조건")
        return "조건 개선 대기", ", ".join(weak) + " 개선 전까지 관망."

    if verdict == "위험차단":
        return "제외", "현재 조건에서는 매수 대상 아님. 차단 사유 해소 전까지 제외."

    if verdict == "통계부족":
        return "데이터 대기", "유사사례가 부족해서 판단 보류. 비교군 또는 기간 확장 필요."

    return "확인 필요", "판정값을 확인해야 함."


if not RESULT_PATH.exists():
    st.info("메인 화면에서 분석 실행을 먼저 누르세요.")
    st.stop()

raw = pd.read_csv(RESULT_PATH)
if raw.empty:
    st.info("분석 결과가 비어 있습니다.")
    st.stop()

rows = []
for _, r in raw.iterrows():
    action, note = action_for(r)
    symbol = str(r.get("symbol", ""))
    rows.append({
        "실행구분": action,
        "판정": r.get("final_verdict", ""),
        "종목": f"{r.get('name','')} ({symbol})",
        "현재가": price_fmt(r.get("close"), symbol),
        "눌림가": price_fmt(r.get("pullback_entry"), symbol),
        "손절가": price_fmt(r.get("stop"), symbol),
        "목표가": price_fmt(r.get("target"), symbol),
        "점수": num(r.get("fast_score")),
        "승률": f"{num(r.get('win_rate20')):.2f}%",
        "평균수익": f"{num(r.get('avg_ret20')):+.2f}%",
        "손익비": f"{num(r.get('rr')):.2f}",
        "거래대금20일비": f"{num(r.get('trading_value_ratio20')):.2f}배",
        "오늘 할 일": note,
    })

df = pd.DataFrame(rows)

order = {
    "우선 검토": 0,
    "소액/분할 검토": 1,
    "거래대금 확인": 2,
    "가격 알림 대기": 3,
    "조건 개선 대기": 4,
    "데이터 대기": 5,
    "제외": 6,
    "확인 필요": 7,
}
df["_order"] = df["실행구분"].map(order).fillna(9)
df = df.sort_values(["_order", "점수"], ascending=[True, False]).drop(columns=["_order"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("우선 검토", int((df["실행구분"] == "우선 검토").sum()))
c2.metric("눌림/알림", int((df["실행구분"] == "가격 알림 대기").sum()))
c3.metric("관망", int((df["실행구분"].isin(["조건 개선 대기", "거래대금 확인", "데이터 대기"])).sum()))
c4.metric("제외", int((df["실행구분"] == "제외").sum()))

st.subheader("오늘 액션")
selected = st.multiselect("실행구분 필터", df["실행구분"].dropna().unique().tolist(), default=df["실행구분"].dropna().unique().tolist())
view = df[df["실행구분"].isin(selected)]
st.dataframe(view, use_container_width=True, hide_index=True)

st.subheader("체크리스트")
st.markdown(
    """
1. `우선 검토`라도 바로 매수하지 말고 차트, 손절가, 포지션 사이징을 확인합니다.
2. `가격 알림 대기`는 현재가 추격 금지입니다. 눌림가 근처에 왔을 때 다시 봅니다.
3. `거래대금 확인`은 당일 거래대금이 붙지 않으면 보류합니다.
4. `조건 개선 대기`는 오늘 매수 대상이 아닙니다.
5. `제외`는 차단 사유가 해소될 때까지 건드리지 않습니다.
    """
)

csv = view.to_csv(index=False).encode("utf-8-sig")
st.download_button("오늘 액션 CSV 다운로드", data=csv, file_name="buyjudge_action_board.csv", mime="text/csv")
