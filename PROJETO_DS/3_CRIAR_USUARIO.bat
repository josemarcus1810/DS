@echo off
cd /d "%~dp0"
echo Ao digitar a senha NADA aparece na tela. E normal. Digite e aperte Enter.
echo.
".venv\Scripts\python.exe" criar_usuario.py
echo.
pause
