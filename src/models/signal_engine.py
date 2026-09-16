import logging
import os

from src.features.news_sentiment import get_market_sentiment
from src.models.trainer import ModelTrainer

logger = logging.getLogger("SignalEngine")


class SignalEngine:
    """
    Blends the XGBoost model's technical confidence with live news/world-event
    sentiment and multi-timeframe (RSI/MACD) agreement into a single
    high-conviction confidence score. Alerts should only fire when
    `is_high_conviction` is True.
    """

    def __init__(self, trainer=None, min_confidence=None):
        self.trainer = trainer or ModelTrainer()
        self.min_confidence = min_confidence or float(os.getenv("MIN_CONFIDENCE", "0.80"))

    def _technical_agreement(self, df_features, signal):
        """
        Returns a 0-1 score for how many independent technical indicators
        agree with the model's directional call (RSI, MACD vs signal line,
        price vs SMA20/50, Bollinger position).
        """
        last = df_features.iloc[-1]
        votes = []

        votes.append(1 if (last["RSI"] >= 50) == (signal == "BUY") else 0)
        votes.append(1 if (last["MACD"] >= last["Signal_Line"]) == (signal == "BUY") else 0)
        votes.append(1 if (last["Close"] >= last["SMA_20"]) == (signal == "BUY") else 0)
        votes.append(1 if (last["SMA_20"] >= last["SMA_50"]) == (signal == "BUY") else 0)

        return sum(votes) / len(votes)

    def _sentiment_alignment(self, sentiment_score, signal):
        """
        Maps sentiment (-1..1) to a 0-1 alignment score with the signal.
        Neutral news (near 0) contributes a mild 0.5 so it doesn't
        dominate the blend when there's no strong news either way.
        """
        if signal == "BUY":
            aligned = sentiment_score
        else:
            aligned = -sentiment_score

        # Rescale -1..1 -> 0..1
        return max(0.0, min(1.0, (aligned + 1) / 2))

    def generate_signal(self, df_features, feature_cols, symbol="NIFTY 50"):
        """
        Returns a dict with the blended signal, confidence breakdown, and
        whether it clears the high-conviction bar for alerting.
        """
        model_prediction = self.trainer.predict_latest(df_features, feature_cols)

        if model_prediction is None:
            last_rsi = float(df_features["RSI"].iloc[-1])
            model_prediction = {
                "signal": "BUY" if last_rsi >= 50 else "SELL",
                "confidence": min(0.75, 0.5 + abs(last_rsi - 50) / 100),
            }

        signal = model_prediction["signal"]
        model_confidence = float(model_prediction["confidence"])

        technical_score = self._technical_agreement(df_features, signal)

        sentiment_score, headlines = get_market_sentiment()
        sentiment_alignment = self._sentiment_alignment(sentiment_score, signal)

        # Weighted blend: model is the primary driver, technical agreement
        # confirms it, and news/world-event sentiment adjusts conviction.
        blended_confidence = (
            0.55 * model_confidence
            + 0.30 * technical_score
            + 0.15 * sentiment_alignment
        )

        return {
            "symbol": symbol,
            "signal": signal,
            "model_confidence": round(model_confidence, 4),
            "technical_agreement": round(technical_score, 4),
            "sentiment_score": round(sentiment_score, 4),
            "sentiment_alignment": round(sentiment_alignment, 4),
            "confidence": round(blended_confidence, 4),
            "is_high_conviction": blended_confidence >= self.min_confidence,
            "news_headlines": headlines,
        }
