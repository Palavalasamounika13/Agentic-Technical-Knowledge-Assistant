@echo off
setlocal
REM One-time setup. Copies the RAG engine from the old project, makes a venv, installs packages, runs tests.
REM Usage:  setup.bat                      (uses default old-project path below)
REM         setup.bat "D:\path\to\old\rag_bot"

set "OLD=C:\Users\mounilka\Downloads\rag_bot\rag_bot"
if not "%~1"=="" set "OLD=%~1"

if not exist "%OLD%\rag\config.py" (
  echo ERROR: old RAG project not found at: %OLD%
  echo Run:  setup.bat "full\path\to\old\rag_bot"   ^(the folder that contains main.py and rag\^)
  pause
  exit /b 1
)

echo [1/5] Copying RAG engine, data, index and key from: %OLD%
xcopy /E /I /Y /Q "%OLD%\rag" rag >nul
if exist "%OLD%\data" xcopy /E /I /Y /Q "%OLD%\data" data >nul
if exist "%OLD%\storage" xcopy /E /I /Y /Q "%OLD%\storage" storage >nul
if exist "%OLD%\.env" (
  copy /Y "%OLD%\.env" .env >nul
) else (
  if not exist .env copy /Y .env.example .env >nul
  echo WARNING: no .env in old project. Edit .env and put your NEW Groq key in it.
)
if not exist storage echo WARNING: no index copied. Build it later:  python main.py build  ^(needs main.py from old project^)

echo [2/5] Creating virtual environment...
if not exist .venv\Scripts\activate.bat python -m venv .venv
if errorlevel 1 ( echo ERROR: could not create venv & pause & exit /b 1 )
call .venv\Scripts\activate.bat

echo [3/5] Installing packages (first time is slow, torch is big)...
python -m pip install -q --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo ERROR: pip install failed & pause & exit /b 1 )

echo [4/5] Running offline tests...
python tests\test_agent.py
if errorlevel 1 ( echo ERROR: tests failed & pause & exit /b 1 )

echo [5/5] Setup done.
echo   Terminal agent:  run_cli.bat
echo   Web UI:          run_ui.bat
pause
