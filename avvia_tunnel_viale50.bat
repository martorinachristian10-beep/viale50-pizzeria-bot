@echo off
title Tunnel Pubblico Pizzeria Viale50 (Porta 5001)
echo ===================================================================
echo   TUNNEL PUBBLICO HTTPS PER PIZZERIA VIALE50 (PORTA 5001)
echo ===================================================================
echo.
echo Avvio del tunnel verso la porta 5001...
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5001
pause
