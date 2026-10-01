@echo off
setlocal
cd /d %~dp0

if not exist .venv (
    echo Criando ambiente virtual...
    python -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py

endlocal
