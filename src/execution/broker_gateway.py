import requests
import logging

try:
    from src.execution.risk_manager import RiskManager
except ImportError:
    from execution.risk_manager import RiskManager

class BrokerGateway:
    """
    Base class or interface for different brokers.
    """
    def __init__(self, api_key, access_token):
        self.api_key = api_key
        self.access_token = access_token
        self.logger = logging.getLogger(self.__class__.__name__)
        self.risk_manager = RiskManager()

    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", product="MIS", stop_loss=None, target=None):
        raise NotImplementedError

    def get_portfolio(self):
        raise NotImplementedError

    def get_orders(self):
        raise NotImplementedError

class ZerodhaKiteGateway(BrokerGateway):
    """
    Implementation for Zerodha Kite Connect API.
    """
    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", product="MIS"):
        url = "https://api.kite.trade/orders/regular"
        headers = {
            "X-Kite-Version": "3", 
            "Authorization": f"token {self.api_key}:{self.access_token}"
        }
        payload = {
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "transaction_type": transaction_type, # BUY/SELL
            "order_type": order_type,
            "quantity": quantity,
            "product": product,
            "validity": "DAY"
        }
        
        self.logger.info(f"Placing order: {transaction_type} {quantity} {symbol}")
        # In a real scenario, uncomment the following:
        # response = requests.post(url, headers=headers, data=payload)
        # return response.json()
        
        # Simulate response for demo
        return {"status": "success", "data": {"order_id": "SIM_123456"}}

class KotakNeoGateway(BrokerGateway):
    """
    Implementation for Kotak Neo (via neo_api_client).
    """
    def __init__(self, api_key, access_token, consumer_secret, phone_number, mpin):
        super().__init__(api_key, access_token)
        self.consumer_secret = consumer_secret
        self.phone_number = phone_number
        self.mpin = mpin
        # In actual use: from neo_api_client import NeoAPI
        # self.client = NeoAPI(api_key=api_key, api_secret=consumer_secret)

    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", product="NRML"):
        self.logger.info(f"Kotak Neo: Placing {transaction_type} for {symbol}")
        # Logic: self.client.place_order(trading_symbol=symbol, ...)
        return {"status": "success", "broker": "Kotak Neo", "order_id": "KOTAK_123"}

    def get_portfolio(self):
        self.logger.info("Kotak Neo: Fetching Portfolio")
        return {
            "status": "success",
            "data": [
                {"symbol": "INFY", "qty": 20, "avg_price": 1400.0, "current_price": 1450.0, "pnl": 1000.0},
                {"symbol": "HDFCBANK", "qty": 10, "avg_price": 1600.0, "current_price": 1580.0, "pnl": -200.0}
            ]
        }

    def get_orders(self):
        return [
            {"order_id": "KOTAK_ORD_1", "symbol": "INFY", "status": "COMPLETED", "side": "BUY", "qty": 20},
        ]

class PaytmMoneyGateway(BrokerGateway):
    """
    Implementation for Paytm Money (via pyPMClient).
    """
    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", product="CASH"):
        self.logger.info(f"Paytm Money: Placing {transaction_type} for {symbol}")
        # Logic: self.pm_client.place_order(symbol=symbol, ...)
        return {"status": "success", "broker": "Paytm Money", "order_id": "PAYTM_123"}

    def get_portfolio(self):
        return {"status": "success", "data": []}

    def get_orders(self):
        return []

class IndstocksGateway(BrokerGateway):
    """
    Implementation for Indstocks (INDmoney).
    Official Docs: https://api-docs.indstocks.com/
    """
    def __init__(self, api_key, access_token):
        super().__init__(api_key, access_token)
        self.base_url = "https://api.indstocks.com"
        self.instruments_cache = {} # Map symbol -> security_id
        self.last_instrument_refresh = {} # Map segment -> ISO timestamp of last successful fetch

    def fetch_instruments(self, segment="equity"):
        """
        Fetches instrument master CSV from the web and caches it.
        Segments: equity, fno, index
        """
        import datetime

        url = f"{self.base_url}/market/instruments?source={segment}"
        headers = {"Authorization": self.access_token}
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                # Parse CSV response
                import csv
                from io import StringIO
                f = StringIO(response.text)
                reader = csv.DictReader(f)
                for row in reader:
                    # Map TRADING_SYMBOL to SECURITY_ID
                    symbol = row.get('TRADING_SYMBOL')
                    sec_id = row.get('SECURITY_ID')
                    if symbol and sec_id:
                        self.instruments_cache[symbol] = sec_id
                self.last_instrument_refresh[segment] = datetime.datetime.utcnow().isoformat()
                self.logger.info(f"Loaded {len(self.instruments_cache)} instruments for {segment}")
            else:
                self.logger.error(f"Failed to fetch {segment} instruments: {response.status_code}")
        except Exception as e:
            self.logger.error(f"Error fetching instruments: {e}")

    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", product="CNC", segment="EQUITY", stop_loss=None, target=None):
        # Risk Management Check
        if not self.risk_manager.validate_order({"stop_loss": stop_loss, "target": target}):
            return {"status": "error", "message": "Order rejected by Risk Manager: Missing SL/Target"}

        # Retrieve security_id from cache
        security_id = self.instruments_cache.get(symbol)
        if not security_id:
            # Try to fetch if cache is empty
            self.fetch_instruments(segment.lower())
            security_id = self.instruments_cache.get(symbol)
        
        if not security_id:
            self.logger.error(f"Security ID not found for symbol: {symbol}")
            return {"status": "error", "message": f"Symbol {symbol} not found in instrument master"}

        url = f"{self.base_url}/order"
        headers = {
            "Authorization": self.access_token,
            "Content-Type": "application/json"
        }
        
        payload = {
            "txn_type": transaction_type.upper(), # BUY or SELL
            "exchange": "NSE",
            "segment": segment.upper(),
            "security_id": str(security_id),
            "qty": int(quantity),
            "order_type": order_type.upper(),
            "product": product.upper(), # CNC, INTRADAY, MARGIN
            "validity": "DAY",
            "is_amo": False,
            "algo_id": "99999" # Regular order
        }
        
        self.logger.info(f"Indstocks: Placing {transaction_type} for {symbol} (ID: {security_id})")
        # In actual use:
        # response = requests.post(url, headers=headers, json=payload)
        # return response.json()
        
        return {"status": "success", "broker": "Indstocks", "order_id": "IND_SIM_123"}

    def get_order_status(self, order_id):
        """
        Fetches the status of a specific order.
        """
        url = f"{self.base_url}/order/{order_id}"
        headers = {"Authorization": self.access_token}
        
        # In actual use:
        # response = requests.get(url, headers=headers)
        # return response.json()
        
        return {
            "status": "success",
            "data": {
                "order_id": order_id,
                "order_status": "COMPLETED",
                "average_price": 2450.50,
                "filled_qty": 1
            }
        }

    def get_orders(self):
        """
        Fetches all recent orders.
        """
        url = f"{self.base_url}/orders"
        headers = {"Authorization": self.access_token}
        
        # In actual use:
        # response = requests.get(url, headers=headers)
        # return response.json()
        
        return [
            {"order_id": "IND_ORD_1", "symbol": "RELIANCE", "status": "COMPLETED", "side": "BUY", "qty": 10},
            {"order_id": "IND_ORD_2", "symbol": "TCS", "status": "COMPLETED", "side": "BUY", "qty": 5},
        ]

    def get_portfolio(self):
        """
        Fetches current holdings/portfolio.
        """
        url = f"{self.base_url}/portfolio/holdings"
        headers = {"Authorization": self.access_token}
        
        # In actual use:
        # response = requests.get(url, headers=headers)
        # return response.json()
        
        return {
            "status": "success",
            "data": [
                {"symbol": "RELIANCE", "qty": 10, "avg_price": 2400.0, "current_price": 2450.0, "pnl": 500.0},
                {"symbol": "TCS", "qty": 5, "avg_price": 3200.0, "current_price": 3150.0, "pnl": -250.0}
            ]
        }

if __name__ == "__main__":
    # Example usage for the user's specific brokers
    kotak = KotakNeoGateway("key", "token", "secret", "999...", "1234")
    paytm = PaytmMoneyGateway("key", "token")
    indstocks = IndstocksGateway("key", "token")
    
    print(kotak.place_order("RELIANCE", "BUY", 1))
