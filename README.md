# TabCrypt — backend

Flask + SQLite API for the TabCrypt guitar app. Relevance-scored tab search, CORS enabled.

## Endpoints
- `GET /api/health` — status check
- `GET /api/search?q=<text>&filter=all|song|artist|album|tuning|instrument`
- `GET /api/tab/<id>` — full tab incl. content
- `POST /api/tab` — JSON body, creates a tab
- `DELETE /api/tab/<id>` — removes a tab

## Deploy (Railway)
Deploy from this repo. Railway auto-installs `requirements.txt` and starts via the `Procfile`.

## Env vars (optional)
- `API_KEY` — if set, POST/DELETE require header `X-API-Key`
- `DB_PATH` — sqlite file path; point at a Railway volume to persist data across redeploys

## Run locally
    pip install -r requirements.txt
    python app.py

