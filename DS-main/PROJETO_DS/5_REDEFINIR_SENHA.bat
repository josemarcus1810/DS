@echo off
cd /d "%~dp0"
echo Use quando alguem esqueceu a senha. A pessoa trocara a senha no proximo login.
echo.
".venv\Scripts\python.exe" redefinir_senha.py
echo.
pause
