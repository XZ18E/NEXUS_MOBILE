"""Экраны мобильной версии: календарь, задачи, статистика, настройки."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hx

from models import (CATEGORIES, EVENT_FORMS, MONTHS_NOM, MONTHS_SHORT, PRIORITY_COLORS, PRIORITY_NAMES,
                    REMINDER_OPTIONS, TASK_FORMS, Event, Task, count_text, fmt_date_long, fmt_date_short,
                    fmt_occurrence_time, month_title, relative_day, add_months)
from ui_kit import (Btn, Card, ChoiceGrid, Dot, Field, Icon, IconBtn, Lbl, Spacer, fade_in, stagger, theme, vbox,
                    with_alpha, message)
from pickers import MonthGrid


# =============================================================== общие карточки

class CheckCircle(ButtonBehavior, Widget):
    def __init__(self, checked: bool, color: str, **kw):
        super().__init__(size_hint=(None, None), size=(dp(44), dp(44)), **kw)
        self.checked, self.hex = checked, color
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        r = dp(11)
        with self.canvas:
            if self.checked:
                Color(*theme.c("accent"))
                Ellipse(pos=(self.center_x - r, self.center_y - r), size=(2 * r, 2 * r))
                Color(1, 1, 1, 1)
                Line(points=[self.center_x - r * .45, self.center_y, self.center_x - r * .1, self.center_y - r * .35,
                             self.center_x + r * .5, self.center_y + r * .4], width=dp(1.8), cap="round", joint="round")
            else:
                Color(*hx(self.hex))
                Line(circle=(self.center_x, self.center_y, r), width=dp(1.8))


class EventCard(ButtonBehavior, Card):
    def __init__(self, app, occ, show_date: bool = False, **kw):
        super().__init__(fill="surface2", radius=16, orientation="horizontal", size_hint_y=None, height=dp(78),
                         padding=[dp(12), dp(10), dp(12), dp(10)], spacing=dp(12), **kw)
        ev = occ.event
        self.app, self.event = app, ev
        bar = Widget(size_hint=(None, 1), width=dp(4))
        with bar.canvas:
            Color(*hx(ev.display_color))
            rr = RoundedRectangle(pos=bar.pos, size=bar.size, radius=[dp(2)])
        bar.bind(pos=lambda w, p: setattr(rr, "pos", p), size=lambda w, s: setattr(rr, "size", s))
        self.add_widget(bar)
        col = BoxLayout(orientation="vertical", spacing=dp(2))
        when = fmt_occurrence_time(occ)
        if show_date:
            when = f"{fmt_date_short(occ.first_day)} · {when}"
        col.add_widget(Lbl(when, 12, ev.display_color, bold=True, size_hint_y=None, height=dp(18)))
        col.add_widget(Lbl(ev.title, 16, "text", bold=True, shorten=True, shorten_from="right"))
        sub = ev.category + (f"  ·  {ev.location}" if ev.location else "") + ("  ·  повтор" if ev.recurrence != "none" else "")
        col.add_widget(Lbl(sub, 12, "muted", size_hint_y=None, height=dp(18), shorten=True, shorten_from="right"))
        self.add_widget(col)
        self.bind(on_release=lambda *_: app.edit_event(ev))


class TaskRow(ButtonBehavior, Card):
    def __init__(self, app, task: Task, **kw):
        super().__init__(fill="surface2", radius=16, orientation="horizontal", size_hint_y=None, height=dp(64),
                         padding=[dp(4), 0, dp(14), 0], spacing=dp(4), **kw)
        self.app, self.task = app, task
        chk = CheckCircle(task.done, PRIORITY_COLORS[task.priority])
        chk.bind(on_release=lambda *_: app.toggle_task(task.id, not task.done))
        self.add_widget(chk)
        col = BoxLayout(orientation="vertical", padding=[0, dp(10), 0, dp(10)])
        title = Lbl(task.title, 15, "faint" if task.done else "text", bold=True, shorten=True, shorten_from="right")
        if task.done:
            title.markup = True
            title.text = f"[s]{task.title}[/s]"
        col.add_widget(title)
        meta = []
        if task.due:
            meta.append(relative_day(task.due) or fmt_date_short(task.due))
        meta.append(PRIORITY_NAMES[task.priority].lower())
        overdue = task.is_overdue()
        col.add_widget(Lbl(("Просрочено · " if overdue else "") + " · ".join(meta), 12,
                           "danger" if overdue else "muted", size_hint_y=None, height=dp(18)))
        self.add_widget(col)
        if task.priority == 2 and not task.done:
            self.add_widget(Dot(PRIORITY_COLORS[2], 9, pos_hint={"center_y": .5}))
        self.bind(on_release=lambda *_: app.edit_task(task))


def empty_state(icon: str, title: str, text: str) -> BoxLayout:
    box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(200), padding=[dp(20), dp(10)],
                    spacing=dp(6))
    ring = Card(fill="accent", radius=32, border=False, fill_alpha=.16, size_hint=(None, None),
                size=(dp(64), dp(64)), pos_hint={"center_x": .5})
    ring.orientation = "vertical"
    ic = Icon(icon, "accent", 30)
    ic.pos_hint = {"center_x": .5, "center_y": .5}
    from kivy.uix.floatlayout import FloatLayout
    fl = FloatLayout()
    fl.add_widget(ic)
    ring.add_widget(fl)
    holder = BoxLayout(size_hint_y=None, height=dp(70))
    holder.add_widget(Widget())
    holder.add_widget(ring)
    holder.add_widget(Widget())
    box.add_widget(holder)
    box.add_widget(Lbl(title, 17, bold=True, halign="center", size_hint_y=None, height=dp(30)))
    box.add_widget(Lbl(text, 13, "muted", wrap=True, halign="center"))
    return box


def page_header(title: str, subtitle: str = "") -> BoxLayout:
    h = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66 if subtitle else 48))
    h.add_widget(Lbl(title, 26, bold=True))
    if subtitle:
        h.add_widget(Lbl(subtitle, 13, "muted", size_hint_y=None, height=dp(20)))
    return h


class ScrollPage(BoxLayout):
    """Страница с прокруткой и отступами под нижнюю панель и кнопку «+»."""

    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.content = vbox(12, [dp(16), dp(10), dp(16), dp(96)])
        self.scroll.add_widget(self.content)
        self.add_widget(self.scroll)


# ===================================================================== календарь

class CalendarScreen(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=[dp(12), dp(6), dp(12), 0], spacing=dp(4), **kw)
        self.app = app
        head = BoxLayout(size_hint_y=None, height=dp(52))
        left, right = IconBtn("chev_l", "text"), IconBtn("chev_r", "text")
        left.bind(on_release=lambda *_: app.shift_month(-1))
        right.bind(on_release=lambda *_: app.shift_month(1))
        self.title = Lbl("", 21, bold=True)
        today = Btn("Сегодня", "default", 13, size_hint=(None, None), size=(dp(92), dp(38)),
                    pos_hint={"center_y": .5})
        today.bind(on_release=lambda *_: app.select(date.today()))
        head.add_widget(left)
        head.add_widget(self.title)
        head.add_widget(today)
        head.add_widget(right)
        self.add_widget(head)

        self.grid = MonthGrid(app.select, app.shift_month, cell_h=48)
        self.add_widget(self.grid)

        self.panel = Card(fill="surface", radius=22, orientation="vertical", padding=[0, dp(8), 0, 0])
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.day = vbox(10, [dp(16), dp(6), dp(16), dp(96)])
        self.scroll.add_widget(self.day)
        self.panel.add_widget(self.scroll)
        self.add_widget(self.panel)

    def refresh(self, direction: int = 0) -> None:
        app, sel = self.app, self.app.selected
        self.title.text = month_title(sel.year, sel.month)
        first = date(sel.year, sel.month, 1)
        start = first - timedelta(days=(first.weekday() - app.first_weekday) % 7)
        end = start + timedelta(days=41)
        dots: dict[date, list[str]] = {}
        for o in app.occurrences(start, end):
            d = max(o.first_day, start)
            while d <= min(o.last_day, end):
                lst = dots.setdefault(d, [])
                if o.event.display_color not in lst:
                    lst.append(o.event.display_color)
                d += timedelta(days=1)
        self.grid.set(sel.year, sel.month, sel, app.first_weekday, dots, app.db.pending_task_counts(start, end))
        if direction:
            self.grid.animate_in(direction)
        self._day_panel()

    def _day_panel(self) -> None:
        app, d = self.app, self.app.selected
        events = app.occurrences(d, d)
        events.sort(key=lambda o: (0 if o.event.all_day else 1, o.start))
        tasks = app.db.tasks_due_on(d)
        c = self.day
        c.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        col = BoxLayout(orientation="vertical")
        rel = relative_day(d)
        col.add_widget(Lbl(fmt_date_long(d), 16, bold=True))
        sub = count_text(len(events), EVENT_FORMS) + (f" · {count_text(len(tasks), TASK_FORMS)}" if tasks else "")
        col.add_widget(Lbl(sub, 12, "muted", size_hint_y=None, height=dp(18)))
        top.add_widget(col)
        if rel:
            chip = Btn(rel, "chip", 12, size_hint=(None, None), size=(dp(88), dp(30)), pos_hint={"center_y": .5})
            chip.set_active(True)
            top.add_widget(chip)
        c.add_widget(top)
        if not events and not tasks:
            c.add_widget(empty_state("calendar", "Свободный день", "На этот день ничего не запланировано.\n"
                                     "Нажмите «+», чтобы добавить событие."))
            return
        cards = []
        for o in events:
            cards.append(EventCard(app, o))
            c.add_widget(cards[-1])
        if tasks:
            c.add_widget(Lbl("ЗАДАЧИ", 11, "faint", bold=True, size_hint_y=None, height=dp(22)))
            for t in tasks:
                cards.append(TaskRow(app, t))
                c.add_widget(cards[-1])
        stagger(cards)


# ======================================================================= задачи

class TasksScreen(ScrollPage):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app, self.status, self.prio = app, "all", -1
        c = self.content
        c.add_widget(page_header("Задачи", "Планируйте дела и отмечайте выполненное"))
        self.stats = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(76))
        c.add_widget(self.stats)
        self.bar = Widget(size_hint_y=None, height=dp(8))
        self.bar.bind(pos=self._draw_bar, size=self._draw_bar)
        self._pct = 0.0
        c.add_widget(self.bar)
        c.add_widget(ChoiceGrid([("all", "Все"), ("active", "Активные"), ("done", "Готово"), ("overdue", "Просроч.")],
                                "all", 4, self._set_status, row_h=40))
        c.add_widget(ChoiceGrid([(-1, "Любой"), (2, "Высокий"), (1, "Средний"), (0, "Низкий")], -1, 4,
                                self._set_prio, row_h=40))
        self.quick = Field("Быстрая задача — нажмите Enter")
        self.quick.bind(on_text_validate=self._quick_add)
        c.add_widget(self.quick)
        self.list = vbox(8)
        c.add_widget(self.list)

    def _set_status(self, v):
        self.status = v
        self.refresh()

    def _set_prio(self, v):
        self.prio = v
        self.refresh()

    def _quick_add(self, inp):
        text = inp.text.strip()
        if text and self.app.save_task(Task(text)):
            inp.text = ""

    def _draw_bar(self, *_):
        self.bar.canvas.clear()
        with self.bar.canvas:
            Color(*theme.c("border"))
            RoundedRectangle(pos=self.bar.pos, size=self.bar.size, radius=[dp(4)])
            if self._pct > 0:
                Color(*theme.c("accent"))
                RoundedRectangle(pos=self.bar.pos, size=(max(dp(8), self.bar.width * self._pct), self.bar.height),
                                 radius=[dp(4)])

    def refresh(self) -> None:
        tasks = self.app.db.all_tasks()
        today = date.today()
        total, done = len(tasks), sum(t.done for t in tasks)
        overdue = sum(t.is_overdue(today) for t in tasks)
        self.stats.clear_widgets()
        for val, cap, col in ((total - done, "Осталось", "accent"), (done, "Выполнено", "success"),
                              (overdue, "Просрочено", "danger")):
            card = Card(fill="surface2", radius=16, orientation="vertical", padding=[dp(14), dp(8)])
            card.add_widget(Lbl(str(val), 24, col, bold=True))
            card.add_widget(Lbl(cap, 12, "muted", size_hint_y=None, height=dp(18)))
            self.stats.add_widget(card)
        self._pct = done / total if total else 0
        self._draw_bar()
        shown = []
        for t in tasks:
            if self.status == "active" and t.done:
                continue
            if self.status == "done" and not t.done:
                continue
            if self.status == "overdue" and not t.is_overdue(today):
                continue
            if self.prio != -1 and t.priority != self.prio:
                continue
            shown.append(t)
        shown.sort(key=lambda t: (t.done, not t.is_overdue(today), t.due or date.max, -t.priority, t.id or 0))
        self.list.clear_widgets()
        if not shown:
            self.list.add_widget(empty_state("tasks", "Задач нет" if not total else "Ничего не найдено",
                                             "Добавьте первую задачу кнопкой «+»." if not total
                                             else "Измените фильтры, чтобы увидеть другие задачи."))
        rows = [TaskRow(self.app, t) for t in shown]
        for r in rows:
            self.list.add_widget(r)
        stagger(rows, .03)


# ==================================================================== статистика

class BarChart(Widget):
    progress = NumericProperty(0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.values: list[int] = []
        self.bind(pos=self._draw, size=self._draw, progress=self._draw)

    def set_values(self, values: list[int]) -> None:
        self.values = values
        self.progress = 0
        Animation(progress=1, d=.7, t="out_cubic").start(self)

    def _draw(self, *_):
        self.canvas.clear()
        if not self.values:
            return
        vmax = max(max(self.values), 4)
        n = len(self.values)
        slot = self.width / n
        bw = min(dp(22), slot * .56)
        with self.canvas:
            Color(*with_alpha(theme.c("border"), .6))
            for k in range(4):
                y = self.y + self.height * k / 3
                Line(points=[self.x, y, self.right, y], width=1, dash_length=dp(3), dash_offset=dp(3))
            for i, v in enumerate(self.values):
                h = max(dp(3), self.height * (v / vmax) * self.progress) if v else dp(3)
                Color(*(theme.c("accent") if v else with_alpha(theme.c("border"), .8)))
                RoundedRectangle(pos=(self.x + slot * (i + .5) - bw / 2, self.y), size=(bw, h), radius=[dp(6)])


class StatsScreen(ScrollPage):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app, self.year = app, date.today().year
        c = self.content
        c.add_widget(page_header("Статистика", "Как вы используете своё время"))
        self.kpi = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(2 * 84 + 10))
        c.add_widget(self.kpi)

        self.chart_card = Card(fill="surface", radius=20, orientation="vertical", size_hint_y=None, height=dp(250),
                               padding=[dp(14), dp(10), dp(14), dp(10)], spacing=dp(6))
        top = BoxLayout(size_hint_y=None, height=dp(40))
        top.add_widget(Lbl("События по месяцам", 15, bold=True))
        prev, nxt = IconBtn("chev_l", "text", 40, 18), IconBtn("chev_r", "text", 40, 18)
        prev.bind(on_release=lambda *_: self._year(-1))
        nxt.bind(on_release=lambda *_: self._year(1))
        self.year_lbl = Lbl("", 15, bold=True, halign="center", size_hint_x=None, width=dp(52))
        top.add_widget(prev)
        top.add_widget(self.year_lbl)
        top.add_widget(nxt)
        self.chart_card.add_widget(top)
        self.chart = BarChart()
        self.chart_card.add_widget(self.chart)
        months = GridLayout(cols=12, size_hint_y=None, height=dp(18))
        for m in MONTHS_SHORT:
            months.add_widget(Lbl(m[:3], 9, "faint", halign="center"))
        self.chart_card.add_widget(months)
        c.add_widget(self.chart_card)

        self.cat_card = Card(fill="surface", radius=20, orientation="vertical", size_hint_y=None,
                             padding=[dp(16), dp(12)], spacing=dp(10))
        self.cat_card.bind(minimum_height=self.cat_card.setter("height"))
        c.add_widget(self.cat_card)

    def _year(self, step: int) -> None:
        self.year += step
        self.refresh()

    def refresh(self) -> None:
        app, today = self.app, date.today()
        self.year_lbl.text = str(self.year)
        occs = [o for o in app.db.events_in_range(date(self.year, 1, 1), date(self.year, 12, 31))
                if o.start.year == self.year]
        counts, by_cat = [0] * 12, {}
        for o in occs:
            counts[o.start.month - 1] += 1
            by_cat[o.event.category] = by_cat.get(o.event.category, 0) + 1
        self.chart.set_values(counts)

        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        tasks = app.db.all_tasks()
        done, overdue = sum(t.done for t in tasks), sum(t.is_overdue(today) for t in tasks)
        items = [(len(app.db.events_in_range(month_start, month_end)), "Событий в этом месяце", "accent"),
                 (len(app.db.events_in_range(today, today + timedelta(days=6))), "На ближайшие 7 дней", "accent2"),
                 (f"{done} из {len(tasks)}" if tasks else "0", "Задач выполнено", "success"),
                 (overdue, "Просроченных задач", "danger")]
        self.kpi.clear_widgets()
        for val, cap, col in items:
            card = Card(fill="surface2", radius=18, orientation="vertical", padding=[dp(14), dp(10)])
            card.add_widget(Lbl(str(val), 26, col, bold=True))
            card.add_widget(Lbl(cap, 12, "muted", size_hint_y=None, height=dp(20)))
            self.kpi.add_widget(card)

        self.cat_card.clear_widgets()
        self.cat_card.add_widget(Lbl("Категории", 15, bold=True, size_hint_y=None, height=dp(26)))
        total = sum(by_cat.values())
        if not total:
            self.cat_card.add_widget(Lbl("В этом году событий нет", 13, "muted", size_hint_y=None, height=dp(24)))
        for name, col in CATEGORIES.items():
            n = by_cat.get(name, 0)
            if not n:
                continue
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(42), spacing=dp(4))
            line = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(8))
            line.add_widget(Dot(col, 10, pos_hint={"center_y": .5}))
            line.add_widget(Lbl(name, 13))
            line.add_widget(Lbl(f"{n} · {n / total * 100:.0f}%", 12, "muted", halign="right", size_hint_x=None,
                                width=dp(90)))
            bar = Widget(size_hint_y=None, height=dp(6))
            frac = n / total

            def draw(w, *_, col=col, frac=frac):
                w.canvas.clear()
                with w.canvas:
                    Color(*theme.c("border"))
                    RoundedRectangle(pos=w.pos, size=w.size, radius=[dp(3)])
                    Color(*hx(col))
                    RoundedRectangle(pos=w.pos, size=(max(dp(6), w.width * frac), w.height), radius=[dp(3)])
            bar.bind(pos=draw, size=draw)
            row.add_widget(line)
            row.add_widget(bar)
            self.cat_card.add_widget(row)


# =================================================================== настройки

class SettingsScreen(ScrollPage):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        c = self.content
        c.add_widget(page_header("Настройки", "Сохраняются автоматически"))

        def section(title: str) -> BoxLayout:
            card = Card(fill="surface", radius=20, orientation="vertical", size_hint_y=None,
                        padding=[dp(16), dp(14)], spacing=dp(10))
            card.bind(minimum_height=card.setter("height"))
            card.add_widget(Lbl(title.upper(), 11, "faint", bold=True, size_hint_y=None, height=dp(20)))
            c.add_widget(card)
            return card

        s = section("Внешний вид")
        s.add_widget(ChoiceGrid([("dark", "Тёмная"), ("light", "Светлая")], theme.name, 2, app.set_theme))

        s = section("Календарь")
        s.add_widget(Lbl("Первый день недели", 14, size_hint_y=None, height=dp(22)))
        s.add_widget(ChoiceGrid([(0, "Понедельник"), (6, "Воскресенье")], app.first_weekday, 2, app.set_first_weekday))
        s.add_widget(Lbl("Напоминание по умолчанию", 14, size_hint_y=None, height=dp(22)))
        s.add_widget(ChoiceGrid(REMINDER_OPTIONS, int(app.db.get_setting("default_reminder", "15")), 2,
                                lambda v: app.db.set_setting("default_reminder", str(v)), row_h=40))

        s = section("Уведомления")
        notif = Btn("Показывать уведомления о событиях", "chip", 14, size_hint_y=None, height=dp(46))
        notif.set_active(app.db.get_setting("notifications", "1") == "1")

        def toggle(*_):
            on = not notif.active
            notif.set_active(on)
            app.db.set_setting("notifications", "1" if on else "0")
        notif.bind(on_release=toggle)
        s.add_widget(notif)
        s.add_widget(Lbl("Напоминания приходят, пока приложение запущено (в том числе свёрнуто).", 12, "muted",
                         wrap=True))

        s = section("Данные")
        s.add_widget(Lbl(str(app.db.path), 11, "muted", wrap=True))
        exp = Btn("Экспорт событий в CSV", size_hint_y=None, height=dp(48))
        exp.bind(on_release=lambda *_: app.export_csv())
        bak = Btn("Резервная копия базы", size_hint_y=None, height=dp(48))
        bak.bind(on_release=lambda *_: app.backup())
        s.add_widget(exp)
        s.add_widget(bak)
        c.add_widget(Lbl("NEXUS Calendar Mobile 1.0 · Kivy · SQLite", 12, "faint", halign="center",
                         size_hint_y=None, height=dp(30)))

    def refresh(self) -> None:
        pass
