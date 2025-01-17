import sqlite3

def initialize_database():
    """
    Create the database schema for Mindbaboon, including goals and goal_history tables.
    """
    conn = sqlite3.connect("mindbaboon.db")

    # Create the goals table with new columns
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
            is_paused INTEGER NOT NULL DEFAULT 0, -- New column to track paused state
            last_email_sent TIMESTAMP,          -- New column to track last email sent
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
            description TEXT,
            next_steps TEXT,
            reward TEXT,
            timestamp TIMESTAMP NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals (id)
        );
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")
