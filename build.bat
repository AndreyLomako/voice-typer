@echo off
chcp 65001 >nul
rem Сборка VoiceTyper-hs.exe (один файл) в папку dist\
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :error
python make_icon.py || goto :error
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name VoiceTyper-hs ^
    --icon assets\icon.ico --version-file version_info.txt ^
    --add-data "assets\icon.ico;assets" ^
    --collect-data customtkinter ^
    --collect-data faster_whisper ^
    --collect-binaries ctranslate2 ^
    --collect-binaries onnxruntime ^
    --exclude-module matplotlib --exclude-module pandas --exclude-module scipy ^
    --exclude-module torch --exclude-module IPython --exclude-module pytest ^
    run.py || goto :error
echo.
echo Готово: dist\VoiceTyper-hs.exe
exit /b 0
:error
echo Сборка не удалась.
exit /b 1
