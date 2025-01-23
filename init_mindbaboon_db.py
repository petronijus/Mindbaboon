import sqlite3
import os

def initialize_database():
    """
    Create the database schema for Mindbaboon, including goals, goal_history,
    iteration_history, and apscheduler tables.
    """
    # Create data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)

    # Connect to database in data directory
    db_path = os.path.join(data_dir, 'mindbaboon.db')
    conn = sqlite3.connect(db_path)

    # Create the goals table
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
            is_paused INTEGER NOT NULL DEFAULT 0,
            last_email_sent TIMESTAMP,
            created_at TIMESTAMP NOT NULL,
            last_reminder_at TIMESTAMP
        );
    """)

    # Create the goal_history table
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

    # Add index for goal_id in goal_history
    conn.execute("CREATE INDEX IF NOT EXISTS idx_goal_history_goal_id ON goal_history (goal_id);")

    # Create the iteration_history table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iteration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (iteration_id) REFERENCES goals (id) ON DELETE CASCADE
        );
    """)

    # Add index for iteration_id in iteration_history
    conn.execute("CREATE INDEX IF NOT EXISTS idx_iteration_history_iteration_id ON iteration_history (iteration_id);")

    # Create the APScheduler jobs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS apscheduler_jobs (
            id VARCHAR(191) NOT NULL,
            next_run_time FLOAT,
            job_state BLOB NOT NULL,
            PRIMARY KEY (id)
        );
    """)

    # Add index for next_run_time in apscheduler_jobs
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apscheduler_jobs_next_run_time ON apscheduler_jobs (next_run_time);")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully in data directory.")
