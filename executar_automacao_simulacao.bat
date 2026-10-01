@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run
pause
