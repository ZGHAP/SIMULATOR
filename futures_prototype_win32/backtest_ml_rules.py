"""
基于你实际交易记录归纳的入场规则
通过决策树分析1154笔交易发现
"""

import pandas as pd
import numpy as np

# ========== 加载数据 ==========
def load_ohlc():
    df = pd.read_csv('/Users/fhu/livedata/AG99.csv')
    df.columns = ['datetime', 'datetime2', 'symbol', 'volume', 'trading_date', 'turnover', 'open_interest', 'open', 'high', 'low', 'close']
    df['timestamp'] = pd.to_datetime(df['datetime'])
    df['bar_time'] = df['timestamp'].dt.floor('15min')
    ohlc = df.groupby('bar_time').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).reset_index()
    return ohlc

# ========== 入场信号 ==========
def get_signal(i, ohlc):
    """
    基于决策树发现的规则
    
    规则1: chg2 > 0.25% (第3根涨幅>0.25%) - 胜率50.6%
    规则3: chg2 > 0.25% AND chg1 > 0.06% - 胜率55.8%
    规则4: chg2 <= 0.25% AND total 0.58%~1.01% - 胜率54.5%
    """
    if i < 6:
        return None
    
    klines = ohlc.iloc[i-6:i]
    closes = klines['close'].values
    opens = klines['open'].values
    
    # 每根的涨跌幅
    chg0 = (closes[0] - opens[0]) / opens[0] * 100
    chg1 = (closes[1] - opens[1]) / opens[1] * 100
    chg2 = (closes[2] - opens[2]) / opens[2] * 100
    chg3 = (closes[3] - opens[3]) / opens[3] * 100
    chg4 = (closes[4] - opens[4]) / opens[4] * 100
    chg5 = (closes[5] - opens[5]) / opens[5] * 100
    
    # 总变化 (K1-K6)
    total = (closes[-1] - opens[0]) / opens[0] * 100
    
    # 规则3: chg2 > 0.25% AND chg1 > 0.06% (胜率55.8%)
    if chg2 > 0.25 and chg1 > 0.06:
        return 'long', '规则3-强反弹确认'
    
    # 规则4: chg2 <= 0.25% AND total 0.58%~1.01% (胜率54.5%)
    if chg2 <= 0.25 and total > 0.58 and total <= 1.01:
        return 'long', '规则4-温和上涨'
    
    # 规则5: chg2 <= 0.25% AND total <= 0.39% AND chg0 <= -0.16% (胜率50.5%)
    if chg2 <= 0.25 and total <= 0.39 and chg0 <= -0.16:
        return 'long', '规则5-跌后反弹'
    
    return None, '无信号'

# ========== 回测 ==========
def run_backtest(ohlc):
    trades = []
    pos = 0
    entry_p, entry_bar, entry_time, entry_reason = 0, 0, None, ""
    
    for i in range(100, len(ohlc)-10):
        price = ohlc.iloc[i]['close']
        time = ohlc.iloc[i]['bar_time']
        
        if pos == 0:
            sig, reason = get_signal(i, ohlc)
            if sig:
                pos = 1
                entry_p, entry_bar, entry_time, entry_reason = price, i, time, reason
        else:
            bars = i - entry_bar
            pnl_pct = (price - entry_p) / entry_p * 100
            
            # 出场条件
            exit_now = False
            exit_reason = ""
            
            # 1. 时间止损：持满2根
            if bars >= 2:
                exit_now = True
                exit_reason = "时间止损"
            
            # 2. 止损：-1.5%
            if pnl_pct < -1.5:
                exit_now = True
                exit_reason = "止损"
            
            # 3. 跟踪止损：有利润后跌破高峰的99.5%
            if pnl_pct > 1:
                entry_klines = ohlc.iloc[entry_bar:i+1]
                max_h = entry_klines['high'].max()
                if price < max_h * 0.995:
                    exit_now = True
                    exit_reason = "跟踪止损"
            
            if exit_now:
                gr = (price - entry_p) / entry_p
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': time,
                    'side': 'long',
                    'entry_price': entry_p,
                    'exit_price': price,
                    'bars_held': bars,
                    'gross_return': gr,
                    'entry_reason': entry_reason,
                    'exit_reason': exit_reason
                })
                pos = 0
    
    return trades

# ========== 主程序 ==========
if __name__ == "__main__":
    print("加载数据...")
    ohlc = load_ohlc()
    print(f"K线数量: {len(ohlc)}")
    
    print("\n运行回测...")
    trades = run_backtest(ohlc)
    df_t = pd.DataFrame(trades)
    
    print(f"\n=== 回测结果 ===")
    print(f"交易数: {len(df_t)}")
    print(f"胜率: {(df_t['gross_return']>0).mean()*100:.1f}%")
    print(f"总PnL: {df_t['gross_return'].sum()*10000:.0f}ticks")
    print(f"平均持仓: {df_t['bars_held'].mean():.1f}根")
    
    # 按规则分组
    print(f"\n按入场规则:")
    for r in df_t['entry_reason'].unique():
        s = df_t[df_t['entry_reason'] == r]
        if len(s) > 0:
            print(f"  {r}: N={len(s)}, 胜率={(s['gross_return']>0).mean()*100:.1f}%")
    
    # 对比实际
    print(f"\n=== 实际交易 ===")
    actual = pd.read_csv('output/sim/AG99_e593f2247554_trades.csv')
    print(f"交易数: {len(actual)}")
    print(f"胜率: {(actual['gross_return']>0).mean()*100:.1f}%")
    print(f"总PnL: {actual['gross_return'].sum()*10000:.0f}ticks")
    
    # 保存
    df_t.to_csv('output/backtest_ml_rules.csv', index=False)
    print(f"\n已保存到: output/backtest_ml_rules.csv")
