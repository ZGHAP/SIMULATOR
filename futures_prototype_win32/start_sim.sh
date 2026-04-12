#!/usr/bin/env bash
set -euo pipefail

# 改这里就行
SYMBOL="AG99"
TIMEFRAME="15m"
INPUT_DIR="$HOME/livedata"
LOOKBACK=30
CHART_HEIGHT=18
OUT_DIR="output/sim"
TICK_SIZE="1"
POSITION_SIZE="1"
EXTRA_ARGS=()

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

INPUT_PATH="$INPUT_DIR/${SYMBOL}.csv"
if [[ ! -f "$INPUT_PATH" ]]; then
  echo "input file not found: $INPUT_PATH" >&2
  exit 1
fi

PYTHON="${PYTHON:-/home/fhu/anaconda3/envs/rq/bin/python}"
CMD=("$PYTHON" run_simulator.py
  --input "$INPUT_PATH"
  --instrument "$SYMBOL"
  --timeframe "$TIMEFRAME"
  --lookback "$LOOKBACK"
  --chart-height "$CHART_HEIGHT"
  --out-dir "$OUT_DIR"
  --tick-size "$TICK_SIZE"
  --position-size "$POSITION_SIZE"
)

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

echo "starting simulator: symbol=$SYMBOL timeframe=$TIMEFRAME input=$INPUT_PATH"
printf 'command: '
printf '%q ' "${CMD[@]}"
printf '\n\n'

exec "${CMD[@]}"
