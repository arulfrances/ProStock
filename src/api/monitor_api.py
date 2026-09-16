import asyncio
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pandas as pd
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.broker_gateway import IndstocksGateway, KotakNeoGateway
from src.ingestion.nse_downloader import NSEDownloader
from src.features.feature_engineer import FeatureEngineer
from src.models.trainer import ModelTrainer
from src.backtest.engine import BacktestEngine
from src.execution.risk_manager import RiskManager
from src.execution.realtime_signal_engine import RealtimeSignalEngine
from src.execution.indstocks_refresh_scheduler import IndstocksRefreshScheduler
from src.utils.market_status import is_market_open

logger = logging.getLogger("MonitorApi")

app = FastAPI(title="Prostock Market API")

realtime_engine = RealtimeSignalEngine()
_engine_task = None
_indstocks_refresh_task = None


@app.on_event("startup")
async def start_realtime_engine():
    global _engine_task
    if os.getenv("REALTIME_ENGINE_ENABLED", "true").lower() == "true":
        _engine_task = asyncio.create_task(realtime_engine.run_forever())
        logger.info("Realtime signal engine started in background.")


@app.on_event("startup")
async def start_indstocks_refresh():
    global _indstocks_refresh_task
    if os.getenv("INDSTOCKS_AUTO_REFRESH_ENABLED", "true").lower() == "true":
        _indstocks_refresh_task = asyncio.create_task(indstocks_refresh_scheduler.run_forever())
        logger.info(
            f"Indstocks instrument refresh scheduled every {indstocks_refresh_scheduler.interval_hours}h."
        )


@app.on_event("shutdown")
async def stop_realtime_engine():
    realtime_engine.stop()
    if _engine_task:
        _engine_task.cancel()
    await realtime_engine.notifier.aclose()


@app.on_event("shutdown")
async def stop_indstocks_refresh():
    indstocks_refresh_scheduler.stop()
    if _indstocks_refresh_task:
        _indstocks_refresh_task.cancel()

# Initialize components
downloader = NSEDownloader()
fe = FeatureEngineer()
trainer = ModelTrainer()
backtester = BacktestEngine()
risk_manager = RiskManager()

# Defaults & Caching
INDEX_CACHE = {
    "last_updated": None,
    "data": {},
    "market": {"open": False, "status": "FETCHING..."}
}

BROKER_CONTEXT = {
    "active": "indstocks",
    "brokers": {
        "indstocks": IndstocksGateway(os.getenv("IND_API_KEY", "key"), os.getenv("IND_ACCESS_TOKEN", "token")),
        "kotak": KotakNeoGateway(
            os.getenv("KOTAK_API_KEY", "key"), 
            os.getenv("KOTAK_ACCESS_TOKEN", "token"),
            os.getenv("KOTAK_CONSUMER_SECRET", "secret"),
            os.getenv("KOTAK_PHONE", "999"),
            os.getenv("KOTAK_MPIN", "1234")
        )
    }
}

indstocks_refresh_scheduler = IndstocksRefreshScheduler(BROKER_CONTEXT["brokers"]["indstocks"])

@app.get("/api")
def read_root():
    return {"status": "Prostock Engine is Running"}

@app.get("/api/health")
def health_check():
    """Cheap endpoint for uptime pingers; does no downstream I/O."""
    return {"status": "ok", "time": pd.Timestamp.now().isoformat()}

@app.get("/api/predictions")
def get_latest_predictions(symbol: str = "NIFTY 50"):
    try:
        valid_indices = ["NIFTY 50", "SENSEX"]
        if symbol.upper() == "NIFTY":
            symbol = "NIFTY 50"
        elif symbol.upper() == "SENSEX":
            symbol = "SENSEX"
        if symbol not in valid_indices:
            return {"status": "error", "message": "Options signals are available for NIFTY 50 and SENSEX only."}

        # 1. Fetch latest data (last 100 days to calculate technical indicators)
        df = downloader.download_index_data(symbol, start_date=(pd.Timestamp.now() - pd.Timedelta(days=100)).strftime('%Y-%m-%d'))
        
        if df is None or df.empty:
            return {"status": "error", "message": "Failed to fetch market data"}
            
        # 2. Engineer features
        df_features = fe.add_technical_indicators(df)
        
        # 3. Get prediction
        feature_cols = [col for col in df_features.columns if col not in ['Target', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
        prediction = trainer.predict_latest(df_features, feature_cols)
        
        current_price = float(df['Close'].iloc[-1])
        atr = float(df_features['ATR'].iloc[-1])

        if prediction is None:
            rsi = float(df_features["RSI"].iloc[-1])
            prediction = {
                "signal": "BUY" if rsi >= 50 else "SELL",
                "confidence": min(0.75, 0.5 + abs(rsi - 50) / 100)
            }
            signal_type = "Educational RSI momentum observation (model unavailable)"
        else:
            signal_type = "Educational model observation"

        sl, target = risk_manager.calculate_levels(current_price, atr, side=prediction["signal"])
        option_side = "CALL (CE)" if prediction["signal"] == "BUY" else "PUT (PE)"

        return {
            "symbol": symbol,
            "price": current_price,
            "signal": prediction["signal"],
            "option_side": option_side,
            "confidence": prediction["confidence"],
            "stop_loss": sl,
            "target": target,
            "signal_type": signal_type,
            "execution": "manual_review_required",
            "timestamp": pd.Timestamp.now().isoformat()
        }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/options-signals")
def get_options_signals(symbol: str = "NIFTY 50"):
    """Cloudflare Pages-compatible endpoint shape for reviewed observations."""
    return get_latest_predictions(symbol)

@app.get("/api/realtime/status")
def get_realtime_status():
    """
    Returns the realtime engine's latest blended-confidence evaluation for
    each tracked symbol, including whether it cleared the high-conviction
    (>= MIN_CONFIDENCE) bar that triggers a Telegram alert.
    """
    return {
        "engine_running": _engine_task is not None and not _engine_task.done(),
        "poll_seconds": realtime_engine.poll_seconds,
        "min_confidence": realtime_engine.signal_engine.min_confidence,
        "telegram_configured": realtime_engine.notifier.is_configured(),
        "symbols": realtime_engine.last_status,
    }

@app.get("/api/indstocks/refresh-status")
def get_indstocks_refresh_status():
    """Reports when the Indstocks instrument master was last pulled from the web."""
    gateway = BROKER_CONTEXT["brokers"]["indstocks"]
    return {
        "auto_refresh_running": _indstocks_refresh_task is not None and not _indstocks_refresh_task.done(),
        "interval_hours": indstocks_refresh_scheduler.interval_hours,
        "segments": indstocks_refresh_scheduler.segments,
        "last_refreshed": gateway.last_instrument_refresh,
        "cached_instrument_count": len(gateway.instruments_cache),
    }

@app.post("/api/indstocks/refresh-now")
async def trigger_indstocks_refresh():
    """Forces an immediate instrument master refresh from the web (outside the 24h cycle)."""
    await indstocks_refresh_scheduler.refresh_now()
    gateway = BROKER_CONTEXT["brokers"]["indstocks"]
    return {"status": "success", "last_refreshed": gateway.last_instrument_refresh}

@app.get("/api/backtest")
def get_backtest_report():
    try:
        # Load the saved model and historical data
        df = downloader.download_index_data("NIFTY 50", start_date="2023-01-01")
        if df is None: return {"status": "error", "message": "No data"}
        
        df_features = fe.add_technical_indicators(df)
        model = trainer.load_model()
        if not model: return {"status": "error", "message": "Model not trained"}
        
        feature_cols = [col for col in df_features.columns if col not in ['Target', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
        predictions = model.predict(df_features[feature_cols])
        
        report = backtester.run_backtest(df_features, predictions)
        return report
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/indices")
def get_all_indices():
    try:
        now = pd.Timestamp.now()
        
        # Check cache (Refresh every 5 minutes)
        if INDEX_CACHE["last_updated"] and (now - INDEX_CACHE["last_updated"]).seconds < 300:
            return {**INDEX_CACHE["data"], "market": INDEX_CACHE["market"]}

        isOpen, status_text = is_market_open()
        indices = ["NIFTY 50", "BANKNIFTY", "SENSEX"]
        results = {}
        
        for idx in indices:
            # For live updates, only fetch last 5 days to be fast
            df = downloader.download_index_data(idx, start_date=(now - pd.Timedelta(days=5)).strftime('%Y-%m-%d'))
            if df is not None and not df.empty:
                current_price = float(df['Close'].iloc[-1])
                prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else current_price
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                results[idx] = {
                    "price": current_price,
                    "change": change,
                    "change_pct": change_pct
                }
        
        # Update Cache
        INDEX_CACHE["data"] = results
        INDEX_CACHE["market"] = {"open": isOpen, "status": status_text}
        INDEX_CACHE["last_updated"] = now
        
        return {**results, "market": INDEX_CACHE["market"]}
    except Exception as e:
        # Fallback to cache if error
        if INDEX_CACHE["data"]:
             return {**INDEX_CACHE["data"], "market": INDEX_CACHE["market"]}
        return {"status": "error", "message": str(e)}

@app.get("/api/config")
def get_config():
    return {"active_broker": BROKER_CONTEXT["active"]}

@app.post("/api/config/switch")
def switch_broker(broker: str):
    if broker.lower() in BROKER_CONTEXT["brokers"]:
        BROKER_CONTEXT["active"] = broker.lower()
        return {"status": "success", "active_broker": BROKER_CONTEXT["active"]}
    return {"status": "error", "message": "Broker not found"}

@app.get("/api/profile")
def get_user_profile():
    active_key = BROKER_CONTEXT["active"]
    active_broker = BROKER_CONTEXT["brokers"][active_key]
    
    try:
        # Mock retrieval based on active broker
        return {
            "status": "success",
            "broker": active_key,
            "data": {
                "first_name": active_key.capitalize(),
                "last_name": "User",
                "email": f"user@{active_key}.com",
                "user_id": f"{active_key.upper()}_123"
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/portfolio")
def get_portfolio():
    active_key = BROKER_CONTEXT["active"]
    return BROKER_CONTEXT["brokers"][active_key].get_portfolio()

@app.get("/api/orders")
def get_orders():
    active_key = BROKER_CONTEXT["active"]
    return BROKER_CONTEXT["brokers"][active_key].get_orders()

@app.get("/api/search")
def search_symbol(query: str):
    """
    Simple search simulation. 
    In reality, this would search a ticker list or call a broker API.
    """
    valid_indices = ["NIFTY 50", "BANKNIFTY", "SENSEX"]
    results = [idx for idx in valid_indices if query.upper() in idx.upper()]
    return {"query": query, "results": results}

# Serve Static Files
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, "index.html"))

@app.get("/{file_path:path}")
async def serve_file(file_path: str):
    file = os.path.join(static_path, file_path)
    if os.path.exists(file):
        return FileResponse(file)
    return FileResponse(os.path.join(static_path, "index.html"))

if __name__ == "__main__":
    import uvicorn
    # Run: python src/api/monitor_api.py
    uvicorn.run(app, host="0.0.0.0", port=8000)
