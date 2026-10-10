@echo off
REM Poros build script (Windows)
if not exist ".venv\Scripts\pyinstaller" (
    echo Create a virtual environment and install the dependencies first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo   .venv\Scripts\pip install -r requirements-windows.txt
    exit /b 1
)

.venv\Scripts\pyinstaller --noconfirm main.spec
