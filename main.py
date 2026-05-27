"""
BuyJudge Python Core

Commands:
  python main.py check
  python main.py scan
  python main.py similar

Outputs:
  outputs/check_result.csv
  outputs/fast_scan.csv
  outputs/similar_scan.csv
  outputs/similar_cases_raw.csv

v0.5 핵심:
- 기본 데이터 기간 5y
- data_cache/ 로컬 캐시 사용
- 위험차단 종목도 눌림 진입가 계산
- 최종판정에 눌림대기 추가
"""
from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


OUTPUT_DIR = Path("outputs")
CACHE_DIR = Path("data_cache")
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

VERDICT_CANDIDATE = "정밀분석후보"
VERDICT_WATCH = "관망"
VERDICT_BLOCK = "제외"
VERDICT_ERROR = "오류"

FINAL_BUY = "매수후보"
FINAL_PULLBACK = "눌림대기"
FINAL_WATCH = "조건부관망"
FINAL_RISK_BLOCK = "위험차단"
FINAL_WEAK = "통계부족"


@dataclass
class Asset:
    symbol: str
    name: str
    asset_type: str
    market: str
    theme: str


@dataclass
class FastResult:
    checked_at: str
    symbol: str
    name: str
    asset_type: str
    market: str
    theme: str
    verdict: str
    score: float
    pattern: str
    close: float
    trading_value: float
    trading_value_ratio20: float
    stop: float
    target: float
    risk_pct: float
    reward_pct: float
    rr: float
    blockers: str
    pullback_entry: float
    pullback_risk_pct: float
    pullback_rr: float
    pullback_gap_pct: float
    pullback_memo: str
    pattern_score: float
    trend_score: float
    value_score: float
    risk_score: float
    memo: str


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def load_universe(path: Path) -> List[Asset]:
    df = pd.read_csv(path, dtype=str).fillna("")
    if "enabled" in df.columns:
        df = df[~df["enabled"].str.upper().isin(["FALSE", "0", "NO", "N"])]
    assets: List[Asset] = []
    for _, r in df.iterrows():
        symbol = str(r.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        assets.append(
            Asset(
                symbol=symbol,
                name=str(r.get("name", symbol)).strip() or symbol,
                asset_type=str(r.get("asset_type", "STOCK")).strip().upper() or "STOCK",
                market=str(r.get("market", "")).strip().upper(),
                theme=str(r.get("theme", "")).strip().upper(),
            )
        )
    return assets


def cache_path(symbol: str, period: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol)
    return CACHE_DIR / f"{safe}_{period}.csv"


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError("OHLCV 컬럼 부족: " + ",".join(missing))
    df = df[needed].dropna().copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df["trading_value"] = df["close"] * df["volume"]
    return df


def read_cache(symbol: str, period: str) -> Optional[pd.DataFrame]:
    path = cache_path(symbol, period)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return normalize_ohlcv(df)
    except Exception:
        return None


def write_cache(symbol: str, period: str, df: pd.DataFrame) -> None:
    path = cache_path(symbol, period)
    df.to_csv(path, encoding="utf-8-sig")


def download_one(symbol: str, period: str = "5y", refresh_cache: bool = False) -> Tuple[Optional[pd.DataFrame], str]:
    if not refresh_cache:
        cached = read_cache(symbol, period)
        if cached is not None and len(cached) >= 140:
            return cached, f"CACHE OK {len(cached)}행"

    try:
        raw = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
        if raw is None or raw.empty:
            return None, "다운로드 결과 비어 있음"
        df = normalize_ohlcv(raw)
        if len(df) < 140:
            return None, f"데이터 부족 {len(df)}행"
        write_cache(symbol, period, df)
        return df, f"DOWNLOAD OK {len(df)}행"
    except Exception as e:
        cached = read_cache(symbol, period)
        if cached is not None and len(cached) >= 140:
            return cached, f"CACHE FALLBACK {len(cached)}행 / download error: {type(e).__name__}"
        return None, f"{type(e).__name__}: {e}"


def load_data_bank(assets: List[Asset], period: str = "5y", refresh_cache: bool = False) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    bank: Dict[str, pd.DataFrame] = {}
    statuses = []
    for i, a in enumerate(assets, 1):
        print(f"[DATA] {i}/{len(assets)} {a.symbol}")
        df, msg = download_one(a.symbol, period=period, refresh_cache=refresh_cache)
        ok = df is not None and not df.empty
        statuses.append({"symbol": a.symbol, "name": a.name, "status": "OK" if ok else "FAIL", "message": msg, "rows": len(df) if ok else 0})
        if ok:
            bank[a.symbol] = df
        if "DOWNLOAD" in msg:
            time.sleep(0.2)
    status_df = pd.DataFrame(statuses)
    status_df.to_csv(OUTPUT_DIR / "data_status.csv", index=False, encoding="utf-8-sig")
    return bank, status_df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in [5, 20, 60, 120]:
        out[f"ma{n}"] = out["close"].rolling(n).mean()
    out["vol5"] = out["volume"].rolling(5).mean()
    out["vol20"] = out["volume"].rolling(20).mean()
    out["tv5"] = out["trading_value"].rolling(5).mean()
    out["tv20"] = out["trading_value"].rolling(20).mean()
    out["tv60"] = out["trading_value"].rolling(60).mean()
    out["high60"] = out["high"].rolling(60).max()
    out["high120"] = out["high"].rolling(120).max()
    out["low20"] = out["low"].rolling(20).min()
    out["ret5"] = out["close"].pct_change(5)
    out["ret20"] = out["close"].pct_change(20)
    out["ret60"] = out["close"].pct_change(60)
    out["volatility20"] = out["close"].pct_change().rolling(20).std()
    return out


def classify_pattern(row: pd.Series) -> str:
    close = row["close"]
    high60 = row["high60"]
    drawdown = 1 - close / high60 if high60 else 0
    if close >= high60 * 0.995 and row["tv20"] > 0 and row["trading_value"] >= row["tv20"] * 1.3:
        return "전고점·박스권 돌파"
    if close > row["ma20"] and close > row["ma60"] and row["ma20"] >= row["ma60"] * 0.98 and 0.03 <= drawdown <= 0.18:
        return "눌림목 재상승"
    if close > row["ma20"] > row["ma60"] > row["ma120"]:
        return "정배열 추세"
    if close > row["ma60"] and row["ret60"] > 0.06 and close < row["high120"] * 0.9:
        return "바닥 다지기 회복"
    return "패턴 약함"


def calc_stop_target(row: pd.Series) -> Tuple[float, float, float, float, float]:
    close = row["close"]
    stop = min(row["low20"], row["ma60"]) * 0.985
    stop = min(stop, close * 0.97)
    target = max(row["high60"], row["high120"] * 0.985)
    if target <= close * 1.04:
        target = close * 1.12
    risk = max(0, (close - stop) / close)
    reward = max(0, (target - close) / close)
    rr = reward / risk if risk > 0 else 0
    return stop, target, risk, reward, rr


def calc_pullback_entry(
    close: float,
    stop: float,
    target: float,
    max_risk_pct: float = 0.12,
    min_rr: float = 1.1,
) -> Tuple[float, float, float, float, str]:
    """
    현재가는 위험해도, 어느 가격까지 눌리면 손절폭/손익비가 정상화되는지 계산.
    """
    close = safe_float(close)
    stop = safe_float(stop)
    target = safe_float(target)

    if close <= 0 or stop <= 0 or target <= close or stop >= close:
        return 0, 0, 0, 0, ""

    risk_limit_entry = stop / (1 - max_risk_pct)
    rr_limit_entry = (target + min_rr * stop) / (1 + min_rr)
    entry = min(close * 0.97, risk_limit_entry, rr_limit_entry)

    if entry >= close * 0.995 or entry <= stop * 1.02:
        return 0, 0, 0, 0, ""

    risk_pct = (entry - stop) / entry
    rr = (target - entry) / (entry - stop) if entry > stop else 0
    gap_pct = (entry / close - 1) * 100

    if risk_pct <= max_risk_pct and rr >= min_rr:
        memo = f"현재가 추격 금지. {gap_pct:.1f}% 눌림 시 손절폭 {risk_pct*100:.1f}%, 손익비 {rr:.2f}"
        return round(entry, 4), round(risk_pct * 100, 2), round(rr, 2), round(gap_pct, 2), memo

    return 0, 0, 0, 0, ""


def blockers(row: pd.Series, risk: float, rr: float, asset: Asset) -> List[str]:
    arr: List[str] = []
    if risk > 0.15:
        arr.append("손절폭 15% 초과")
    if rr < 1.1:
        arr.append("손익비 1.1 미만")
    if row["ret5"] > 0.20:
        arr.append("5일 20% 이상 급등")
    if row["ma20"] > 0 and row["close"] / row["ma20"] > 1.18:
        arr.append("20일선 과열")
    if row["close"] < row["ma60"] and row["ma20"] < row["ma60"]:
        arr.append("60일선 아래 약세")
    if asset.asset_type == "STOCK" and asset.symbol.endswith((".KS", ".KQ")) and row["close"] < 1000:
        arr.append("동전주 차단")
    if asset.asset_type == "STOCK" and not asset.symbol.endswith((".KS", ".KQ")) and row["close"] < 5:
        arr.append("페니주 차단")
    return arr


def score_fast(row: pd.Series, pattern: str, asset: Asset) -> Tuple[float, dict]:
    parts = {}
    pattern_score = {
        "전고점·박스권 돌파": 24,
        "눌림목 재상승": 22,
        "정배열 추세": 20,
        "바닥 다지기 회복": 18,
        "패턴 약함": 4,
    }.get(pattern, 4)

    if row["close"] > row["ma60"]:
        pattern_score += 3
    if row["trading_value"] >= row["tv20"] * 1.2:
        pattern_score += 3
    if row["ret5"] > 0.18:
        pattern_score -= 6
    parts["pattern"] = max(0, min(30, pattern_score))

    trend = 0
    if row["close"] > row["ma20"]:
        trend += 6
    if row["close"] > row["ma60"]:
        trend += 6
    if row["ma20"] > row["ma60"]:
        trend += 5
    if row["ma60"] > row["ma120"]:
        trend += 4
    if row["ret60"] > 0:
        trend += 4
    parts["trend"] = max(0, min(25, trend))

    value = 0
    if row["tv20"] > 0:
        tv_ratio = row["trading_value"] / row["tv20"]
        if tv_ratio >= 2.0:
            value += 15
        elif tv_ratio >= 1.5:
            value += 12
        elif tv_ratio >= 1.2:
            value += 9
        elif tv_ratio >= 0.9:
            value += 5
        if row["tv5"] >= row["tv20"] * 1.1:
            value += 5
    parts["value"] = max(0, min(20, value))

    risk_score = 10
    if row["ret5"] > 0.20:
        risk_score = 0
    elif row["ret5"] > 0.12:
        risk_score = 4
    elif row["close"] / row["ma20"] > 1.16:
        risk_score = 3
    parts["risk"] = risk_score
    parts["asset_bonus"] = 5 if asset.asset_type == "ETF" else 0

    return round(sum(parts.values()), 2), parts


def analyze_fast(asset: Asset, df: pd.DataFrame) -> FastResult:
    ind = add_indicators(df).dropna().copy()
    if len(ind) < 30:
        raise ValueError("지표 계산 후 데이터 부족")

    row = ind.iloc[-1]
    pattern = classify_pattern(row)
    score, parts = score_fast(row, pattern, asset)
    stop, target, risk, reward, rr = calc_stop_target(row)
    block = blockers(row, risk, rr, asset)
    tv_ratio = row["trading_value"] / row["tv20"] if row["tv20"] else 0

    pull_entry, pull_risk, pull_rr, pull_gap, pull_memo = calc_pullback_entry(row["close"], stop, target)

    if block:
        verdict = VERDICT_BLOCK
    elif score >= 70 and pattern != "패턴 약함":
        verdict = VERDICT_CANDIDATE
    elif score >= 45:
        verdict = VERDICT_WATCH
    else:
        verdict = VERDICT_BLOCK

    return FastResult(
        checked_at=now_text(),
        symbol=asset.symbol,
        name=asset.name,
        asset_type=asset.asset_type,
        market=asset.market,
        theme=asset.theme,
        verdict=verdict,
        score=score,
        pattern=pattern,
        close=round(float(row["close"]), 4),
        trading_value=round(float(row["trading_value"]), 2),
        trading_value_ratio20=round(float(tv_ratio), 2),
        stop=round(float(stop), 4),
        target=round(float(target), 4),
        risk_pct=round(risk * 100, 2),
        reward_pct=round(reward * 100, 2),
        rr=round(float(rr), 2),
        blockers=", ".join(block),
        pullback_entry=pull_entry,
        pullback_risk_pct=pull_risk,
        pullback_rr=pull_rr,
        pullback_gap_pct=pull_gap,
        pullback_memo=pull_memo,
        pattern_score=parts["pattern"],
        trend_score=parts["trend"],
        value_score=parts["value"],
        risk_score=parts["risk"],
        memo="빠른 필터 결과",
    )


def error_fast_row(asset: Asset, message: str) -> dict:
    base = {f.name: 0 for f in FastResult.__dataclass_fields__.values()}
    base.update({
        "checked_at": now_text(),
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "market": asset.market,
        "theme": asset.theme,
        "verdict": VERDICT_ERROR,
        "pattern": "-",
        "blockers": message,
        "memo": "데이터/분석 오류",
        "pullback_memo": "",
    })
    return base


def check_command(args) -> None:
    assets = load_universe(Path(args.universe))
    _, status_df = load_data_bank(assets, period=args.period, refresh_cache=args.refresh_cache)
    status_df.to_csv(OUTPUT_DIR / "check_result.csv", index=False, encoding="utf-8-sig")
    print("[DONE] outputs/check_result.csv 저장")


def scan_command(args) -> None:
    assets = load_universe(Path(args.universe))
    bank, status_df = load_data_bank(assets, period=args.period, refresh_cache=args.refresh_cache)
    rows: List[dict] = []

    for a in assets:
        df = bank.get(a.symbol)
        if df is None:
            msg = status_df.loc[status_df["symbol"] == a.symbol, "message"]
            rows.append(error_fast_row(a, str(msg.iloc[0]) if len(msg) else "데이터 없음"))
            continue

        try:
            r = analyze_fast(a, df)
            rows.append(asdict(r))
            print(f"[SCAN] {a.symbol} {r.verdict} {r.score}점 {r.pattern}")
        except Exception as e:
            rows.append(error_fast_row(a, f"{type(e).__name__}: {e}"))

    out = pd.DataFrame(rows)
    order = {VERDICT_CANDIDATE: 0, VERDICT_WATCH: 1, VERDICT_BLOCK: 2, VERDICT_ERROR: 3}
    out["_order"] = out["verdict"].map(order).fillna(9)
    out = out.sort_values(["_order", "score"], ascending=[True, False]).drop(columns=["_order"])
    out.to_csv(OUTPUT_DIR / "fast_scan.csv", index=False, encoding="utf-8-sig")
    print("[DONE] outputs/fast_scan.csv 저장")


def make_vector(df: pd.DataFrame, end_idx: int, window: int) -> Optional[np.ndarray]:
    ind = add_indicators(df).dropna().copy()
    if end_idx - window + 1 < 0 or end_idx >= len(ind):
        return None
    w = ind.iloc[end_idx - window + 1 : end_idx + 1].copy()
    if len(w) < window:
        return None

    base = w["close"].iloc[0]
    if base <= 0:
        return None

    points = np.linspace(0, len(w) - 1, 16).round().astype(int)
    price_shape = (w["close"].iloc[points].values / base) - 1

    tv = w["trading_value"].replace(0, np.nan).ffill().fillna(0)
    tv_mean = tv.mean() if tv.mean() > 0 else 1
    tv_shape = np.log((tv.iloc[points].values + 1) / (tv_mean + 1))

    last = w.iloc[-1]
    extras = np.array([
        last["ret5"],
        last["ret20"],
        last["ret60"],
        last["close"] / last["ma20"] - 1 if last["ma20"] else 0,
        last["close"] / last["ma60"] - 1 if last["ma60"] else 0,
        np.log((last["trading_value"] + 1) / (last["tv20"] + 1)) if last["tv20"] else 0,
    ])

    return np.nan_to_num(np.concatenate([price_shape, tv_shape, extras]), nan=0.0, posinf=0.0, neginf=0.0)


def future_outcome(ind: pd.DataFrame, end_idx: int, horizon: int) -> Optional[Tuple[float, float, float]]:
    if end_idx + horizon >= len(ind):
        return None
    base = ind["close"].iloc[end_idx]
    if base <= 0:
        return None
    future = ind.iloc[end_idx + 1 : end_idx + horizon + 1]
    ret = ind["close"].iloc[end_idx + horizon] / base - 1
    max_up = future["high"].max() / base - 1
    max_down = future["low"].min() / base - 1
    return ret * 100, max_up * 100, max_down * 100


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None or len(a) != len(b):
        return 0
    dist = float(np.sqrt(np.mean((a - b) ** 2)))
    return round(100 / (1 + dist * 3), 2)


def select_for_similarity(fast: pd.DataFrame, max_candidates: int) -> pd.DataFrame:
    fast = fast.copy()
    fast["score"] = pd.to_numeric(fast["score"], errors="coerce").fillna(0)
    fast["trading_value_ratio20"] = pd.to_numeric(fast["trading_value_ratio20"], errors="coerce").fillna(0)
    fast["pullback_entry"] = pd.to_numeric(fast.get("pullback_entry", 0), errors="coerce").fillna(0)

    mask = (
        fast["verdict"].isin([VERDICT_CANDIDATE, VERDICT_WATCH])
        | (fast["score"] >= 65)
        | ((fast["score"] >= 55) & (fast["trading_value_ratio20"] >= 1.2))
        | ((fast["score"] >= 65) & (fast["pullback_entry"] > 0))
    )
    return fast[mask].sort_values(["score", "trading_value_ratio20"], ascending=[False, False]).head(max_candidates)


def final_decision(row: pd.Series, stats: dict, args) -> Tuple[str, str]:
    fast_score = safe_float(row.get("score", 0))
    blockers_text = str(row.get("blockers", "") or "")
    rr = safe_float(row.get("rr", 0))
    tv_ratio = safe_float(row.get("trading_value_ratio20", 0))
    pullback_entry = safe_float(row.get("pullback_entry", 0))
    pullback_rr = safe_float(row.get("pullback_rr", 0))
    pullback_gap_pct = safe_float(row.get("pullback_gap_pct", 0))
    pullback_memo = str(row.get("pullback_memo", "") or "")

    has_blocker = blockers_text.strip() not in ["", "nan", "NaN", "None"]
    enough_cases = stats["count"] >= args.min_cases
    similar_quality = stats["avg_similarity"] >= args.min_similarity
    win_ok = stats["win_rate"] >= args.min_winrate
    ret_ok = stats["avg_ret"] >= args.min_avgret
    rr_ok = rr >= args.min_rr
    tv_ok = tv_ratio >= args.min_tv_ratio
    pullback_ok = pullback_entry > 0 and pullback_rr >= args.min_rr

    reasons = [
        f"조건식 {fast_score:.1f}점",
        f"유사사례 {stats['count']}건",
        f"평균유사도 {stats['avg_similarity']:.1f}%",
        f"20일상승확률 {stats['win_rate']:.1f}%",
        f"20일평균수익 {stats['avg_ret']:+.1f}%",
        f"현재손익비 {rr:.2f}",
        f"거래대금20일비 {tv_ratio:.2f}배",
    ]

    if has_blocker:
        if pullback_ok and enough_cases and similar_quality and (win_ok or ret_ok):
            return FINAL_PULLBACK, " / ".join(reasons) + f" / 눌림진입 {pullback_entry:.4f}({pullback_gap_pct:.1f}%), 눌림손익비 {pullback_rr:.2f} / {pullback_memo}"
        return FINAL_RISK_BLOCK, " / ".join(reasons) + f" / 차단사유: {blockers_text}"

    if not enough_cases or not similar_quality:
        return FINAL_WEAK, " / ".join(reasons) + " / 유사사례 수 또는 유사도 부족"

    if fast_score >= args.buy_score and win_ok and ret_ok and rr_ok and tv_ok:
        return FINAL_BUY, " / ".join(reasons) + " / 조건식+유사통계+리스크 통과"

    if fast_score >= args.watch_score or (win_ok and ret_ok):
        return FINAL_WATCH, " / ".join(reasons) + " / 일부 조건 미달, 관망"

    return FINAL_WEAK, " / ".join(reasons) + " / 조건식·통계 모두 약함"


def similar_command(args) -> None:
    scan_command(args)

    fast = pd.read_csv(OUTPUT_DIR / "fast_scan.csv")
    candidates = select_for_similarity(fast, args.max_candidates)

    assets = load_universe(Path(args.universe))
    asset_map = {a.symbol: a for a in assets}
    bank, _ = load_data_bank(assets, period=args.period, refresh_cache=args.refresh_cache)

    results = []
    case_rows = []

    for _, cand in candidates.iterrows():
        symbol = cand["symbol"]
        asset = asset_map.get(symbol)
        df = bank.get(symbol)
        if asset is None or df is None:
            continue

        target_ind = add_indicators(df).dropna().copy()
        target_vec = make_vector(df, len(target_ind) - 1, args.window)
        if target_vec is None:
            continue

        cases = []
        for other_symbol, other_df in bank.items():
            other_asset = asset_map.get(other_symbol)
            if other_asset is None:
                continue
            if other_asset.asset_type != asset.asset_type or other_asset.market != asset.market:
                continue

            ind = add_indicators(other_df).dropna().copy()
            last_end = len(ind) - args.horizon - 1

            for end_idx in range(args.window - 1, last_end, args.step):
                if other_symbol == symbol and end_idx > len(ind) - args.window - args.horizon:
                    continue

                vec = make_vector(other_df, end_idx, args.window)
                out = future_outcome(ind, end_idx, args.horizon)
                if vec is None or out is None:
                    continue

                sim = similarity(target_vec, vec)
                if sim < args.min_similarity:
                    continue

                ret, max_up, max_down = out
                cases.append({
                    "target_symbol": symbol,
                    "target_name": cand["name"],
                    "case_symbol": other_symbol,
                    "case_name": other_asset.name,
                    "case_date": str(ind.index[end_idx].date()),
                    "similarity": sim,
                    "ret20": round(ret, 2),
                    "max_up20": round(max_up, 2),
                    "max_down20": round(max_down, 2),
                })

        cases = sorted(cases, key=lambda x: x["similarity"], reverse=True)[: args.top_n]
        case_rows.extend(cases)

        if cases:
            ret_arr = np.array([c["ret20"] for c in cases])
            max_up_arr = np.array([c["max_up20"] for c in cases])
            max_down_arr = np.array([c["max_down20"] for c in cases])
            sim_arr = np.array([c["similarity"] for c in cases])

            stats = {
                "count": len(cases),
                "win_rate": round(float(np.mean(ret_arr > 0) * 100), 2),
                "avg_ret": round(float(np.mean(ret_arr)), 2),
                "avg_max_up": round(float(np.mean(max_up_arr)), 2),
                "avg_max_down": round(float(np.mean(max_down_arr)), 2),
                "avg_similarity": round(float(np.mean(sim_arr)), 2),
                "top_similarity": round(float(np.max(sim_arr)), 2),
            }

            if stats["win_rate"] >= 60 and stats["avg_ret"] >= 3:
                direction = "상승우위"
            elif stats["win_rate"] <= 45 or stats["avg_ret"] < 0:
                direction = "하락위험"
            else:
                direction = "혼조"

            top_cases = " / ".join([f"{c['case_name']} {c['case_date']} 유사도 {c['similarity']}%→{c['ret20']}%" for c in cases[:3]])
        else:
            stats = {"count": 0, "win_rate": 0, "avg_ret": 0, "avg_max_up": 0, "avg_max_down": 0, "avg_similarity": 0, "top_similarity": 0}
            direction = "유사사례부족"
            top_cases = ""

        final_verdict, decision_reason = final_decision(cand, stats, args)
        results.append({
            "symbol": symbol,
            "name": cand["name"],
            "fast_verdict": cand["verdict"],
            "final_verdict": final_verdict,
            "fast_score": cand["score"],
            "pattern": cand["pattern"],
            "close": cand.get("close", 0),
            "stop": cand.get("stop", 0),
            "target": cand.get("target", 0),
            "trading_value_ratio20": cand.get("trading_value_ratio20", 0),
            "rr": cand.get("rr", 0),
            "blockers": cand.get("blockers", ""),
            "pullback_entry": cand.get("pullback_entry", 0),
            "pullback_risk_pct": cand.get("pullback_risk_pct", 0),
            "pullback_rr": cand.get("pullback_rr", 0),
            "pullback_gap_pct": cand.get("pullback_gap_pct", 0),
            "similar_case_count": stats["count"],
            "avg_similarity": stats["avg_similarity"],
            "top_similarity": stats["top_similarity"],
            "win_rate20": stats["win_rate"],
            "avg_ret20": stats["avg_ret"],
            "avg_max_up20": stats["avg_max_up"],
            "avg_max_down20": stats["avg_max_down"],
            "direction": direction,
            "top_cases": top_cases,
            "decision_reason": decision_reason,
        })

    out = pd.DataFrame(results)
    if not out.empty:
        order = {FINAL_BUY: 0, FINAL_PULLBACK: 1, FINAL_WATCH: 2, FINAL_RISK_BLOCK: 3, FINAL_WEAK: 4}
        out["_order"] = out["final_verdict"].map(order).fillna(9)
        out = out.sort_values(["_order", "fast_score"], ascending=[True, False]).drop(columns=["_order"])

    out.to_csv(OUTPUT_DIR / "similar_scan.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(case_rows).to_csv(OUTPUT_DIR / "similar_cases_raw.csv", index=False, encoding="utf-8-sig")
    print("[DONE] outputs/similar_scan.csv 저장")
    print("[DONE] outputs/similar_cases_raw.csv 저장")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BuyJudge Python Core")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--universe", default="universe_core.csv")
        p.add_argument("--period", default="5y")
        p.add_argument("--refresh-cache", action="store_true")

    p_check = sub.add_parser("check")
    add_common(p_check)

    p_scan = sub.add_parser("scan")
    add_common(p_scan)

    p_sim = sub.add_parser("similar")
    add_common(p_sim)
    p_sim.add_argument("--max-candidates", type=int, default=15)
    p_sim.add_argument("--window", type=int, default=60)
    p_sim.add_argument("--horizon", type=int, default=20)
    p_sim.add_argument("--step", type=int, default=5)
    p_sim.add_argument("--top-n", type=int, default=30)
    p_sim.add_argument("--buy-score", type=float, default=70)
    p_sim.add_argument("--watch-score", type=float, default=45)
    p_sim.add_argument("--min-cases", type=int, default=8)
    p_sim.add_argument("--min-similarity", type=float, default=55)
    p_sim.add_argument("--min-winrate", type=float, default=55)
    p_sim.add_argument("--min-avgret", type=float, default=1)
    p_sim.add_argument("--min-rr", type=float, default=1.1)
    p_sim.add_argument("--min-tv-ratio", type=float, default=0.8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "check":
        check_command(args)
    elif args.command == "scan":
        scan_command(args)
    elif args.command == "similar":
        similar_command(args)
    else:
        raise ValueError(f"알 수 없는 명령: {args.command}")


if __name__ == "__main__":
    main()
