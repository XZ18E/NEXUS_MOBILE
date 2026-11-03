"""Тесты помощника: python tests/test_assistant.py"""
import sys, tempfile
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant import parse, execute
from database import Database

NOW = datetime(2026, 11, 2, 12, 0)      # понедельник


class Host:
    default_reminder = 15
    def __init__(self):
        self.db = Database(Path(tempfile.mkdtemp()) / "a.db")
    def save_event(self, ev):
        self.db.add_event(ev); return True
    def save_task(self, t):
        self.db.add_task(t); return True


def ev(text):
    i = parse(text, NOW)
    assert i.kind == "add_event", (text, i)
    return i


def test_add_event():
    i = ev("Завтра в 15:00 встреча с Аней, напомни за час")
    assert i.start == datetime(2026, 11, 3, 15, 0) and i.title == "Встреча с Аней", i
    assert i.reminder == 60 and i.category == "Встреча" and not i.all_day, i
    i = ev("день рождения мамы 12 марта каждый год")
    assert i.start.date() == date(2027, 3, 12) and i.all_day and i.recurrence == "yearly", i
    assert i.title == "День рождения мамы", i
    i = ev("каждый понедельник в 9 утра планерка")
    assert i.recurrence == "weekly" and i.start == datetime(2026, 11, 2, 9, 0) and i.title == "Планерка", i
    i = ev("добавь событие послезавтра в 7 вечера кино на 2 часа")
    assert i.start == datetime(2026, 11, 4, 19, 0) and (i.end - i.start).seconds == 7200, i
    i = ev("в пятницу в 18:30 ужин")
    assert i.start == datetime(2026, 11, 6, 18, 30), i
    i = ev("через 2 часа позвонить маме")
    assert i.start == datetime(2026, 11, 2, 14, 0) and i.title == "Позвонить маме", i
    i = ev("напомни завтра в 10 позвонить маме")
    assert i.reminder == 0 and i.start.hour == 10 and i.title == "Позвонить маме", i
    i = ev("5 ноября в 14.30 врач")
    assert i.start == datetime(2026, 11, 5, 14, 30) and i.category == "Здоровье", i
    i = ev("01.12 экзамен")
    assert i.start.date() == date(2026, 12, 1) and i.category == "Учёба", i
    i = ev("в 8 утра зарядка каждый день")
    assert i.recurrence == "daily" and i.start == datetime(2026, 11, 3, 8, 0), i   # 8:00 сегодня уже прошло


def test_task_find_open_help():
    i = parse("добавь задачу купить билеты до пятницы", NOW)
    assert i.kind == "add_task" and i.title == "Купить билеты" and i.day == date(2026, 11, 6), i
    i = parse("добавь срочную задачу отправить отчёт завтра", NOW)
    assert i.kind == "add_task" and i.day == date(2026, 11, 3), i
    assert parse("что у меня завтра?", NOW).kind == "find"
    assert parse("найди врача", NOW).kind == "find"
    assert parse("открой 5 ноября", NOW).kind == "open"
    assert parse("помощь", NOW).kind == "help"
    assert parse("абракадабра", NOW).kind == "unknown"


def test_execute():
    h = Host()
    r = execute(ev("Завтра в 15:00 встреча с Аней, напомни за час"), h, NOW)
    assert r.changed and "Готово" in r.text and r.open_date == date(2026, 11, 3), r
    execute(ev("день рождения мамы 12 марта каждый год"), h, NOW)
    execute(ev("5 ноября в 14:30 врач"), h, NOW)
    r = execute(parse("что у меня завтра", NOW), h, NOW)
    assert len(r.items) == 1, r
    r = execute(parse("найди врача", NOW), h, NOW)
    assert len(r.items) == 1 and r.open_date == date(2026, 11, 5), r
    r = execute(parse("когда день рождения мамы", NOW), h, NOW)
    assert len(r.items) == 1 and r.items[0].first_day == date(2027, 3, 12), r
    r = execute(parse("открой врача", NOW), h, NOW)
    assert "Открываю" in r.text, r
    r = execute(parse("найди зубы", NOW), h, NOW)
    assert not r.items and "Ничего" in r.text, r
    r = execute(parse("добавь задачу купить хлеб завтра", NOW), h, NOW)
    assert r.changed and h.db.all_tasks()[0].title == "Купить хлеб", h.db.all_tasks()
    r = execute(parse("что у меня сегодня", NOW), h, NOW)
    assert "ничего" in r.text.lower(), r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("OK", name)
