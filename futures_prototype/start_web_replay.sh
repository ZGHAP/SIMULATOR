#!/usr/bin/env bash
set -euo pipefail
PYTHON="${PYTHON:-/home/fhu/anaconda3/envs/rq/bin/python}"

SYMBOL="SC99"
TIMEFRAME="15m"
INPUT_DIR="$HOME/livedata"
LOOKBACK=51
OUT_DIR="output/sim"
TICK_SIZE="0.1"
POSITION_SIZE="1"
HOST="0.0.0.0"
PORT="8765"
EXTRA_ARGS=()

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

INPUT_PATH="$INPUT_DIR/${SYMBOL}.csv"
if [[ ! -f "$INPUT_PATH" ]]; then
  echo "input file not found: $INPUT_PATH" >&2
  exit 1
fi

CMD=("$PYTHON" web_replay_server.py
  --input "$INPUT_PATH"
  --instrument "$SYMBOL"
  --timeframe "$TIMEFRAME"
  --lookback "$LOOKBACK"
  --out-dir "$OUT_DIR"
  --tick-size "$TICK_SIZE"
  --position-size "$POSITION_SIZE"
  --host "$HOST"
  --port "$PORT"
)

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

echo "starting web replay: symbol=$SYMBOL timeframe=$TIMEFRAME input=$INPUT_PATH"
printf 'command: '
printf '%q ' "${CMD[@]}"
printf '\nopen: http://%s:%s\n\n' "$HOST" "$PORT"

exec "${CMD[@]}"
