from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

# ----------------------------------------------------
# Database helper
# ----------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("mindbaboon.db")
    conn.row_factory = sqlite3.Row
    return conn

# ----------------------------------------------------
# Home / List View
# ----------------------------------------------------
@app.route("/")
def index():
    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return render_template("index.html", tasks=tasks)

# ----------------------------------------------------
# Add a new task
# ----------------------------------------------------
@app.route("/add", methods=["GET", "POST"])
def add_task():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form.get("description", "")

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO tasks (title, description, completed) VALUES (?, ?, ?)",
            (title, description, 0),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    return render_template("add.html")

# ----------------------------------------------------
# Edit a task
# ----------------------------------------------------
@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):
    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    if not task:
        conn.close()
        return "Task not found", 404

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        completed = request.form.get("completed", "off")
        completed = 1 if completed == "on" else 0

        conn.execute(
            "UPDATE tasks SET title = ?, description = ?, completed = ? WHERE id = ?",
            (title, description, completed, task_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("edit.html", task=task)

# ----------------------------------------------------
# Delete a task
# ----------------------------------------------------
@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Make sure mindbaboon.db exists by running init_mindbaboon_db.py first
    app.run(debug=True)
