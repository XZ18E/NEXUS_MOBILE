"""Сетка месяца (используется и в главном экране, и в выборе даты) и окна выбора даты/времени."""
from __future__ import annotations

from datetime import date, time, timedelta

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, RoundedRectangle, Translate
from kivy.properties import NumericProperty
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from models import MONTHS_NOM, WEEKDAYS_SHORT, add_months
from ui_kit import Btn, ChoiceGrid, IconBtn, Lbl, Sheet, theme, with_alpha
from kivy.utils import get_color_from_hex as hx


class DayCell(ButtonBehavior, FloatLayout):
    def __init__(self, d: date, in_month: bool, today: bool, selected: bool, colors: list[str], pending: int, **kw):
        super().__init__(**kw)
        self.date = d
        self.num = Label(text=str(d.day), font_size=sp(15), bold=today or selected,
                         color=(1, 1, 1, 1) if today else theme.c("text" if in_month else "faint"),
                         size_hint=(1, None), height=dp(40), pos_hint={"x": 0, "top": 1})
        self.add_widget(self.num)
        self._state = (in_month, today, selected, colors[:3], pending)
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        in_month, today, selected, colors, pending = self._state
        self.canvas.before.clear()
        with self.canvas.before:
            if selected:
                Color(*with_alpha(theme.c("accent"), .2))
                RoundedRectangle(pos=(self.x + dp(2), self.y + dp(2)), size=(self.width - dp(4), self.height - dp(4)),
                                 radius=[dp(12)])
                Color(*theme.c("accent"))
                Line(rounded_rectangle=(self.x + dp(2), self.y + dp(2), self.width - dp(4), self.height - dp(4), dp(12)),
                     width=1.3)
            if today:
                d = dp(30)
                Color(*theme.c("accent"))
                # центр кружка совпадает с центром подписи с числом (верх ячейки минус половина высоты подписи)
                Ellipse(pos=(self.center_x - d / 2, self.top - dp(20) - d / 2), size=(d, d))
            n = len(colors) + (1 if pending else 0)
            if n:
                r, gap = dp(2.6), dp(4)
                total = n * 2 * r + (n - 1) * gap
                x = self.center_x - total / 2
                for col in colors:
                    Color(*hx(col))
                    Ellipse(pos=(x, self.y + dp(7)), size=(2 * r, 2 * r))
                    x += 2 * r + gap
                if pending:
                    Color(*theme.c("warning"))
                    Line(circle=(x + r, self.y + dp(7) + r, r), width=1.2)


class MonthGrid(BoxLayout):
    """Шапка дней недели + 6 строк по 7 дней. Поддерживает свайп влево/вправо."""

    slide = NumericProperty(0)

    def __init__(self, on_select, on_swipe=None, cell_h: float = 50, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(24) + 6 * dp(cell_h), **kw)
        with self.canvas.before:
            PushMatrix()
            self._tr = Translate()
        with self.canvas.after:
            PopMatrix()
        self.on_select, self.on_swipe, self.cell_h = on_select, on_swipe, cell_h
        self._down = None
        self.head = GridLayout(cols=7, size_hint_y=None, height=dp(24))
        self.grid = GridLayout(cols=7, rows=6)
        self.add_widget(self.head)
        self.add_widget(self.grid)

    def set(self, year: int, month: int, selected: date, first_weekday: int, dots: dict | None = None,
            pending: dict | None = None) -> None:
        dots, pending = dots or {}, pending or {}
        self.head.clear_widgets()
        for i in range(7):
            idx = (first_weekday + i) % 7
            self.head.add_widget(Lbl(WEEKDAYS_SHORT[idx].upper(), 11, "accent2" if idx >= 5 else "faint", bold=True,
                                     halign="center"))
        first = date(year, month, 1)
        start = first - timedelta(days=(first.weekday() - first_weekday) % 7)
        today = date.today()
        self.grid.clear_widgets()
        for i in range(42):
            d = start + timedelta(days=i)
            cell = DayCell(d, d.month == month, d == today, d == selected, dots.get(d, []), pending.get(d, 0))
            cell.bind(on_release=lambda c: self.on_select(c.date))
            self.grid.add_widget(cell)
        self.first_visible, self.last_visible = start, start + timedelta(days=41)

    def on_slide(self, _inst, value):
        self._tr.x = value

    def animate_in(self, direction: int) -> None:
        """Сетка «выезжает» со стороны, куда листаем."""
        Animation.cancel_all(self)
        self.opacity, self.slide = 0, direction * dp(70)
        Animation(slide=0, opacity=1, d=.3, t="out_cubic").start(self)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._down = touch.pos
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self._down and self.on_swipe:
            dx, dy = touch.pos[0] - self._down[0], touch.pos[1] - self._down[1]
            self._down = None
            if abs(dx) > dp(70) and abs(dy) < dp(45):
                self.on_swipe(1 if dx < 0 else -1)
        return super().on_touch_up(touch)


class DatePicker(Sheet):
    def __init__(self, current: date, first_weekday: int, on_pick, allow_clear: bool = False, title="Выбор даты"):
        super().__init__(title, .74)
        self.view = date(current.year, current.month, 1)
        self.current, self.fw, self.on_pick = current, first_weekday, on_pick
        nav = BoxLayout(size_hint_y=None, height=dp(48))
        left, right = IconBtn("chev_l", "text"), IconBtn("chev_r", "text")
        left.bind(on_release=lambda *_: self.shift(-1))
        right.bind(on_release=lambda *_: self.shift(1))
        self.title = Lbl("", 17, bold=True, halign="center")
        nav.add_widget(left)
        nav.add_widget(self.title)
        nav.add_widget(right)
        self.body.add_widget(nav)
        self.grid = MonthGrid(self.pick, self.shift, cell_h=46)
        self.body.add_widget(self.grid)
        self.redraw()
        if allow_clear:
            clear = Btn("Без даты")
            clear.bind(on_release=lambda *_: (self.dismiss(), on_pick(None)))
            self.footer.add_widget(clear)
        cancel = Btn("Отмена")
        cancel.bind(on_release=lambda *_: self.dismiss())
        self.footer.add_widget(cancel)

    def shift(self, step: int) -> None:
        self.view = add_months(self.view, step)
        self.redraw()

    def redraw(self) -> None:
        self.title.text = f"{MONTHS_NOM[self.view.month - 1].capitalize()} {self.view.year}"
        self.grid.set(self.view.year, self.view.month, self.current, self.fw)

    def pick(self, d: date) -> None:
        self.dismiss()
        self.on_pick(d)


class TimePicker(Sheet):
    def __init__(self, current: time, on_pick):
        super().__init__("Выбор времени", .8)
        self.hour, self.minute, self.on_pick = current.hour, (current.minute // 5) * 5, on_pick
        self.caption("ЧАСЫ")
        self.hours = ChoiceGrid([(h, f"{h:02d}") for h in range(24)], self.hour, 6, self._set_hour, row_h=44)
        self.body.add_widget(self.hours)
        self.caption("МИНУТЫ")
        self.mins = ChoiceGrid([(m, f"{m:02d}") for m in range(0, 60, 5)], self.minute, 6, self._set_min, row_h=44)
        self.body.add_widget(self.mins)
        cancel = Btn("Отмена")
        cancel.bind(on_release=lambda *_: self.dismiss())
        ok = Btn("Готово", "primary")
        ok.bind(on_release=lambda *_: (self.dismiss(), self.on_pick(time(self.hour, self.minute))))
        self.footer.add_widget(cancel)
        self.footer.add_widget(ok)

    def _set_hour(self, h):
        self.hour = h

    def _set_min(self, m):
        self.minute = m


class MonthPager(StencilView):
    """Две сетки месяца едут рядом: старая уезжает, новая заезжает (как в системных календарях)."""

    def __init__(self, make_grid, cell_h: float = 50, **kw):
        super().__init__(size_hint_y=None, height=dp(24) + 6 * dp(cell_h), **kw)
        self.make_grid = make_grid
        self.current: MonthGrid | None = None
        self._old: MonthGrid | None = None
        self.bind(pos=self._relayout, size=self._relayout)

    def _relayout(self, *_):
        for g in (self.current,):
            if g is not None and not self._old:
                g.size = self.size
                g.pos = self.pos

    def _finish(self) -> None:
        """Мгновенно завершает идущую анимацию."""
        if self._old is not None:
            Animation.cancel_all(self._old)
            self.remove_widget(self._old)
            self._old = None
        if self.current is not None:
            Animation.cancel_all(self.current)
            self.current.opacity = 1
            self.current.size, self.current.pos = self.size, self.pos

    def show(self, year: int, month: int, direction: int = 0) -> None:
        self._finish()
        grid = self.make_grid(year, month)
        grid.size_hint = (None, None)
        grid.size = self.size
        if self.current is None or direction == 0 or self.width < 10:
            if self.current is not None:
                self.remove_widget(self.current)
            grid.pos = self.pos
            self.add_widget(grid)
            self.current = grid
            return
        old, self._old = self.current, self.current
        grid.pos = (self.x + direction * self.width, self.y)
        grid.opacity = .0
        self.add_widget(grid)
        self.current = grid
        w = self.width

        def go(dt):
            t = "in_out_cubic"
            Animation(x=self.x - direction * w * .6, opacity=0, d=.40, t=t).start(old)
            a = Animation(x=self.x, opacity=1, d=.40, t=t)
            a.bind(on_complete=lambda *_: self._done(old))
            a.start(grid)
        Clock.schedule_once(go, 0)      # анимация стартует со следующего кадра, когда сетка уже построена

    def _done(self, old) -> None:
        if self._old is old:
            self.remove_widget(old)
            self._old = None
            self.current.pos, self.current.size = self.pos, self.size
