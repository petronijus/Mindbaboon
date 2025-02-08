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
    """, (key, value))
    conn.commit()
    conn.close()
