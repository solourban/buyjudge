# BuyJudge

Python/Streamlit 기반 주식·ETF 매수후보 분석 보조 도구입니다.

> 투자 추천이나 자동 주문 프로그램이 아닙니다. 실제 매매 전에는 반드시 가상매매·수동 검증이 필요합니다.

## 현재 목표

BuyJudge는 모든 기능을 다 넣은 금융 터미널이 아니라, 아래 흐름을 빠르게 만드는 것이 1차 목표입니다.

```text
시장상태 확인
→ 감시군 빠른 필터
→ 유사사례 분석
→ 매수후보/눌림대기/관망/위험차단 판정
→ 차트/예상경로 확인
→ 포지션 사이징
→ 액션 판단
```

## 주요 화면

- `app.py`: 메인 대시보드
  - Market Pulse 요약
  - 오늘 볼 후보
  - 차트/예상 경로
  - 분할매수·손절·익절 플랜
  - 전체 요약표
- `pages/1_strategy.py`: 전략 분류
- `pages/2_position_sizing.py`: 포지션 사이징
- `pages/3_action_board.py`: 액션보드
- `pages/4_symbol_search.py`: 종목 검색/차트
- `pages/5_instant_analysis.py`: 직접 티커 즉석 분석
- `pages/6_horizon_lab.py`: 20/60/120거래일 시나리오 실험

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## CLI 실행

```bash
python main.py check --universe universe_core.csv --period 5y
python main.py scan --universe universe_core.csv --period 5y
python main.py similar --universe universe_core.csv --period 5y --max-candidates 30
```

Windows에서는 아래 파일을 실행할 수도 있습니다.

- `run_windows_1_check.bat`
- `run_windows_2_scan.bat`
- `run_windows_3_similar.bat`
- `run_windows_all.bat`

## 결과 파일

`outputs/` 폴더에 생성됩니다.

- `check_result.csv`
- `fast_scan.csv`
- `similar_scan.csv`
- `similar_cases_raw.csv`
- `data_status.csv`
- `manual_scan.csv` : 즉석 분석 결과

## 데이터 정책

- 기본 데이터는 `yfinance` 공개/지연 데이터를 사용합니다.
- 데이터가 없으면 가짜 숫자를 넣지 않습니다.
- 화면에는 가능한 한 `데이터 없음`, `데이터 부족`, `불러오기 실패`, `지연/공개 데이터`처럼 상태를 표시합니다.
- 실시간성, 체결 가능성, 호가, 수수료, 세금, 환율은 별도 검증이 필요합니다.

## 안정화 체크

코드 문법 오류는 아래 명령으로 먼저 확인합니다.

```bash
python scripts/smoke_check.py
```

GitHub Actions에도 같은 smoke check를 추가했습니다.

## 개발 기준

1. 기능 추가보다 앱이 안 죽는 것이 우선입니다.
2. 실제 데이터와 가짜 데이터는 절대 섞지 않습니다.
3. 실제 주문 기능은 붙이지 않습니다. 붙이더라도 Paper Trading이 먼저입니다.
4. 후보 판정은 참고용이며, 실매매 전 뉴스·공시·실적·시장상태를 따로 확인합니다.
5. 중복 코드가 늘어나면 `core/`, `ui/` 모듈로 분리합니다.
