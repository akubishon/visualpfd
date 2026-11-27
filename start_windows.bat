@echo off
setlocal
cd /d "%~dp0"
set "VISUALPFD_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "VISUALPFD_PYTHON=.venv\Scripts\python.exe"
"%VISUALPFD_PYTHON%" -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false --client.toolbarMode=minimal
pause
