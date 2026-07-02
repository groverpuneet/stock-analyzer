"""Legacy single-verdict signal report (Session A-E).

SUPERSEDED by the 4-pillar explainable engine in `signals/` (Session L): technical,
fundamental, flow, and external pillars combined per SHORT/MID/LONG horizon into
signal_explanations. The Dagster `nse_signals` asset now calls `signals.engine.run_signals`.
This module is kept for the CLI text report and as reference; `run_pillar_signals()`
delegates to the new engine.
"""
import psycopg2
import pandas as pd
from datetime import datetime


def run_pillar_signals(**kwargs):
    """Delegate to the new 4-pillar engine (signals/engine.py)."""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from signals.engine import run_signals
    return run_signals(**kwargs)


DB_PARAMS = {
    'dbname': 'stock_analyzer',
    'user': 'puneetgrover',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def get_latest_data(stock_id, days=5):
    conn = psycopg2.connect(**DB_PARAMS)
    
    query = """
        SELECT 
            dp.date,
            dp.close,
            dp.volume,
            ti.rsi_14,
            ti.sma_20,
            ti.sma_50,
            ti.sma_200,
            ti.macd,
            ti.macd_signal,
            ti.bollinger_upper,
            ti.bollinger_lower
        FROM daily_prices dp
        LEFT JOIN technical_indicators ti ON dp.stock_id = ti.stock_id AND dp.date = ti.date
        WHERE dp.stock_id = %s
        ORDER BY dp.date DESC
        LIMIT %s
    """
    
    df = pd.read_sql_query(query, conn, params=(stock_id, days))
    conn.close()
    
    return df.sort_values('date').reset_index(drop=True)

def check_rsi_signals(df):
    signals = []
    
    if len(df) < 1:
        return signals
    
    latest = df.iloc[-1]
    
    if pd.notna(latest['rsi_14']):
        if latest['rsi_14'] < 30:
            signals.append({
                'type': 'RSI_OVERSOLD',
                'signal': 'BUY',
                'strength': 'STRONG' if latest['rsi_14'] < 25 else 'MODERATE',
                'message': f"RSI at {latest['rsi_14']:.2f} - Oversold"
            })
        elif latest['rsi_14'] > 70:
            signals.append({
                'type': 'RSI_OVERBOUGHT',
                'signal': 'SELL',
                'strength': 'STRONG' if latest['rsi_14'] > 75 else 'MODERATE',
                'message': f"RSI at {latest['rsi_14']:.2f} - Overbought"
            })
    
    return signals

def check_ma_crossover(df):
    signals = []
    
    if len(df) < 2:
        return signals
    
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    if pd.notna(current['sma_50']) and pd.notna(current['sma_200']):
        if previous['sma_50'] <= previous['sma_200'] and current['sma_50'] > current['sma_200']:
            signals.append({
                'type': 'GOLDEN_CROSS',
                'signal': 'BUY',
                'strength': 'STRONG',
                'message': f"Golden Cross - SMA50 above SMA200"
            })
        elif previous['sma_50'] >= previous['sma_200'] and current['sma_50'] < current['sma_200']:
            signals.append({
                'type': 'DEATH_CROSS',
                'signal': 'SELL',
                'strength': 'STRONG',
                'message': f"Death Cross - SMA50 below SMA200"
            })
    
    if pd.notna(current['sma_20']):
        if previous['close'] <= previous['sma_20'] and current['close'] > current['sma_20']:
            signals.append({
                'type': 'PRICE_ABOVE_SMA20',
                'signal': 'BUY',
                'strength': 'MODERATE',
                'message': f"Price crossed above 20-SMA"
            })
        elif previous['close'] >= previous['sma_20'] and current['close'] < current['sma_20']:
            signals.append({
                'type': 'PRICE_BELOW_SMA20',
                'signal': 'SELL',
                'strength': 'MODERATE',
                'message': f"Price crossed below 20-SMA"
            })
    
    return signals

def check_macd_signals(df):
    signals = []
    
    if len(df) < 2:
        return signals
    
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    if pd.notna(current['macd']) and pd.notna(current['macd_signal']):
        if previous['macd'] <= previous['macd_signal'] and current['macd'] > current['macd_signal']:
            signals.append({
                'type': 'MACD_BULLISH',
                'signal': 'BUY',
                'strength': 'MODERATE',
                'message': f"MACD bullish crossover"
            })
        elif previous['macd'] >= previous['macd_signal'] and current['macd'] < current['macd_signal']:
            signals.append({
                'type': 'MACD_BEARISH',
                'signal': 'SELL',
                'strength': 'MODERATE',
                'message': f"MACD bearish crossover"
            })
    
    return signals

def check_bollinger_signals(df):
    signals = []
    
    if len(df) < 1:
        return signals
    
    latest = df.iloc[-1]
    
    if pd.notna(latest['bollinger_upper']) and pd.notna(latest['bollinger_lower']):
        if latest['close'] <= latest['bollinger_lower']:
            signals.append({
                'type': 'BOLLINGER_LOWER',
                'signal': 'BUY',
                'strength': 'MODERATE',
                'message': f"At lower Bollinger Band"
            })
        elif latest['close'] >= latest['bollinger_upper']:
            signals.append({
                'type': 'BOLLINGER_UPPER',
                'signal': 'SELL',
                'strength': 'MODERATE',
                'message': f"At upper Bollinger Band"
            })
    
    return signals

def check_volume_spike(df):
    signals = []
    
    if len(df) < 5:
        return signals
    
    latest = df.iloc[-1]
    avg_volume = df.iloc[-5:-1]['volume'].mean()
    
    if latest['volume'] > avg_volume * 2:
        signals.append({
            'type': 'VOLUME_SPIKE',
            'signal': 'WATCH',
            'strength': 'MODERATE',
            'message': f"Volume: {latest['volume']:,} (avg: {avg_volume:,.0f})"
        })
    
    return signals

def analyze_stock(stock_id, symbol):
    df = get_latest_data(stock_id, days=5)
    
    if len(df) == 0:
        return None
    
    all_signals = []
    all_signals.extend(check_rsi_signals(df))
    all_signals.extend(check_ma_crossover(df))
    all_signals.extend(check_macd_signals(df))
    all_signals.extend(check_bollinger_signals(df))
    all_signals.extend(check_volume_spike(df))
    
    if not all_signals:
        return None
    
    latest = df.iloc[-1]
    
    return {
        'symbol': symbol,
        'date': latest['date'],
        'close': latest['close'],
        'signals': all_signals
    }

def generate_daily_report():
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.tradingsymbol
        FROM watchlist w
        JOIN stocks s ON w.stock_id = s.id
        WHERE w.name = 'Default'
        ORDER BY s.tradingsymbol
    """)
    
    stocks = cursor.fetchall()
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print(f"DAILY ANALYSIS REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    buy_signals = []
    sell_signals = []
    watch_signals = []
    
    for stock_id, symbol in stocks:
        try:
            result = analyze_stock(stock_id, symbol)
            
            if result:
                for signal in result['signals']:
                    signal_info = {
                        'symbol': symbol,
                        'close': result['close'],
                        'signal': signal
                    }
                    
                    if signal['signal'] == 'BUY':
                        buy_signals.append(signal_info)
                    elif signal['signal'] == 'SELL':
                        sell_signals.append(signal_info)
                    else:
                        watch_signals.append(signal_info)
        
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    if buy_signals:
        print("\n🟢 BUY SIGNALS:")
        print("-" * 60)
        for sig in buy_signals:
            strength = "⚡" if sig['signal']['strength'] == 'STRONG' else "→"
            print(f"{strength} {sig['symbol']:12} ₹{sig['close']:8.2f}  {sig['signal']['message']}")
    
    if sell_signals:
        print("\n🔴 SELL SIGNALS:")
        print("-" * 60)
        for sig in sell_signals:
            strength = "⚡" if sig['signal']['strength'] == 'STRONG' else "→"
            print(f"{strength} {sig['symbol']:12} ₹{sig['close']:8.2f}  {sig['signal']['message']}")
    
    if watch_signals:
        print("\n🟡 WATCH LIST:")
        print("-" * 60)
        for sig in watch_signals:
            print(f"→ {sig['symbol']:12} ₹{sig['close']:8.2f}  {sig['signal']['message']}")
    
    if not buy_signals and not sell_signals and not watch_signals:
        print("\n✓ No significant signals detected today")
    
    print("\n" + "="*60)
    print(f"\nSummary: {len(buy_signals)} BUY | {len(sell_signals)} SELL | {len(watch_signals)} WATCH")
    print("="*60 + "\n")

if __name__ == "__main__":
    generate_daily_report()
