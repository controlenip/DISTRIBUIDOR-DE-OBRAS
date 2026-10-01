@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode excel-copy --output output\BASE_LIST_DISTRIBUIDA.xlsx
pause
