@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto fail
)
set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install -r requirements.txt "pyinstaller>=6.16,<7"
if errorlevel 1 goto fail
"%PY%" setup_model.py
if errorlevel 1 goto fail
"%PY%" presenter.py --self-test
if errorlevel 1 goto fail
"%PY%" -m PyInstaller --noconfirm --clean --onedir --console --name JR-Voice-Presenter --collect-all vosk --collect-all sounddevice --collect-all _sounddevice_data --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes --hidden-import win32timezone presenter.py
if errorlevel 1 goto fail
robocopy "models\vosk-model-small-en-us-0.15" "dist\JR-Voice-Presenter\models\vosk-model-small-en-us-0.15" /E
if errorlevel 8 goto fail
"dist\JR-Voice-Presenter\JR-Voice-Presenter.exe" --self-test
if errorlevel 1 goto fail
"dist\JR-Voice-Presenter\JR-Voice-Presenter.exe" --list-devices
if errorlevel 1 goto fail
echo Build complete: dist\JR-Voice-Presenter\JR-Voice-Presenter.exe
exit /b 0
:fail
echo Build failed. Check the error above.
exit /b 1
