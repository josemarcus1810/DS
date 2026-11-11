
@echo off
cd /d "%~dp0"

echo ==========================================
echo       SISTEMA DE ALMOXARIFADO
echo ==========================================
echo.
echo Sistema iniciando...
echo O navegador sera aberto automaticamente.
echo.
echo Endereco: http://127.0.0.1:5000
echo Para DESLIGAR, feche esta janela ou aperte Ctrl+C.
echo.

start "" http://127.0.0.1:5000

".venv\Scripts\python.exe" app.py

echo.
echo Sistema encerrado.
pause
