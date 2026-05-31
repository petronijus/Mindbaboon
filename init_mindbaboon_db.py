import sqlite3
import os
from datetime import datetime
import pytz

TIMEZONE = pytz.timezone('Europe/Prague')


def _column_names(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def initialize_database():
    """
    Create the database schema for Mindbaboon, including goals, goal_history,
    iteration_history, and apscheduler tables. Idempotent — safe to run on
    every container start.
    """
    data_dir = 'data'
    os.makedirs(data_dir, exist_ok=True)

    db_path = os.path.join(data_dir, 'mindbaboon.db')
    conn = sqlite3.connect(db_path)

    # The is_silenced flag: 1 means "don't send reminder emails for this goal
    # right now". Set automatically when a reminder fires (awaiting user
    # response), cleared when user responds via /iteration/<id> form. Can
    # also be set/cleared via API /snooze and /resume.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT NOT NULL,
            goal_description TEXT,
            time_span TEXT,
            end_date TEXT,
            iteration TEXT,
            next_steps TEXT,
            reward TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            is_silenced INTEGER NOT NULL DEFAULT 0,
            last_email_sent TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            last_reminder_at TIMESTAMP
        );
    """)

    # Migration: existing DBs have `is_paused`. Rename to `is_silenced`.
    cols = _column_names(conn, "goals")
    if "is_paused" in cols and "is_silenced" not in cols:
        conn.execute("ALTER TABLE goals RENAME COLUMN is_paused TO is_silenced")

    # Migration: `goals.completed` must be an integer flag (0/1). A legacy code
    # path wrote the iteration answer ("yes"/"no") into it, which broke
    # `completed == 0/1` comparisons (hidden "iterate" button, goal missing from
    # the active API list). Normalize any non-1 value to 0 (active); keep 1.
    conn.execute("UPDATE goals SET completed = CASE WHEN completed IN (1, '1') THEN 1 ELSE 0 END")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS goal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            completed TEXT NOT NULL,
            was_done TEXT,
            next_steps TEXT,
            reward TEXT,
            timestamp TIMESTAMP NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals (id) ON DELETE CASCADE
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_goal_history_goal_id ON goal_history (goal_id);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS iteration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            next_run TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (iteration_id) REFERENCES goals (id) ON DELETE CASCADE
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_iteration_history_iteration_id ON iteration_history (iteration_id);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS apscheduler_jobs (
            id VARCHAR(191) NOT NULL,
            next_run_time FLOAT,
            job_state BLOB NOT NULL,
            PRIMARY KEY (id)
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_apscheduler_jobs_next_run_time ON apscheduler_jobs (next_run_time);")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully in data directory.")
