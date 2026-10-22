import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).with_name("life_manager.db")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Общее',
            priority TEXT NOT NULL DEFAULT 'Средний',
            due_date TEXT DEFAULT '',
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS habits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS habit_log(
            habit_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            PRIMARY KEY(habit_id, day),
            FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );
        """)
        self.conn.commit()

    def tasks(self):
        return self.conn.execute("SELECT * FROM tasks ORDER BY done, CASE priority WHEN 'Высокий' THEN 0 WHEN 'Средний' THEN 1 ELSE 2 END, id DESC").fetchall()

    def add_task(self, title, category, priority, due_date):
        self.conn.execute("INSERT INTO tasks(title,category,priority,due_date,created_at) VALUES(?,?,?,?,datetime('now'))",(title,category,priority,due_date))
        self.conn.commit()

    def toggle_task(self, task_id):
        self.conn.execute("UPDATE tasks SET done=1-done WHERE id=?",(task_id,))
        self.conn.commit()

    def delete_task(self, task_id):
        self.conn.execute("DELETE FROM tasks WHERE id=?",(task_id,))
        self.conn.commit()

    def notes(self):
        return self.conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()

    def get_note(self, note_id):
        return self.conn.execute("SELECT * FROM notes WHERE id=?",(note_id,)).fetchone()

    def save_note(self, note_id, title, body):
        if note_id:
            self.conn.execute("UPDATE notes SET title=?,body=?,updated_at=datetime('now') WHERE id=?",(title,body,note_id))
        else:
            self.conn.execute("INSERT INTO notes(title,body,updated_at) VALUES(?,?,datetime('now'))",(title,body))
        self.conn.commit()

    def delete_note(self, note_id):
        self.conn.execute("DELETE FROM notes WHERE id=?",(note_id,))
        self.conn.commit()

    def habits(self):
        return self.conn.execute("""SELECT h.*, EXISTS(
            SELECT 1 FROM habit_log l WHERE l.habit_id=h.id AND l.day=?
        ) AS done_today,
        (SELECT COUNT(*) FROM habit_log l WHERE l.habit_id=h.id) AS total
        FROM habits h ORDER BY h.id DESC""",(date.today().isoformat(),)).fetchall()

    def add_habit(self, name):
        self.conn.execute("INSERT OR IGNORE INTO habits(name,created_at) VALUES(?,datetime('now'))",(name,))
        self.conn.commit()

    def toggle_habit(self, habit_id):
        day=date.today().isoformat()
        exists=self.conn.execute("SELECT 1 FROM habit_log WHERE habit_id=? AND day=?",(habit_id,day)).fetchone()
        if exists:
            self.conn.execute("DELETE FROM habit_log WHERE habit_id=? AND day=?",(habit_id,day))
        else:
            self.conn.execute("INSERT INTO habit_log(habit_id,day) VALUES(?,?)",(habit_id,day))
        self.conn.commit()

    def delete_habit(self, habit_id):
        self.conn.execute("DELETE FROM habit_log WHERE habit_id=?",(habit_id,))
        self.conn.execute("DELETE FROM habits WHERE id=?",(habit_id,))
        self.conn.commit()

    def stats(self):
        tasks=self.conn.execute("SELECT COUNT(*) total, COALESCE(SUM(done),0) done FROM tasks").fetchone()
        habits=self.conn.execute("SELECT COUNT(*) FROM habits").fetchone()[0]
        today=self.conn.execute("SELECT COUNT(*) FROM habit_log WHERE day=?",(date.today().isoformat(),)).fetchone()[0]
        notes=self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        return dict(tasks), habits, today, notes
