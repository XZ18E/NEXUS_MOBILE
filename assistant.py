"""Встроенный помощник: понимает русские фразы и работает без интернета.

Это не нейросеть, а разбор по правилам: даты («завтра», «в пятницу», «5 ноября»), время («в 15:00», «в 7 вечера»),
повторения («каждый год»), напоминания («за час»), команды («добавь», «найди», «открой», «что у меня»).
Модуль не зависит от интерфейса, поэтому его можно тестировать отдельно (tests/test_assistant.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from models import (CATEGORIES, EVENT_FORMS, TASK_FORMS, Event, Occurrence, Task, add_months, count_text,
                    expand_event, fmt_date_long, fmt_occurrence_time, relative_day)

WEEKDAYS = [("понедельник", 0), ("вторник", 1), ("сред", 2), ("четверг", 3), ("пятниц", 4), ("суббот", 5),
            ("воскресень", 6)]
WD_RE = r"(понедельник\w*|вторник\w*|сред[аыуе]|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)"
MONTH_STEMS = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр",
               "декабр"]
MONTH_RE = (r"(январ\w*|феврал\w*|марта|апрел\w*|мая|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|"
            r"декабр\w*)")

ADD_VERBS = r"\b(добав\w*|созда\w*|запиш\w*|запланир\w*|постав\w*|напомн\w*|назнач\w*|внес\w*|занес\w*|записать)\b"
FIND_RE = r"\b(найд\w*|поищ\w*|поиск\w*|покаж\w*|показать|где|когда|что у меня|что запланировано|какие|какой|есть ли|список|что у меня)\b"
OPEN_RE = r"\b(откро\w*|перейд\w*|открыть|переключ\w*)\b"
HELP_RE = r"\b(помощь|помоги|что ты умеешь|что умеешь|привет|здравствуй\w*|команды)\b"

CATEGORY_WORDS = {
    "Здоровье": ["врач", "доктор", "стоматолог", "анализ", "поликлиник", "тренировк", "зарядк", "спортзал", "бассейн",
                 "лекарств", "массаж", "йога"],
    "Встреча": ["встреч", "созвон", "собеседован", "переговор", "звонок", "совещани", "планерк", "обед", "ужин",
                "кофе"],
    "Учёба": ["лекци", "экзамен", "зачет", "зачёт", "урок", "семинар", "курс", "учеб", "контрольн", "домашк"],
    "Работа": ["работ", "дедлайн", "отчет", "отчёт", "презентаци", "проект", "задач", "клиент", "релиз"],
    "Личное": ["день рождения", "др ", "праздник", "отпуск", "свидани", "кино", "концерт", "поездк", "годовщин",
               "юбилей"],
}
YEARLY_WORDS = ["день рождения", "днюха", "годовщин", "юбилей", "др "]

STOP_EDGE = {"до", "в", "во", "на", "о", "об", "про", "по", "к", "с", "и", "а", "мне", "пожалуйста", "нам", "что", "это",
             "мой", "моё", "мое", "моя", "на", "для", "ли", "у", "меня", "мной", "новое", "новую", "новый"}
NOISE_WORDS = {"событие", "событии", "событий", "события", "задачу", "задача", "задачи", "напоминание",
               "напоминалку", "календарь", "календаре", "календаря"}


@dataclass
class Intent:
    kind: str                       # add_event | add_task | find | open | help | unknown
    title: str = ""
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    recurrence: str = "none"
    reminder: int | None = None     # None = взять значение по умолчанию
    category: str = "Другое"
    priority: int = 1
    query: str = ""
    day: date | None = None
    day_to: date | None = None
    explicit_reminder: bool = False


@dataclass
class Reply:
    text: str
    items: list = field(default_factory=list)     # список Occurrence / Task для показа
    open_date: date | None = None
    changed: bool = False


# ------------------------------------------------------------------ разбор

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def _weekday_index(word: str) -> int:
    for stem, idx in WEEKDAYS:
        if word.startswith(stem):
            return idx
    return 0


def _month_index(word: str) -> int:
    for i, stem in enumerate(MONTH_STEMS):
        if word.startswith(stem):
            # «ма» совпадает с «март» и «май»: проверяем по порядку, март идёт раньше
            if stem == "ма":
                continue
            return i + 1
    return 5 if word.startswith("ма") else 1


def _next_weekday(base: date, idx: int, include_today: bool = False) -> date:
    delta = (idx - base.weekday()) % 7
    if delta == 0 and not include_today:
        delta = 7
    return base + timedelta(days=delta)


class _Text:
    """Строка, из которой по мере распознавания вырезаются найденные фрагменты."""

    def __init__(self, text: str):
        self.s = " " + _norm(text) + " "

    def take(self, pattern: str):
        m = re.search(pattern, self.s)
        if m:
            self.s = self.s[:m.start()] + " " + self.s[m.end():]
        return m

    def has(self, pattern: str) -> bool:
        return re.search(pattern, self.s) is not None


def parse(text: str, now: datetime | None = None) -> Intent:
    now = now or datetime.now()
    today = now.date()
    raw = _norm(text)
    t = _Text(text)
    _remember_case(text)

    if re.fullmatch(HELP_RE.replace(r"\b", "") + r"[\s!?.]*", raw) or raw in ("?", "help"):
        return Intent("help")

    # --- повторение
    recurrence, rec_weekday = "none", None
    m = t.take(r"\bкажд(?:ый|ую|ое|ые)\s+" + WD_RE)
    if m:
        recurrence, rec_weekday = "weekly", _weekday_index(m.group(1))
    elif t.take(r"\b(каждый год|ежегодно|раз в год|каждый год)\b"):
        recurrence = "yearly"
    elif t.take(r"\b(каждый месяц|ежемесячно|раз в месяц)\b"):
        recurrence = "monthly"
    elif t.take(r"\b(каждую неделю|еженедельно|раз в неделю)\b"):
        recurrence = "weekly"
    elif t.take(r"\b(каждый день|ежедневно|каждое утро|каждый вечер)\b"):
        recurrence = "daily"

    # --- напоминание «за час / за 15 минут / за день»
    reminder, explicit = None, False
    m = t.take(r"\b(?:напомн\w*\s+)?за\s+(полчаса|час|день|сутки|\d+)\s*(минут\w*|мин|час\w*|ч|дн\w*|день)?\b")
    if m:
        explicit = True
        n, unit = m.group(1), (m.group(2) or "")
        if n == "полчаса":
            reminder = 30
        elif n in ("час",):
            reminder = 60
        elif n in ("день", "сутки"):
            reminder = 1440
        else:
            k = int(n)
            if unit.startswith(("час", "ч")):
                reminder = k * 60
            elif unit.startswith("дн") or unit == "день":
                reminder = k * 1440
            else:
                reminder = k
    elif re.search(r"\bнапомн\w*\b", raw):
        reminder, explicit = 0, True

    # --- длительность «на 2 часа / на полтора часа / на 30 минут»
    duration = None
    m = t.take(r"\bна\s+(полтора часа|полчаса|час|\d+\s*(?:час\w*|ч|минут\w*|мин))\b")
    if m:
        d = m.group(1)
        if d.startswith("полтора"):
            duration = timedelta(minutes=90)
        elif d == "полчаса":
            duration = timedelta(minutes=30)
        elif d == "час":
            duration = timedelta(hours=1)
        else:
            k = int(re.match(r"\d+", d).group(0))
            duration = timedelta(hours=k) if "час" in d or d.endswith("ч") else timedelta(minutes=k)

    # --- «через N ...»
    day: date | None = None
    day_to: date | None = None
    start_dt: datetime | None = None
    m = t.take(r"\bчерез\s+(полчаса|час|день|неделю|месяц|год|\d+)\s*(минут\w*|мин|час\w*|ч|дн\w*|недел\w*|месяц\w*|"
               r"год\w*|лет)?\b")
    if m:
        n, unit = m.group(1), m.group(2) or ""
        k = {"полчаса": 30, "час": 1, "день": 1, "неделю": 1, "месяц": 1, "год": 1}.get(n) or int(n)
        if n == "полчаса" or unit.startswith(("мин",)):
            start_dt = now + timedelta(minutes=k)
        elif n == "час" or unit.startswith(("час", "ч")):
            start_dt = now + timedelta(hours=k)
        elif n == "день" or unit.startswith("дн"):
            day = today + timedelta(days=k)
        elif n == "неделю" or unit.startswith("недел"):
            day = today + timedelta(weeks=k)
        elif n == "месяц" or unit.startswith("месяц"):
            day = add_months(today, k)
        else:
            day = add_months(today, 12 * k)
        if start_dt:
            start_dt = start_dt.replace(second=0, microsecond=0)
            day = start_dt.date()

    # --- диапазоны «на этой/следующей неделе», «в этом месяце»
    if day is None:
        m = t.take(r"\b(?:на|в|за)\s+(эт\w+|следующ\w+|прошл\w+)\s+(недел\w+|месяц\w*)\b")
        if m:
            which, unit = m.group(1), m.group(2)
            shift = 1 if which.startswith("след") else -1 if which.startswith("прошл") else 0
            if unit.startswith("недел"):
                monday = today - timedelta(days=today.weekday()) + timedelta(weeks=shift)
                day, day_to = monday, monday + timedelta(days=6)
            else:
                first = add_months(today.replace(day=1), shift)
                day, day_to = first, add_months(first, 1) - timedelta(days=1)

    # --- конкретные даты
    if day is None:
        m = t.take(r"\b(\d{1,2})\s+" + MONTH_RE + r"(?:\s+(\d{4}))?\b")
        if m:
            mon = _month_index(m.group(2))
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                day = date(year, mon, int(m.group(1)))
                if not m.group(3) and day < today:
                    day = date(year + 1, mon, int(m.group(1)))
            except ValueError:
                day = None
    if day is None:
        m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b(?!\s*:)", t.s)
        if m and 1 <= int(m.group(2)) <= 12:
            try:
                year = int(m.group(3)) if m.group(3) else today.year
                year += 2000 if year < 100 else 0
                cand = date(year, int(m.group(2)), int(m.group(1)))
                if not m.group(3) and cand < today:
                    cand = date(year + 1, cand.month, cand.day)
                day = cand
                t.s = t.s[:m.start()] + " " + t.s[m.end():]
            except ValueError:
                pass
    if day is None:
        for word, shift in (("послезавтра", 2), ("завтра", 1), ("сегодня", 0), ("вчера", -1)):
            if t.take(r"\b" + word + r"\b"):
                day = today + timedelta(days=shift)
                break
    if day is None:
        m = t.take(r"\b(?:в|во|на|к|до)\s+(?:(следующ\w+|ближайш\w+)\s+)?" + WD_RE + r"\b")
        if m:
            day = _next_weekday(today, _weekday_index(m.group(2)))
            if m.group(1) and m.group(1).startswith("следующ") and day.isocalendar()[1] == today.isocalendar()[1]:
                day += timedelta(days=7)
    if day is None and rec_weekday is not None:
        day = _next_weekday(today, rec_weekday, include_today=True)

    # --- время
    tm: time | None = start_dt.time() if start_dt else None
    if tm is None:
        if t.take(r"\bв полдень\b"):
            tm = time(12, 0)
        elif t.take(r"\bв полночь\b"):
            tm = time(0, 0)
        else:
            m = t.take(r"\b(?:в|к)?\s*(\d{1,2})[:.](\d{2})\s*(утра|вечера|дня|ночи)?\b")
            if m:
                tm = _mk_time(int(m.group(1)), int(m.group(2)), m.group(3))
            else:
                m = t.take(r"\b(?:в|к)\s+(\d{1,2})\s*(?:час\w*)?\s*(утра|вечера|дня|ночи)?(?=\s|$|[,.!?])")
                if m and 0 <= int(m.group(1)) <= 24:
                    tm = _mk_time(int(m.group(1)), 0, m.group(2))
    if tm is None:
        for word, hh in (("утром", 9), ("днем", 13), ("вечером", 19), ("ночью", 23)):
            if t.take(r"\b" + word + r"\b"):
                tm = time(hh, 0)
                break

    # --- команда
    rest = t.s
    is_add = re.search(ADD_VERBS, raw) is not None
    is_find = re.search(FIND_RE, raw) is not None
    is_open = re.search(OPEN_RE, raw) is not None
    is_task = re.search(r"\bзадач\w*\b", raw) is not None or re.search(r"\b(сделать|дело)\b", raw) is not None

    title = _clean_title(rest)
    category = _guess_category(title)
    yearly_hint = any(w in (title.lower() + " ") for w in YEARLY_WORDS)

    if is_open and not is_add:
        return Intent("open", query=title, day=day, day_to=day_to)
    if is_find and not (is_add and title and not re.search(r"\bчто у меня\b", raw)):
        return Intent("find", query=title, day=day, day_to=day_to)

    if is_task and (is_add or title):
        title = _clean_title(re.sub(r"\b(задач\w*|сделать)\b", " ", rest))
        prio = 2 if re.search(r"\b(срочно|важно|важная|высокий)\b", raw) else 1
        title = _clean_title(re.sub(r"\b(срочно|важно|важная|высокий приоритет)\b", " ", title))
        return Intent("add_task", title=title, day=day, priority=prio)

    if is_add or (title and (day or tm)):
        if day is None and tm is not None:
            day = today if datetime.combine(today, tm) > now else today + timedelta(days=1)
        if day is None:
            day = today
        if recurrence == "none" and yearly_hint:
            recurrence = "yearly"
        all_day = tm is None
        if all_day:
            start = datetime.combine(day, time.min)
            end = datetime.combine(day_to or day, time(23, 59))
        else:
            start = datetime.combine(day, tm)
            end = start + (duration or timedelta(hours=1))
        return Intent("add_event", title=title, start=start, end=end, all_day=all_day, recurrence=recurrence,
                      reminder=reminder, explicit_reminder=explicit, category=category)
    return Intent("unknown", query=title)


def _mk_time(h: int, m: int, period: str | None) -> time:
    if period in ("вечера", "дня") and h < 12:
        h += 12
    elif period == "ночи" and h == 12:
        h = 0
    elif period == "утра" and h == 12:
        h = 0
    return time(min(h, 23), min(m, 59))


_CASE_MAP: dict[str, str] = {}


def _remember_case(text: str) -> None:
    """Запоминает исходное написание слов, чтобы имена остались с заглавной буквы."""
    _CASE_MAP.clear()
    for w in re.findall(r"[\w-]+", text):
        _CASE_MAP.setdefault(w.lower().replace("ё", "е"), w)


def _clean_title(s: str) -> str:
    s = re.sub(ADD_VERBS, " ", s)
    s = re.sub(FIND_RE, " ", s)
    s = re.sub(OPEN_RE, " ", s)
    s = re.sub(r"[,;:!?.«»\"“”]+", " ", s)
    words = [w for w in s.split() if w not in NOISE_WORDS]
    while words and words[0] in STOP_EDGE:
        words.pop(0)
    while words and words[-1] in STOP_EDGE:
        words.pop()
    out = " ".join(_CASE_MAP.get(w, w) for w in words)
    return out[:1].upper() + out[1:] if out else ""


def _guess_category(title: str) -> str:
    low = title.lower() + " "
    for cat, words in CATEGORY_WORDS.items():
        if any(w in low for w in words):
            return cat
    return "Другое"


# ------------------------------------------------------------ поиск и выполнение

def _prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def match_event(ev: Event, tokens: list[str]) -> bool:
    """Мягкое сравнение слов запроса со словами события (учитывает русские окончания)."""
    hay = _norm(" ".join((ev.title, ev.description, ev.location, ev.category))).split()
    for tok in tokens:
        ok = False
        for w in hay:
            cp = _prefix(tok, w)
            if cp >= 2 and cp >= 0.6 * min(len(tok), len(w)) and cp >= min(len(tok), len(w)) - 3:
                ok = True
                break
        if not ok:
            return False
    return True


def _tokens(query: str) -> list[str]:
    return [w for w in _norm(query).split() if len(w) >= 3 and w not in NOISE_WORDS and w not in STOP_EDGE]


def _next_occurrence(ev: Event, today: date) -> Occurrence | None:
    occs = expand_event(ev, today, today + timedelta(days=800))
    if occs:
        return occs[0]
    past = expand_event(ev, today - timedelta(days=800), today - timedelta(days=1))
    return past[-1] if past else None


def execute(intent: Intent, host, now: datetime | None = None) -> Reply:
    """Выполняет команду. host: .db, .save_event(ev) -> bool, .save_task(task) -> bool, .default_reminder."""
    now = now or datetime.now()
    today = now.date()
    db = host.db

    if intent.kind == "help":
        return Reply("Я помощник календаря. Примеры:\n"
                     "• «Завтра в 15:00 встреча с Аней, напомни за час»\n"
                     "• «День рождения мамы 12 марта каждый год»\n"
                     "• «Каждый понедельник в 9 планёрка»\n"
                     "• «Добавь задачу купить билеты до пятницы»\n"
                     "• «Что у меня завтра?» · «Найди врача» · «Открой 5 ноября»")

    if intent.kind == "add_event":
        if not intent.title:
            return Reply("Не понял название события. Напишите, например: «Завтра в 15:00 встреча с Аней».")
        rem = intent.reminder
        if rem is None:
            rem = -1 if intent.all_day else host.default_reminder
        ev = Event(title=intent.title, start=intent.start, end=intent.end, all_day=intent.all_day,
                   category=intent.category, reminder=rem, recurrence=intent.recurrence)
        if not host.save_event(ev):
            return Reply("Не удалось сохранить событие.")
        extra = []
        if ev.recurrence != "none":
            extra.append({"daily": "каждый день", "weekly": "каждую неделю", "monthly": "каждый месяц",
                          "yearly": "каждый год"}[ev.recurrence])
        if rem >= 0:
            extra.append("напомню " + ("в момент начала" if rem == 0 else
                                       "за 1 день" if rem == 1440 else "за 1 час" if rem == 60 else f"за {rem} мин"))
        when = fmt_date_long(ev.start.date()) + ("" if ev.all_day else f", {ev.start:%H:%M}")
        return Reply(f"Готово: «{ev.title}» — {when}" + (f" ({', '.join(extra)})" if extra else "") + ".",
                     open_date=ev.start.date(), changed=True)

    if intent.kind == "add_task":
        if not intent.title:
            return Reply("Не понял, какую задачу добавить. Например: «Добавь задачу купить билеты до пятницы».")
        task = Task(intent.title, due=intent.day, priority=intent.priority)
        if not host.save_task(task):
            return Reply("Не удалось сохранить задачу.")
        due = f" на {fmt_date_long(task.due)}" if task.due else ""
        return Reply(f"Задача добавлена: «{task.title}»{due}.", changed=True)

    if intent.kind in ("find", "open"):
        tokens = _tokens(intent.query)
        if intent.day and not tokens:
            end = intent.day_to or intent.day
            occs = db.events_in_range(intent.day, end)
            tasks = [t for t in db.all_tasks() if t.due and intent.day <= t.due <= end and not t.done]
            if intent.kind == "open":
                return Reply(f"Открываю {fmt_date_long(intent.day)}.", open_date=intent.day)
            if not occs and not tasks:
                return Reply("На этот период ничего не запланировано.", open_date=intent.day)
            head = relative_day(intent.day) or fmt_date_long(intent.day)
            head = head if end == intent.day else f"{intent.day:%d.%m} – {end:%d.%m}"
            return Reply(f"{head}: {count_text(len(occs), EVENT_FORMS)}"
                         + (f", {count_text(len(tasks), TASK_FORMS)}" if tasks else "") + ".",
                         items=occs + tasks, open_date=intent.day)
        if not tokens:
            occs = db.events_in_range(today, today)
            if not occs:
                return Reply("Сегодня ничего не запланировано.", open_date=today)
            return Reply(f"Сегодня: {count_text(len(occs), EVENT_FORMS)}.", items=occs, open_date=today)
        found = []
        for ev in db.all_events():
            if match_event(ev, tokens):
                occ = _next_occurrence(ev, today)
                if occ:
                    found.append(occ)
        if intent.day:
            end = intent.day_to or intent.day
            found = [o for o in found if o.first_day <= end and o.last_day >= intent.day]
        found.sort(key=lambda o: (o.first_day < today, abs((o.first_day - today).days)))
        tasks = [t for t in db.all_tasks() if all(any(_prefix(tok, w) >= max(2, min(len(tok), len(w)) - 3)
                                                      for w in _norm(t.title).split()) for tok in tokens)][:5]
        if not found and not tasks:
            return Reply(f"Ничего не нашёл по запросу «{intent.query}». Попробуйте одно ключевое слово.")
        first = found[0] if found else None
        if intent.kind == "open" and first:
            return Reply(f"Открываю «{first.event.title}» — {fmt_date_long(first.first_day)}.",
                         open_date=first.first_day, items=[first])
        text = f"Нашёл: {count_text(len(found), EVENT_FORMS)}" + (f", {count_text(len(tasks), TASK_FORMS)}"
                                                                  if tasks else "") + "."
        return Reply(text, items=found[:6] + tasks, open_date=first.first_day if first else None)

    return Reply("Не совсем понял. Скажите, например: «Завтра в 15:00 встреча с Аней» или «Что у меня сегодня?». "
                 "Напишите «помощь», чтобы увидеть примеры.")


def describe_item(item) -> str:
    """Короткая строка для списка результатов в чате."""
    if isinstance(item, Occurrence):
        return f"{fmt_date_long(item.first_day)} · {fmt_occurrence_time(item)} · {item.event.title}"
    due = f" · до {item.due:%d.%m}" if item.due else ""
    return f"Задача · {item.title}{due}"
