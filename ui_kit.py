"""Набор виджетов NEXUS Mobile: тема, карточки, кнопки, поля, иконки и всплывающие листы (Kivy)."""
from __future__ import annotations

import math

from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hx

PALETTES = {
    "dark": dict(bg="#13141A", surface="#1B1D26", surface2="#262935", border="#363A4D", text="#E9EBF3",
                 muted="#A0A6BC", faint="#6C7289", accent="#4D8DFF", accent2="#8B5CF6", danger="#F43F5E",
                 success="#22C55E", warning="#F59E0B"),
    "light": dict(bg="#EEF1F9", surface="#FFFFFF", surface2="#F0F2FA", border="#D9DEEE", text="#1A1D2B",
                  muted="#5A617C", faint="#9299B1", accent="#3B76F0", accent2="#7C3AED", danger="#E11D48",
                  success="#16A34A", warning="#D97706"),
}


class Theme:
    """Простая тема: после смены интерфейс пересобирается целиком (см. NexusApp.rebuild)."""
    name = "dark"

    def apply(self, name: str) -> None:
        self.name = name if name in PALETTES else "dark"
        for k, v in PALETTES[self.name].items():
            setattr(self, k, hx(v))

    def c(self, key, alpha: float | None = None):
        col = list(getattr(self, key)) if isinstance(key, str) and hasattr(self, key) else list(
            hx(key) if isinstance(key, str) else key)
        if alpha is not None:
            col[3] = alpha
        return col


theme = Theme()
theme.apply("dark")


def with_alpha(color: str | list, alpha: float) -> list:
    col = list(hx(color)) if isinstance(color, str) else list(color)
    col[3] = alpha
    return col


# ---------------------------------------------------------------- базовые виджеты

class Card(BoxLayout):
    """Скруглённая карточка с заливкой из темы."""

    def __init__(self, fill: str = "surface", radius: float = 16, border: bool = True, fill_alpha: float = 1.0,
                 **kw):
        super().__init__(**kw)
        self._fill, self._radius, self._border, self._alpha = fill, dp(radius), border, fill_alpha
        with self.canvas.before:
            self._fc = Color(*theme.c(fill, fill_alpha))
            self._fr = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
            self._bc = Color(*(theme.c("border") if border else (0, 0, 0, 0)))
            self._bl = Line(rounded_rectangle=(*self.pos, *self.size, self._radius), width=1)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *_):
        self._fr.pos, self._fr.size = self.pos, self.size
        self._bl.rounded_rectangle = (*self.pos, *self.size, self._radius)

    def set_fill(self, rgba) -> None:
        self._fc.rgba = rgba


def Lbl(text: str = "", size: float = 14, color="text", bold: bool = False, wrap: bool = False,
        halign: str = "left", **kw) -> Label:
    lb = Label(text=text, font_size=sp(size), color=theme.c(color) if isinstance(color, str) and hasattr(theme, color)
               else (hx(color) if isinstance(color, str) else color), bold=bold, halign=halign, valign="middle", **kw)
    if wrap:
        lb.size_hint_y = None
        lb.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        lb.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(2)))
    else:
        lb.bind(size=lambda i, s: setattr(i, "text_size", s))
    return lb


class Btn(ButtonBehavior, Label):
    """Кнопка: kind = default | primary | ghost | danger | chip."""

    def __init__(self, text: str = "", kind: str = "default", fs: float = 14, **kw):
        super().__init__(text=text, font_size=sp(fs), bold=True, **kw)
        self.kind, self.active = kind, False
        self.halign = self.valign = "center"
        self.bind(size=lambda i, s: setattr(i, "text_size", s))
        with self.canvas.before:
            self._c = Color()
            self._r = RoundedRectangle(radius=[dp(14)])
            self._bc = Color()
            self._bl = Line(width=1)
        self.bind(pos=self._upd, size=self._upd, state=self._upd)
        self._upd()

    def set_active(self, on: bool) -> None:
        self.active = on
        self._upd()

    def _upd(self, *_):
        k, down = self.kind, self.state == "down"
        fill, line, txt = theme.c("surface2"), theme.c("border"), theme.c("text")
        if k == "primary":
            fill, line, txt = theme.c("accent"), theme.c("accent"), (1, 1, 1, 1)
        elif k == "ghost":
            fill, line, txt = (0, 0, 0, 0), (0, 0, 0, 0), theme.c("muted")
        elif k == "danger":
            fill, line, txt = with_alpha(theme.c("danger"), .14), with_alpha(theme.c("danger"), .4), theme.c("danger")
        elif k == "chip":
            if self.active:
                fill, line, txt = with_alpha(theme.c("accent"), .25), theme.c("accent"), theme.c("text")
            else:
                txt = theme.c("muted")
        if down:
            fill = [min(1, v + .08) for v in fill[:3]] + [max(fill[3], .6)]
        self._c.rgba, self._bc.rgba, self.color = fill, line, txt
        self._r.pos, self._r.size = self.pos, self.size
        self._bl.rounded_rectangle = (*self.pos, *self.size, dp(14))


class Field(TextInput):
    def __init__(self, hint: str = "", multiline: bool = False, text: str = "", **kw):
        super().__init__(text=text, hint_text=hint, multiline=multiline, background_normal="", background_active="",
                         background_color=(0, 0, 0, 0), foreground_color=theme.c("text"),
                         hint_text_color=theme.c("faint"), cursor_color=theme.c("accent"),
                         selection_color=with_alpha(theme.c("accent"), .35), padding=[dp(14), dp(14), dp(14), dp(10)],
                         font_size=sp(15), size_hint_y=None, height=dp(100) if multiline else dp(48),
                         write_tab=False, **kw)
        with self.canvas.before:
            self._c = Color(*theme.c("surface2"))
            self._r = RoundedRectangle(radius=[dp(14)])
            self._bc = Color(*theme.c("border"))
            self._bl = Line(width=1)
        self.bind(pos=self._upd, size=self._upd, focus=self._upd)
        self._upd()

    def _upd(self, *_):
        self._r.pos, self._r.size = self.pos, self.size
        self._bl.rounded_rectangle = (*self.pos, *self.size, dp(14))
        self._bc.rgba = theme.c("accent") if self.focus else theme.c("border")


class Icon(Widget):
    """Иконки, нарисованные линиями (шрифты с иконками на Android не нужны)."""

    def __init__(self, name: str, color="muted", size: float = 24, **kw):
        super().__init__(size_hint=(None, None), size=(dp(size), dp(size)), **kw)
        self.name, self.color_key = name, color
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def set_color(self, color) -> None:
        self.color_key = color
        self.redraw()

    def redraw(self, *_):
        self.canvas.clear()
        s = min(self.width, self.height) / 24
        ox, oy = self.x, self.y

        def P(x, y):
            return ox + x * s, oy + (24 - y) * s

        def pts(*q):
            return [c for x, y in q for c in P(x, y)]

        col = theme.c(self.color_key) if isinstance(self.color_key, str) else self.color_key
        w = max(1.7 * s, dp(1.6))
        n = self.name
        with self.canvas:
            Color(*col)
            if n == "calendar":
                x, y = P(3.5, 20.5)
                Line(rounded_rectangle=(x, y, 17 * s, 15.5 * s, 3 * s), width=w)
                Line(points=pts((3.5, 10), (20.5, 10)), width=w)
                Line(points=pts((8, 3), (8, 7)), width=w, cap="round")
                Line(points=pts((16, 3), (16, 7)), width=w, cap="round")
            elif n == "tasks":
                cx, cy = P(12, 12)
                Line(circle=(cx, cy, 8.5 * s), width=w)
                Line(points=pts((8, 12.5), (11, 15.5), (16, 9)), width=w, cap="round", joint="round")
            elif n == "stats":
                for x, top in ((6, 13), (12, 5), (18, 10)):
                    Line(points=pts((x, 20), (x, top)), width=2.6 * s, cap="round")
            elif n == "gear":
                cx, cy = P(12, 12)
                Line(circle=(cx, cy, 6.2 * s), width=w)
                Line(circle=(cx, cy, 2.4 * s), width=w)
                for k in range(8):
                    a = math.radians(k * 45)
                    Line(points=pts((12 + 6.2 * math.cos(a), 12 + 6.2 * math.sin(a)),
                                    (12 + 9.6 * math.cos(a), 12 + 9.6 * math.sin(a))), width=w, cap="round")
            elif n == "plus":
                Line(points=pts((12, 5), (12, 19)), width=w * 1.15, cap="round")
                Line(points=pts((5, 12), (19, 12)), width=w * 1.15, cap="round")
            elif n == "chev_l":
                Line(points=pts((14.5, 6), (8.5, 12), (14.5, 18)), width=w, cap="round", joint="round")
            elif n == "chev_r":
                Line(points=pts((9.5, 6), (15.5, 12), (9.5, 18)), width=w, cap="round", joint="round")
            elif n == "check":
                Line(points=pts((5, 12.5), (10, 17.5), (19, 7)), width=w, cap="round", joint="round")
            elif n == "close":
                Line(points=pts((6, 6), (18, 18)), width=w, cap="round")
                Line(points=pts((18, 6), (6, 18)), width=w, cap="round")
            elif n == "trash":
                Line(points=pts((4, 7), (20, 7)), width=w, cap="round")
                Line(points=pts((6, 7), (7, 20), (17, 20), (18, 7)), width=w, cap="round", joint="round")
                Line(points=pts((9, 7), (9, 4), (15, 4), (15, 7)), width=w, cap="round", joint="round")
            elif n == "pin":
                cx, cy = P(12, 9.5)
                Line(circle=(cx, cy, 6 * s), width=w)
                Line(points=pts((8, 14), (12, 21), (16, 14)), width=w, cap="round", joint="round")
            elif n == "sparkle":
                cx, cy = P(12, 12)
                Line(points=pts((12, 3), (14, 10), (21, 12), (14, 14), (12, 21), (10, 14), (3, 12), (10, 10), (12, 3)),
                     width=w, joint="round", cap="round")
                Line(points=pts((19, 3.5), (19, 7)), width=w, cap="round")
                Line(points=pts((17.2, 5.2), (20.8, 5.2)), width=w, cap="round")
            elif n == "send":
                Line(points=pts((4, 12), (20, 4), (14, 20), (11.5, 13), (4, 12)), width=w, joint="round", cap="round")
            elif n == "repeat":
                cx, cy = P(12, 12)
                Line(circle=(cx, cy, 7 * s, 90, 360 + 0), width=w)


class IconBtn(ButtonBehavior, Widget):
    def __init__(self, icon: str, color="muted", box: float = 44, glyph: float = 22, **kw):
        super().__init__(size_hint=(None, None), size=(dp(box), dp(box)), **kw)
        self.icon = Icon(icon, color, glyph)
        self.add_widget(self.icon)
        self.bind(pos=self._place, size=self._place)
        self._place()

    def _place(self, *_):
        self.icon.center = self.center


class Dot(Widget):
    def __init__(self, color, size: float = 10, **kw):
        super().__init__(size_hint=(None, None), size=(dp(size), dp(size)), **kw)
        with self.canvas:
            Color(*(hx(color) if isinstance(color, str) else color))
            self._e = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._e, "pos", self.pos), size=lambda *_: setattr(self._e, "size", self.size))


class Spacer(Widget):
    def __init__(self, h: float = 8, **kw):
        super().__init__(size_hint_y=None, height=dp(h), **kw)


def vbox(spacing: float = 10, padding=0, **kw) -> BoxLayout:
    b = BoxLayout(orientation="vertical", spacing=dp(spacing), size_hint_y=None, padding=padding, **kw)
    b.bind(minimum_height=b.setter("height"))
    return b


def stagger(widgets, step: float = .04, d: float = .26, max_items: int = 14) -> None:
    """Плавное поочерёдное появление элементов списка."""
    from kivy.clock import Clock
    for i, w in enumerate(widgets):
        w.opacity = 0
        delay = step * min(i, max_items)
        Clock.schedule_once(lambda dt, w=w: Animation(opacity=1, d=d, t="out_quad").start(w), delay)


def fade_in(widget, d: float = .25) -> None:
    widget.opacity = 0
    Animation(opacity=1, d=d, t="out_quad").start(widget)


class ChoiceGrid(GridLayout):
    """Сетка кнопок-вариантов (категории, напоминания, приоритеты)."""

    def __init__(self, options, value, cols: int = 3, on_change=None, row_h: float = 42, **kw):
        rows = math.ceil(len(options) / cols)
        super().__init__(cols=cols, spacing=dp(8), size_hint_y=None, height=rows * dp(row_h) + (rows - 1) * dp(8), **kw)
        self.value, self.on_change, self._btns = value, on_change, {}
        for key, label in options:
            b = Btn(label, "chip", 13, size_hint_y=None, height=dp(row_h))
            b.bind(on_release=lambda w, k=key: self.select(k))
            self.add_widget(b)
            self._btns[key] = b
        self._sync()

    def select(self, key) -> None:
        self.value = key
        self._sync()
        if self.on_change:
            self.on_change(key)

    def _sync(self) -> None:
        for k, b in self._btns.items():
            b.set_active(k == self.value)


# ------------------------------------------------------------ всплывающие листы

class Sheet(ModalView):
    """Модальное окно-карточка с прокручиваемым телом и панелью кнопок."""
    stack: list["Sheet"] = []

    def __init__(self, title: str, height_hint: float = .92, closable: bool = True, **kw):
        super().__init__(size_hint=(.94, height_hint), background="", background_color=(0, 0, 0, 0),
                         overlay_color=(0, 0, 0, .62), auto_dismiss=False, **kw)
        card = Card(orientation="vertical", fill="surface", radius=24, padding=[0, dp(6), 0, dp(12)], spacing=dp(6))
        head = BoxLayout(size_hint_y=None, height=dp(52), padding=[dp(20), 0, dp(6), 0])
        head.add_widget(Lbl(title, 18, bold=True))
        if closable:
            x = IconBtn("close", "muted", 44, 20)
            x.bind(on_release=lambda *_: self.dismiss())
            head.add_widget(x)
        card.add_widget(head)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.body = vbox(12, [dp(20), dp(4), dp(20), dp(8)])
        self.scroll.add_widget(self.body)
        card.add_widget(self.scroll)
        self.footer = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10), padding=[dp(20), 0])
        card.add_widget(self.footer)
        self.add_widget(card)

    def on_open(self):
        Sheet.stack.append(self)
        self.opacity = 0
        Animation(opacity=1, d=.22, t="out_quad").start(self)

    def on_dismiss(self):
        if self in Sheet.stack:
            Sheet.stack.remove(self)

    def caption(self, text: str) -> Label:
        lb = Lbl(text, 12, "muted", bold=True, size_hint_y=None, height=dp(20))
        self.body.add_widget(lb)
        return lb


def confirm(title: str, text: str, on_ok, ok_text: str = "Удалить") -> None:
    sh = Sheet(title, .3, closable=False)
    sh.size_hint = (.88, None)
    sh.height = dp(250)
    sh.body.add_widget(Lbl(text, 14, "muted", wrap=True))
    cancel = Btn("Отмена")
    cancel.bind(on_release=lambda *_: sh.dismiss())
    ok = Btn(ok_text, "danger")
    ok.bind(on_release=lambda *_: (sh.dismiss(), on_ok()))
    sh.footer.add_widget(cancel)
    sh.footer.add_widget(ok)
    sh.open()


def message(title: str, text: str) -> None:
    sh = Sheet(title, .3, closable=False)
    sh.size_hint = (.88, None)
    sh.height = dp(280)
    sh.body.add_widget(Lbl(text, 14, "muted", wrap=True))
    ok = Btn("Понятно", "primary")
    ok.bind(on_release=lambda *_: sh.dismiss())
    sh.footer.add_widget(ok)
    sh.open()
