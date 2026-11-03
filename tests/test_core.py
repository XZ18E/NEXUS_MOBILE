"""Тесты ядра (без графики): python -m pytest tests  или  python tests/test_core.py"""
import sys, tempfile, os
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import Database
from models import Event, Task, expand_event, validate_event, add_months, plural


def make_db():
    d = tempfile.mkdtemp()
    return Database(Path(d) / "t.db")


def test_event_crud_and_persistence():
    db = make_db()
    ev = Event("Встреча", datetime(2026, 10, 29, 10), datetime(2026, 10, 29, 11), category="Работа", reminder=15)
    db.add_event(ev)
    assert ev.id
    path = db.path
    db.close()
    db2 = Database(path)                       # «перезапуск» программы
    got = db2.get_event(ev.id)
    assert got.title == "Встреча" and got.reminder == 15
    got.title = "Новое имя"
    db2.update_event(got)
    assert db2.get_event(ev.id).title == "Новое имя"
    db2.delete_event(ev.id)
    assert db2.get_event(ev.id) is None


def test_recurrence():
    ev = Event("Планерка", datetime(2026, 1, 5, 9), datetime(2026, 1, 5, 10), recurrence="weekly")
    occ = expand_event(ev, date(2026, 10, 1), date(2026, 10, 31))
    assert all(o.start.weekday() == 0 for o in occ) and len(occ) == 4
    ev = Event("31-е", datetime(2026, 1, 31, 9), datetime(2026, 1, 31, 10), recurrence="monthly")
    occ = expand_event(ev, date(2026, 2, 1), date(2026, 2, 28))
    assert len(occ) == 1 and occ[0].start.day == 28
    ev = Event("До", datetime(2026, 10, 1, 9), datetime(2026, 10, 1, 10), recurrence="daily",
               recurrence_until=date(2026, 10, 5))
    assert len(expand_event(ev, date(2026, 10, 1), date(2026, 10, 31))) == 5


def test_yearly():
    ev = Event("ДР", datetime(2020, 2, 29), datetime(2020, 2, 29, 23, 59), all_day=True, recurrence="yearly")
    got = expand_event(ev, date(2027, 1, 1), date(2028, 12, 31))
    assert [o.start.date() for o in got] == [date(2027, 2, 28), date(2028, 2, 29)], got
    ev = Event("Годовщина", datetime(2015, 11, 5, 19), datetime(2015, 11, 5, 21), recurrence="yearly",
               recurrence_until=date(2026, 12, 31))
    assert [o.start.year for o in expand_event(ev, date(2026, 1, 1), date(2030, 12, 31))] == [2026]
    assert expand_event(ev, date(2026, 1, 1), date(2026, 10, 31)) == []


def test_multiday_and_midnight():
    ev = Event("Поездка", datetime(2026, 10, 10), datetime(2026, 10, 12, 23, 59), all_day=True)
    assert len(expand_event(ev, date(2026, 10, 11), date(2026, 10, 11))) == 1
    ev = Event("Ночь", datetime(2026, 10, 10, 22), datetime(2026, 10, 11, 0))
    occ = expand_event(ev, date(2026, 10, 11), date(2026, 10, 11))
    assert occ == []                           # ровно до полуночи — следующий день не занят


def test_validation():
    ok = Event("A", datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11))
    assert validate_event(ok) is None
    assert validate_event(Event("", ok.start, ok.end))
    assert validate_event(Event("A", ok.start, ok.start - timedelta(hours=1)))


def test_tasks_search_export_backup():
    db = make_db()
    t = Task("Купить хлеб", due=date(2026, 10, 29), priority=2)
    db.add_task(t)
    db.set_task_done(t.id, True)
    assert db.all_tasks()[0].done and db.all_tasks()[0].completed_at
    assert db.search_tasks("ХЛЕБ")             # регистр кириллицы не важен
    db.add_event(Event("Приём у врача", datetime(2026, 10, 30, 9), datetime(2026, 10, 30, 10)))
    assert db.search_events("врача")
    csv_path = db.path.parent / "e.csv"
    assert db.export_events_csv(csv_path) == 1 and csv_path.exists()
    bak = db.path.parent / "b.db"
    db.backup_to(bak)
    assert len(Database(bak).all_events()) == 1
    db.set_setting("theme", "light")
    assert db.get_setting("theme") == "light"


def test_misc():
    assert plural(1, ("событие", "события", "событий")) == "событие"
    assert plural(12, ("событие", "события", "событий")) == "событий"
    assert plural(23, ("событие", "события", "событий")) == "события"
    assert add_months(date(2026, 12, 31), 2) == date(2027, 2, 28)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("OK", name)
