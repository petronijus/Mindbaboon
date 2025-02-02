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