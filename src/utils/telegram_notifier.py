import logging
import os

import httpx

logger = logging.getLogger("TelegramNotifier")

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    """
    Sends alerts directly to the Telegram Bot API (no intermediate hop),
    minimizing delivery latency for time-sensitive trade signals.
    """

    def __init__(self, bot_token=None, chat_id=None, timeout_seconds=5.0):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    def is_configured(self):
        return bool(self.bot_token and self.chat_id)

    @staticmethod
    def format_signal_message(signal):
        confidence_pct = signal["confidence"] * 100
        option = signal.get("option")
        lines = [
            f"🚨 {signal['symbol']} {signal['signal']} SIGNAL ({confidence_pct:.1f}% confidence)",
            "",
            f"Entry Price: {signal['price']:.2f}",
        ]
        if option:
            lines.append(f"Option: {option['contract']}")
        lines += [
            f"Stop Loss: {signal['stop_loss']}",
            f"Target: {signal['target']}",
            "",
            f"Model confidence: {signal['model_confidence'] * 100:.1f}%",
            f"Technical agreement: {signal['technical_agreement'] * 100:.1f}%",
            f"News sentiment alignment: {signal['sentiment_alignment'] * 100:.1f}%",
            "",
            "⚠️ Educational signal only. Not investment advice. Trade at your own risk.",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_early_warning_message(signal, lead_seconds):
        confidence_pct = signal["confidence"] * 100
        min_confidence_pct = float(os.getenv("MIN_CONFIDENCE", "0.80")) * 100
        minutes_ahead = lead_seconds / 60
        option = signal.get("option")
        lines = [
            f"⏳ {signal['symbol']} {signal['signal']} building (~{minutes_ahead:.1f} min ahead)",
            "",
            f"Current confidence: {confidence_pct:.1f}% (confirms at {min_confidence_pct:.0f}%)",
            f"Index price: {signal['price']:.2f}",
        ]
        if option:
            lines.append(f"Watching: {option['contract']}")
        lines += [
            "",
            "This is an early heads-up, not a confirmed signal. A follow-up alert "
            "will fire if it crosses the confidence threshold.",
            "⚠️ Educational signal only. Not investment advice.",
        ]
        return "\n".join(lines)

    async def send_async(self, message):
        if not self.is_configured():
            logger.warning("Telegram is not configured; skipping alert dispatch.")
            return {"status": "error", "message": "Telegram not configured"}

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }

        try:
            response = await self._client.post(url, json=payload)
            if response.status_code == 200:
                return {"status": "sent"}
            logger.error(f"Telegram send failed: {response.status_code} {response.text}")
            return {"status": "error", "message": response.text}
        except Exception as e:
            logger.error(f"Telegram send exception: {e}")
            return {"status": "error", "message": str(e)}

    async def aclose(self):
        await self._client.aclose()
