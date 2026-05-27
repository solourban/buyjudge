"""
BuyJudge HTML report generator.

Reads:
  outputs/fast_scan.csv
  outputs/similar_scan.csv

Writes:
  outputs/latest_report.html
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("outputs")
REPORT_PATH = OUTPUT_DIR / "latest_report.html"


def esc(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return escape(str(x))


def read_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def badge_class(v: str) -> str:
    if v == "매수후보":
        return "buy"
    if v == "눌림대기":
        return "pullback"
    if v == "조건부관망":
        return "watch"
    if v == "위험차단":
        return "block"
    return "weak"


def card(row: pd.Series) -> str:
    verdict = str(row.get("final_verdict", ""))
    cls = badge_class(verdict)
    return f"""
    <section class="card {cls}">
      <div class="head">
        <div>
          <div class="name">{esc(row.get('name'))} <span>{esc(row.get('symbol'))}</span></div>
          <div class="meta">{esc(row.get('pattern'))} · 방향 {esc(row.get('direction'))}</div>
        </div>
        <div class="badge {cls}">{esc(verdict)}</div>
      </div>

      <div class="score-row">
        <div class="score">{esc(row.get('fast_score'))}점</div>
        <div class="score-sub">유사사례 {esc(row.get('similar_case_count'))}건 · 평균유사도 {esc(row.get('avg_similarity'))}% · 상승확률 {esc(row.get('win_rate20'))}% · 평균수익 {esc(row.get('avg_ret20'))}%</div>
      </div>

      <div class="metrics">
        <div><b>현재가</b><br>{esc(row.get('close'))}</div>
        <div><b>손절</b><br>{esc(row.get('stop'))}</div>
        <div><b>목표</b><br>{esc(row.get('target'))}</div>
        <div><b>현재 손익비</b><br>{esc(row.get('rr'))}</div>
        <div><b>눌림 진입가</b><br>{esc(row.get('pullback_entry'))}</div>
        <div><b>눌림 손익비</b><br>{esc(row.get('pullback_rr'))}</div>
        <div><b>눌림폭</b><br>{esc(row.get('pullback_gap_pct'))}%</div>
        <div><b>거래대금 20일비</b><br>{esc(row.get('trading_value_ratio20'))}배</div>
      </div>

      <details>
        <summary>판정 이유 / 유사사례 보기</summary>
        <div class="detail">
          <b>판정 이유</b><br>{esc(row.get('decision_reason'))}<br><br>
          <b>대표 유사사례</b><br>{esc(row.get('top_cases'))}<br><br>
          <b>차단 사유</b><br>{esc(row.get('blockers'))}
        </div>
      </details>
    </section>
    """


def table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<div class='empty'>데이터 없음</div>"
    cols = [c for c in ["final_verdict", "symbol", "name", "fast_score", "pattern", "similar_case_count", "win_rate20", "avg_ret20", "pullback_entry", "pullback_rr", "decision_reason"] if c in df.columns]
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    rows = []
    for _, r in df.iterrows():
        rows.append("<tr>" + "".join(f"<td>{esc(r.get(c))}</td>" for c in cols) + "</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    similar = read_csv("similar_scan.csv")
    fast = read_csv("fast_scan.csv")

    if not similar.empty and "final_verdict" in similar.columns:
        order = {"매수후보": 0, "눌림대기": 1, "조건부관망": 2, "위험차단": 3, "통계부족": 4}
        similar["_order"] = similar["final_verdict"].map(order).fillna(9)
        similar = similar.sort_values(["_order", "fast_score"], ascending=[True, False]).drop(columns=["_order"])

    groups = {}
    for key in ["매수후보", "눌림대기", "조건부관망", "위험차단", "통계부족"]:
        if similar.empty or "final_verdict" not in similar.columns:
            groups[key] = pd.DataFrame()
        else:
            groups[key] = similar[similar["final_verdict"] == key]

    cards = []
    for title, df in groups.items():
        cards.append(f"<h2>{esc(title)} <span>{len(df)}</span></h2>")
        if df.empty:
            cards.append("<div class='empty'>해당 없음</div>")
        else:
            cards.extend(card(r) for _, r in df.head(20).iterrows())

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BuyJudge Report</title>
<style>
:root {{ --bg:#0f1117; --panel:#171b24; --panel2:#101521; --line:#2a3140; --text:#eef2ff; --muted:#9aa4b2; --buy:#28d17c; --pull:#60a5fa; --watch:#ffd166; --block:#ff6b6b; --weak:#a78bfa; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:28px; background:linear-gradient(135deg,#0f1117,#151823); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',Arial,sans-serif; }}
.wrap {{ max-width:1200px; margin:0 auto; }}
header {{ background:rgba(23,27,36,.94); border:1px solid var(--line); border-radius:24px; padding:24px; margin-bottom:22px; box-shadow:0 18px 60px rgba(0,0,0,.35); }}
h1 {{ margin:0 0 8px; font-size:32px; }}
.sub {{ color:var(--muted); line-height:1.6; }}
.stats {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-top:18px; }}
.stat {{ background:var(--panel2); border:1px solid var(--line); border-radius:18px; padding:16px; }}
.stat .num {{ font-size:28px; font-weight:900; }}
.stat .label {{ color:var(--muted); font-size:13px; }}
h2 {{ margin:28px 0 12px; }}
h2 span {{ color:var(--muted); font-size:16px; }}
.card {{ background:rgba(23,27,36,.95); border:1px solid var(--line); border-radius:22px; padding:20px; margin:12px 0; }}
.card.buy {{ border-color:rgba(40,209,124,.5); }} .card.pullback {{ border-color:rgba(96,165,250,.5); }} .card.watch {{ border-color:rgba(255,209,102,.45); }} .card.block {{ border-color:rgba(255,107,107,.35); }} .card.weak {{ border-color:rgba(167,139,250,.35); }}
.head {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
.name {{ font-size:22px; font-weight:900; }} .name span {{ color:var(--muted); font-size:14px; }}
.meta {{ color:var(--muted); margin-top:6px; }}
.badge {{ padding:8px 12px; border-radius:999px; font-weight:900; white-space:nowrap; }}
.badge.buy {{ background:rgba(40,209,124,.14); color:var(--buy); }} .badge.pullback {{ background:rgba(96,165,250,.14); color:var(--pull); }} .badge.watch {{ background:rgba(255,209,102,.14); color:var(--watch); }} .badge.block {{ background:rgba(255,107,107,.14); color:var(--block); }} .badge.weak {{ background:rgba(167,139,250,.14); color:var(--weak); }}
.score-row {{ display:flex; gap:16px; align-items:end; margin:16px 0; }} .score {{ font-size:38px; font-weight:950; color:var(--pull); }} .score-sub {{ color:var(--muted); padding-bottom:7px; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }} .metrics div {{ background:#0f141f; border:1px solid var(--line); border-radius:16px; padding:13px; color:var(--muted); }} .metrics b {{ color:#dbeafe; }}
summary {{ cursor:pointer; color:#bfdbfe; margin-top:12px; }} .detail {{ margin-top:10px; background:#0b1018; border:1px solid var(--line); border-radius:14px; padding:14px; color:var(--muted); line-height:1.65; }}
.empty {{ padding:18px; border:1px dashed var(--line); border-radius:18px; color:var(--muted); background:rgba(23,27,36,.6); }}
.table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:18px; }} table {{ width:100%; border-collapse:collapse; background:#171b24; }} th,td {{ padding:10px; border-bottom:1px solid var(--line); text-align:left; font-size:13px; vertical-align:top; }} th {{ background:#101521; color:#bfdbfe; }}
@media(max-width:900px) {{ body {{ padding:14px; }} .stats,.metrics {{ grid-template-columns:1fr; }} .head,.score-row {{ flex-direction:column; align-items:flex-start; }} }}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>BuyJudge Report</h1>
<div class="sub">생성시간: {esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}<br>Python 분석 결과를 HTML로 변환한 리포트입니다. 투자 추천이 아니라 판단 보조용입니다.</div>
<div class="stats">
<div class="stat"><div class="num" style="color:var(--buy)">{len(groups['매수후보'])}</div><div class="label">매수후보</div></div>
<div class="stat"><div class="num" style="color:var(--pull)">{len(groups['눌림대기'])}</div><div class="label">눌림대기</div></div>
<div class="stat"><div class="num" style="color:var(--watch)">{len(groups['조건부관망'])}</div><div class="label">조건부관망</div></div>
<div class="stat"><div class="num" style="color:var(--block)">{len(groups['위험차단'])}</div><div class="label">위험차단</div></div>
<div class="stat"><div class="num" style="color:var(--weak)">{len(groups['통계부족'])}</div><div class="label">통계부족</div></div>
</div>
</header>
{''.join(cards)}
<h2>전체 요약표</h2>
{table(similar)}
<h2>빠른 필터 원본</h2>
{table(fast)}
</div>
</body>
</html>"""
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"[DONE] {REPORT_PATH} 생성")


if __name__ == "__main__":
    main()
