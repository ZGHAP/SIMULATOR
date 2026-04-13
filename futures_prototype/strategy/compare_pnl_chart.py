#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_pnl_chart.py — Overlay two trades files on a PnL comparison chart.

Default mode: manual SC99 vs auto SC99
Pass --mode ag  : auto SC99 vs auto AG99 (silver test)
Pass --a / --b  : any two custom files
"""
from __future__ import annotations
import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DARK  = "#111722"; GRID = "#2a3342"; TXT = "#8aa0b4"
GREEN = "#37d67a"; RED  = "#ff5c5c"; BLUE = "#4db3ff"; GOLD = "#ffd700"

HERE = Path(__file__).resolve().parent.parent


def load(path: Path, tick: float, label: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["entry_time"])
    if "pnl_ticks" in df.columns:
        df["pnl"] = df["pnl_ticks"].astype(float)
        df["is_stop"] = df["exit_reason"] == "hard_stop"
        df["is_session_flat"] = df["exit_reason"] == "session_flat"
    else:
        df["pnl"] = (df["exit_price"].astype(float) - df["entry_price"].astype(float)) \
                    * df["side"].map({"long": 1, "short": -1}) / tick
        df["is_stop"] = df["exit_reason_label"].isin(
            ["hard_stop_entry_minus_20", "hard_stop_entry_plus_20"])
        df["is_session_flat"] = df["exit_reason_label"] == "forced_session_flat_close"
    df["label"] = label
    return df.sort_values("entry_time").reset_index(drop=True)


def stats(df: pd.DataFrame) -> dict:
    wins = df[df["pnl"] > 0]; losses = df[df["pnl"] <= 0]
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) else float("inf")
    cum = df["pnl"].cumsum(); dd = (cum - cum.cummax()).min()
    return dict(n=len(df), wr=len(wins)/len(df), pf=pf,
                total=df["pnl"].sum(), avg_w=wins["pnl"].mean(),
                avg_l=losses["pnl"].mean(), max_dd=dd,
                stop_rate=df["is_stop"].mean())


def monthly(df: pd.DataFrame) -> pd.Series:
    return df.set_index("entry_time")["pnl"].resample("M").sum()


def ax_style(ax):
    ax.set_facecolor(DARK); ax.tick_params(colors=TXT, labelsize=9)
    for sp in ax.spines.values(): sp.set_color(GRID)
    ax.grid(color=GRID, lw=0.5, ls="--", alpha=0.7)


def make_chart(dfa: pd.DataFrame, dfb: pd.DataFrame,
               col_a: str, col_b: str,
               label_a: str, label_b: str,
               out: Path) -> None:
    sa, sb = stats(dfa), stats(dfb)
    dfa["cum"] = dfa["pnl"].cumsum()
    dfb["cum"] = dfb["pnl"].cumsum()

    # Monthly overlap
    mo_a = monthly(dfa); mo_b = monthly(dfb)
    mo = pd.DataFrame({"a": mo_a, "b": mo_b}).fillna(0)
    start = max(dfa["entry_time"].min(), dfb["entry_time"].min())
    end   = min(dfa["entry_time"].max(), dfb["entry_time"].max())
    mo_ov = mo[(mo.index >= start) & (mo.index <= end)]

    fig = plt.figure(figsize=(18, 16), facecolor=DARK)
    title = f"{label_a}  vs  {label_b}  |  PnL Comparison"
    fig.suptitle(title, color="#e0e6f0", fontsize=14, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.52, wspace=0.30,
                           left=0.07, right=0.97, top=0.95, bottom=0.05)
    ax_cum  = fig.add_subplot(gs[0, :])
    ax_dd_a = fig.add_subplot(gs[1, 0]); ax_dd_b = fig.add_subplot(gs[1, 1])
    ax_mo   = fig.add_subplot(gs[2, :])
    ax_bh_a = fig.add_subplot(gs[3, 0]); ax_bh_b = fig.add_subplot(gs[3, 1])

    for ax in [ax_cum, ax_dd_a, ax_dd_b, ax_mo, ax_bh_a, ax_bh_b]:
        ax_style(ax)

    # ── 1. Cumulative PnL ─────────────────────────────────────────────────────
    ax_cum.plot(dfa["entry_time"], dfa["cum"], color=col_a, lw=1.6, label=label_a, zorder=3)
    ax_cum.plot(dfb["entry_time"], dfb["cum"], color=col_b, lw=1.6, label=label_b, zorder=3)
    ax_cum.axhline(0, color=GRID, lw=0.8)
    ax_cum.set_title("Cumulative PnL (ticks)", color=TXT, fontsize=11, pad=6)
    ax_cum.set_ylabel("Ticks", color=TXT, fontsize=9)
    ax_cum.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_cum.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_cum.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    for df_, s_, col_, lbl_, off in [
        (dfa, sa, col_a, label_a, 14),
        (dfb, sb, col_b, label_b, -22),
    ]:
        ax_cum.annotate(f"{lbl_}: {s_['total']:+.0f}t",
                        xy=(df_["entry_time"].iloc[-1], df_["cum"].iloc[-1]),
                        xytext=(-100, off), textcoords="offset points",
                        color=col_, fontsize=10, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=col_, lw=1))

    def sbox(s, lbl, col):
        return (f"{lbl}\n"
                f"Trades: {s['n']}  WR: {s['wr']:.1%}  PF: {s['pf']:.2f}\n"
                f"Total: {s['total']:+.0f}t  MaxDD: {s['max_dd']:.0f}t\n"
                f"AvgW: {s['avg_w']:+.1f}t  AvgL: {s['avg_l']:+.1f}t  StopRate: {s['stop_rate']:.0%}")

    ax_cum.text(0.01, 0.97, sbox(sa, f"── {label_a}", col_a),
                transform=ax_cum.transAxes, color=col_a, fontsize=8,
                va="top", bbox=dict(boxstyle="round,pad=0.4", fc="#1a2230", ec=GRID))
    ax_cum.text(0.35, 0.97, sbox(sb, f"── {label_b}", col_b),
                transform=ax_cum.transAxes, color=col_b, fontsize=8,
                va="top", bbox=dict(boxstyle="round,pad=0.4", fc="#1a2230", ec=GRID))
    leg = ax_cum.legend(fontsize=9, facecolor="#1a2230", edgecolor=GRID, loc="lower right")
    [t.set_color(TXT) for t in leg.get_texts()]

    # ── 2. Drawdowns ──────────────────────────────────────────────────────────
    for ax, df_, col_, lbl_ in [
        (ax_dd_a, dfa, col_a, label_a),
        (ax_dd_b, dfb, col_b, label_b),
    ]:
        cum = df_["pnl"].cumsum(); dd = cum - cum.cummax()
        ax.fill_between(df_["entry_time"], dd, 0, alpha=0.75, color=col_)
        ax.set_title(f"{lbl_} Drawdown  (max {dd.min():.0f}t)", color=TXT, fontsize=10, pad=6)
        ax.set_ylabel("Ticks", color=TXT, fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    # ── 3. Monthly PnL comparison ─────────────────────────────────────────────
    x = np.arange(len(mo_ov)); w = 0.38
    ax_mo.bar(x - w/2, mo_ov["a"], w, color=col_a, alpha=0.75, label=label_a)
    ax_mo.bar(x + w/2, mo_ov["b"], w, color=col_b, alpha=0.75, label=label_b)
    ax_mo.axhline(0, color=GRID, lw=0.8)
    ax_mo.set_title("Monthly PnL Comparison (overlap period)", color=TXT, fontsize=10, pad=6)
    ax_mo.set_ylabel("Ticks", color=TXT, fontsize=9)
    step = max(1, len(mo_ov) // 24)
    ax_mo.set_xticks(x[::step])
    ax_mo.set_xticklabels([str(d)[:7] for d in mo_ov.index[::step]],
                          rotation=35, ha="right", fontsize=7.5, color=TXT)
    leg3 = ax_mo.legend(fontsize=9, facecolor="#1a2230", edgecolor=GRID)
    [t.set_color(TXT) for t in leg3.get_texts()]

    # ── 4. Bars held avg PnL ──────────────────────────────────────────────────
    bb_bins = [0, 1, 2, 3, 5, 10, 999]; bb_labs = ["1","2","3","4-5","6-10","11+"]
    for ax, df_, col_, lbl_ in [
        (ax_bh_a, dfa, col_a, label_a),
        (ax_bh_b, dfb, col_b, label_b),
    ]:
        df_ = df_.copy()
        df_["bb"] = pd.cut(df_["bars_held"], bins=bb_bins, labels=bb_labs)
        bh = (df_.groupby("bb", observed=True)["pnl"]
              .agg(["mean","count"])
              .join(df_.groupby("bb", observed=True)["pnl"]
                    .apply(lambda s: (s > 0).mean()).rename("wr")))
        colors = [GREEN if v >= 0 else RED for v in bh["mean"]]
        bars = ax.bar(range(len(bh)), bh["mean"], color=colors, alpha=0.85)
        ax.axhline(0, color=GRID, lw=0.8)
        ax.set_xticks(range(len(bh))); ax.set_xticklabels(bh.index, color=TXT, fontsize=9)
        ax.set_title(f"{lbl_} — Avg PnL by Bars Held", color=TXT, fontsize=10, pad=6)
        ax.set_xlabel("Bars", color=TXT, fontsize=9); ax.set_ylabel("Avg Ticks", color=TXT, fontsize=9)
        for bar, (_, row) in zip(bars, bh.iterrows()):
            yoff = 0.3 if row["mean"] >= 0 else -1.8
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + yoff,
                    f"{row['wr']:.0%}\nn={int(row['count'])}",
                    ha="center", va="bottom", color=TXT, fontsize=7.5)

    fig.savefig(out, dpi=140, facecolor=DARK, bbox_inches="tight")
    print(f"Saved → {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="manual_vs_auto",
                   choices=["manual_vs_auto", "sc_vs_ag"],
                   help="Preset comparison mode")
    p.add_argument("--a", default=None, help="Path to trades CSV A")
    p.add_argument("--b", default=None, help="Path to trades CSV B")
    p.add_argument("--label-a", default=None)
    p.add_argument("--label-b", default=None)
    p.add_argument("--tick-a", type=float, default=0.1)
    p.add_argument("--tick-b", type=float, default=0.1)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    if args.a and args.b:
        path_a = Path(args.a); path_b = Path(args.b)
        la = args.label_a or path_a.stem
        lb = args.label_b or path_b.stem
        tick_a, tick_b = args.tick_a, args.tick_b
        col_a, col_b = BLUE, GREEN
        out = Path(args.out) if args.out else HERE / "output/chart/compare_custom.png"
    elif args.mode == "sc_vs_ag":
        path_a = HERE / "output/csv/sc99_auto_trades.csv"
        path_b = HERE / "output/csv/ag99_auto_trades.csv"
        la, lb = "SC99 Auto", "AG99 Auto (Silver)"
        tick_a, tick_b = 0.1, 1.0
        col_a, col_b = BLUE, GOLD
        out = HERE / "output/chart/sc99_vs_ag99_compare.png"
    else:  # manual_vs_auto
        path_a = HERE / "output/sim/SC99_73256598410d_trades.csv"
        path_b = HERE / "output/csv/sc99_auto_trades.csv"
        la, lb = "SC99 Manual", "SC99 Auto"
        tick_a, tick_b = 0.1, 0.1
        col_a, col_b = BLUE, GREEN
        out = HERE / "output/chart/sc99_compare_pnl.png"

    print(f"Loading A: {path_a}")
    print(f"Loading B: {path_b}")
    dfa = load(path_a, tick_a, la)
    dfb = load(path_b, tick_b, lb)
    make_chart(dfa, dfb, col_a, col_b, la, lb, out)


if __name__ == "__main__":
    main()
