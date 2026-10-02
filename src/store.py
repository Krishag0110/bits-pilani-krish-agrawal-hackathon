"""Small persistent SQLite store for signals, scenarios, and source health."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


DEFAULT_ENDPOINTS = {
    "news": "https://api.gdeltproject.org/api/v2/doc/doc",
    "social": "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
}


def _initial_status(source):
    return {
        "state": "idle",
        "last_attempt_at": None,
        "last_success_at": None,
        "fetched": 0,
        "added": 0,
        "error": "",
        "endpoint": DEFAULT_ENDPOINTS[source],
    }


class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=8.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    impact_score INTEGER NOT NULL,
                    ingested_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
                    triggered_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS source_status (
                    source TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_signals_ingested ON signals(ingested_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_triggered ON runs(triggered_at)")
            for source in DEFAULT_ENDPOINTS:
                connection.execute(
                    "INSERT OR IGNORE INTO source_status(source,payload) VALUES (?,?)",
                    (source, json.dumps(_initial_status(source))),
                )

    def has_signals(self):
        with self._connection() as connection:
            return bool(connection.execute("SELECT 1 FROM signals LIMIT 1").fetchone())

    def reset(self):
        with self._connection() as connection:
            connection.execute("DELETE FROM runs")
            connection.execute("DELETE FROM signals")
            for source in DEFAULT_ENDPOINTS:
                connection.execute(
                    "INSERT OR REPLACE INTO source_status(source,payload) VALUES (?,?)",
                    (source, json.dumps(_initial_status(source))),
                )

    def insert_signal(self, signal, fingerprint):
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO signals
                (id,fingerprint,source,provenance,impact_score,ingested_at,payload)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    signal["id"], fingerprint, signal["source"], signal["provenance"],
                    signal["impact_score"], signal["ingested_at"],
                    json.dumps(signal, ensure_ascii=False),
                ),
            )
            if cursor.rowcount:
                return signal, True
            row = connection.execute(
                "SELECT payload FROM signals WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if not row:
                raise RuntimeError("Signal id collision")
            return json.loads(row["payload"]), False

    def get_signal(self, signal_id):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM signals WHERE id = ?", (signal_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_signals(self, limit=100):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM signals ORDER BY ingested_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def insert_run(self, run):
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO runs(id,signal_id,triggered_at,payload) VALUES (?,?,?,?)",
                (run["id"], run["signal_id"], run["triggered_at"], json.dumps(run, ensure_ascii=False)),
            )

    def list_runs(self, limit=30):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs ORDER BY triggered_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def latest_run_for_signal(self, signal_id):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE signal_id = ? ORDER BY triggered_at DESC, rowid DESC LIMIT 1",
                (signal_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def source_status(self):
        with self._connection() as connection:
            rows = connection.execute("SELECT source,payload FROM source_status").fetchall()
        return {row["source"]: json.loads(row["payload"]) for row in rows}

    def update_source_status(self, source, state, attempted_at, fetched, added, error="", endpoint=""):
        statuses = self.source_status()
        status = statuses.get(source, _initial_status(source))
        status.update({
            "state": state,
            "last_attempt_at": attempted_at,
            "fetched": int(fetched),
            "added": int(added),
            "error": str(error)[:500],
            "endpoint": endpoint or status["endpoint"],
        })
        if state in {"ok", "degraded"}:
            status["last_success_at"] = attempted_at
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO source_status(source,payload) VALUES (?,?)",
                (source, json.dumps(status, ensure_ascii=False)),
            )
        return status

    def counts(self):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT provenance, COUNT(*) AS n FROM signals GROUP BY provenance"
            ).fetchall()
            high = connection.execute(
                "SELECT COUNT(*) AS n FROM signals WHERE impact_score > 7"
            ).fetchone()["n"]
        by_provenance = {row["provenance"]: row["n"] for row in rows}
        return {
            "total_signals": sum(by_provenance.values()),
            "live_signals": by_provenance.get("live", 0),
            "demo_signals": by_provenance.get("demo", 0),
            "manual_signals": by_provenance.get("manual", 0),
            "high_impact_signals": high,
        }
