import os
import time
from collections import OrderedDict
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from textblob import TextBlob


HF_MODEL_NAME = os.getenv(
    "HF_SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest"
)
HF_API_URL = os.getenv(
    "HF_SENTIMENT_API_URL",
    f"https://router.huggingface.co/hf-inference/models/{HF_MODEL_NAME}",
)

_CACHE_MAX_SIZE = int(os.getenv("SENTIMENT_CACHE_SIZE", "256"))
_CACHE_TTL_SECONDS = int(os.getenv("SENTIMENT_CACHE_TTL_SECONDS", "1800"))
_inference_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


def classify_sentiment(text: str) -> dict:
    """
    Analyze text with a stronger transformer model (Hugging Face Inference API),
    with automatic fallback to TextBlob for reliability.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return _neutral_response(provider="none", model="none")

    cached = _cache_get(cleaned)
    if cached:
        cached_copy = dict(cached)
        cached_copy["from_cache"] = True
        return cached_copy

    provider = os.getenv("SENTIMENT_PROVIDER", "auto").lower()
    use_hf = provider in {"auto", "hf", "huggingface"}

    if use_hf:
        hf_result = _classify_with_hf(cleaned)
        if hf_result:
            _cache_set(cleaned, hf_result)
            return hf_result

    fallback = _classify_with_textblob(cleaned)
    _cache_set(cleaned, fallback)
    return fallback


def _classify_with_hf(text: str) -> Optional[dict]:
    if requests is None:
        return None

    token = os.getenv("HF_API_TOKEN", "").strip()
    if not token:
        return None

    timeout_seconds = float(os.getenv("HF_API_TIMEOUT", "8"))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"inputs": text, "options": {"wait_for_model": True}}

    max_retries = int(os.getenv("HF_API_MAX_RETRIES", "3"))
    backoff_seconds = float(os.getenv("HF_API_RETRY_BACKOFF", "0.55"))
    raw = None
    for attempt in range(max_retries):
        try:
            response = requests.post(
                HF_API_URL, headers=headers, json=payload, timeout=timeout_seconds
            )
            if response.status_code == 200:
                raw = response.json()
                break
            # Retry transient statuses only.
            if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries - 1:
                time.sleep(backoff_seconds * (2**attempt))
                continue
            return None
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(backoff_seconds * (2**attempt))
                continue
            return None

    if raw is None:
        return None

    scores = _extract_score_list(raw)
    if not scores:
        return None

    best = max(scores, key=lambda item: item.get("score", 0.0))
    best_label = _normalize_label(best.get("label", "neutral"))
    confidence = round(float(best.get("score", 0.0)), 2)
    polarity = _label_to_polarity(best_label, confidence)

    neutral_score = _score_for_label(scores, "neutral")
    subjectivity = round(max(0.05, min(0.95, 1.0 - neutral_score)), 3)

    return {
        "polarity": round(polarity, 3),
        "subjectivity": subjectivity,
        "label": best_label.title(),
        "confidence": max(0.5, confidence),
        "provider": "huggingface",
        "model": HF_MODEL_NAME,
        "from_cache": False,
    }


def _classify_with_textblob(text: str) -> dict:
    blob = TextBlob(text)
    polarity = round(blob.sentiment.polarity, 3)
    subjectivity = round(blob.sentiment.subjectivity, 3)

    if polarity > 0.1:
        label = "Positive"
    elif polarity < -0.1:
        label = "Negative"
    else:
        label = "Neutral"

    confidence = round(min(0.99, max(0.5, abs(polarity) + 0.5)), 2)

    return {
        "polarity": polarity,
        "subjectivity": subjectivity,
        "label": label,
        "confidence": confidence,
        "provider": "textblob",
        "model": "textblob-default",
        "from_cache": False,
    }


def _extract_score_list(raw_response) -> list[dict]:
    if isinstance(raw_response, list):
        if raw_response and isinstance(raw_response[0], list):
            return [item for item in raw_response[0] if isinstance(item, dict)]
        return [item for item in raw_response if isinstance(item, dict)]
    return []


def _normalize_label(raw_label: str) -> str:
    label = (raw_label or "").strip().lower()
    if label in {"positive", "pos", "label_2", "label_1"}:
        return "positive"
    if label in {"negative", "neg", "label_0"}:
        return "negative"
    return "neutral"


def _label_to_polarity(label: str, confidence: float) -> float:
    if label == "positive":
        return max(0.2, confidence)
    if label == "negative":
        return -max(0.2, confidence)
    return 0.0


def _score_for_label(scores: list[dict], target_label: str) -> float:
    normalized_target = _normalize_label(target_label)
    for item in scores:
        if _normalize_label(item.get("label", "")) == normalized_target:
            return float(item.get("score", 0.0))
    return 0.35


def _neutral_response(provider: str, model: str) -> dict:
    return {
        "polarity": 0.0,
        "subjectivity": 0.0,
        "label": "Neutral",
        "confidence": 0.5,
        "provider": provider,
        "model": model,
        "from_cache": False,
    }


def _cache_get(text: str) -> Optional[dict]:
    key = _cache_key(text)
    found = _inference_cache.get(key)
    if not found:
        return None
    ts, payload = found
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _inference_cache.pop(key, None)
        return None
    _inference_cache.move_to_end(key)
    return dict(payload)


def _cache_set(text: str, payload: dict) -> None:
    key = _cache_key(text)
    _inference_cache[key] = (time.time(), dict(payload))
    _inference_cache.move_to_end(key)
    while len(_inference_cache) > _CACHE_MAX_SIZE:
        _inference_cache.popitem(last=False)


def _cache_key(text: str) -> str:
    return " ".join(text.lower().split())
