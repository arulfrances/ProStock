import logging
import os
import time

logger = logging.getLogger("NewsSentiment")

DEFAULT_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/business.xml",
]

# Keeps repeated calls cheap during a fast polling loop.
_CACHE_TTL_SECONDS = 120
_cache = {"timestamp": 0.0, "score": 0.0, "headlines": []}


def _get_feed_urls():
    raw = os.getenv("NEWS_FEED_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return DEFAULT_FEEDS


def _fetch_headlines(feed_urls, limit_per_feed=15, timeout=5):
    headlines = []
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser is not installed; skipping news sentiment.")
        return headlines

    for url in feed_urls:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:limit_per_feed]:
                title = getattr(entry, "title", None)
                if title:
                    headlines.append(title)
        except Exception as e:
            logger.warning(f"Failed to fetch news feed {url}: {e}")
    return headlines


def _score_headlines(headlines):
    """
    Returns a sentiment score in [-1, 1] using VADER when available,
    falling back to a small finance keyword lexicon otherwise.
    """
    if not headlines:
        return 0.0

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        analyzer = SentimentIntensityAnalyzer()
        scores = [analyzer.polarity_scores(h)["compound"] for h in headlines]
        return sum(scores) / len(scores)
    except ImportError:
        pass

    positive_words = {
        "rally", "surge", "gain", "gains", "bullish", "upgrade", "upgraded", "beats",
        "record high", "rebound", "rises", "growth", "outperform", "strong", "positive",
    }
    negative_words = {
        "crash", "plunge", "selloff", "sell-off", "bearish", "downgrade", "downgraded",
        "misses", "record low", "slump", "falls", "recession", "underperform", "weak",
        "negative", "war", "conflict", "sanctions",
    }

    total = 0.0
    for headline in headlines:
        text = headline.lower()
        pos_hits = sum(1 for w in positive_words if w in text)
        neg_hits = sum(1 for w in negative_words if w in text)
        if pos_hits or neg_hits:
            total += (pos_hits - neg_hits) / max(pos_hits + neg_hits, 1)

    return max(-1.0, min(1.0, total / len(headlines)))


def get_market_sentiment(force_refresh=False):
    """
    Returns a cached (score, headlines) tuple summarizing recent market/world
    news sentiment. Score ranges from -1 (very bearish) to +1 (very bullish).
    """
    now = time.time()
    if not force_refresh and (now - _cache["timestamp"]) < _CACHE_TTL_SECONDS:
        return _cache["score"], _cache["headlines"]

    headlines = _fetch_headlines(_get_feed_urls())
    score = _score_headlines(headlines)

    _cache["timestamp"] = now
    _cache["score"] = score
    _cache["headlines"] = headlines[:10]

    return score, _cache["headlines"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s, h = get_market_sentiment(force_refresh=True)
    print(f"Sentiment score: {s:.3f}")
    for headline in h:
        print(f" - {headline}")
