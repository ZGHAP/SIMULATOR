@echo off
setlocal

:: ---- configure these ----
set SYMBOL=SC99
set TIMEFRAME=15m
set INPUT_DIR=%USERPROFILE%\livedata
set LOOKBACK=51
set OUT_DIR=output\sim
set TICK_SIZE=0.1
set POSITION_SIZE=1
set HOST=0.0.0.0
set PORT=8765

:: use "python" from PATH, or override with full path e.g.:
:: set PYTHON=C:\Users\you\anaconda3\envs\rq\python.exe
if not defined PYTHON set PYTHON=python

:: ---- do not edit below ----
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set INPUT_PATH=%INPUT_DIR%\%SYMBOL%.csv
if not exist "%INPUT_PATH%" (
    echo input file not found: %INPUT_PATH% 1>&2
    exit /b 1
)

echo starting web replay: symbol=%SYMBOL% timeframe=%TIMEFRAME% input=%INPUT_PATH%
echo open: http://%HOST%:%PORT%
echo.

"%PYTHON%" web_replay_server.py ^
    --input "%INPUT_PATH%" ^
    --instrument "%SYMBOL%" ^
    --timeframe "%TIMEFRAME%" ^
    --lookback "%LOOKBACK%" ^
    --out-dir "%OUT_DIR%" ^
    --tick-size "%TICK_SIZE%" ^
    --position-size "%POSITION_SIZE%" ^
    --host "%HOST%" ^
    --port "%PORT%"
