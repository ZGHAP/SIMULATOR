from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from features_v2 import load_ohlcv


RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
CYAN = "\x1b[36m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"


@dataclass
class ViewerConfig:
    window: int = 30
    height: int = 20
    candle_width: int = 2
    gap: int = 0
    y_padding_ratio: float = 0.05
    color: bool = True
    unicode: bool = True


@dataclass
class CandleGlyph:
    wick: str
    bull_body: str
    bear_body: str
    empty: str


UNICODE_GLYPHS = CandleGlyph(
    wick="│",
    bull_body="█",
    bear_body="▓",
    empty=" ",
)
ASCII_GLYPHS = CandleGlyph(
    wick="|",
    bull_body="#",
    bear_body="@",
    empty=" ",
)


class TerminalKlineRenderer:
    def __init__(self, config: ViewerConfig | None = None) -> None:
        self.config = config or ViewerConfig()
        self.glyphs = UNICODE_GLYPHS if self.config.unicode else ASCII_GLYPHS

    def render(self, df: pd.DataFrame, instrument: str | None = None, timeframe: str | None = None) -> str:
        window_df = df.tail(self.config.window).reset_index(drop=True).copy()
        if window_df.empty:
            return "no data"

        high_max = float(window_df["high"].max())
        low_min = float(window_df["low"].min())
        span = max(high_max - low_min, 1e-9)
        pad = span * self.config.y_padding_ratio
        top = high_max + pad
        bottom = low_min - pad
        plot_span = max(top - bottom, 1e-9)

        chart = [
            [self.glyphs.empty for _ in range(self._chart_width())]
            for _ in range(self.config.height)
        ]
        color_map: list[list[str | None]] = [
            [None for _ in range(self._chart_width())]
            for _ in range(self.config.height)
        ]

        last_idx = len(window_df) - 1
        for idx, row in window_df.iterrows():
            x0 = idx * (self.config.candle_width + self.config.gap)
            self._draw_candle(chart, color_map, row, x0, top, bottom, plot_span, is_live=(idx == last_idx))

        last = window_df.iloc[-1]
        first = window_df.iloc[0]
        last_close = float(last["close"])
        change_pct = ((last_close / float(first["close"])) - 1.0) if float(first["close"]) != 0 else 0.0
        body_mean = ((window_df["close"] - window_df["open"]).abs()).mean()
        range_mean = (window_df["high"] - window_df["low"]).mean()
        current_row = self._price_to_row(last_close, top, bottom, plot_span)

        lines: list[str] = []
        header = f"{BOLD if self.config.color else ''}{instrument or 'INSTR'} {timeframe or ''}  window={len(window_df)}  last={last_close:.4f}  move={change_pct:+.2%}{RESET if self.config.color else ''}"
        lines.append(header.strip())
        lines.append(
            f"range={low_min:.4f} → {high_max:.4f}  pos={(last_close - low_min) / max(high_max - low_min, 1e-9):.1%}  avg_body={body_mean:.4f}  avg_range={range_mean:.4f}"
        )

        ticks = self._build_axis_ticks(top, bottom)
        for y in range(self.config.height):
            price_label = f"{ticks[y]:>10.4f} ┤"
            row_text = self._render_row(chart[y], color_map[y])
            marker = f" {CYAN}◀ last{RESET}" if y == current_row and self.config.color else (" < last" if y == current_row else "")
            lines.append(price_label + row_text + marker)

        lines.append(" " * 11 + "└" + "─" * self._chart_width())
        lines.append(self._time_axis(window_df["date"]))
        lines.append(self._legend())
        return "\n".join(lines)

    def _draw_candle(
        self,
        chart: list[list[str]],
        color_map: list[list[str | None]],
        row: pd.Series,
        x0: int,
        top: float,
        bottom: float,
        plot_span: float,
        is_live: bool = False,
    ) -> None:
        open_price = float(row["open"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])

        is_bull = close_price >= open_price
        body_char = self.glyphs.bull_body if is_bull else self.glyphs.bear_body
        color = GREEN if is_bull else RED

        high_y = self._price_to_row_floor(high_price, top, plot_span)
        low_y = self._price_to_row_ceil(low_price, top, plot_span)

        body_high_price = max(open_price, close_price)
        body_low_price = min(open_price, close_price)
        body_top = self._price_to_row_floor(body_high_price, top, plot_span)
        body_bottom = self._price_to_row_ceil(body_low_price, top, plot_span)

        # Live candle: keep the current forming body visually stable.
        if is_live and open_price != close_price and body_bottom - body_top == 1:
            pass
        elif open_price != close_price and body_top == body_bottom:
            body_bottom = min(self.config.height - 1, body_top + 1)

        wick_x = x0 + (self.config.candle_width // 2)
        for y in range(high_y, min(body_top, low_y) + 1):
            self._put(chart, color_map, y, wick_x, self.glyphs.wick, color)
        for y in range(max(body_bottom, high_y), low_y + 1):
            self._put(chart, color_map, y, wick_x, self.glyphs.wick, color)

        for y in range(body_top, body_bottom + 1):
            for x in range(x0, min(x0 + self.config.candle_width, self._chart_width())):
                self._put(chart, color_map, y, x, body_char, color)

    def _put(
        self,
        chart: list[list[str]],
        color_map: list[list[str | None]],
        y: int,
        x: int,
        char: str,
        color: str | None,
    ) -> None:
        if 0 <= y < self.config.height and 0 <= x < self._chart_width():
            chart[y][x] = char
            color_map[y][x] = color

    def _render_row(self, chars: list[str], colors: list[str | None]) -> str:
        if not self.config.color:
            return "".join(chars)
        out: list[str] = []
        active: str | None = None
        for char, color in zip(chars, colors):
            if color != active:
                if active is not None:
                    out.append(RESET)
                if color is not None:
                    out.append(color)
                active = color
            out.append(char)
        if active is not None:
            out.append(RESET)
        return "".join(out)

    def _build_axis_ticks(self, top: float, bottom: float) -> list[float]:
        if self.config.height <= 1:
            return [top]
        step = (top - bottom) / (self.config.height - 1)
        return [top - i * step for i in range(self.config.height)]

    def _price_to_row(self, price: float, top: float, bottom: float, plot_span: float) -> int:
        normalized = (top - price) / plot_span
        row = int(round(normalized * (self.config.height - 1)))
        return max(0, min(self.config.height - 1, row))

    def _price_to_row_floor(self, price: float, top: float, plot_span: float) -> int:
        normalized = (top - price) / plot_span
        row = int(math.floor(normalized * (self.config.height - 1)))
        return max(0, min(self.config.height - 1, row))

    def _price_to_row_ceil(self, price: float, top: float, plot_span: float) -> int:
        normalized = (top - price) / plot_span
        row = int(math.ceil(normalized * (self.config.height - 1)))
        return max(0, min(self.config.height - 1, row))

    def _chart_width(self) -> int:
        return self.config.window * self.config.candle_width + (self.config.window - 1) * self.config.gap

    def _time_axis(self, dates: Iterable[pd.Timestamp]) -> str:
        dates = list(dates)
        width = self._chart_width()
        axis = [" " for _ in range(width)]
        if not dates:
            return ""
        anchors = [0, len(dates) // 2, len(dates) - 1]
        labels = [dates[i].strftime("%m-%d %H:%M") for i in anchors]
        for n, (idx, label) in enumerate(zip(anchors, labels)):
            x0 = idx * (self.config.candle_width + self.config.gap)
            if n == 1:
                x0 = max(0, min(width - len(label), x0 - len(label) // 2))
            elif n == 2:
                x0 = max(0, width - len(label))
            for offset, ch in enumerate(label):
                pos = x0 + offset
                if 0 <= pos < width:
                    axis[pos] = ch
        return " " * 12 + "".join(axis)

    def _legend(self) -> str:
        bull = f"{GREEN}bull{RESET}" if self.config.color else "bull"
        bear = f"{RED}bear{RESET}" if self.config.color else "bear"
        return f"{' ' * 12}{bull}={self.glyphs.bull_body}  {bear}={self.glyphs.bear_body}  wick={self.glyphs.wick}"


def load_frame(path: str, timeframe: str | None = None) -> pd.DataFrame:
    return load_ohlcv(path, timeframe=timeframe)


def clear_screen() -> None:
    print("\x1b[2J\x1b[H", end="")


def infer_instrument(path: str) -> str:
    return Path(path).stem.upper()
