import os
import requests
import pandas as pd
from datetime import datetime, timedelta
import zipfile
import io

class NSEDownloader:
    """
    Downloads historical and daily data from NSE.
    Note: NSE has strict rate limiting and header requirements.
    """
    
    BASE_URL = "https://www.nseindia.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = "/tmp/prostock-data" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "data"
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, "raw")
        self.processed_dir = os.path.join(data_dir, "processed")
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._init_dirs()

    def _init_dirs(self):
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    def _get_cookies(self):
        # Visit home page to get cookies
        self.session.get(self.BASE_URL)

    def download_index_data(self, index_name="NIFTY 50", start_date=None, end_date=None):
        """
        Uses yfinance as a reliable fallback for index data if official NSE scrape fails.
        Indices: ^NSEI (Nifty 50), ^NSEBANK (Bank Nifty), ^BSESN (Sensex)
        """
        import yfinance as yf
        
        tickers = {
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "SENSEX": "^BSESN"
        }
        
        symbol = tickers.get(index_name.upper())
        if not symbol:
            print(f"Index {index_name} not supported via yfinance.")
            return None

        print(f"Downloading {index_name} data from yfinance...")
        ticker = yf.Ticker(symbol)
        
        # Determine period based on start_date
        period = "max"
        if start_date:
            # yf.download is often more reliable for specific dates in older SDKs
            # But let's try history first
            df = ticker.history(start=start_date, end=end_date)
        else:
            df = ticker.history(period="5y")
            
        if not df.empty:
            # Flatten columns if multiindex (history usually isn't but just in case)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]
                
            file_path = os.path.join(self.processed_dir, f"{index_name.lower().replace(' ', '_')}_historical.parquet")
            df.to_parquet(file_path)
            print(f"Saved to {file_path}")
            return df
        
        print(f"Warning: No data returned for {symbol}")
        return None

    def download_bhavcopy(self, date):
        """
        Downloads the Equity Bhavcopy for a specific date.
        Format: https://www.nseindia.com/content/historical/EQUITIES/2023/JAN/cm01JAN2023bhav.csv.zip
        """
        date_obj = pd.to_datetime(date)
        day = date_obj.strftime("%d")
        month = date_obj.strftime("%b").upper()
        year = date_obj.strftime("%Y")
        
        filename = f"cm{day}{month}{year}bhav.csv"
        url = f"{self.BASE_URL}/content/historical/EQUITIES/{year}/{month}/{filename}.zip"
        
        print(f"Attempting to download bhavcopy from {url}")
        
        try:
            self._get_cookies()
            response = self.session.get(url)
            if response.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    z.extractall(self.raw_dir)
                print(f"Successfully downloaded {filename}")
                return os.path.join(self.raw_dir, filename)
            else:
                print(f"Failed to download. Status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error downloading bhavcopy: {e}")
            return None

if __name__ == "__main__":
    downloader = NSEDownloader()
    # Example: Recent Nifty 50 data
    downloader.download_index_data("NIFTY 50", start_date="2024-01-01")
    # Example: Bhavcopy (might fail depending on NSE session/IP rating)
    # downloader.download_bhavcopy("2024-01-24")
