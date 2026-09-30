@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bot de Ofertas Telegram
:loop
uv run python -m ofertas run
echo.
echo O bot parou (código %errorlevel%). Reiniciando em 15 segundos... (feche a janela para sair)
timeout /t 15 >nul
goto loop
