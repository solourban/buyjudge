@echo off
chcp 65001 > nul
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py similar
pause
