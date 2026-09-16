import asyncio
import logging
import os
import time
from collections import defaultdict, deque

import numpy as np
import pandas as pd

from src.execution.option_selector import select_option_strike
from src.execution.risk_manager import RiskManager
from src.features.feature_engineer import FeatureEngineer
from src.ingestion.nse_downloader import NSEDownloader
from src.models.signal_engine import SignalEngine
from src.utils.market_status import is_market_open
from src.utils.telegram_notifier import TelegramNotifier

logger = logging.getLogger("RealtimeSignalEngine")

NON_FEATURE_COLUMNS = ["Target", "Open", "High", "Low", "Close", "Adj Close", "Volume"]


class RealtimeSignalEngine:
    """
    Polls each configured symbol on a fixed interval and dispatches a
    Telegram alert immediately whenever a fresh high-conviction (>= MIN_CONFIDENCE)
    signal appears, so there's no batching/buffering delay before delivery.

    It also tracks each symbol's confidence trend and, when it is climbing
    toward MIN_CONFIDENCE, sends an early "heads up" alert roughly
    EARLY_WARNING_LEAD_SECONDS (default 5 minutes) before the confirmed
    signal is projected to fire.
    """

    def __init__(self, symbols=None, poll_seconds=None, notifier=None):
        self.symbols = symbols or self._get_symbols_from_env()
        self.poll_seconds = poll_seconds or int(os.getenv("REALTIME_POLL_SECONDS", "20"))
        self.early_warning_enabled = os.getenv("EARLY_WARNING_ENABLED", "true").lower() == "true"
        self.early_warning_lead_seconds = int(os.getenv("EARLY_WARNING_LEAD_SECONDS", "300"))

        self.downloader = NSEDownloader()
        self.fe = FeatureEngineer()
        self.signal_engine = SignalEngine()
        self.risk_manager = RiskManager()
        self.notifier = notifier or TelegramNotifier()

        # Tracks the last alerted (signal, symbol) pair to avoid repeat spam.
        self._last_alerted = {}
        self._last_early_warned = {}
        # Rolling (timestamp, confidence) history per symbol/signal for trend projection.
        self._confidence_history = defaultdict(lambda: deque(maxlen=30))
        self._running = False
        self.last_status = {}

    @staticmethod
    def _get_symbols_from_env():
        raw = os.getenv("REALTIME_SYMBOLS", "NIFTY 50,BANKNIFTY,SENSEX")
        return [s.strip() for s in raw.split(",") if s.strip()]

    def _build_feature_frame(self, symbol):
        df = self.downloader.download_index_data(
            symbol, start_date=(pd.Timestamp.now() - pd.Timedelta(days=100)).strftime("%Y-%m-%d")
        )
        if df is None or df.empty:
            return None
        return self.fe.add_technical_indicators(df)

    def _project_lead_seconds(self, symbol, signal, confidence):
        """
        Fits a linear trend to recent confidence readings for this symbol's
        current signal direction and returns the estimated number of seconds
        until it is projected to cross MIN_CONFIDENCE (None if it isn't
        trending upward toward the threshold).
        """
        history = self._confidence_history[symbol]
        now = time.time()
        history.append((now, signal, confidence))

        # Only use recent points that share the current signal direction.
        window_seconds = self.early_warning_lead_seconds * 3
        points = [(t, c) for t, s, c in history if s == signal and (now - t) <= window_seconds]

        if len(points) < 3:
            return None

        times = np.array([p[0] for p in points])
        confidences = np.array([p[1] for p in points])

        slope, intercept = np.polyfit(times, confidences, 1)
        if slope <= 0:
            return None

        min_confidence = self.signal_engine.min_confidence
        projected_cross_time = (min_confidence - intercept) / slope
        lead_seconds = projected_cross_time - now

        if 0 < lead_seconds <= self.early_warning_lead_seconds:
            return lead_seconds
        return None

    async def evaluate_symbol(self, symbol):
        try:
            df_features = await asyncio.to_thread(self._build_feature_frame, symbol)
            if df_features is None:
                return None

            feature_cols = [c for c in df_features.columns if c not in NON_FEATURE_COLUMNS]
            result = self.signal_engine.generate_signal(df_features, feature_cols, symbol=symbol)

            current_price = float(df_features["Close"].iloc[-1])
            atr = float(df_features["ATR"].iloc[-1])
            stop_loss, target = self.risk_manager.calculate_levels(current_price, atr, side=result["signal"])
            option = select_option_strike(symbol, current_price, side=result["signal"])

            result.update({
                "price": current_price,
                "stop_loss": stop_loss,
                "target": target,
                "option": option,
                "timestamp": pd.Timestamp.now().isoformat(),
            })

            self.last_status[symbol] = result

            if result["is_high_conviction"]:
                dedup_key = (symbol, result["signal"])
                if self._last_alerted.get(symbol) != dedup_key:
                    message = self.notifier.format_signal_message(result)
                    # Fire-and-forget dispatch keeps the poll loop from
                    # blocking on network I/O, minimizing end-to-end delay.
                    asyncio.create_task(self.notifier.send_async(message))
                    self._last_alerted[symbol] = dedup_key
                    self._last_early_warned.pop(symbol, None)
                    logger.info(f"High-conviction {result['signal']} alert dispatched for {symbol}")
            else:
                # Signal dropped below threshold; allow a future re-alert.
                self._last_alerted.pop(symbol, None)

                if self.early_warning_enabled:
                    lead_seconds = self._project_lead_seconds(symbol, result["signal"], result["confidence"])
                    dedup_key = (symbol, result["signal"])
                    if lead_seconds is not None and self._last_early_warned.get(symbol) != dedup_key:
                        message = self.notifier.format_early_warning_message(result, lead_seconds)
                        asyncio.create_task(self.notifier.send_async(message))
                        self._last_early_warned[symbol] = dedup_key
                        logger.info(
                            f"Early warning dispatched for {symbol} "
                            f"(~{lead_seconds / 60:.1f} min ahead of {result['signal']} signal)"
                        )
                    elif lead_seconds is None:
                        # Trend faded; allow a fresh early warning if it resumes.
                        self._last_early_warned.pop(symbol, None)

            return result
        except Exception as e:
            logger.error(f"Error evaluating {symbol}: {e}")
            return None

    async def run_forever(self):
        self._running = True
        while self._running:
            is_open, _ = is_market_open()
            if is_open:
                await asyncio.gather(*(self.evaluate_symbol(sym) for sym in self.symbols))
            await asyncio.sleep(self.poll_seconds)

    def stop(self):
        self._running = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = RealtimeSignalEngine()
    asyncio.run(engine.run_forever())

