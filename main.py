from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask("Mindbaboon")

def get_db():
    db = sqlite3.connect('todos.db')
    return db

@app.route('/')
def index():
    db = get_db()
    cur = db.execute('SELECT id, task FROM todos')
    todos = cur.fetchall()
    return render_template('index.html', todos=todos)

@app.route('/add', methods=['POST'])
def add():
    task = request.form['task']
    db = get_db()
    db.execute('INSERT INTO todos (task) VALUES (?)', [task])
    db.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:todo_id>')
def edit(todo_id):
    db = get_db()
    cur = db.execute('SELECT id, task FROM todos WHERE id = ?', [todo_id])
    todo = cur.fetchone()
    return render_template('edit.html', todo=todo)

@app.route('/update/<int:todo_id>', methods=['POST'])
def update(todo_id):
    task = request.form['task']
    db = get_db()
    db.execute('UPDATE todos SET task = ? WHERE id = ?', [task, todo_id])
    db.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:todo_id>')
def delete(todo_id):
    db = get_db()
    db.execute('DELETE FROM todos WHERE id = ?', [todo_id])
    db.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
