"""
回测脚本 - 动态判断反弹vs反转
核心逻辑：反弹tick < 下跌tick = 分歧（反弹不是反转）
"""

import pandas as pd
import numpy as np

# ========== 加载数据 ==========
def load_data():
    df = pd.read_csv('/Users/fhu/livedata/AG99.csv')
    df.columns = ['datetime', 'datetime2', 'symbol', 'volume', 'trading_date', 'turnover', 'open_interest', 'open', 'high', 'low', 'close']
    df['timestamp'] = pd.to_datetime(df['datetime'])
    df['bar_time'] = df['timestamp'].dt.floor('15min')
    ohlc = df.groupby('bar_time').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).reset_index()
    ohlc = ohlc.set_index('bar_time').sort_index().reset_index()
    return ohlc

# ========== 入场信号 ==========
def get_signal(i, ohlc):
    """
    K1: 下跌
    K2: 反弹 (反弹幅度 < 下跌幅度 = 分歧；>= 下跌幅度 = 反转)
    K3: 走势
    K4: 确认
    """
    if i < 4:
        return None
    
    k0, k1, k2, k3, k4 = ohlc.iloc[i-4], ohlc.iloc[i-3], ohlc.iloc[i-2], ohlc.iloc[i-1], ohlc.iloc[i]
    
    # K1下跌 tick数
    k1_decline = k0['close'] - k1['close']  # 正数表示跌
    
    # K2反弹 tick数
    k2_rebound = k2['close'] - k1['close']  # 正数表示涨
    
    # 分歧：反弹 < 下跌 (反弹是分歧，不是反转)
    is_divergence = (k1_decline > 0) and (k2_rebound > 0) and (k2_rebound < k1_decline)
    
    # K3继续跌 tick数
    k3_decline = k2['close'] - k3['close']
    
    # 模式1: 追空
    # 分歧出现后继续跌，且跌幅 >= K1的60%
    if is_divergence and k3_decline > 0 and k3_decline >= k1_decline * 0.6:
        return 'short'
    
    # 模式2: 做多
    # 分歧出现后跌放缓（< K1的40%）+ K4涨
    if is_divergence and k3_decline > 0 and k3_decline < k1_decline * 0.4:
        if k4['close'] > k3['close']:
            return 'long'
    
    return None

# ========== 出场逻辑 ==========
def run_backtest(ohlc):
    trades = []
    pos = 0
    entry_p, entry_bar, entry_time = 0, 0, None
    
    for i in range(100, len(ohlc)-10):
        price = ohlc.iloc[i]['close']
        time = ohlc.iloc[i]['bar_time']
        
        # 入场
        if pos == 0:
            sig = get_signal(i, ohlc)
            if sig:
                pos = 1 if sig == 'long' else -1
                entry_p, entry_bar, entry_time = price, i, time
        
        # 持仓中
        else:
            bars = i - entry_bar
            pnl_pct = (price - entry_p) / entry_p * 100 if pos == 1 else (entry_p - price) / entry_p * 100
            
            # 出场判断
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
            
            # 3. 有利润后让利润跑
            if pnl_pct > 1:
                # 看下一根是否继续同向
                next_k = ohlc.iloc[i+1] if i+1 < len(ohlc) else None
                if next_k is not None:
                    cont = (next_k['close'] > price) if pos == 1 else (next_k['close'] < price)
                    if not cont:
                        # 不继续同向，分歧延续，出
                        exit_now = True
                        exit_reason = "分歧延续"
                    elif bars >= 4:
                        # 太久还不大涨，就出
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
                    'exit_reason': exit_reason
                })
                pos = 0
    
    return trades

# ========== 主程序 ==========
if __name__ == "__main__":
    print("加载数据...")
    ohlc = load_data()
    print(f"K线数量: {len(ohlc)}")
    
    print("运行回测...")
    trades = run_backtest(ohlc)
    df_t = pd.DataFrame(trades)
    
    print(f"\n=== 回测结果 ===")
    print(f"交易数: {len(df_t)}")
    print(f"胜率: {(df_t['gross_return']>0).mean()*100:.1f}%")
    print(f"总PnL: {df_t['gross_return'].sum()*10000:.0f}ticks")
    print(f"平均持仓: {df_t['bars_held'].mean():.1f}根")
    
    # 对比实际
    print(f"\n=== 实际交易 ===")
    actual = pd.read_csv('output/sim/AG99_e593f2247554_trades.csv')
    print(f"交易数: {len(actual)}")
    print(f"胜率: {(actual['gross_return']>0).mean()*100:.1f}%")
    print(f"总PnL: {actual['gross_return'].sum()*10000:.0f}ticks")
    print(f"平均持仓: {actual['bars_held'].mean():.1f}根")
    
    # 保存
    df_t.to_csv('output/backtest_dynamic.csv', index=False)
    print(f"\n已保存到: output/backtest_dynamic.csv")
