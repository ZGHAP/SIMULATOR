"""
回测脚本 - 按用户描述的一致转分歧系统
"""

import pandas as pd
import numpy as np

# ========== 参数设置 ==========
STRONG_REBOUND_PCT = 1.5  # 强反弹阈值 (%)
STRONG_DECLINE_RATIO = 0.8  # 继续强势下跌比例 (K3跌幅/K1跌幅)
EXIT_PROFIT_PCT = 3.0  # 止盈阈值 (%)
STOP_LOSS_PCT = 2.0  # 止损阈值 (%)
TIME_EXIT_BARS = 3  # 时间止损持仓根数

# ========== 加载数据 ==========
def load_data():
    df = pd.read_csv('/Users/fhu/livedata/AG99.csv')
    df.columns = ['datetime', 'datetime2', 'symbol', 'volume', 'trading_date', 'turnover', 'open_interest', 'open', 'high', 'low', 'close']
    df['timestamp'] = pd.to_datetime(df['datetime'])
    df['bar_time'] = df['timestamp'].dt.floor('15min')
    ohlc = df.groupby('bar_time').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).reset_index()
    ohlc = ohlc.set_index('bar_time').sort_index().reset_index()
    return ohlc

# ========== 信号判断 ==========
def get_signal(i, ohlc):
    """
    K1: 下跌
    K2: 强反弹
    K3: 
      - 继续跌且强 -> 追空
      - 跌但不强 -> 等K4，若K4涨则做多
    """
    if i < 4:
        return None, None
    
    k0 = ohlc.iloc[i-4]  # K-1
    k1 = ohlc.iloc[i-3]  # K1
    k2 = ohlc.iloc[i-2]  # K2
    k3 = ohlc.iloc[i-1]  # K3
    k4 = ohlc.iloc[i]    # K4
    
    # K1下跌
    k1_down = k1['close'] < k0['close']
    # K2强反弹
    k2_up = k2['close'] > k1['close']
    k2_rebound = (k2['close'] - k2['open']) / k2['open'] * 100 >= STRONG_REBOUND_PCT
    # K3下跌
    k3_down = k3['close'] < k2['close']
    # K1和K3的跌幅
    k1_decline = (k0['close'] - k1['close']) / k0['close'] * 100
    k3_decline = (k2['close'] - k3['close']) / k2['close'] * 100
    
    # 模式1: 追空 (K1跌 + K2强反弹 + K3继续跌且强)
    if k1_down and k2_up and k2_rebound and k3_down and k3_decline >= k1_decline * STRONG_DECLINE_RATIO:
        return 'short', '追空'
    
    # 模式2: 做多 (K1跌 + K2强反弹 + K3跌但不强 + K4涨)
    if k1_down and k2_up and k2_rebound and k3_down and k3_decline < k1_decline * 0.5:
        if k4['close'] > k3['close']:
            return 'long', '做多'
    
    return None, '无信号'

# ========== 回测 ==========
def run_backtest(ohlc):
    trades = []
    pos = 0  # 0=空仓, 1=多, -1=空
    entry_p = 0
    entry_bar = 0
    entry_r = ""
    entry_time = None
    
    for i in range(100, len(ohlc)-5):
        price = ohlc.iloc[i]['close']
        time = ohlc.iloc[i]['bar_time']
        
        # 入场
        if pos == 0:
            sig, reason = get_signal(i, ohlc)
            if sig:
                pos = 1 if sig == 'long' else -1
                entry_p = price
                entry_bar = i
                entry_r = reason
                entry_time = time
        
        # 持仓中
        else:
            bars = i - entry_bar
            pnl = (price - entry_p) / entry_p * 100 if pos == 1 else (entry_p - price) / entry_p * 100
            
            # 出场条件
            exit_now = False
            exit_reason = ""
            
            # 1. 时间止损
            if bars >= TIME_EXIT_BARS:
                exit_now = True
                exit_reason = "时间止损"
            
            # 2. 止损
            if pnl < -STOP_LOSS_PCT:
                exit_now = True
                exit_reason = "止损"
            
            # 3. 止盈 (大涨持有)
            if pnl >= EXIT_PROFIT_PCT and bars >= 4:
                exit_now = True
                exit_reason = "止盈"
            
            if exit_now:
                gr = (price - entry_p) / entry_p if pos == 1 else (entry_p - price) / entry_p
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': time,
                    'side': 'long' if pos == 1 else 'short',
                    'entry_price': entry_p,
                    'exit_price': price,
                    'bars_held': bars,
                    'gross_return': gr,
                    'entry_reason': entry_r,
                    'exit_reason': exit_reason
                })
                pos = 0
    
    return trades

# ========== 主程序 ==========
if __name__ == "__main__":
    print("加载数据...")
    ohlc = load_data()
    print(f"K线数量: {len(ohlc)}")
    
    print("\n运行回测...")
    trades = run_backtest(ohlc)
    df_t = pd.DataFrame(trades)
    
    print(f"\n=== 回测结果 ===")
    print(f"交易数: {len(df_t)}")
    
    if len(df_t) > 0:
        wins = df_t[df_t['gross_return'] > 0]
        print(f"胜率: {len(wins)/len(df_t)*100:.1f}%")
        print(f"总PnL: {df_t['gross_return'].sum()*10000:.0f} ticks")
        print(f"平均持仓: {df_t['bars_held'].mean():.1f}根")
        
        print(f"\n按入场模式:")
        for r in df_t['entry_reason'].unique():
            s = df_t[df_t['entry_reason'] == r]
            if len(s) > 0:
                print(f"  {r}: N={len(s)}, 胜率={(s['gross_return']>0).mean()*100:.1f}%")
    
    # 对比实际
    print(f"\n=== 实际交易 ===")
    actual = pd.read_csv('output/sim/AG99_e593f2247554_trades.csv')
    print(f"交易数: {len(actual)}")
    print(f"胜率: {(actual['gross_return']>0).mean()*100:.1f}%")
    print(f"总PnL: {actual['gross_return'].sum()*10000:.0f} ticks")
