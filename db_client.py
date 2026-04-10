from supabase import create_client, Client
import config

class DBClient:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    def upload_data(self, data_list):
        try:
            self.client.table("bitcoin_shadow_stocks").insert(data_list).execute()
            print(f"成功上傳 {len(data_list)} 筆數據至雲端 SQL")
        except Exception as e:
            print(f"資料庫同步失敗: {e}")