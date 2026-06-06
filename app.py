"""
TABCRYPT backend
Flask + SQLite tab vault. Relevance-scored search. CORS enabled.
Single file on purpose: easy to edit from mobile / GitHub, easy to deploy on Railway.

Env vars (all optional):
  PORT      port to bind (Railway sets this automatically)         default 8000
  DB_PATH   path to the sqlite file                                default tabcrypt.db
  API_KEY   if set, POST/DELETE require header  X-API-Key: <key>   default unset (open)

Endpoints:
  GET    /api/health
  GET    /api/search?q=<text>&filter=all|song|artist|album|tuning|instrument
  GET    /api/tab/<id>
  POST   /api/tab            JSON body -> creates, returns {"id": ...}
  DELETE /api/tab/<id>
"""

import os
import time
import sqlite3
from flask import Flask, request, jsonify, g

DB_PATH = os.environ.get("DB_PATH", "tabcrypt.db")
API_KEY = os.environ.get("API_KEY")  # if set, required for writes

app = Flask(__name__)

# ---- fields each filter searches against -------------------------------------
FILTER_FIELDS = {
    "all": ["title", "artist", "album", "tuning", "instrument"],
    "song": ["title"],
    "artist": ["artist"],
    "album": ["album"],
    "tuning": ["tuning"],
    "instrument": ["instrument"],
}

# ---- original demo content (NOT a copyrighted transcription) -----------------
DEMO_CONTENT = """DROP A  ( A  E  A  D  F#  B )   .   ~150 BPM   .   ORIGINAL DEMO RIFF

  B|---------------------------------------|
 F#|---------------------------------------|
  D|---------------------------------------|
  A|------------------5--5-----------------|
  E|---------7--7----------------7--7-------|
  A|--0-0-0--------0-0--------0-0-----------|
     P.M.--------------------------------- |

  ( repeat x4 )  ->  breakdown: open A chugs, palm muted

  A|--0-0-0-0--0-0-0-0--0--0----0-0-0-0-0--|
     P.M.--------------------------------- |
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS tabs (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    artist      TEXT DEFAULT '',
    album       TEXT DEFAULT '',
    tuning      TEXT DEFAULT '',
    instrument  TEXT DEFAULT '',
    difficulty  TEXT DEFAULT '',
    content     TEXT NOT NULL,
    source      TEXT DEFAULT '',
    created     REAL
);
"""

COLS = ["id", "title", "artist", "album", "tuning",
        "instrument", "difficulty", "content", "source", "created"]


# ---- db plumbing -------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    try:
        # Ensure directory exists
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        db = sqlite3.connect(DB_PATH)
        db.executescript(SCHEMA)
        count = db.execute("SELECT COUNT(*) FROM tabs").fetchone()[0]
        if count == 0:
            db.execute(
                "INSERT INTO tabs (id,title,artist,album,tuning,instrument,difficulty,content,source,created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("demo-1", "Untitled Crawl", "Original / Demo", "-", "Drop A",
                 "Guitar (6-string)", "Intermediate", DEMO_CONTENT, "self", time.time()),
            )
        db.commit()
        db.close()
        print(f"✓ Database initialized at {DB_PATH}")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        # Don't crash - Railway workers will keep retrying


# ---- search scoring (validated: exact 100 / prefix 70 / contains 40) ---------
def score_row(row, q, filt):
    fields = FILTER_FIELDS.get(filt, FILTER_FIELDS["all"])
    best = 0
    for f in fields:
        v = (row[f] or "").lower()
        if not v:
            continue
        if v == q:
            best = max(best, 100)
        elif v.startswith(q):
            best = max(best, 70)
        elif q in v:
            best = max(best, 40)
    return best


# ---- CORS so the frontend artifact / site can call this ----------------------
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return resp


def authorized():
    return (not API_KEY) or (request.headers.get("X-API-Key") == API_KEY)


# ---- routes ------------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify(status="ok", db=DB_PATH)


@app.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    filt = request.args.get("filter", "all")
    if filt not in FILTER_FIELDS:
        filt = "all"

    db = get_db()
    rows = db.execute(
        "SELECT id,title,artist,album,tuning,instrument,difficulty FROM tabs"
    ).fetchall()

    scored = []
    for r in rows:
        s = 1 if not q else score_row(r, q, filt)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: (-x[0], (x[1]["title"] or "").lower()))

    results = [dict(r) for _, r in scored]
    return jsonify(results=results, count=len(results))


@app.route("/api/tab/<tab_id>")
def get_tab(tab_id):
    db = get_db()
    r = db.execute("SELECT * FROM tabs WHERE id=?", (tab_id,)).fetchone()
    if not r:
        return jsonify(error="not found"), 404
    return jsonify(dict(r))


@app.route("/api/tab", methods=["POST", "OPTIONS"])
def add_tab():
    if request.method == "OPTIONS":
        return ("", 204)
    if not authorized():
        return jsonify(error="unauthorized"), 401

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not title or not content:
        return jsonify(error="title and content are required"), 400

    tab_id = "t-" + str(int(time.time() * 1000))
    db = get_db()
    db.execute(
        "INSERT INTO tabs (id,title,artist,album,tuning,instrument,difficulty,content,source,created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            tab_id,
            title,
            (data.get("artist") or "").strip(),
            (data.get("album") or "").strip(),
            (data.get("tuning") or "").strip(),
            (data.get("instrument") or "").strip(),
            (data.get("difficulty") or "").strip(),
            content,
            (data.get("source") or "user").strip(),
            time.time(),
        ),
    )
    db.commit()
    return jsonify(id=tab_id), 201


@app.route("/api/tab/<tab_id>", methods=["DELETE", "OPTIONS"])
def delete_tab(tab_id):
    if request.method == "OPTIONS":
        return ("", 204)
    if not authorized():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    db.execute("DELETE FROM tabs WHERE id=?", (tab_id,))
    db.commit()
    return jsonify(deleted=tab_id)


# build the table + seed at import time (works under gunicorn too)
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
