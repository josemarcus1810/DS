@echo off
cd /d "%~dp0"
echo Instalando o sistema (so precisa fazer isto uma vez)...
echo.
where py >nul 2>nul
if %errorlevel%==0 (set PYTHON=py) else (set PYTHON=python)
if not exist ".venv\Scripts\python.exe" %PYTHON% -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Terminou. Se NAO apareceu nenhum erro em vermelho acima, esta tudo certo.
pause
