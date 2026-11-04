@echo off
cd /d "%~dp0"
echo Sistema iniciando. Quando aparecer 'Running on http://127.0.0.1:5000',
echo abra o navegador e digite: http://127.0.0.1:5000
echo Para DESLIGAR o sistema, feche esta janela ou aperte Ctrl+C.
echo.
".venv\Scripts\python.exe" app.py
echo.
pause
