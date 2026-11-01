"""Модели данных NEXUS Calendar: события, задачи, повторения и русские форматы дат.

Модуль не зависит от Qt и SQLite — его можно тестировать отдельно.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# ----------------------------------------------------------------- справочники

CATEGORIES: dict[str, str] = {
    "Работа": "#4D8DFF",
    "Личное": "#A855F7",
    "Учёба": "#22C55E",
    "Здоровье": "#F43F5E",
    "Встреча": "#F59E0B",
    "Другое": "#94A3B8",
}
DEFAULT_CATEGORY = "Другое"

# Палитра для ручного выбора цвета события
EXTRA_COLORS = ["#06B6D4", "#EC4899"]

RECURRENCE_OPTIONS = [
    ("none", "Не повторять"),
    ("daily", "Каждый день"),
    ("weekly", "Каждую неделю"),
    ("monthly", "Каждый месяц"),
]
RECURRENCE_NAMES = dict(RECURRENCE_OPTIONS)

REMINDER_OPTIONS = [
    (-1, "Без напоминания"),
    (0, "В момент начала"),
    (5, "За 5 минут"),
    (10, "За 10 минут"),
    (15, "За 15 минут"),
    (30, "За 30 минут"),
    (60, "За 1 час"),
    (1440, "За 1 день"),
]
REMINDER_NAMES = dict(REMINDER_OPTIONS)

PRIORITY_NAMES = {0: "Низкий", 1: "Средний", 2: "Высокий"}
PRIORITY_COLORS = {0: "#22C55E", 1: "#F59E0B", 2: "#F43F5E"}

MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
WEEKDAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


# ----------------------------------------------------------------------- модели

@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    description: str = ""
    all_day: bool = False
    category: str = DEFAULT_CATEGORY
    color: str = ""                     # "" -> цвет берётся из категории
    location: str = ""
    reminder: int = -1                  # минуты до начала, -1 = без напоминания
    recurrence: str = "none"            # none | daily | weekly | monthly
    recurrence_until: date | None = None
    id: int | None = None

    @property
    def display_color(self) -> str:
        return self.color or CATEGORIES.get(self.category, CATEGORIES[DEFAULT_CATEGORY])


@dataclass(frozen=True)
class Occurrence:
    """Одно конкретное вхождение события (для повторяющихся событий их много)."""
    event: Event
    start: datetime
    end: datetime

    @property
    def first_day(self) -> date:
        return self.start.date()

    @property
    def last_day(self) -> date:
        # Событие, заканчивающееся ровно в 00:00, не «залезает» на следующий день.
        if self.end > self.start:
            return (self.end - timedelta(microseconds=1)).date()
        return self.start.date()

    @property
    def is_multiday(self) -> bool:
        return self.last_day > self.first_day

    def covers(self, day: date) -> bool:
        return self.first_day <= day <= self.last_day

    @property
    def is_band(self) -> bool:
        """Рисовать ли событие полосой «весь день» (а не блоком по времени)."""
        return self.event.all_day or (self.last_day - self.first_day).days >= 2


@dataclass
class Task:
    title: str
    description: str = ""
    due: date | None = None
    priority: int = 1
    done: bool = False
    completed_at: datetime | None = None
    created_at: datetime | None = None
    id: int | None = None

    def is_overdue(self, today: date | None = None) -> bool:
        return (not self.done) and self.due is not None and self.due < (today or date.today())


# ---------------------------------------------------------------- повторения

def add_months(value, months: int):
    """Прибавляет месяцы к date/datetime, обрезая день до длины месяца (31 янв -> 28 фев)."""
    m = value.month - 1 + months
    year = value.year + m // 12
    month = m % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def expand_event(ev: Event, range_start: date, range_end: date) -> list[Occurrence]:
    """Возвращает вхождения события, пересекающиеся с [range_start, range_end]."""
    duration = ev.end - ev.start
    result: list[Occurrence] = []

    def add(start: datetime) -> None:
        occ = Occurrence(ev, start, start + duration)
        if occ.first_day <= range_end and occ.last_day >= range_start:
            result.append(occ)

    if ev.recurrence == "none":
        add(ev.start)
        return result

    until = ev.recurrence_until
    span_days = duration.days + 1
    guard = 0

    if ev.recurrence in ("daily", "weekly"):
        step = 1 if ev.recurrence == "daily" else 7
        # Пропускаем всё, что заведомо закончилось до начала диапазона
        skip = (range_start - ev.start.date()).days - span_days
        n = max(0, skip // step)
        while guard < 5000:
            guard += 1
            start = ev.start + timedelta(days=n * step)
            if start.date() > range_end or (until and start.date() > until):
                break
            add(start)
            n += 1
    elif ev.recurrence == "monthly":
        diff = (range_start.year - ev.start.year) * 12 + range_start.month - ev.start.month
        n = max(0, diff - span_days // 28 - 1)
        while guard < 2000:
            guard += 1
            start = add_months(ev.start, n)
            if start.date() > range_end or (until and start.date() > until):
                break
            add(start)
            n += 1
    else:  # неизвестный тип — считаем обычным событием
        add(ev.start)
    return result


def validate_event(ev: Event) -> str | None:
    """Проверка корректности события. Возвращает текст ошибки или None."""
    if not ev.title.strip():
        return "Введите название события."
    if len(ev.title.strip()) > 120:
        return "Название слишком длинное (максимум 120 символов)."
    if ev.end < ev.start:
        return "Окончание не может быть раньше начала."
    if ev.recurrence != "none" and ev.recurrence_until and ev.recurrence_until < ev.start.date():
        return "Дата окончания повторов раньше начала события."
    return None


# --------------------------------------------------------------- форматирование

def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return forms[2]
    r = n % 10
    if r == 1:
        return forms[0]
    if 2 <= r <= 4:
        return forms[1]
    return forms[2]


def count_text(n: int, forms: tuple[str, str, str]) -> str:
    return f"{n} {plural(n, forms)}"


EVENT_FORMS = ("событие", "события", "событий")
TASK_FORMS = ("задача", "задачи", "задач")


def fmt_date_long(d: date) -> str:
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]} {d.year}"


def fmt_date_short(d: date) -> str:
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}"


def month_title(year: int, month: int) -> str:
    return f"{MONTHS_NOM[month - 1].capitalize()} {year}"


def relative_day(d: date, today: date | None = None) -> str | None:
    today = today or date.today()
    delta = (d - today).days
    return {0: "Сегодня", 1: "Завтра", -1: "Вчера"}.get(delta)


def fmt_occurrence_time(occ: Occurrence) -> str:
    if occ.event.all_day:
        if occ.is_multiday:
            return f"{fmt_date_short(occ.first_day)} – {fmt_date_short(occ.last_day)}"
        return "Весь день"
    if occ.is_multiday:
        return (f"{fmt_date_short(occ.first_day)} {occ.start:%H:%M} – "
                f"{fmt_date_short(occ.last_day)} {occ.end:%H:%M}")
    if occ.end == occ.start:
        return f"{occ.start:%H:%M}"
    return f"{occ.start:%H:%M} – {occ.end:%H:%M}"
