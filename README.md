# BuyJudge

Python 기반 주식/ETF 매수후보 분석기입니다.

## 현재 목표

1. `check`: yfinance 데이터 수집 확인
2. `scan`: 전체 감시군 빠른 필터
3. `similar`: 빠른 필터 후보만 유사사례 통계 분석

## 실행 순서

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py check
python main.py scan
python main.py similar
```

Windows에서는 아래 파일을 순서대로 실행해도 됩니다.

- `run_windows_1_check.bat`
- `run_windows_2_scan.bat`
- `run_windows_3_similar.bat`

## 결과 파일

`outputs/` 폴더에 생성됩니다.

- `check_result.csv`
- `fast_scan.csv`
- `similar_scan.csv`
- `similar_cases_raw.csv`
- `data_status.csv`

## 주의

이 프로젝트는 투자 추천이 아니라 분석 보조 도구입니다. 자동주문 연결 전에는 반드시 Paper Trading 검증이 필요합니다.
