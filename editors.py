"""Окна создания и редактирования событий и задач."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hx

from models import (CATEGORIES, EXTRA_COLORS, MONTHS_SHORT, PRIORITY_NAMES, RECURRENCE_OPTIONS, REMINDER_OPTIONS,
                    Event, Task, validate_event)
from pickers import DatePicker, TimePicker
from ui_kit import Btn, ChoiceGrid, Field, Lbl, Sheet, confirm, theme


def fmt_date(d: date) -> str:
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year}"


class Swatch(ButtonBehavior, Widget):
    def __init__(self, color: str, **kw):
        super().__init__(**kw)
        self.hex, self.selected = color, False
        self.bind(pos=self._draw, size=self._draw)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        d = min(self.width, self.height) * .62
        with self.canvas:
            Color(*hx(self.hex))
            Ellipse(pos=(self.center_x - d / 2, self.center_y - d / 2), size=(d, d))
            if self.selected:
                Color(*theme.c("text"))
                Line(circle=(self.center_x, self.center_y, d / 2 + dp(4)), width=1.6)


class EventEditor(Sheet):
    def __init__(self, app, event: Event | None = None, start: datetime | None = None):
        super().__init__("Редактирование события" if event else "Новое событие")
        self.app, self.event = app, event
        if event:
            s, e = event.start, event.end
        else:
            s = start or app.default_start()
            e = s + timedelta(hours=1)
        self.start, self.end = s, e
        self.duration = e - s
        self.all_day = bool(event and event.all_day)
        self.category = event.category if event and event.category in CATEGORIES else "Другое"
        self.color = event.display_color if event else CATEGORIES[self.category]
        self.color_touched = bool(event and event.color)
        self.reminder = event.reminder if event else int(app.db.get_setting("default_reminder", "15"))
        self.recurrence = event.recurrence if event else "none"
        self.until: date | None = event.recurrence_until if event else None

        b = self.body
        self.caption("НАЗВАНИЕ")
        self.title_in = Field("Название события", text=event.title if event else "")
        b.add_widget(self.title_in)

        self.caption("КАТЕГОРИЯ")
        self.cat_grid = ChoiceGrid([(k, k) for k in CATEGORIES], self.category, 3, self._cat_changed)
        b.add_widget(self.cat_grid)

        self.caption("ЦВЕТ")
        row = BoxLayout(size_hint_y=None, height=dp(44))
        self.swatches = []
        for col in list(CATEGORIES.values()) + EXTRA_COLORS:
            sw = Swatch(col)
            sw.bind(on_release=lambda w: self._pick_color(w.hex))
            row.add_widget(sw)
            self.swatches.append(sw)
        b.add_widget(row)
        self._sync_swatches()

        self.allday_btn = Btn("Событие на весь день", "chip", 14, size_hint_y=None, height=dp(44))
        self.allday_btn.set_active(self.all_day)
        self.allday_btn.bind(on_release=lambda *_: self._toggle_all_day())
        b.add_widget(self.allday_btn)

        self.caption("НАЧАЛО")
        self.sd, self.st, r1 = self._dt_row(True)
        b.add_widget(r1)
        self.caption("ОКОНЧАНИЕ")
        self.ed, self.et, r2 = self._dt_row(False)
        b.add_widget(r2)

        self.caption("МЕСТО ПРОВЕДЕНИЯ")
        self.loc_in = Field("Где пройдёт событие", text=event.location if event else "")
        b.add_widget(self.loc_in)

        self.caption("НАПОМИНАНИЕ")
        self.rem_grid = ChoiceGrid(REMINDER_OPTIONS, self.reminder, 2, lambda v: setattr(self, "reminder", v))
        b.add_widget(self.rem_grid)

        self.caption("ПОВТОРЕНИЕ")
        self.rec_grid = ChoiceGrid(RECURRENCE_OPTIONS, self.recurrence, 2, self._rec_changed)
        b.add_widget(self.rec_grid)
        self.until_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.until_btn = Btn("", "default", 14)
        self.until_btn.bind(on_release=lambda *_: self._pick_until())
        self.until_clear = Btn("Сбросить", "ghost", 13, size_hint_x=.35)
        self.until_clear.bind(on_release=lambda *_: self._set_until(None))
        self.until_row.add_widget(self.until_btn)
        self.until_row.add_widget(self.until_clear)
        b.add_widget(self.until_row)

        self.caption("ОПИСАНИЕ")
        self.desc_in = Field("Заметки, ссылка, детали…", multiline=True, text=event.description if event else "")
        b.add_widget(self.desc_in)
        self.error = Lbl("", 13, "danger", wrap=True)
        b.add_widget(self.error)

        if event:
            delete = Btn("Удалить", "danger", size_hint_x=.4)
            delete.bind(on_release=lambda *_: self._delete())
            self.footer.add_widget(delete)
        save = Btn("Сохранить", "primary")
        save.bind(on_release=lambda *_: self._save())
        self.footer.add_widget(save)
        self._refresh()

    # ---- построение
    def _dt_row(self, is_start: bool):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        d = Btn("", "default", 14, size_hint_x=.62)
        t = Btn("", "default", 14, size_hint_x=.38)
        d.bind(on_release=lambda *_: self._pick_date(is_start))
        t.bind(on_release=lambda *_: self._pick_time(is_start))
        row.add_widget(d)
        row.add_widget(t)
        return d, t, row

    def _refresh(self) -> None:
        self.sd.text, self.ed.text = fmt_date(self.start.date()), fmt_date(self.end.date())
        self.st.text, self.et.text = f"{self.start:%H:%M}", f"{self.end:%H:%M}"
        for t in (self.st, self.et):
            t.opacity = 0 if self.all_day else 1
            t.disabled = self.all_day
            t.size_hint_x = 0 if self.all_day else .38
        self.until_btn.text = "Повторять до: " + (fmt_date(self.until) if self.until else "без ограничения")
        show_until = self.recurrence != "none"
        self.until_row.opacity = 1 if show_until else 0
        self.until_row.height = dp(48) if show_until else 0
        self.until_row.disabled = not show_until

    def _sync_swatches(self) -> None:
        for sw in self.swatches:
            sw.set_selected(sw.hex.lower() == self.color.lower())

    # ---- реакции
    def _cat_changed(self, cat: str) -> None:
        self.category = cat
        if not self.color_touched:
            self.color = CATEGORIES[cat]
            self._sync_swatches()

    def _pick_color(self, col: str) -> None:
        self.color, self.color_touched = col, True
        self._sync_swatches()

    def _toggle_all_day(self) -> None:
        self.all_day = not self.all_day
        self.allday_btn.set_active(self.all_day)
        self._refresh()

    def _rec_changed(self, key: str) -> None:
        self.recurrence = key
        self._refresh()

    def _set_until(self, d) -> None:
        self.until = d
        self._refresh()

    def _pick_until(self) -> None:
        DatePicker(self.until or self.start.date(), self.app.first_weekday, self._set_until, True,
                   "Повторять до").open()

    def _pick_date(self, is_start: bool) -> None:
        cur = (self.start if is_start else self.end).date()

        def done(d: date):
            if is_start:
                self.start = datetime.combine(d, self.start.time())
                self.end = self.start + self.duration
            else:
                self.end = datetime.combine(d, self.end.time())
                self.duration = self.end - self.start
            self._refresh()
        DatePicker(cur, self.app.first_weekday, done).open()

    def _pick_time(self, is_start: bool) -> None:
        cur = (self.start if is_start else self.end).time()

        def done(t: time):
            if is_start:
                self.start = datetime.combine(self.start.date(), t)
                self.end = self.start + self.duration       # конец сдвигается вместе с началом
            else:
                self.end = datetime.combine(self.end.date(), t)
                self.duration = self.end - self.start
            self._refresh()
        TimePicker(cur, done).open()

    def _collect(self) -> Event:
        s, e = self.start, self.end
        if self.all_day:
            s = datetime.combine(s.date(), time.min)
            e = datetime.combine(e.date(), time(23, 59))
        color = "" if self.color.lower() == CATEGORIES[self.category].lower() else self.color
        return Event(id=self.event.id if self.event else None, title=self.title_in.text.strip(),
                     description=self.desc_in.text.strip(), start=s, end=e, all_day=self.all_day,
                     category=self.category, color=color, location=self.loc_in.text.strip(), reminder=self.reminder,
                     recurrence=self.recurrence,
                     recurrence_until=self.until if self.recurrence != "none" else None)

    def _save(self) -> None:
        ev = self._collect()
        problem = validate_event(ev)
        if problem:
            self.error.text = problem
            self.scroll.scroll_to(self.error)
            return
        if self.app.save_event(ev):
            self.dismiss()

    def _delete(self) -> None:
        extra = " Вместе с ним исчезнут все повторения." if self.event.recurrence != "none" else ""
        confirm("Удалить событие?", f"«{self.event.title}» будет удалено без возможности восстановления.{extra}",
                lambda: (self.app.delete_event(self.event.id), self.dismiss()))


class TaskEditor(Sheet):
    def __init__(self, app, task: Task | None = None, due: date | None = None):
        super().__init__("Редактирование задачи" if task else "Новая задача", .8)
        self.app, self.task = app, task
        self.due = task.due if task else due
        self.priority = task.priority if task else 1
        b = self.body
        self.caption("НАЗВАНИЕ")
        self.title_in = Field("Что нужно сделать?", text=task.title if task else "")
        b.add_widget(self.title_in)
        self.caption("ПРИОРИТЕТ")
        b.add_widget(ChoiceGrid([(k, v) for k, v in PRIORITY_NAMES.items()], self.priority, 3,
                                lambda v: setattr(self, "priority", v)))
        self.caption("СРОК ВЫПОЛНЕНИЯ")
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.due_btn = Btn("", "default", 14)
        self.due_btn.bind(on_release=lambda *_: self._pick_due())
        clear = Btn("Без срока", "ghost", 13, size_hint_x=.35)
        clear.bind(on_release=lambda *_: self._set_due(None))
        row.add_widget(self.due_btn)
        row.add_widget(clear)
        b.add_widget(row)
        self.caption("ОПИСАНИЕ")
        self.desc_in = Field("Подробности (необязательно)", multiline=True, text=task.description if task else "")
        b.add_widget(self.desc_in)
        self.error = Lbl("", 13, "danger", wrap=True)
        b.add_widget(self.error)
        if task:
            delete = Btn("Удалить", "danger", size_hint_x=.4)
            delete.bind(on_release=lambda *_: confirm("Удалить задачу?", f"«{task.title}» будет удалена.",
                                                      lambda: (app.delete_task(task.id), self.dismiss())))
            self.footer.add_widget(delete)
        save = Btn("Сохранить", "primary")
        save.bind(on_release=lambda *_: self._save())
        self.footer.add_widget(save)
        self._set_due(self.due)

    def _set_due(self, d) -> None:
        self.due = d
        self.due_btn.text = fmt_date(d) if d else "Срок не задан"

    def _pick_due(self) -> None:
        DatePicker(self.due or date.today(), self.app.first_weekday, self._set_due, True, "Срок выполнения").open()

    def _save(self) -> None:
        title = self.title_in.text.strip()
        if not title:
            self.error.text = "Введите название задачи."
            return
        t = self.task or Task(title)
        t.title, t.due, t.priority, t.description = title, self.due, self.priority, self.desc_in.text.strip()
        if self.app.save_task(t):
            self.dismiss()
