import sqlite3
from config import DB_PATH

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            url         TEXT UNIQUE,        -- dedup key
            source      TEXT,               -- linkedin / naukri / etc
            score       INTEGER,            -- LLM score out of 10
            score_reason TEXT,
            status      TEXT DEFAULT 'seen',
            -- seen | approved | rejected | applied | messaged
            found_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            applied_at  TIMESTAMP,
            notes       TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            key     TEXT PRIMARY KEY,
            value   TEXT,
            updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # agent_memory stores things like:
    # "last_run_date", "total_applied", "preferred_domains", etc.
    # The agent can read/write this freely.

    conn.commit()
    conn.close()
    print("[DB] Initialized.")

def job_exists(url: str) -> bool:
    """Check if we've already seen this job."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def insert_job(job: dict):
    """Insert a new job. Silently skip if URL already exists."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO jobs (title, company, location, url, source, score, score_reason)
            VALUES (:title, :company, :location, :url, :source, :score, :score_reason)
        """, job)
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # duplicate URL, skip
    finally:
        conn.close()

def update_job_status(url: str, status: str, notes: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE jobs SET status = ?, notes = ? WHERE url = ?",
        (status, notes, url)
    )
    conn.commit()
    conn.close()

def get_jobs_by_status(status: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE status = ?", (status,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def set_memory(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO agent_memory (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated = CURRENT_TIMESTAMP
    """, (key, value))
    conn.commit()
    conn.close()

def get_memory(key: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM agent_memory WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None