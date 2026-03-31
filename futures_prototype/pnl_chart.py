import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# ── load ──────────────────────────────────────────────────────────────────────
f = Path(__file__).parent / "output/sim/AG99_e593f2247554_trades.csv"
df = pd.read_csv(f, parse_dates=["entry_time", "exit_time"])

# tick PnL (tick_size = 1.0 for AG99)
df["pnl"] = (df["exit_price"] - df["entry_price"]) * df["side"].map({"long": 1, "short": -1})
df["cum_pnl"] = df["pnl"].cumsum()
df["trade_no"] = range(1, len(df) + 1)

wins = df[df["pnl"] > 0]
losses = df[df["pnl"] < 0]

win_rate = len(wins) / len(df)
avg_win = wins["pnl"].mean()
avg_loss = losses["pnl"].mean()
profit_factor = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) else float("inf")
total_pnl = df["pnl"].sum()

# max drawdown
peak = df["cum_pnl"].cummax()
drawdown = df["cum_pnl"] - peak
max_dd = drawdown.min()

# rolling win rate (50-trade window)
df["rolling_wr"] = (df["pnl"] > 0).rolling(50, min_periods=10).mean() * 100

# ── figure ────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(16, 12), facecolor="#111722")
fig.suptitle("AG99 15m  |  Manual Sim PnL Analysis", color="#e0e6f0",
             fontsize=15, fontweight="bold", y=0.98)

gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.32,
                       left=0.07, right=0.97, top=0.93, bottom=0.07)

ax_cum   = fig.add_subplot(gs[0, :])   # full-width cumulative PnL
ax_hist  = fig.add_subplot(gs[1, 0])   # trade PnL histogram
ax_wr    = fig.add_subplot(gs[1, 1])   # rolling win rate
ax_dd    = fig.add_subplot(gs[2, 0])   # drawdown
ax_bars  = fig.add_subplot(gs[2, 1])   # bars held distribution

DARK = "#111722"
GRID = "#2a3342"
TXT  = "#8aa0b4"
GREEN = "#37d67a"
RED   = "#ff5c5c"
BLUE  = "#4db3ff"
GOLD  = "#ffd700"

for ax in [ax_cum, ax_hist, ax_wr, ax_dd, ax_bars]:
    ax.set_facecolor(DARK)
    ax.tick_params(colors=TXT, labelsize=9)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.grid(color=GRID, linewidth=0.6, linestyle="--")

# ── cumulative PnL ─────────────────────────────────────────────────────────
ax_cum.plot(df["trade_no"], df["cum_pnl"], color=BLUE, linewidth=1.4, zorder=3)
ax_cum.fill_between(df["trade_no"], df["cum_pnl"], 0,
                    where=df["cum_pnl"] >= 0, alpha=0.15, color=GREEN, zorder=2)
ax_cum.fill_between(df["trade_no"], df["cum_pnl"], 0,
                    where=df["cum_pnl"] < 0, alpha=0.15, color=RED, zorder=2)
ax_cum.axhline(0, color=GRID, linewidth=0.8)
ax_cum.set_title("Cumulative PnL (ticks)", color=TXT, fontsize=10, pad=6)
ax_cum.set_xlabel("Trade #", color=TXT, fontsize=9)
ax_cum.set_ylabel("Ticks", color=TXT, fontsize=9)
final_color = GREEN if total_pnl >= 0 else RED
ax_cum.annotate(f"Final: {total_pnl:+.0f}t",
                xy=(len(df), df["cum_pnl"].iloc[-1]),
                xytext=(-60, 12), textcoords="offset points",
                color=final_color, fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=final_color, lw=1))

# stats box
stats = (f"Trades: {len(df)}  |  Win rate: {win_rate:.1%}  |  "
         f"Avg W: {avg_win:+.1f}t  Avg L: {avg_loss:+.1f}t  |  "
         f"PF: {profit_factor:.2f}  |  Max DD: {max_dd:.0f}t")
ax_cum.text(0.01, 0.04, stats, transform=ax_cum.transAxes,
            color=TXT, fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a2230", edgecolor=GRID))

# ── histogram ──────────────────────────────────────────────────────────────
bins = np.linspace(df["pnl"].quantile(0.01), df["pnl"].quantile(0.99), 50)
ax_hist.hist(wins["pnl"], bins=bins, color=GREEN, alpha=0.75, label=f"Win ({len(wins)})")
ax_hist.hist(losses["pnl"], bins=bins, color=RED, alpha=0.75, label=f"Loss ({len(losses)})")
ax_hist.axvline(0, color=GRID, linewidth=1)
ax_hist.axvline(avg_win, color=GREEN, linewidth=1, linestyle="--", alpha=0.8)
ax_hist.axvline(avg_loss, color=RED, linewidth=1, linestyle="--", alpha=0.8)
ax_hist.set_title("Trade PnL Distribution (ticks)", color=TXT, fontsize=10, pad=6)
ax_hist.set_xlabel("Ticks", color=TXT, fontsize=9)
ax_hist.set_ylabel("Count", color=TXT, fontsize=9)
leg = ax_hist.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
for t in leg.get_texts():
    t.set_color(TXT)

# ── rolling win rate ───────────────────────────────────────────────────────
ax_wr.plot(df["trade_no"], df["rolling_wr"], color=GOLD, linewidth=1.2)
ax_wr.axhline(50, color=GRID, linewidth=0.8, linestyle="--")
ax_wr.axhline(win_rate * 100, color=BLUE, linewidth=0.9, linestyle=":",
              label=f"Overall {win_rate:.1%}")
ax_wr.set_title("Rolling Win Rate (50-trade)", color=TXT, fontsize=10, pad=6)
ax_wr.set_xlabel("Trade #", color=TXT, fontsize=9)
ax_wr.set_ylabel("%", color=TXT, fontsize=9)
ax_wr.set_ylim(0, 100)
leg2 = ax_wr.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
for t in leg2.get_texts():
    t.set_color(TXT)

# ── drawdown ───────────────────────────────────────────────────────────────
ax_dd.fill_between(df["trade_no"], drawdown, 0, alpha=0.7, color=RED, zorder=3)
ax_dd.plot(df["trade_no"], drawdown, color=RED, linewidth=0.8, zorder=4)
ax_dd.set_title(f"Drawdown  (max {max_dd:.0f}t)", color=TXT, fontsize=10, pad=6)
ax_dd.set_xlabel("Trade #", color=TXT, fontsize=9)
ax_dd.set_ylabel("Ticks", color=TXT, fontsize=9)

# ── bars held distribution ─────────────────────────────────────────────────
max_bars = int(df["bars_held"].quantile(0.97))
bins_b = np.arange(0.5, max_bars + 1.5, 1)
w_bars = wins[wins["bars_held"] <= max_bars]["bars_held"]
l_bars = losses[losses["bars_held"] <= max_bars]["bars_held"]
ax_bars.hist(w_bars, bins=bins_b, color=GREEN, alpha=0.75, label="Win")
ax_bars.hist(l_bars, bins=bins_b, color=RED, alpha=0.75, label="Loss")
ax_bars.set_title("Bars Held Distribution", color=TXT, fontsize=10, pad=6)
ax_bars.set_xlabel("Bars", color=TXT, fontsize=9)
ax_bars.set_ylabel("Count", color=TXT, fontsize=9)
leg3 = ax_bars.legend(fontsize=8, facecolor="#1a2230", edgecolor=GRID)
for t in leg3.get_texts():
    t.set_color(TXT)

# ── save ──────────────────────────────────────────────────────────────────
out = Path(__file__).parent / "output/pnl_analysis.png"
fig.savefig(out, dpi=140, facecolor=DARK, bbox_inches="tight")
print(f"Saved → {out}")
plt.show()
