@echo off
chcp 65001 > nul
echo BuyJudge 전체 실행: check - scan - similar - html report
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py check
python main.py scan
python main.py similar
python report.py
echo.
echo 완료. outputs 폴더를 확인하세요.
if exist outputs\latest_report.html start outputs\latest_report.html
pause
