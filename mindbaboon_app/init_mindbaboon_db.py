import sqlite3

def init_db():
    conn = sqlite3.connect("mindbaboon.db")
    cursor = conn.cursor()

    # Create the 'goals' table with the updated structure
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT NOT NULL,
            goal_description TEXT,
            time_span TEXT,
            end_date TEXT,
            iteration TEXT,
            next_step_description TEXT,
            reward TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL,
            last_reminder_at TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Mindbaboon database (goals table) initialized successfully with new columns.")
