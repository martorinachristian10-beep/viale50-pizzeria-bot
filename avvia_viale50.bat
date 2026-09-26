@echo off
title Assistente WhatsApp Pizzeria Viale50 (Comiso)
echo ========================================================
echo   ASSISTENTE WHATSAPP PIZZERIA VIALE50 - COMISO
echo ========================================================
echo.
cd /d "%~dp0"

set "PYTHON_CMD=..\euronics_whatsapp\.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    set "PYTHON_CMD=python"
)

echo Avvio server Pizzeria Viale50 su porta 5001...
echo.
echo Apri nel browser: http://127.0.0.1:5001/chat
echo Schermo Tablet Cassa: http://127.0.0.1:5001/admin
echo.
"%PYTHON_CMD%" app.py
pause
