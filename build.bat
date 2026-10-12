@echo off
chcp 65001 >nul
rem Сборка VoiceTyper-hs.exe: результат в папке release
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :error
python build.py %* || goto :error
exit /b 0
:error
echo Сборка не удалась.
exit /b 1
