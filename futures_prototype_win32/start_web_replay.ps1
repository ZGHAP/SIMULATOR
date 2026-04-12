# start_web_replay.ps1 — Windows PowerShell launcher

# ---- configure these ----
$SYMBOL        = "SC99"
$TIMEFRAME     = "15m"
$INPUT_DIR     = "$env:USERPROFILE\livedata"
$LOOKBACK      = 51
$OUT_DIR       = "output\sim"
$TICK_SIZE     = "0.1"
$POSITION_SIZE = 1
$HOST          = "0.0.0.0"
$PORT          = 8765

# Use "python" from PATH, or override e.g.:
# $PYTHON = "C:\Users\you\anaconda3\envs\rq\python.exe"
$PYTHON = if ($env:PYTHON) { $env:PYTHON } else { "python" }

# ---- do not edit below ----
Set-Location $PSScriptRoot

$INPUT_PATH = Join-Path $INPUT_DIR "$SYMBOL.csv"
if (-not (Test-Path $INPUT_PATH)) {
    Write-Error "input file not found: $INPUT_PATH"
    exit 1
}

Write-Host "starting web replay: symbol=$SYMBOL timeframe=$TIMEFRAME input=$INPUT_PATH"
Write-Host "open: http://${HOST}:${PORT}"
Write-Host ""

& $PYTHON web_replay_server.py `
    --input      $INPUT_PATH `
    --instrument $SYMBOL `
    --timeframe  $TIMEFRAME `
    --lookback   $LOOKBACK `
    --out-dir    $OUT_DIR `
    --tick-size  $TICK_SIZE `
    --position-size $POSITION_SIZE `
    --host       $HOST `
    --port       $PORT
