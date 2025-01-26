import sqlite3
import os

def get_db_connection():
    """Get database connection with proper error handling and path resolution"""
    try:
        # First try the Docker volume path
        data_dir = '/app/data'
        if not os.path.exists(data_dir):
            # Fallback to local development path
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

        db_path = os.path.join(data_dir, 'mindbaboon.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise 