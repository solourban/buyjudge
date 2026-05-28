from pathlib import Path
import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title="BuyJudge Position", page_icon="💰", layout="wide")
st.title("💰 Position Sizing")
st.caption("후보별 손절가 기준으로 1회 손실 한도를 넘지 않도록 비중을 계산합니다. 자동 주문이 아니라 판단 보조입니다.")

path = Path("outputs") / "similar_scan.csv"
if not path.exists():
    st.info("메인 화면에서 분석 실행을 먼저 누르세요.")
    st.stop()

df = pd.read_csv(path)
if df.empty:
    st.info("분석 결과가 비어 있습니다.")
    st.stop()


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


def money_fmt(value):
    v = num(value)
    return f"₩{v:,.0f}"


with st.sidebar:
    st.header("자금 기준")
    capital = st.number_input("총 시드", min_value=100000, value=5000000, step=100000)
    risk_pct = st.slider("1종목 최대 손실 허용", 0.2, 5.0, 1.0, 0.1)
    max_position_pct = st.slider("1종목 최대 투입 비중", 5, 50, 20, 1)
    usdkrw = st.number_input("달러 환율", min_value=900, value=1400, step=10)

risk_budget = capital * risk_pct / 100
max_position_value = capital * max_position_pct / 100

st.metric("1종목 손실 한도", money_fmt(risk_budget))
st.metric("1종목 최대 투입금", money_fmt(max_position_value))

candidates = df[df["final_verdict"].isin(["매수후보", "눌림대기", "조건부관망"])].copy()
if candidates.empty:
    st.info("포지션 계산 대상 후보가 없습니다.")
    st.stop()

rows = []
for _, r in candidates.iterrows():
    symbol = str(r.get("symbol", ""))
    verdict = str(r.get("final_verdict", ""))
    name = str(r.get("name", ""))
    close = num(r.get("close"))
    stop = num(r.get("stop"))
    pullback = num(r.get("pullback_entry"))
    target = num(r.get("target"))

    if verdict == "눌림대기" and pullback > 0:
        entry = pullback
        entry_label = "눌림 진입가"
    else:
        entry = close
        entry_label = "현재가"

    if entry <= 0 or stop <= 0 or entry <= stop:
        continue

    unit_risk_price = entry - stop
    unit_risk_krw = unit_risk_price if is_kr(symbol) else unit_risk_price * usdkrw
    entry_krw = entry if is_kr(symbol) else entry * usdkrw
    target_krw = target if is_kr(symbol) else target * usdkrw

    qty_by_risk = math.floor(risk_budget / unit_risk_krw) if unit_risk_krw > 0 else 0
    qty_by_cap = math.floor(max_position_value / entry_krw) if entry_krw > 0 else 0
    qty = max(0, min(qty_by_risk, qty_by_cap))
    buy_value = qty * entry_krw
    expected_loss = qty * unit_risk_krw
    expected_gain = qty * max(0, target_krw - entry_krw)
    position_pct = buy_value / capital * 100 if capital > 0 else 0
    loss_pct_capital = expected_loss / capital * 100 if capital > 0 else 0
    gain_pct_capital = expected_gain / capital * 100 if capital > 0 else 0
    rr = expected_gain / expected_loss if expected_loss > 0 else 0

    rows.append({
        "판정": verdict,
        "종목": f"{name} ({symbol})",
        "진입 기준": entry_label,
        "진입가": price_fmt(entry, symbol),
        "손절가": price_fmt(stop, symbol),
        "목표가": price_fmt(target, symbol),
        "수량": qty,
        "투입금": money_fmt(buy_value),
        "시드 대비 비중": f"{position_pct:.2f}%",
        "예상 손실": money_fmt(expected_loss),
        "시드 대비 손실": f"{loss_pct_capital:.2f}%",
        "예상 목표수익": money_fmt(expected_gain),
        "시드 대비 목표수익": f"{gain_pct_capital:.2f}%",
        "포지션 손익비": f"{rr:.2f}",
        "주의": "수량 0이면 손절폭이 넓거나 시드/비중 기준상 진입 불가" if qty == 0 else "",
    })

result = pd.DataFrame(rows)
if result.empty:
    st.info("계산 가능한 후보가 없습니다. 손절가와 진입가를 확인하세요.")
    st.stop()

st.subheader("후보별 포지션 계산")
st.dataframe(result, use_container_width=True, hide_index=True)

st.subheader("해석")
st.markdown(
    """
- 이 표는 **얼마를 벌지**보다 먼저 **틀렸을 때 얼마를 잃을지**를 고정합니다.
- `1종목 최대 손실 허용`이 1%면, 한 종목이 손절되어도 전체 시드의 약 1% 이내로 제한하는 구조입니다.
- 눌림대기 종목은 현재가가 아니라 `눌림 진입가` 기준으로 계산합니다.
- 실제 매매 전에는 호가 단위, 세금, 수수료, 환율, 체결 가능 수량을 따로 확인해야 합니다.
    """
)
