from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any


@dataclass
class StrategyConfig:
    timeframe: str = "15m"
    breakout_lookback_bars: int = 20
    expand_window_bars: int = 3
    hold_window_bars: int = 1
    follow_through_bars: int = 3
    pullback_lookback_bars: int = 12
    cooldown_bars_after_failure: int = 2

    hard_stop_pct: float = 0.02
    min_expansion_pct: float = 0.012
    min_close_hold_ratio: float = 0.35
    min_volume_ratio: float = 1.8
    min_volume_zscore: float = 1.2
    min_reconfirm_volume_ratio: float = 1.5
    min_reconfirm_close_strength: float = 0.60
    max_pullback_depth_pct: float = 0.018
    max_pullback_bars: int = 6
    min_movement_efficiency: float = 0.22
    max_volume_displacement_ratio_z: float = 1.5
    min_prior_trend_score: float = 0.55
    min_breakout_score: float = 0.55
    min_reconfirm_score: float = 0.52

    @classmethod
    def from_json(cls, path: str | None) -> "StrategyConfig":
        if not path:
            return cls()
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() in {".yaml", ".yml"}:
            payload = _parse_simple_yaml(text)
        else:
            payload = json.loads(text)
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.lower() in {"true", "false"}:
            payload[key] = value.lower() == "true"
            continue
        try:
            if any(ch in value for ch in [".", "e", "E"]):
                payload[key] = float(value)
            else:
                payload[key] = int(value)
            continue
        except ValueError:
            pass
        payload[key] = value
    return payload
