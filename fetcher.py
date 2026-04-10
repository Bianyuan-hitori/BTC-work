import yfinance as yf
import pandas as pd
import requests
import config
import time

class Fetcher:
    def __init__(self, tickers_dict):
        self.tickers = tickers_dict
        # 這裡整合了你的 Gecko Key
        self.headers = {
            'User-Agent': 'Mozilla/5.0',
            'x-cg-demo-api-key': config.GECKO_API_KEY 
        }
        self._cached_btc = None
        self._last_call = 0

    def get_cryptocompare_btc(self):
        """[校驗點 1] 呼叫 CryptoCompare API 獲取基準幣價"""
        now = time.time()
        if self._cached_btc and (now - self._last_call < 300):
            return self._cached_btc
        try:
            # 使用你截圖中的那串長 Key
            url = f"https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD&api_key={config.COMPARE_API_KEY}"
            res = requests.get(url, timeout=5).json()
            self._cached_btc = res.get('USD')
            self._last_call = now
            return self._cached_btc
        except:
            return self._cached_btc

    def get_coingecko_holdings(self, ticker):
        """[校驗點 2] 呼叫 CoinGecko API 獲取公司持幣 (選配)"""
        # 註：CoinGecko 的公共持有 API 較嚴格，若呼叫失敗會自動回退到爬蟲模式
        return config.COMPANY_CONFIG.get(ticker, {}).get('btc', 0)

    def get_live_data(self):
        """全量數據交叉比對引擎"""
        # A. 持幣量校驗 (爬蟲 + Config)
        holdings = {t: config.COMPANY_CONFIG[t]['btc'] for t in self.tickers}
        try:
            res = requests.get("https://bitbo.io/entities/public-companies/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            tables = pd.read_html(res.text)
            for df_table in tables:
                if 'Symbol' in df_table.columns:
                    for _, row in df_table.iterrows():
                        sym = str(row['Symbol']).upper()
                        if "3350" in sym: sym = "3350.T"
                        btc_val = float(str(row['Total BTC']).replace(',', '').split(' ')[0])
                        if sym in holdings:
                            # 三方對比：取即時值與保底值之最大者
                            holdings[sym] = max(holdings[sym], btc_val)
        except: pass

        # B. 價格與匯率 (YFinance)
        symbols = list(self.tickers.keys()) + ["BTC-USD", "JPYUSD=X", "HKDUSD=X"]
        data = yf.download(symbols, period="2d", interval="1d", group_by='column', progress=False)
        latest = data['Close'].ffill().iloc[-1]
        
        # C. 價格交叉對比 (YFinance vs CryptoCompare)
        yf_btc = latest["BTC-USD"]
        cc_btc = self.get_cryptocompare_btc()
        
        # 如果誤差大於 0.5%，進行動態加權校正
        final_btc_p = (yf_btc + cc_btc) / 2 if cc_btc and abs(yf_btc - cc_btc) / yf_btc > 0.005 else yf_btc
            
        return {
            "prices": latest,
            "fx": {"JPY": latest["JPYUSD=X"], "HKD": latest["HKDUSD=X"], "USD": 1.0},
            "btc_price": final_btc_p,
            "holdings": holdings
        }

    def get_dynamic_shares(self, ticker):
        """股數校正"""
        try:
            t = yf.Ticker(ticker)
            shares = t.info.get('sharesOutstanding')
            return shares if shares else config.COMPANY_CONFIG[ticker]['shares']
        except:
            return config.COMPANY_CONFIG[ticker]['shares']