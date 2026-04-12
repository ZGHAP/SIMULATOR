#!/usr/bin/env python3
"""PnL analysis chart — auto-detects latest trades file or accepts --instrument arg."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "output/sim"


def find_trades(instrument: str | None) -> Path:
    files = sorted(OUT_DIR.glob("*_trades.csv"), key=lambda f: f.stat().st_mtime)
    if not files:
        sys.exit("No trades files found in output/sim/")
    if instrument:
        files = [f for f in files if f.name.upper().startswith(instrument.upper())]
        if not files:
            sys.exit(f"No trades file found for {instrument}")
    return files[-1]  # most recently modified


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--instrument", "-i", default=None)
    p.add_argument("--tick-size", "-t", type=float, default=None)
    p.add_argument("--file", "-f", default=None, help="Direct path to trades CSV (skips auto-detect)")
    p.add_argument("--label", "-l", default=None, help="Label override for chart title")
    args = p.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        path = find_trades(args.instrument)
    print(f"Loading: {path}")

    df = pd.read_csv(path, parse_dates=["entry_time"])
    if "exit_time" in df.columns:
        df["exit_time"] = pd.to_datetime(df["exit_time"])

    # Determine instrument label
    instrument = args.label or (df["instrument"].iloc[0] if "instrument" in df.columns else path.stem.split("_")[0])
    tick = args.tick_size or (0.1 if "SC" in instrument.upper() else 1.0)
    print(f"Instrument: {instrument}  tick_size: {tick}")

    # Support pre-computed pnl_ticks column (from strategy_auto.py output)
    if "pnl_ticks" in df.columns:
        df["pnl"] = df["pnl_ticks"].astype(float)
    else:
        df["pnl"] = (df["exit_price"].astype(float) - df["entry_price"].astype(float)) * df["side"].map({"long": 1, "short": -1}) / tick
    df["cum_pnl"] = df["pnl"].cumsum()
    df["trade_no"] = range(1, len(df) + 1)
    df["win"] = df["pnl"] > 0
    df["hour"] = df["entry_time"].dt.hour
    df["year"] = df["entry_time"].dt.year
    df["rolling_wr"] = (df["pnl"] > 0).rolling(50, min_periods=10).mean() * 100
    df["bb"] = pd.cut(df["bars_held"], bins=[0, 1, 2, 3, 5, 10, 999],
                      labels=["1", "2", "3", "4-5", "6-10", "11+"])

    wins = df[df["win"]]; losses = df[~df["win"]]
    peak = df["cum_pnl"].cummax(); drawdown = df["cum_pnl"] - peak
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) else float("inf")
    wr = len(wins) / len(df)
    total = df["pnl"].sum()

    # ── colours ──────────────────────────────────────────────────────────────
    DARK = "#111722"; GRID = "#2a3342"; TXT = "#8aa0b4"
    GREEN = "#37d67a"; RED = "#ff5c5c"; BLUE = "#4db3ff"; GOLD = "#ffd700"

    fig = plt.figure(figsize=(16, 14), facecolor=DARK)
    fig.suptitle(f"{instrument} 15m  |  PnL Analysis  ({len(df):,} trades)",
                 color="#e0e6f0", fontsize=15, fontweight="bold", y=0.98)
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.5, wspace=0.32,
                           left=0.07, right=0.97, top=0.93, bottom=0.06)
    ax_cum = fig.add_subplot(gs[0, :])
    ax_hist = fig.add_subplot(gs[1, 0]); ax_wr = fig.add_subplot(gs[1, 1])
    ax_dd = fig.add_subplot(gs[2, 0]); ax_bh = fig.add_subplot(gs[2, 1])
    ax_yr = fig.add_subplot(gs[3, 0]); ax_hr = fig.add_subplot(gs[3, 1])

    for ax in [ax_cum, ax_hist, ax_wr, ax_dd, ax_bh, ax_yr, ax_hr]:
        ax.set_facecolor(DARK); ax.tick_params(colors=TXT, labelsize=9)
        for sp in ax.spines.values(): sp.set_color(GRID)
        ax.grid(color=GRID, linewidth=0.6, linestyle="--")

    dates = df["entry_time"]

    # cumulative PnL
    ax_cum.plot(dates, df["cum_pnl"], color=BLUE, linewidth=1.4, zorder=3)
    ax_cum.fill_between(dates, df["cum_pnl"], 0,
                        where=df["cum_pnl"] >= 0, alpha=0.15, color=GREEN)
    ax_cum.fill_between(dates, df["cum_pnl"], 0,
                        where=df["cum_pnl"] < 0, alpha=0.15, color=RED)
    ax_cum.axhline(0, color=GRID, linewidth=0.8)
    ax_cum.set_title("Cumulative PnL (ticks)", color=TXT, fontsize=10, pad=6)
    ax_cum.set_xlabel("Date", color=TXT, fontsize=9)
    ax_cum.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_cum.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_cum.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_cum.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    fc = GREEN if total >= 0 else RED
    ax_cum.annotate(f"Final: {total:+.0f}t",
                    xy=(dates.iloc[-1], df["cum_pnl"].iloc[-1]),
                    xytext=(-70, 12), textcoords="offset points",
                    color=fc, fontsize=10, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=fc, lw=1))
    stats = (f"Trades: {len(df)}  |  WR: {wr:.1%}  |  "
             f"Avg W: {wins['pnl'].mean():+.1f}t  Avg L: {losses['pnl'].mean():+.1f}t  |  "
             f"PF: {pf:.2f}  |  Max DD: {drawdown.min():.0f}t")
    ax_cum.text(0.01, 0.05, stats, transform=ax_cum.transAxes, color=TXT, fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a2230", edgecolor=GRID))

    # histogram
    bins = np.linspace(df["pnl"].quantile(0.01), df["pnl"].quantile(0.99), 50)
    ax_hist.hist(wins["pnl"], bins=bins, color=GREEN, alpha=0.75, label=f"Win ({len(wins)})")
    ax_hist.hist(losses["pnl"], bins=bins, color=RED, alpha=0.75, label=f"Loss ({len(losses)})")
    ax_hist.axvline(0, color=GRID, linewidth=1)
    ax_hist.axvline(wins["pnl"].mean(), color=GREEN, linewidth=1, linestyle="--", alpha=0.8)
    ax_hist.axvline(losses["pnl"].mean(), color=RED, linewidth=1, linestyle="--", alpha=0.8)
    ax_hist.set_title("Trade PnL Distribution (ticks)", color=TXT, fontsize=10, pad=6)
    ax_hist.set_xlabel("Ticks", color=TXT, fontsize=9); ax_hist.set_ylabel("Count", color=TXT, fontsize=9)
    leg = ax_hist.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
    [t.set_color(TXT) for t in leg.get_texts()]

    # rolling win rate
    ax_wr.plot(dates, df["rolling_wr"], color=GOLD, linewidth=1.2)
    ax_wr.axhline(50, color=GRID, linewidth=0.8, linestyle="--")
    ax_wr.axhline(wr * 100, color=BLUE, linewidth=0.9, linestyle=":", label=f"Overall {wr:.1%}")
    ax_wr.set_title("Rolling Win Rate (50-trade)", color=TXT, fontsize=10, pad=6)
    ax_wr.set_xlabel("Date", color=TXT, fontsize=9); ax_wr.set_ylabel("%", color=TXT, fontsize=9)
    ax_wr.set_ylim(0, 100)
    ax_wr.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_wr.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_wr.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    leg2 = ax_wr.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
    [t.set_color(TXT) for t in leg2.get_texts()]

    # drawdown
    ax_dd.fill_between(dates, drawdown, 0, alpha=0.7, color=RED)
    ax_dd.set_title(f"Drawdown  (max {drawdown.min():.0f}t)", color=TXT, fontsize=10, pad=6)
    ax_dd.set_xlabel("Date", color=TXT, fontsize=9); ax_dd.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_dd.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_dd.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    # bars held
    bh = (df.groupby("bb", observed=True)["pnl"]
          .agg(["mean", "sum"])
          .join(df.groupby("bb", observed=True)["win"].mean().rename("wr")))
    bar_colors = [GREEN if v >= 0 else RED for v in bh["mean"]]
    bars = ax_bh.bar(range(len(bh)), bh["mean"], color=bar_colors, alpha=0.8)
    ax_bh.axhline(0, color=GRID, linewidth=0.8)
    ax_bh.set_xticks(range(len(bh))); ax_bh.set_xticklabels(bh.index, color=TXT, fontsize=9)
    ax_bh.set_title("Avg PnL by Bars Held", color=TXT, fontsize=10, pad=6)
    ax_bh.set_xlabel("Bars", color=TXT, fontsize=9); ax_bh.set_ylabel("Avg Ticks", color=TXT, fontsize=9)
    for bar, wr_v in zip(bars, bh["wr"]):
        ax_bh.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                   f"{wr_v:.0%}", ha="center", va="bottom", color=TXT, fontsize=8)

    # by year
    yg = df.groupby("year")["pnl"].sum()
    ax_yr.bar(yg.index, yg.values, color=[GREEN if v >= 0 else RED for v in yg], alpha=0.8)
    ax_yr.axhline(0, color=GRID, linewidth=0.8)
    ax_yr.set_title("Total PnL by Year", color=TXT, fontsize=10, pad=6)
    ax_yr.set_xlabel("Year", color=TXT, fontsize=9); ax_yr.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_yr.set_xticks(yg.index)

    # by hour
    hg = df.groupby("hour")["pnl"].sum()
    ax_hr.bar(hg.index, hg.values, color=[GREEN if v >= 0 else RED for v in hg], alpha=0.8)
    ax_hr.axhline(0, color=GRID, linewidth=0.8)
    ax_hr.set_title("Total PnL by Entry Hour", color=TXT, fontsize=10, pad=6)
    ax_hr.set_xlabel("Hour", color=TXT, fontsize=9); ax_hr.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_hr.set_xticks(hg.index)

    out = Path(__file__).resolve().parent.parent / f"output/{instrument.lower()}_pnl_analysis.png"
    fig.savefig(out, dpi=140, facecolor=DARK, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
