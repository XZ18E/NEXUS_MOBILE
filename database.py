"""Слой работы с данными: SQLite, CRUD для событий и задач, настройки, экспорт, резервные копии."""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
from datetime import date, datetime, time
from pathlib import Path

from models import (Event, Occurrence, Task, expand_event, RECURRENCE_NAMES, REMINDER_NAMES)


def get_data_dir() -> Path:
    """Папка data рядом с программой (или с EXE). Если писать туда нельзя — %APPDATA%."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    candidate = base / "data"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / "NEXUS Calendar"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    all_day INTEGER DEFAULT 0,
    category TEXT DEFAULT 'Другое',
    color TEXT DEFAULT '',
    location TEXT DEFAULT '',
    reminder INTEGER DEFAULT -1,
    recurrence TEXT DEFAULT 'none',
    recurrence_until TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    due TEXT,
    priority INTEGER DEFAULT 1,
    done INTEGER DEFAULT 0,
    completed_at TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sent_reminders (
    event_id INTEGER NOT NULL,
    occ_start TEXT NOT NULL,
    PRIMARY KEY (event_id, occ_start),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
"""


def _row_to_event(r: sqlite3.Row) -> Event:
    return Event(
        id=r["id"], title=r["title"], description=r["description"] or "",
        start=datetime.fromisoformat(r["start_at"]), end=datetime.fromisoformat(r["end_at"]),
        all_day=bool(r["all_day"]), category=r["category"] or "Другое", color=r["color"] or "",
        location=r["location"] or "", reminder=r["reminder"] if r["reminder"] is not None else -1,
        recurrence=r["recurrence"] or "none",
        recurrence_until=date.fromisoformat(r["recurrence_until"]) if r["recurrence_until"] else None,
    )


def _row_to_task(r: sqlite3.Row) -> Task:
    return Task(
        id=r["id"], title=r["title"], description=r["description"] or "",
        due=date.fromisoformat(r["due"]) if r["due"] else None,
        priority=r["priority"], done=bool(r["done"]),
        completed_at=datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None,
        created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
    )


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else get_data_dir() / "nexus.db"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------- события
    @staticmethod
    def _event_params(ev: Event) -> tuple:
        return (ev.title.strip(), ev.description.strip(), ev.start.isoformat(), ev.end.isoformat(),
                int(ev.all_day), ev.category, ev.color, ev.location.strip(), ev.reminder,
                ev.recurrence, ev.recurrence_until.isoformat() if ev.recurrence_until else None)

    def add_event(self, ev: Event) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO events (title, description, start_at, end_at, all_day, category, color,"
                " location, reminder, recurrence, recurrence_until) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                self._event_params(ev))
        ev.id = cur.lastrowid
        return ev.id

    def update_event(self, ev: Event) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE events SET title=?, description=?, start_at=?, end_at=?, all_day=?, category=?,"
                " color=?, location=?, reminder=?, recurrence=?, recurrence_until=? WHERE id=?",
                self._event_params(ev) + (ev.id,))
            # Время изменилось — напоминания должны сработать заново
            self.conn.execute("DELETE FROM sent_reminders WHERE event_id=?", (ev.id,))

    def delete_event(self, event_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    def get_event(self, event_id: int) -> Event | None:
        r = self.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return _row_to_event(r) if r else None

    def all_events(self) -> list[Event]:
        rows = self.conn.execute("SELECT * FROM events ORDER BY start_at").fetchall()
        return [_row_to_event(r) for r in rows]

    def events_in_range(self, start: date, end: date) -> list[Occurrence]:
        """Все вхождения событий (включая повторяющиеся) за период, отсортированные по началу."""
        lo = datetime.combine(start, time.min).isoformat()
        hi = datetime.combine(end, time.max).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM events WHERE recurrence != 'none' OR (start_at <= ? AND end_at >= ?)",
            (hi, lo)).fetchall()
        occs: list[Occurrence] = []
        for r in rows:
            occs.extend(expand_event(_row_to_event(r), start, end))
        occs.sort(key=lambda o: (o.start, o.event.title.casefold()))
        return occs

    def search_events(self, text: str, limit: int = 50) -> list[Event]:
        # LIKE в SQLite не умеет регистронезависимый поиск по кириллице — ищем в Python
        needle = text.strip().casefold()
        if not needle:
            return []
        found = []
        for ev in self.all_events():
            hay = " ".join((ev.title, ev.description, ev.location, ev.category)).casefold()
            if needle in hay:
                found.append(ev)
        found.sort(key=lambda e: e.start, reverse=True)
        return found[:limit]

    # -------------------------------------------------------------- задачи
    def add_task(self, t: Task) -> int:
        created = (t.created_at or datetime.now()).isoformat(timespec="seconds")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tasks (title, description, due, priority, done, completed_at, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (t.title.strip(), t.description.strip(), t.due.isoformat() if t.due else None, t.priority,
                 int(t.done), t.completed_at.isoformat(timespec="seconds") if t.completed_at else None, created))
        t.id = cur.lastrowid
        return t.id

    def update_task(self, t: Task) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET title=?, description=?, due=?, priority=? WHERE id=?",
                (t.title.strip(), t.description.strip(), t.due.isoformat() if t.due else None, t.priority, t.id))

    def set_task_done(self, task_id: int, done: bool) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET done=?, completed_at=? WHERE id=?",
                (int(done), datetime.now().isoformat(timespec="seconds") if done else None, task_id))

    def delete_task(self, task_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def all_tasks(self) -> list[Task]:
        rows = self.conn.execute("SELECT * FROM tasks").fetchall()
        return [_row_to_task(r) for r in rows]

    def tasks_due_on(self, day: date) -> list[Task]:
        rows = self.conn.execute("SELECT * FROM tasks WHERE due=? ORDER BY done, priority DESC, id",
                                 (day.isoformat(),)).fetchall()
        return [_row_to_task(r) for r in rows]

    def pending_task_counts(self, start: date, end: date) -> dict[date, int]:
        rows = self.conn.execute(
            "SELECT due, COUNT(*) AS n FROM tasks WHERE done=0 AND due BETWEEN ? AND ? GROUP BY due",
            (start.isoformat(), end.isoformat())).fetchall()
        return {date.fromisoformat(r["due"]): r["n"] for r in rows}

    def search_tasks(self, text: str, limit: int = 50) -> list[Task]:
        needle = text.strip().casefold()
        if not needle:
            return []
        found = [t for t in self.all_tasks() if needle in f"{t.title} {t.description}".casefold()]
        found.sort(key=lambda t: (t.done, t.due or date.max))
        return found[:limit]

    # ----------------------------------------------------------- настройки
    def get_setting(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r and r["value"] is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    # ------------------------------------------------------- напоминания
    def reminder_sent(self, event_id: int, occ_start: datetime) -> bool:
        r = self.conn.execute("SELECT 1 FROM sent_reminders WHERE event_id=? AND occ_start=?",
                              (event_id, occ_start.isoformat())).fetchone()
        return r is not None

    def mark_reminder_sent(self, event_id: int, occ_start: datetime) -> None:
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO sent_reminders(event_id, occ_start) VALUES(?,?)",
                              (event_id, occ_start.isoformat()))
            # Чистим старое, чтобы таблица не росла бесконечно
            self.conn.execute("DELETE FROM sent_reminders WHERE occ_start < ?",
                              (datetime.now().replace(microsecond=0).isoformat()[:10],))

    # ---------------------------------------------------- экспорт и бэкап
    def export_events_csv(self, path: str | Path) -> int:
        """CSV с разделителем «;» и BOM — корректно открывается в русском Excel."""
        events = self.all_events()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Название", "Описание", "Категория", "Начало", "Окончание", "Весь день",
                        "Место", "Напоминание", "Повтор", "Повторять до"])
            for e in events:
                w.writerow([
                    e.title, e.description, e.category,
                    e.start.strftime("%d.%m.%Y") if e.all_day else e.start.strftime("%d.%m.%Y %H:%M"),
                    e.end.strftime("%d.%m.%Y") if e.all_day else e.end.strftime("%d.%m.%Y %H:%M"),
                    "Да" if e.all_day else "Нет", e.location,
                    REMINDER_NAMES.get(e.reminder, ""), RECURRENCE_NAMES.get(e.recurrence, ""),
                    e.recurrence_until.strftime("%d.%m.%Y") if e.recurrence_until else "",
                ])
        return len(events)

    def backup_to(self, dest: str | Path) -> None:
        """Консистентная копия базы средствами SQLite (безопасна, даже пока база открыта)."""
        dest = Path(dest)
        if dest.exists() and dest.resolve() == self.path.resolve():
            raise ValueError("Нельзя сохранить копию поверх рабочей базы.")
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()
