
@echo off
cd /d "%~dp0"

echo ==========================================
echo    CRIAR USUARIO - ALMOXARIFADO
echo ==========================================
echo.
echo Preencha os dados do colaborador.
echo.
echo ATENCAO: Ao digitar a senha, nada aparece.
echo Isso e normal.
echo.

".venv\Scripts\python.exe" criar_usuario.py

echo.
pause
