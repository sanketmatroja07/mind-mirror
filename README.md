# Mind Mirror — Check In. Reflect. Grow.

Capstone-style app built with Flask + TextBlob.  
Users can write daily entries, get sentiment classification, and view emotional trends over time.

## Features
- Web UI for daily journal input
- Sentiment analysis with transformer upgrade path (Hugging Face) + TextBlob fallback
- SQLite-based entry timeline
- Emotional summary dashboard
- User authentication (register/login/logout)
- Multi-user data isolation
- CLI mode for add/list entries
- Search + sentiment filters
- Delete with confirmation
- CSV export

## Setup
```bash
cd "/Users/sanket/ai-journal-app"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m textblob.download_corpora
```

## Optional: Stronger AI Model (Hugging Face)

By default, sentiment works via TextBlob fallback.  
To enable transformer-based inference:

```bash
export SENTIMENT_PROVIDER=hf
export HF_API_TOKEN="your_huggingface_token"
# optional
export HF_SENTIMENT_MODEL="cardiffnlp/twitter-roberta-base-sentiment-latest"
export HF_API_MAX_RETRIES=3
export HF_API_RETRY_BACKOFF=0.55
export SENTIMENT_CACHE_TTL_SECONDS=1800
export SENTIMENT_CACHE_SIZE=256
```

If API is unavailable, the app automatically falls back to TextBlob so journaling never breaks.
Entry metadata also stores provider/model used (Hugging Face vs TextBlob).

## Run Web App
```bash
python3 app.py
```
Open: `http://127.0.0.1:5000`

## Run CLI
```bash
python3 cli.py add "Today was challenging but productive."
python3 cli.py list
```
