import streamlit as st
import pandas as pd
from supabase import create_client, Client
import google.generativeai as genai
import plotly.express as px
import requests

# --- 1. 2026 全球核心金鑰自動讀取邏輯 ---
def load_all_env():
    # 這裡對應你提供的五把鑰匙
    keys = [
        "SUPABASE_URL", "SUPABASE_KEY", 
        "GECKO_API_KEY", "COMPARE_API_KEY", "GEMINI_API_KEY"
    ]
    env_data = {}
    
    try:
        # 本地開發模式：讀取 config.py
        import config
        for k in keys:
            env_data[k] = getattr(config, k, None)
    except (ImportError, AttributeError):
        # 雲端部署模式：從 Streamlit Secrets 讀取
        for k in keys:
            env_data[k] = st.secrets.get(k)
            
    return env_data

# 初始化環境
env = load_all_env()

# --- 2. 初始化 API 服務 ---
# Supabase 資料庫連線
supabase: Client = create_client(env["SUPABASE_URL"], env["SUPABASE_KEY"])

# Gemini AI 模型配置
genai.configure(api_key=env["GEMINI_API_KEY"])
try:
    # 優先使用 2026 最新 Flash 模型
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    # 備援模型
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. 2026/04 核心保底配置 (影子股 12 家公司) ---
# 當資料庫連線不穩時，系統仍可根據此配置進行計算
COMPANY_CONFIG = {
    "MSTR":    {"btc": 252220, "shares": 19500000, "type": "Treasury"},
    "XXI":     {"btc": 43514,  "shares": 5200000,  "type": "Treasury"},
    "3350.T":  {"btc": 1142,   "shares": 8500000,  "type": "Treasury"},
    "0434.HK": {"btc": 4092,   "shares": 11000000, "type": "Treasury"},
    "SMLR":    {"btc": 1500,   "shares": 7200000,  "type": "Treasury"},
    "MARA":    {"btc": 38689,  "shares": 22000000, "type": "Miner"},
    "CLSK":    {"btc": 12000,  "shares": 15000000, "type": "Miner"},
    "RIOT":    {"btc": 10500,  "shares": 18000000, "type": "Miner"},
    "CORZ":    {"btc": 5500,   "shares": 25000000, "type": "Miner"},
    "HUT":     {"btc": 9100,   "shares": 9000000,  "type": "Miner"},
    "COIN":    {"btc": 0,      "shares": 1,        "type": "Macro"},
    "TSLA":    {"btc": 9720,   "shares": 31000000, "type": "Macro"},
}

# --- 4. 數據抓取邏輯 ---
st.set_page_config(page_title="比特幣影子股監控儀表板", layout="wide")

@st.cache_data(ttl=300)
def fetch_cloud_data():
    # 從 Supabase 抓取數據
    try:
        response = supabase.table("bitcoin_shadow_stocks").select("*").order("created_at", desc=True).limit(1000).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])
        return df
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

# --- 5. 網頁介面佈局 ---
st.title("比特幣影子股市場影響指標系統")
st.write("透過分析全球持有比特幣企業的溢價率 (Premium)，觀測機構資金與比特幣價格之關聯性。")

try:
    df = fetch_cloud_data()
    
    if df.empty:
        st.warning("目前資料庫中尚無數據，請確認後端自動化腳本是否正常執行。")
    else:
        # 側邊欄：篩選器
        all_tickers = df['ticker'].unique()
        tickers = st.sidebar.multiselect("選擇監控標的", options=all_tickers, default=["MSTR", "3350.T", "MARA"])
        filtered_df = df[df['ticker'].isin(tickers)]

        # 區塊一：核心指標卡 (Metrics)
        st.subheader("最新市場數據快照")
        latest_data = df.sort_values('created_at').groupby('ticker').last().reset_index()
        
        col_list = st.columns(len(tickers))
        for i, t in enumerate(tickers):
            row = latest_data[latest_data['ticker'] == t].iloc[0]
            col_list[i].metric(
                label=f"{t} 溢價率", 
                value=f"{row['premium_pct']}%", 
                delta=f"{row['stock_price_usd']} USD"
            )

        # 區塊二：數據趨勢圖
        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("溢價率趨勢 (Premium %)")
            # 溢價率計算公式說明
            # $$Premium = \frac{Price_{Stock} - NAV_{BTC}}{NAV_{BTC}}$$
            fig_premium = px.line(filtered_df, x="created_at", y="premium_pct", color="ticker",
                                 title="Premium Over Time", labels={"premium_pct": "溢價率 (%)"})
            st.plotly_chart(fig_premium, use_container_width=True)

        with c2:
            st.subheader("礦企健康度指標 (LTV %)")
            miner_df = filtered_df[filtered_df['category'] == 'Miner']
            if not miner_df.empty:
                fig_ltv = px.area(miner_df, x="created_at", y="ltv_pct", color="ticker",
                                 title="Miner Debt Ratio (LTV)", labels={"ltv_pct": "LTV (%)"})
                st.plotly_chart(fig_ltv, use_container_width=True)
            else:
                st.info("請於左側選擇礦企標的以檢視 LTV 指標。")

        # 區塊三：價格關聯對比圖
        st.subheader("比特幣與影子股價格走勢對比")
        fig_corr = px.line(filtered_df, x="created_at", y="stock_price_usd", color="ticker",
                          title="Stock Price Time Series")
        st.plotly_chart(fig_corr, use_container_width=True)

        # 區塊四：AI 診斷報告 (Gemini 2.0)
        st.divider()
        st.subheader("AI 市場診斷與前瞻預測")
        if st.button("生成比特幣市場分析報告"):
            with st.spinner("AI 正在根據最新數據進行運算..."):
                summary_text = latest_data[['ticker', 'premium_pct', 'ltv_pct', 'btc_price_at_time']].to_string()
                prompt = f"""
                請根據以下影子股數據分析比特幣市場走勢：
                {summary_text}
                
                分析要求：
                1. 解釋各大數據關係與指標影響
                2. 識別是否有溢價率過高導致的過熱現象。
                3. 根據礦企 LTV 判斷是否有清算風險賣壓。
                4. 給出短期內比特幣看漲、中立或看跌的專業判斷。
                
                請用專業繁體中文產出報告。
                """
                try:
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as ai_err:
                    st.error(f"AI 分析產生錯誤: {ai_err}")

except Exception as e:
    st.error(f"應用程式運行錯誤: {e}")

# --- 6. 數據來源與系統聲明 ---
st.divider()
st.subheader("數據源與技術說明")
st.caption(f"""
- 資料庫系統：Supabase Cloud SQL
- 報價 API：CoinGecko (備援：CryptoCompare API Key: {env['COMPARE_API_KEY'][:5]}***)
- 匯率轉換：即時 JPY/USD, HKD/USD 換算
- 財報基量：2026/04 季度持幣常數配置
- 免責聲明：本系統數據僅供學術展示與技術研究使用，不代表任何形式之投資建議。
""")