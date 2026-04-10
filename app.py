import streamlit as st
import pandas as pd
from supabase import create_client, Client
import google.generativeai as genai
import plotly.express as px
import config  # 匯入你的設定檔

# --- 1. 初始化與設定 ---
st.set_page_config(page_title="比特幣影子股監控儀表板", layout="wide")

# 從 config 匯入連線資訊
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# Gemini AI 設定
genai.configure(api_key=config.GEMINI_API_KEY)
try:
    # 使用 2026 年穩定版本模型
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    # 備援模型方案
    model = genai.GenerativeModel('gemini-pro')

# --- 2. 數據獲取函數 ---
@st.cache_data(ttl=300)
def fetch_data():
    # 從 Supabase 抓取歷史指標紀錄
    response = supabase.table("bitcoin_shadow_stocks").select("*").order("created_at", desc=True).limit(1000).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['created_at'] = pd.to_datetime(df['created_at'])
    return df

# --- 3. 網頁介面佈局 ---
st.title("比特幣影子股市場影響指標系統")
st.write("本系統監控全球主要持有比特幣之企業，並計算其溢價率作為市場信心與比特幣價格走勢之參考指標。")

try:
    df = fetch_data()
    
    if df.empty:
        st.warning("目前資料庫中尚無數據，請確認 NAS 爬蟲是否正常運作。")
    else:
        # 側邊欄設定
        tickers = st.sidebar.multiselect(
            "選擇分析對象", 
            options=df['ticker'].unique(), 
            default=["MSTR", "XXI", "3350.T", "MARA"]
        )
        filtered_df = df[df['ticker'].isin(tickers)]

        # --- 第一區塊：核心數據指標 ---
        st.subheader("最新市場快照")
        latest_data = df.sort_values('created_at').groupby('ticker').last().reset_index()
        
        col_metrics = st.columns(len(tickers))
        for i, t in enumerate(tickers):
            row = latest_data[latest_data['ticker'] == t].iloc[0]
            col_metrics[i].metric(
                label=f"{t} 溢價率", 
                value=f"{row['premium_pct']}%", 
                delta=f"{row['stock_price_usd']} USD"
            )

        # --- 第二區塊：圖表分析 ---
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("影子股溢價率趨勢 (市場情緒)")
            # 溢價率公式：$$Premium = \frac{Price_{Stock} - NAV_{BTC}}{NAV_{BTC}}$$
            fig_premium = px.line(filtered_df, x="created_at", y="premium_pct", color="ticker",
                                 title="Premium/Discount Trend", labels={"premium_pct": "溢價率 (%)", "created_at": "時間"})
            st.plotly_chart(fig_premium, use_container_width=True)

        with c2:
            st.subheader("礦企健康度 LTV (潛在拋售壓力)")
            # 針對類別為 Miner 的公司顯示 LTV
            miner_df = filtered_df[filtered_df['category'] == 'Miner']
            if not miner_df.empty:
                fig_ltv = px.area(miner_df, x="created_at", y="ltv_pct", color="ticker",
                                 title="Miner Loan-to-Value (LTV)", labels={"ltv_pct": "LTV (%)"})
                st.plotly_chart(fig_ltv, use_container_width=True)
            else:
                st.info("請選擇礦企標的以顯示 LTV 數據。")

        # --- 第三區塊：價格關聯分析 ---
        st.subheader("比特幣價格與影子股走勢對照")
        fig_corr = px.line(filtered_df, x="created_at", y="stock_price_usd", color="ticker",
                          title="Stock Price vs BTC Time Series")
        st.plotly_chart(fig_corr, use_container_width=True)

        # --- 第四區塊：AI 診斷報告 ---
        st.divider()
        st.subheader("AI 數據診斷與趨勢預測")
        if st.button("點擊產出分析報告"):
            with st.spinner("AI 正在分析市場數據中..."):
                summary = latest_data[['ticker', 'premium_pct', 'ltv_pct', 'btc_price_at_time']].to_string()
                prompt = f"""
                你是一位專業的比特幣宏觀分析師。請根據以下影子股數據進行診斷：
                {summary}
                
                分析重點：
                1. 各大影子股溢價率的一致性表現。
                2. 判斷目前市場處於「恐慌折價」還是「瘋狂溢價」。
                3. 礦企債務比是否對幣價構成潛在威脅。
                4. 給出短期比特幣走勢的分析建議。
                5. 解釋各大數據意涵與其他投資建議
                請以繁體中文撰寫，內容須專業且精簡。
                """
                try:
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as ai_err:
                    st.error(f"AI 分析產生錯誤: {ai_err}")

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

# --- 5. 數據來源 ---
st.divider()
st.subheader("數據來源與聲明")
st.caption("""
1. 即時報價數據：經由 Yahoo Finance (yfinance) API 與compare gecko bitbo Treasuries嘗試多處獲取。
2. 匯率轉換：自動抓取 JPY/USD 與 HKD/USD 匯率進行即時換算。
3. 財務數據：企業持幣量與發行股數根據 2026 年最新季度財報 (10-Q/10-K) 進行手動更新與維護。
4. 免責聲明：本系統數據僅供學術研究與技術展示使用，不構成任何投資建議。
""")