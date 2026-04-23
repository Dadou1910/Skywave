import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Database path ─────────────────────────────────────────────────────────────
# Stored next to the project folder, not inside it, so it survives code
# updates and git cleans. ~/skywave_data/skywave.db
DB_DIR  = Path.home() / "skywave_data"
DB_PATH = DB_DIR / "skywave.db"


# ── Schema ────────────────────────────────────────────────────────────────────
#
# sessions          — one row per recording session (start → stop)
# readings          — one row per second of EEG data, foreign-keyed to session
# training_sessions — one row per training session, references a sessions row
# training_events   — timestamped in/out events for the target state
#
# Design notes:
#   - All timestamps are ISO-8601 strings (UTC). Simple, portable, readable.
#   - readings stores the 5 normalised scores (0–100) + raw blink strength.
#   - We store normalised scores, not raw ratios, because the normalised
#     values are what's meaningful for long-term trend analysis.
#   - Foreign keys are enabled per-connection (SQLite requires this explicitly).

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    source_name TEXT    NOT NULL,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    recorded_at TEXT    NOT NULL,
    focus       REAL,
    relax       REAL,
    stress      REAL,
    flow        REAL,
    fatigue     REAL,
    blink       INTEGER
);

CREATE TABLE IF NOT EXISTS training_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    target_metric   TEXT    NOT NULL,
    target_threshold REAL   NOT NULL,
    started_at      TEXT    NOT NULL,
    ended_at        TEXT,
    -- total seconds spent above threshold during this training session
    seconds_on_target INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS training_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    event_type          TEXT    NOT NULL,  -- 'enter' or 'exit'
    recorded_at         TEXT    NOT NULL,
    score_at_event      REAL
);

CREATE INDEX IF NOT EXISTS idx_readings_session ON readings(session_id);
CREATE INDEX IF NOT EXISTS idx_readings_time    ON readings(recorded_at);
"""


# ── Database ──────────────────────────────────────────────────────────────────
class Database:
    """
    Thread-safe SQLite interface.

    SQLite connections cannot be shared across threads, so we use
    threading.local() to give each thread its own connection.
    All public methods can be called from any thread safely.
    """

    def __init__(self, path: Path = DB_PATH):
        self._path   = path
        self._local  = threading.local()
        DB_DIR.mkdir(parents=True, exist_ok=True)
        # Initialise schema on the main thread
        self._execute(SCHEMA, script=True)
        # Migration: add note column to training_sessions if missing
        try:
            self._execute("ALTER TABLE training_sessions ADD COLUMN note TEXT")
        except sqlite3.OperationalError:
            pass

    # ── Connection management ─────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Return this thread's connection, creating it if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return self._local.conn

    def _execute(self, sql: str, params=(), script=False):
        conn = self._conn()
        if script:
            conn.executescript(sql)
        else:
            conn.execute(sql, params)
            conn.commit()

    def _query(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self._conn().execute(sql, params).fetchall()

    def _query_one(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        return self._conn().execute(sql, params).fetchone()

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_users(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM users ORDER BY name")

    def add_user(self, name: str) -> int:
        conn   = self._conn()
        cursor = conn.execute(
            "INSERT INTO users (name, created_at) VALUES (?, ?)",
            (name.strip(), _now()),
        )
        conn.commit()
        return cursor.lastrowid

    def delete_user(self, user_id: int) -> None:
        """Delete user and all their data (sessions cascade to readings/training)."""
        conn = self._conn()
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        return self._query_one("SELECT * FROM users WHERE id = ?", (user_id,))

    # ── Sessions ──────────────────────────────────────────────────────────────

    def start_session(self, source_name: str, note: str = "", user_id: Optional[int] = None) -> int:
        """Create a new session row and return its id."""
        conn   = self._conn()
        cursor = conn.execute(
            "INSERT INTO sessions (user_id, started_at, source_name, note) VALUES (?, ?, ?, ?)",
            (user_id, _now(), source_name, note),
        )
        conn.commit()
        return cursor.lastrowid

    def end_session(self, session_id: int, note: str = "") -> None:
        self._execute(
            "UPDATE sessions SET ended_at = ?, note = ? WHERE id = ?",
            (_now(), note.strip() or None, session_id),
        )

    def get_sessions(self, limit: int = 100, user_id: Optional[int] = None) -> list[sqlite3.Row]:
        """Return recent sessions, most recent first. Scoped to user if user_id given."""
        where  = "WHERE s.user_id = ?" if user_id is not None else ""
        params = (user_id, limit) if user_id is not None else (limit,)
        return self._query(
            f"""
            SELECT
                s.id,
                s.started_at,
                s.ended_at,
                s.source_name,
                s.note,
                COUNT(r.id) AS reading_count,
                AVG(r.focus)   AS avg_focus,
                AVG(r.relax)   AS avg_relax,
                AVG(r.stress)  AS avg_stress,
                AVG(r.flow)    AS avg_flow,
                AVG(r.fatigue) AS avg_fatigue
            FROM sessions s
            LEFT JOIN readings r ON r.session_id = s.id
            {where}
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT ?
            """,
            params,
        )

    def get_session_readings(self, session_id: int) -> list[sqlite3.Row]:
        """Return all readings for a specific session, oldest first."""
        return self._query(
            "SELECT * FROM readings WHERE session_id = ? ORDER BY recorded_at",
            (session_id,),
        )

    def get_training_session_readings(self, training_session_id: int) -> list[sqlite3.Row]:
        """Return readings that fall within the time window of a training session."""
        return self._query(
            """
            SELECT r.*
            FROM readings r
            JOIN training_sessions ts ON ts.session_id = r.session_id
            WHERE ts.id = ?
              AND r.recorded_at >= ts.started_at
              AND (ts.ended_at IS NULL OR r.recorded_at <= ts.ended_at)
            ORDER BY r.recorded_at ASC
            """,
            (training_session_id,),
        )

    # ── Readings ──────────────────────────────────────────────────────────────

    def insert_reading(
        self,
        session_id: int,
        scores: dict,
    ) -> None:
        """
        Insert one second of EEG scores.
        scores dict must have keys: focus, relax, stress, flow, fatigue.
        blink is optional (may be None).
        """
        self._execute(
            """
            INSERT INTO readings
                (session_id, recorded_at, focus, relax, stress, flow, fatigue, blink)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                _now(),
                scores.get("focus"),
                scores.get("relax"),
                scores.get("stress"),
                scores.get("flow"),
                scores.get("fatigue"),
                scores.get("blink"),
            ),
        )

    # ── Training sessions ─────────────────────────────────────────────────────

    def start_training_session(
        self,
        session_id: int,
        target_metric: str,
        target_threshold: float,
    ) -> int:
        conn   = self._conn()
        cursor = conn.execute(
            """
            INSERT INTO training_sessions
                (session_id, target_metric, target_threshold, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, target_metric, target_threshold, _now()),
        )
        conn.commit()
        return cursor.lastrowid

    def end_training_session(
        self,
        training_session_id: int,
        seconds_on_target: int,
        note: str = "",
    ) -> None:
        self._execute(
            """
            UPDATE training_sessions
            SET ended_at = ?, seconds_on_target = ?, note = ?
            WHERE id = ?
            """,
            (_now(), seconds_on_target, note.strip() or None, training_session_id),
        )

    def log_training_event(
        self,
        training_session_id: int,
        event_type: str,          # 'enter' or 'exit'
        score_at_event: float,
    ) -> None:
        self._execute(
            """
            INSERT INTO training_events
                (training_session_id, event_type, recorded_at, score_at_event)
            VALUES (?, ?, ?, ?)
            """,
            (training_session_id, event_type, _now(), score_at_event),
        )

    def get_training_history(
        self,
        target_metric: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[int] = None,
    ) -> list[sqlite3.Row]:
        """
        Return training sessions with their stats.
        Optionally filter by metric and/or user.
        """
        clauses: list[str] = []
        params:  list      = []
        if target_metric is not None:
            clauses.append("ts.target_metric = ?")
            params.append(target_metric)
        if user_id is not None:
            clauses.append("s.user_id = ?")
            params.append(user_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return self._query(
            f"""
            SELECT
                ts.id,
                ts.target_metric,
                ts.target_threshold,
                ts.started_at,
                ts.ended_at,
                ts.seconds_on_target,
                ts.note,
                s.source_name
            FROM training_sessions ts
            JOIN sessions s ON s.id = ts.session_id
            {where}
            ORDER BY ts.started_at DESC
            LIMIT ?
            """,
            tuple(params),
        )

    # ── Long-term trends ──────────────────────────────────────────────────────

    def get_daily_averages(self, days: int = 30, user_id: Optional[int] = None) -> list[sqlite3.Row]:
        """Return per-day average scores for the last N days, scoped to user if given."""
        if user_id is not None:
            return self._query(
                """
                SELECT
                    DATE(r.recorded_at) AS day,
                    AVG(r.focus)   AS focus,
                    AVG(r.relax)   AS relax,
                    AVG(r.stress)  AS stress,
                    AVG(r.flow)    AS flow,
                    AVG(r.fatigue) AS fatigue,
                    COUNT(r.id)    AS reading_count
                FROM readings r
                JOIN sessions s ON s.id = r.session_id
                WHERE r.recorded_at >= DATE('now', ?)
                  AND s.user_id = ?
                GROUP BY day
                ORDER BY day
                """,
                (f"-{days} days", user_id),
            )
        return self._query(
            """
            SELECT
                DATE(recorded_at) AS day,
                AVG(focus)   AS focus,
                AVG(relax)   AS relax,
                AVG(stress)  AS stress,
                AVG(flow)    AS flow,
                AVG(fatigue) AS fatigue,
                COUNT(*)     AS reading_count
            FROM readings
            WHERE recorded_at >= DATE('now', ?)
            GROUP BY day
            ORDER BY day
            """,
            (f"-{days} days",),
        )

    def get_all_time_averages(self, user_id: Optional[int] = None) -> Optional[sqlite3.Row]:
        """Return lifetime averages, scoped to user if given."""
        if user_id is not None:
            return self._query_one(
                """
                SELECT
                    AVG(r.focus)   AS focus,
                    AVG(r.relax)   AS relax,
                    AVG(r.stress)  AS stress,
                    AVG(r.flow)    AS flow,
                    AVG(r.fatigue) AS fatigue,
                    COUNT(r.id)    AS total_readings,
                    COUNT(DISTINCT r.session_id) AS total_sessions
                FROM readings r
                JOIN sessions s ON s.id = r.session_id
                WHERE s.user_id = ?
                """,
                (user_id,),
            )
        return self._query_one(
            """
            SELECT
                AVG(focus)   AS focus,
                AVG(relax)   AS relax,
                AVG(stress)  AS stress,
                AVG(flow)    AS flow,
                AVG(fatigue) AS fatigue,
                COUNT(*)     AS total_readings,
                COUNT(DISTINCT session_id) AS total_sessions
            FROM readings
            """
        )

    def get_user_extended_stats(self, user_id: int) -> dict:
        """Comprehensive stats for the profile screen."""
        basic = self._query_one(
            """
            SELECT
                COUNT(DISTINCT s.id)  AS total_sessions,
                COUNT(r.id)           AS total_readings,
                SUM(CASE WHEN s.ended_at IS NOT NULL
                    THEN (julianday(s.ended_at) - julianday(s.started_at)) * 86400
                    ELSE 0 END)       AS total_seconds,
                COUNT(DISTINCT DATE(r.recorded_at)) AS active_days,
                AVG(r.focus)   AS avg_focus,   MAX(r.focus)   AS best_focus,
                AVG(r.relax)   AS avg_relax,   MAX(r.relax)   AS best_relax,
                AVG(r.stress)  AS avg_stress,  MAX(r.stress)  AS best_stress,
                AVG(r.flow)    AS avg_flow,    MAX(r.flow)    AS best_flow,
                AVG(r.fatigue) AS avg_fatigue, MAX(r.fatigue) AS best_fatigue
            FROM sessions s
            LEFT JOIN readings r ON r.session_id = s.id
            WHERE s.user_id = ?
            """,
            (user_id,),
        )
        training = self._query_one(
            """
            SELECT
                COUNT(ts.id)              AS training_sessions,
                SUM(ts.seconds_on_target) AS total_on_target
            FROM training_sessions ts
            JOIN sessions s ON s.id = ts.session_id
            WHERE s.user_id = ? AND ts.ended_at IS NOT NULL
            """,
            (user_id,),
        )
        hour_row = self._query_one(
            """
            SELECT strftime('%H', started_at) AS hour
            FROM sessions WHERE user_id = ?
            GROUP BY hour ORDER BY COUNT(*) DESC LIMIT 1
            """,
            (user_id,),
        )
        days_rows = self._query(
            """
            SELECT DISTINCT DATE(r.recorded_at) AS day
            FROM readings r JOIN sessions s ON s.id = r.session_id
            WHERE s.user_id = ? ORDER BY day
            """,
            (user_id,),
        )
        return {
            "basic":       basic,
            "training":    training,
            "active_hour": int(hour_row["hour"]) if hour_row and hour_row["hour"] else None,
            "active_days": [row["day"] for row in days_rows],
        }

    def get_training_stats_by_metric(self, user_id: Optional[int] = None) -> list[sqlite3.Row]:
        """Return per-metric training summary: session count, avg and best seconds on target."""
        if user_id is not None:
            return self._query(
                """
                SELECT
                    ts.target_metric,
                    COUNT(ts.id)              AS session_count,
                    AVG(ts.seconds_on_target) AS avg_seconds,
                    MAX(ts.seconds_on_target) AS best_seconds
                FROM training_sessions ts
                JOIN sessions s ON s.id = ts.session_id
                WHERE s.user_id = ?
                  AND ts.ended_at IS NOT NULL
                GROUP BY ts.target_metric
                ORDER BY ts.target_metric
                """,
                (user_id,),
            )
        return self._query(
            """
            SELECT
                target_metric,
                COUNT(id)              AS session_count,
                AVG(seconds_on_target) AS avg_seconds,
                MAX(seconds_on_target) AS best_seconds
            FROM training_sessions
            WHERE ended_at IS NOT NULL
            GROUP BY target_metric
            ORDER BY target_metric
            """
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    """Current local time as ISO-8601 string."""
    return datetime.now().isoformat(timespec="seconds")