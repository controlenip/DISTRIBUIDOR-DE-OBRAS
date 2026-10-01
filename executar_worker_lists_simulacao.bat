@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
echo.
echo ATENCAO: configure MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, MS_SITE_ID e MS_LIST_ID no ambiente antes de executar.
python worker_lists.py --designers PROJETISTAS.xlsx
pause
