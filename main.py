import pandas as pd
from supabase import create_client
import config
from fetcher import Fetcher
import datetime

def calculate_category_weighted_score(row):
    """
    實作「面向權重」邏輯：
    - Treasury (國庫型): 估值(50%)、效能(30%)、風險(20%)
    - Miner (礦企型): 估值(20%)、效能(40%)、風險(40%)
    """
    cat = row['category']
    pre = row['premium_pct']
    psat = row['p_sat_ratio']
    ltv = row['ltv_pct']
    
    # 基礎分計算 (0-100分制)
    # 估值分：溢價越低分數越高，折價(pre < 0)直接滿分
    v_score = 100 if pre < 0 else max(0, 100 - (pre / 2))
    # 效能分：P/SAT 越低越划算 (基準設為 1000 聰/美金)
    h_score = max(0, 100 * (1 - (psat / 1000)))
    # 風險分：LTV 越低越安全
    r_score = max(0, 100 * (1 - (ltv / 100)))
    
    if cat == 'Treasury':
        score = (v_score * 0.5) + (h_score * 0.3) + (r_score * 0.2)
    elif cat == 'Miner':
        score = (v_score * 0.2) + (h_score * 0.4) + (r_score * 0.4)
    else:
        score = (v_score + h_score + r_score) / 3
    return round(score, 1)

def main():
    supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    fetcher = Fetcher(config.COMPANY_CONFIG)
    data = fetcher.get_live_data()
    btc_p = data['btc_price']
    
    # 計算全市場總持幣 (用於計算市場佔比)
    total_market_btc = sum(info['btc'] for info in config.COMPANY_CONFIG.values())
    
    rows = []
    print(f"[{datetime.datetime.now()}] 啟動數據計算與匯率對沖...")

    for ticker, info in config.COMPANY_CONFIG.items():
        try:
            # 1. 抓取原始股價
            raw_p = data['prices'][ticker]
            
            # 2. 【核心修正】強制換匯對照邏輯
            # YFinance 的匯率 Key 通常是 'JPYUSD=X' 這種格式
            suffix = ticker.split('.')[-1] if '.' in ticker else 'USD'
            
            if suffix == 'T': # 東京證交所
                fx_rate = data['fx'].get('JPYUSD=X', 0.0065)
                stock_p = raw_p * fx_rate
            elif suffix == 'HK': # 香港證交所
                fx_rate = data['fx'].get('HKDUSD=X', 0.128)
                stock_p = raw_p * fx_rate
            else: # 預設為美金標的
                stock_p = raw_p
            
            # 3. 基礎數據與 12 項指標計算
            shares = info['shares']
            btc_per_s = info['btc'] / shares
            nav_ps = btc_per_s * btc_p
            
            row = {
                "ticker": ticker,
                "category": info['type'],
                "btc_price_at_time": btc_p,
                "stock_price_usd": round(stock_p, 4),
                "premium_pct": round(((stock_p / nav_ps) - 1) * 100, 2) if nav_ps > 0 else 0,
                "btc_per_share": btc_per_s,
                "sats_per_share": round(btc_per_s * 100000000, 2),
                "p_sat_ratio": round(stock_p / (btc_per_s * 1000), 4) if btc_per_s > 0 else 0,
                "debt": info['debt'],
                "mnav": round((info['btc'] * btc_p) - info['debt'], 2),
                "ltv_pct": round((info['debt'] / (info['btc'] * btc_p)) * 100, 2) if info['btc'] > 0 else 0,
                "implied_beta": round(abs(((stock_p / nav_ps) - 1)) + 1, 2) if nav_ps > 0 else 1
            }
            
            # 4. 新增：市場權重與分類加權評分
            row["market_weight_pct"] = round((info['btc'] / total_market_btc) * 100, 2)
            row["dat_score"] = calculate_category_weighted_score(row)
            
            rows.append(row)
            print(f" {ticker} 計算完成 (最終美金價: {row['stock_price_usd']})")
            
        except Exception as e:
            print(f" {ticker} 處理失敗: {e}")
            continue

    # 5. 上傳至 Supabase
    if rows:
        try:
            supabase.table("bitcoin_shadow_stocks").insert(rows).execute()
            print(f"[{datetime.datetime.now()}]  全數據同步成功正確校準。")
        except Exception as e:
            print(f" Supabase 上傳失敗: {e}")

if __name__ == "__main__":
    main()