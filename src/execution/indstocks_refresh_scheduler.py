import asyncio
import logging
import os

logger = logging.getLogger("IndstocksRefreshScheduler")

DEFAULT_SEGMENTS = ["equity", "fno", "index"]


class IndstocksRefreshScheduler:
    """
    Periodically re-fetches the Indstocks instrument master from the web so
    the symbol -> security_id cache doesn't go stale. Runs on a fixed
    interval (default: every 24 hours) as a background asyncio task.
    """

    def __init__(self, gateway, interval_hours=None, segments=None):
        self.gateway = gateway
        self.interval_hours = interval_hours or float(os.getenv("INDSTOCKS_REFRESH_HOURS", "24"))
        self.segments = segments or self._get_segments_from_env()
        self._running = False

    @staticmethod
    def _get_segments_from_env():
        raw = os.getenv("INDSTOCKS_REFRESH_SEGMENTS")
        if raw:
            return [s.strip() for s in raw.split(",") if s.strip()]
        return DEFAULT_SEGMENTS

    async def refresh_now(self):
        for segment in self.segments:
            await asyncio.to_thread(self.gateway.fetch_instruments, segment)

    async def run_forever(self):
        self._running = True
        # Fetch once at startup so the cache is warm immediately.
        await self.refresh_now()
        while self._running:
            await asyncio.sleep(self.interval_hours * 3600)
            if not self._running:
                break
            logger.info("Refreshing Indstocks instrument master from the web.")
            await self.refresh_now()

    def stop(self):
        self._running = False
