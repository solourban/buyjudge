@echo off
chcp 65001 > nul
echo BuyJudge 전체 실행: check - scan - similar
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py check
python main.py scan
python main.py similar
echo.
echo 완료. outputs 폴더를 확인하세요.
pause
