"""
Lightweight SQLite visit logger.
Records per-request data: timestamp, path, anonymized IP, user agent.
"""

import hashlib
import os
import sqlite3
import threading
from datetime import date, timedelta

import config

_DB_PATH = config.ANALYTICS_DB
_lock = threading.Lock()

os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS visits ("
        "  id        INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  ts        TEXT NOT NULL,"
        "  path      TEXT NOT NULL,"
        "  ip_hash   TEXT,"
        "  user_agent TEXT"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits (ts)")
    conn.commit()
    return conn


def _hash_ip(ip):
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def record_visit(path, ip, user_agent):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO visits (ts, path, ip_hash, user_agent) VALUES (?, ?, ?, ?)",
                (ts, path, _hash_ip(ip), user_agent or None),
            )
            conn.commit()
        finally:
            conn.close()


def get_stats(days=30):
    """
    Return summary stats for the last `days` days:
      - daily: list of {date, visits, unique_visitors} oldest-first
      - top_paths: list of {path, visits} sorted by visits desc
      - top_agents: list of {user_agent, visits} sorted by visits desc
    """
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _lock:
        conn = _connect()
        try:
            daily = conn.execute(
                "SELECT substr(ts, 1, 10) AS day,"
                "       COUNT(*) AS visits,"
                "       COUNT(DISTINCT ip_hash) AS unique_visitors"
                " FROM visits WHERE ts >= ?"
                " GROUP BY day ORDER BY day",
                (start,),
            ).fetchall()

            top_paths = conn.execute(
                "SELECT path, COUNT(*) AS visits"
                " FROM visits WHERE ts >= ?"
                " GROUP BY path ORDER BY visits DESC LIMIT 20",
                (start,),
            ).fetchall()

            top_agents = conn.execute(
                "SELECT user_agent, COUNT(*) AS visits"
                " FROM visits WHERE ts >= ?"
                " GROUP BY user_agent ORDER BY visits DESC LIMIT 10",
                (start,),
            ).fetchall()
        finally:
            conn.close()

    return {
        "daily": [dict(r) for r in daily],
        "top_paths": [dict(r) for r in top_paths],
        "top_agents": [dict(r) for r in top_agents],
    }
