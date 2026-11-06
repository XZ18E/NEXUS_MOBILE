"""Экран «Помощник»: чат, в котором события и задачи создаются обычными русскими фразами."""
from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

import assistant
from models import Occurrence
from ui_kit import Btn, Card, Field, Icon, IconBtn, Lbl, theme, vbox, stagger

QUICK = ["Что у меня сегодня?", "Что у меня завтра?", "Завтра в 15:00 встреча, напомни за час",
         "День рождения мамы 12 марта каждый год", "Найди врача", "Помощь"]


class _Host:
    """Мост между помощником и приложением."""

    def __init__(self, app):
        self.app = app
        self.db = app.db

    @property
    def default_reminder(self) -> int:
        return int(self.app.db.get_setting("default_reminder", "15"))

    def save_event(self, ev) -> bool:
        return self.app.save_event(ev)

    def save_task(self, t) -> bool:
        return self.app.save_task(t)


class AssistantScreen(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=[dp(12), dp(6), dp(12), dp(8)], spacing=dp(8), **kw)
        self.app, self.host = app, _Host(app)
        self._welcomed = False

        head = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        head.add_widget(Icon("sparkle", "accent", 26, pos_hint={"center_y": .5}))
        col = BoxLayout(orientation="vertical")
        col.add_widget(Lbl("Помощник", 24, bold=True))
        col.add_widget(Lbl("Работает без интернета", 12, "muted", size_hint_y=None, height=dp(16)))
        head.add_widget(col)
        self.add_widget(head)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.chat = vbox(10, [0, dp(4), 0, dp(10)])
        self.scroll.add_widget(self.chat)
        self.add_widget(self.scroll)

        chips = ScrollView(size_hint_y=None, height=dp(44), do_scroll_y=False, bar_width=0)
        row = BoxLayout(size_hint_x=None, spacing=dp(8))
        row.bind(minimum_width=row.setter("width"))
        for q in QUICK:
            b = Btn(q, "chip", 12, size_hint=(None, None), size=(dp(len(q) * 7.4 + 28), dp(38)))
            b.bind(on_release=lambda w, q=q: self.send(q))
            row.add_widget(b)
        chips.add_widget(row)
        self.add_widget(chips)

        bar = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.input = Field("Напишите, что сделать…")
        self.input.bind(on_text_validate=lambda *_: self._send_from_input())
        self.input.size_hint_y = 1
        send = IconBtn("send", (1, 1, 1, 1), 52, 22)
        with send.canvas.before:
            from kivy.graphics import Color, Ellipse
            Color(*theme.c("accent"))
            self._circle = Ellipse(pos=send.pos, size=send.size)
        send.bind(pos=lambda w, p: setattr(self._circle, "pos", p), size=lambda w, s: setattr(self._circle, "size", s))
        send.bind(on_press=lambda *_: self._send_from_input())   # on_press: окно меняет размер, когда прячется клавиатура
        bar.add_widget(self.input)
        bar.add_widget(send)
        self.add_widget(bar)

    def _send_from_input(self) -> None:
        text = self.input.text
        self.send(text)
        # клавиатура остаётся открытой — можно сразу писать следующее сообщение
        Clock.schedule_once(lambda dt: setattr(self.input, "focus", True), .05)

    def refresh(self) -> None:
        if not self._welcomed:
            self._welcomed = True
            self._bubble("Привет! Я помогу с календарём. Скажите, например: «Завтра в 15:00 встреча с Аней, "
                         "напомни за час» или «Что у меня сегодня?».", mine=False)

    # ---- сообщения
    def _bubble(self, text: str, mine: bool) -> BoxLayout:
        row = BoxLayout(size_hint_y=None, padding=[dp(46) if mine else 0, 0, 0 if mine else dp(46), 0])
        row.bind(minimum_height=row.setter("height"))
        card = Card(fill="accent" if mine else "surface2", radius=18, border=not mine, orientation="vertical",
                    size_hint=(1, None), padding=[dp(14), dp(10)])
        card.bind(minimum_height=card.setter("height"))
        lb = Lbl(text, 14, (1, 1, 1, 1) if mine else "text", wrap=True)
        card.add_widget(lb)
        row.add_widget(card)
        self.chat.add_widget(row)
        stagger([row], 0, .24)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), .05)
        return row

    def _items(self, reply: assistant.Reply) -> None:
        if not reply.items:
            return
        box = vbox(6, [0, 0, dp(40), 0])
        for it in reply.items:
            b = Btn(assistant.describe_item(it), "default", 12, size_hint_y=None, height=dp(44))
            b.halign = "left"
            b.padding = (dp(12), 0)
            d = it.first_day if isinstance(it, Occurrence) else getattr(it, "due", None)
            if isinstance(it, Occurrence) or d is not None:
                b.bind(on_release=lambda w, d=d: self.app.open_day(d))
            box.add_widget(b)
        self.chat.add_widget(box)
        stagger(list(box.children)[::-1], .05)

    def send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.input.text = ""
        self._bubble(text, True)
        typing = self._bubble("…", False)
        intent = assistant.parse(text)

        def answer(dt):
            self.chat.remove_widget(typing)
            reply = assistant.execute(intent, self.host)
            self._bubble(reply.text, False)
            self._items(reply)
            if reply.open_date:
                btn = Btn("Показать в календаре", "primary", 13, size_hint=(None, None), size=(dp(210), dp(40)))
                btn.bind(on_release=lambda *_: self.app.open_day(reply.open_date))
                self.chat.add_widget(btn)
                stagger([btn], 0, .3)
            Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), .1)
        Clock.schedule_once(answer, .35)
