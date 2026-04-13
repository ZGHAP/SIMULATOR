#!/usr/bin/env python3
"""Aggregated PnL comparison chart — all instruments on one page."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE  = Path(__file__).resolve().parent.parent
DARK  = "#111722"; GRID = "#2a3342"; TXT = "#8aa0b4"
GREEN = "#37d67a"; RED  = "#ff5c5c"; BLUE = "#4db3ff"
GOLD  = "#ffd700"; PURPLE = "#bb86fc"; ORANGE = "#ff9800"

INSTRUMENTS = [
    dict(name="SC99",  file="output/csv/sc99_auto_trades.csv",  tick=0.1,  col=BLUE,   label="SC99 (Crude Oil)"),
    dict(name="AG99",  file="output/csv/ag99_auto_trades.csv",  tick=1.0,  col=GOLD,   label="AG99 (Silver)"),
    dict(name="AU99",  file="output/csv/au99_auto_trades.csv",  tick=0.05, col=ORANGE, label="AU99 (Gold)"),
    dict(name="J99",   file="output/csv/j99_auto_trades.csv",   tick=0.5,  col=PURPLE, label="J99 (Coking Coal)"),
]


def load(cfg: dict) -> pd.DataFrame:
    df = pd.read_csv(HERE / cfg["file"], parse_dates=["entry_time"])
    df["pnl"] = df["pnl_ticks"].astype(float)
    df["win"] = df["pnl"] > 0
    df["is_stop"] = df["exit_reason"] == "hard_stop"
    df["year"] = df["entry_time"].dt.year
    df["month"] = df["entry_time"].dt.to_period("M")
    df["cum"] = df["pnl"].cumsum()
    df["label"] = cfg["label"]
    df["col"] = cfg["col"]
    return df.sort_values("entry_time").reset_index(drop=True)


def stats(df: pd.DataFrame) -> dict:
    w = df[df["win"]]; l = df[~df["win"]]
    pf = w["pnl"].sum() / abs(l["pnl"].sum()) if len(l) else float("inf")
    cum = df["pnl"].cumsum()
    dd = (cum - cum.cummax()).min()
    return dict(n=len(df), wr=len(w)/len(df), pf=pf, total=df["pnl"].sum(),
                avg_w=w["pnl"].mean(), avg_l=l["pnl"].mean(),
                max_dd=dd, stop_rate=df["is_stop"].mean())


def ax_style(ax):
    ax.set_facecolor(DARK); ax.tick_params(colors=TXT, labelsize=9)
    for sp in ax.spines.values(): sp.set_color(GRID)
    ax.grid(color=GRID, lw=0.5, ls="--", alpha=0.7)


def main():
    datasets = [load(cfg) for cfg in INSTRUMENTS]

    fig = plt.figure(figsize=(20, 18), facecolor=DARK)
    fig.suptitle("Auto Breakout Strategy — All Instruments Comparison",
                 color="#e0e6f0", fontsize=15, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.50, wspace=0.28,
                           left=0.07, right=0.97, top=0.95, bottom=0.05)
    ax_cum  = fig.add_subplot(gs[0, :])   # cumulative PnL all instruments
    ax_dd   = fig.add_subplot(gs[1, :])   # drawdown all instruments
    ax_yr   = fig.add_subplot(gs[2, :])   # yearly PnL grouped bars
    ax_bh   = fig.add_subplot(gs[3, 0])   # bars held avg PnL
    ax_stat = fig.add_subplot(gs[3, 1])   # stats table

    for ax in [ax_cum, ax_dd, ax_yr, ax_bh]:
        ax_style(ax)

    # ── 1. Cumulative PnL ─────────────────────────────────────────────────────
    for df in datasets:
        ax_cum.plot(df["entry_time"], df["cum"],
                    color=df["col"].iloc[0], lw=1.6, label=df["label"].iloc[0], zorder=3)
        ax_cum.annotate(f"{df['cum'].iloc[-1]:+.0f}t",
                        xy=(df["entry_time"].iloc[-1], df["cum"].iloc[-1]),
                        xytext=(6, 0), textcoords="offset points",
                        color=df["col"].iloc[0], fontsize=9, fontweight="bold", va="center")
    ax_cum.axhline(0, color=GRID, lw=0.8)
    ax_cum.set_title("Cumulative PnL (ticks)", color=TXT, fontsize=11, pad=6)
    ax_cum.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_cum.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_cum.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_cum.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    leg = ax_cum.legend(fontsize=9, facecolor="#1a2230", edgecolor=GRID, loc="upper left")
    [t.set_color(TXT) for t in leg.get_texts()]

    # ── 2. Drawdown ───────────────────────────────────────────────────────────
    for df in datasets:
        cum = df["pnl"].cumsum(); dd = cum - cum.cummax()
        col = df["col"].iloc[0]
        ax_dd.plot(df["entry_time"], dd, color=col, lw=1.2, alpha=0.85,
                   label=f"{df['label'].iloc[0]}  (max {dd.min():.0f}t)")
        ax_dd.fill_between(df["entry_time"], dd, 0, color=col, alpha=0.08)
    ax_dd.axhline(0, color=GRID, lw=0.8)
    ax_dd.set_title("Drawdown (ticks)", color=TXT, fontsize=11, pad=6)
    ax_dd.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_dd.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_dd.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    leg2 = ax_dd.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID, loc="lower left")
    [t.set_color(TXT) for t in leg2.get_texts()]

    # ── 3. Yearly PnL grouped bars ────────────────────────────────────────────
    all_years = sorted(set(y for df in datasets for y in df["year"].unique()))
    n_inst = len(datasets)
    w = 0.18; offsets = np.linspace(-(n_inst-1)*w/2, (n_inst-1)*w/2, n_inst)
    x = np.arange(len(all_years))

    for df, off in zip(datasets, offsets):
        yr_pnl = df.groupby("year")["pnl"].sum()
        vals = [yr_pnl.get(y, 0) for y in all_years]
        colors = [GREEN if v >= 0 else RED for v in vals]
        bars = ax_yr.bar(x + off, vals, w, color=colors, alpha=0.8,
                         label=df["label"].iloc[0])
        # label non-zero bars
        for bar, val in zip(bars, vals):
            if abs(val) > 50:
                ax_yr.text(bar.get_x() + bar.get_width()/2,
                           bar.get_height() + (15 if val >= 0 else -40),
                           f"{val:+.0f}", ha="center", fontsize=6.5,
                           color=df["col"].iloc[0])

    ax_yr.axhline(0, color=GRID, lw=0.8)
    ax_yr.set_title("Annual PnL by Instrument (ticks)", color=TXT, fontsize=11, pad=6)
    ax_yr.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_yr.set_xticks(x); ax_yr.set_xticklabels(all_years, color=TXT, fontsize=9)
    leg3 = ax_yr.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
    [t.set_color(TXT) for t in leg3.get_texts()]

    # ── 4. Bars held avg PnL overlay ─────────────────────────────────────────
    bb_bins = [0,1,2,3,5,10,999]; bb_labs = ["1","2","3","4-5","6-10","11+"]
    offsets_bh = np.linspace(-(n_inst-1)*0.1, (n_inst-1)*0.1, n_inst)
    xbh = np.arange(len(bb_labs))
    for df, off in zip(datasets, offsets_bh):
        df2 = df.copy()
        df2["bb"] = pd.cut(df2["bars_held"], bins=bb_bins, labels=bb_labs)
        bh = df2.groupby("bb", observed=True)["pnl"].mean()
        vals = [bh.get(b, 0) for b in bb_labs]
        ax_bh.plot(xbh + off, vals, "o-", color=df["col"].iloc[0],
                   lw=1.4, ms=5, label=df["label"].iloc[0])
    ax_bh.axhline(0, color=GRID, lw=0.8)
    ax_bh.set_title("Avg PnL by Bars Held", color=TXT, fontsize=10, pad=6)
    ax_bh.set_xlabel("Bars held", color=TXT, fontsize=9)
    ax_bh.set_ylabel("Avg Ticks", color=TXT, fontsize=9)
    ax_bh.set_xticks(xbh); ax_bh.set_xticklabels(bb_labs, color=TXT, fontsize=9)
    leg4 = ax_bh.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
    [t.set_color(TXT) for t in leg4.get_texts()]

    # ── 5. Stats table ────────────────────────────────────────────────────────
    ax_stat.set_facecolor(DARK)
    for sp in ax_stat.spines.values(): sp.set_visible(False)
    ax_stat.set_xticks([]); ax_stat.set_yticks([])
    ax_stat.set_title("Strategy Summary", color=TXT, fontsize=10, pad=6)

    headers = ["Instrument", "Trades", "WR", "PF", "Total", "AvgW", "AvgL", "StopRate", "MaxDD"]
    col_x   = [0.0, 0.13, 0.22, 0.31, 0.42, 0.55, 0.67, 0.79, 0.91]
    row_h   = 0.13
    y0      = 0.88

    for j, h in enumerate(headers):
        ax_stat.text(col_x[j], y0, h, transform=ax_stat.transAxes,
                     color=TXT, fontsize=8, fontweight="bold", va="top")

    for i, (df, cfg) in enumerate(zip(datasets, INSTRUMENTS)):
        s = stats(df)
        y = y0 - (i + 1) * row_h
        col = cfg["col"]
        row = [cfg["name"],
               str(s["n"]),
               f"{s['wr']:.1%}",
               f"{s['pf']:.2f}",
               f"{s['total']:+.0f}t",
               f"{s['avg_w']:+.1f}t",
               f"{s['avg_l']:+.1f}t",
               f"{s['stop_rate']:.0%}",
               f"{s['max_dd']:.0f}t"]
        for j, val in enumerate(row):
            ax_stat.text(col_x[j], y, val, transform=ax_stat.transAxes,
                         color=col, fontsize=8.5, va="top")

    # separator line
    ax_stat.plot([0, 1], [y0 - row_h * 0.5] * 2, color=GRID, lw=0.8,
                 transform=ax_stat.transAxes)

    # aggregated row
    all_pnl = pd.concat([df["pnl"] for df in datasets])
    aw = all_pnl[all_pnl>0]; al = all_pnl[all_pnl<=0]
    tot = all_pnl.sum()
    pf_all = aw.sum()/abs(al.sum())
    y_agg = y0 - (n_inst + 1.3) * row_h
    ax_stat.plot([0, 1], [y_agg + row_h*0.7] * 2, color=GRID, lw=0.8,
                 transform=ax_stat.transAxes)
    agg_vals = ["ALL", str(sum(s["n"] for s in [stats(df) for df in datasets])),
                f"{(all_pnl>0).mean():.1%}", f"{pf_all:.2f}", f"{tot:+.0f}t",
                f"{aw.mean():+.1f}t", f"{al.mean():+.1f}t", "—", "—"]
    for j, val in enumerate(agg_vals):
        ax_stat.text(col_x[j], y_agg, val, transform=ax_stat.transAxes,
                     color="#e0e6f0", fontsize=8.5, fontweight="bold", va="top")

    out = HERE / "output/chart/all_instruments_compare.png"
    fig.savefig(out, dpi=140, facecolor=DARK, bbox_inches="tight")
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
