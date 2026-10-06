@echo off
rem Copia banco, canais e configuracao para a pasta backups (mantem os 14 mais recentes).
cd /d "%~dp0"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%i
if not exist backups mkdir backups
mkdir "backups\%STAMP%"
copy /y .env "backups\%STAMP%\" >nul
copy /y config.yaml "backups\%STAMP%\" >nul
copy /y data\canais.json "backups\%STAMP%\" >nul
copy /y data\nichos.json "backups\%STAMP%\" >nul
copy /y data\ofertas.db "backups\%STAMP%\" >nul
powershell -NoProfile -Command "Get-ChildItem backups -Directory | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item -Recurse -Force"
echo Backup salvo em backups\%STAMP%
