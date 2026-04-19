import sqlite3
import os

def get_db_connection():
    """Get database connection from the Docker volume."""
    try:
        # Always use the Docker volume at /app/data.
        data_dir = 'data'
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, 'mindbaboon.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise 

def get_setting(key):
    """Retrieve a setting value from the settings table."""
    conn = get_db_connection()
    setting = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return setting["value"] if setting else None

def set_setting(key, value):
    """Insert or update a setting in the settings table."""
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def get_iteration_slot():
    """Return dict {weekday:0-6, hour:0-23, minute:0-59} for global iteration window."""
    from config import DEFAULT_ITERATION_SLOT
    weekday = int(get_setting("iteration_weekday") or DEFAULT_ITERATION_SLOT["weekday"])
    hour = int(get_setting("iteration_hour") or DEFAULT_ITERATION_SLOT["hour"])
    minute = int(get_setting("iteration_minute") or DEFAULT_ITERATION_SLOT["minute"])
    return {"weekday": weekday, "hour": hour, "minute": minute}


def set_iteration_slot(weekday=None, hour=None, minute=None):
    if weekday is not None:
        set_setting("iteration_weekday", int(weekday))
    if hour is not None:
        set_setting("iteration_hour", int(hour))
    if minute is not None:
        set_setting("iteration_minute", int(minute))
