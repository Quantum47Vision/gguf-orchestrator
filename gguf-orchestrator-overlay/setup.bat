@echo off
REM ============================================================
REM  GGUF ORCHESTRATOR — Windows Setup Script
REM  Run this once to install all dependencies.
REM  Double-click or run from cmd: setup.bat
REM ============================================================

echo.
echo  GGUF ORCHESTRATOR — Setup
echo  ========================
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
echo  [OK] Python found

REM ── Create virtual environment ───────────────────────────────
if not exist ".venv" (
    echo  Creating virtual environment...
    python -m venv .venv
)
echo  [OK] Virtual environment ready

REM ── Activate venv ────────────────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Upgrade pip ──────────────────────────────────────────────
python -m pip install --upgrade pip --quiet

REM ── Install base dependencies ─────────────────────────────────
echo  Installing Python dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo  [WARN] Some packages failed. Continuing...
)

REM ── Install llama-cpp-python with CUDA (GTX 1070) ─────────────
echo.
echo  Installing llama-cpp-python with CUDA support (GTX 1070)...
echo  This may take a few minutes...
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --quiet
if %ERRORLEVEL% NEQ 0 (
    echo  [WARN] CUDA build failed. Falling back to CPU-only llama-cpp-python...
    pip install llama-cpp-python --quiet
)
echo  [OK] llama-cpp-python installed

REM ── Setup PostgreSQL database ─────────────────────────────────
echo.
echo  Setting up PostgreSQL database...
echo  Make sure PostgreSQL is running and check config.yaml for credentials.
echo.

REM Try to create the database (requires psql in PATH)
where psql >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    psql -U postgres -c "CREATE DATABASE gguf_orchestrator;" 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo  [OK] Database 'gguf_orchestrator' created
    ) else (
        echo  [INFO] Database may already exist - that's fine
    )
    psql -U postgres -d gguf_orchestrator -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>nul
    echo  [OK] pgvector extension enabled
) else (
    echo  [WARN] psql not found in PATH.
    echo.
    echo  Please run these commands manually in pgAdmin or psql:
    echo    CREATE DATABASE gguf_orchestrator;
    echo    \c gguf_orchestrator
    echo    CREATE EXTENSION IF NOT EXISTS vector;
    echo.
    echo  Also check: https://github.com/pgvector/pgvector#installation
)

REM ── Check model files ─────────────────────────────────────────
echo.
echo  Checking model paths from config.yaml...
python check_models.py

echo.
echo  ============================================
echo   Setup complete!
echo   Edit config.yaml to set your model paths.
echo   Then run:  start.bat
echo  ============================================
echo.
pause
