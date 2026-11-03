"""NEXUS Calendar Mobile — точка входа (Kivy, Android/desktop)."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.utils import platform

from database import Database
from assistant_screen import AssistantScreen
from editors import EventEditor, TaskEditor
import widget_sync
from models import Event, Task, add_months, validate_event
from screens import CalendarScreen, SettingsScreen, StatsScreen, TasksScreen
from ui_kit import Card, Icon, Lbl, Sheet, confirm, fade_in, message, theme, with_alpha

TABS = [("calendar", "Календарь", "calendar"), ("tasks", "Задачи", "tasks"), ("assistant", "Помощник", "sparkle"),
        ("stats", "Статистика", "stats"), ("settings", "Ещё", "gear")]


class NavItem(ButtonBehavior, BoxLayout):
    def __init__(self, key: str, text: str, icon: str, **kw):
        super().__init__(orientation="vertical", padding=[0, dp(8), 0, dp(6)], spacing=dp(2), **kw)
        self.key = key
        self.icon = Icon(icon, "faint", 24, pos_hint={"center_x": .5})
        self.label = Lbl(text, 11, "faint", bold=True, halign="center", size_hint_y=None, height=dp(16))
        self.add_widget(self.icon)
        self.add_widget(self.label)

    def set_active(self, on: bool) -> None:
        self.icon.set_color("accent" if on else "faint")
        self.label.color = theme.c("accent" if on else "faint")


class Fab(ButtonBehavior, Widget):
    scale = NumericProperty(1.0)

    def pulse(self) -> None:
        Animation.cancel_all(self, "scale")
        Animation(scale=1.18, d=.12, t="out_quad").start(self)
        Clock.schedule_once(lambda dt: Animation(scale=1.0, d=.35, t="out_elastic").start(self), .12)

    def __init__(self, **kw):
        super().__init__(size_hint=(None, None), size=(dp(60), dp(60)), **kw)
        self.icon = Icon("plus", (1, 1, 1, 1), 28)
        self.add_widget(self.icon)
        self.bind(pos=self._draw, size=self._draw, state=self._draw, scale=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            w, h = self.width * self.scale, self.height * self.scale
            x, y = self.center_x - w / 2, self.center_y - h / 2
            Color(0, 0, 0, .28)
            Ellipse(pos=(x - dp(1), y - dp(4)), size=(w + dp(2), h + dp(2)))
            Color(*theme.c("accent2") if self.state == "down" else theme.c("accent"))
            Ellipse(pos=(x, y), size=(w, h))
        self.icon.center = self.center


class NexusApp(App):
    title = "NEXUS Calendar"

    # ------------------------------------------------------------ запуск
    def build(self):
        self.db = Database(Path(self.user_data_dir) / "nexus.db")
        theme.apply(self.db.get_setting("theme", "dark"))
        self.first_weekday = 6 if self.db.get_setting("first_weekday", "0") == "6" else 0
        self.selected = date.today()
        self.tab = "calendar"
        self.pages: dict = {}
        Window.clearcolor = theme.bg
        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self._on_key)
        self.root_box = FloatLayout()
        self._build_ui()
        Clock.schedule_interval(self.check_reminders, 20)
        Clock.schedule_once(self.check_reminders, 2)
        Clock.schedule_interval(lambda dt: self._midnight_check(), 60)
        self._today = date.today()
        if platform == "android":
            self._request_android_permissions()
        return self.root_box

    def on_resume(self):
        widget_sync.sync(self)

    def on_pause(self):
        widget_sync.sync(self)
        return True          # не закрывать приложение при сворачивании — напоминания продолжают работать

    def on_stop(self):
        self.db.close()

    def _build_ui(self) -> None:
        self.root_box.clear_widgets()
        self.pages.clear()
        Window.clearcolor = theme.bg
        col = BoxLayout(orientation="vertical", pos_hint={"x": 0, "y": 0}, size_hint=(1, 1))
        self.container = BoxLayout()
        col.add_widget(self.container)
        nav = Card(fill="surface", radius=0, orientation="horizontal", size_hint_y=None, height=dp(64))
        self.nav_items = {}
        for key, text, icon in TABS:
            item = NavItem(key, text, icon)
            item.bind(on_release=lambda w: self.goto(w.key))
            nav.add_widget(item)
            self.nav_items[key] = item
        col.add_widget(nav)
        self.root_box.add_widget(col)
        self.fab = Fab()
        self.fab.bind(on_release=lambda *_: self._fab())
        self.root_box.add_widget(self.fab)
        Window.bind(size=lambda *_: self._place_fab())
        self.goto(self.tab, animate=False)

    def _place_fab(self) -> None:
        self.fab.pos = (Window.width - self.fab.width - dp(18), dp(64) + dp(16))

    def _page(self, key: str):
        if key not in self.pages:
            cls = {"calendar": CalendarScreen, "tasks": TasksScreen, "assistant": AssistantScreen, "stats": StatsScreen,
                   "settings": SettingsScreen}[key]
            self.pages[key] = cls(self)
        return self.pages[key]

    def goto(self, key: str, animate: bool = True) -> None:
        self.tab = key
        page = self._page(key)
        self.container.clear_widgets()
        self.container.add_widget(page)
        for k, item in self.nav_items.items():
            item.set_active(k == key)
        page.refresh()
        self.fab.opacity = 1 if key in ("calendar", "tasks") else 0
        self.fab.disabled = key not in ("calendar", "tasks")
        self._place_fab()
        if key in ("calendar", "tasks"):
            self.fab.pulse()
        if animate:
            fade_in(page, .22)

    def refresh(self) -> None:
        widget_sync.sync(self)
        for key, page in self.pages.items():
            if key == self.tab or key in ("calendar", "tasks"):
                page.refresh()

    def rebuild(self) -> None:
        """Пересборка интерфейса (после смены темы)."""
        self._build_ui()

    # ------------------------------------------------------------- действия
    def _fab(self) -> None:
        if self.tab == "tasks":
            self.edit_task(None)
        else:
            self.new_event()

    def default_start(self, day: date | None = None) -> datetime:
        day, now = day or self.selected, datetime.now()
        if day == now.date():
            return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0) if now.hour < 23 \
                else now.replace(hour=23, minute=0, second=0, microsecond=0)
        return datetime.combine(day, datetime.min.time()).replace(hour=9)

    def select(self, d: date, direction: int = 0) -> None:
        old = self.selected
        if not direction and (d.year, d.month) != (old.year, old.month):
            direction = 1 if d > old else -1
        self.selected = d
        if "calendar" in self.pages:
            self.pages["calendar"].refresh(direction)

    def open_day(self, d: date) -> None:
        """Из помощника: открыть календарь на нужном дне."""
        self.selected = d
        self.goto("calendar")

    def shift_month(self, step: int) -> None:
        self.select(add_months(self.selected, step), step)

    def occurrences(self, start: date, end: date):
        try:
            return self.db.events_in_range(start, end)
        except (sqlite3.Error, ValueError) as e:
            message("Ошибка", f"Не удалось прочитать события:\n{e}")
            return []

    def new_event(self) -> None:
        EventEditor(self, None, self.default_start()).open()

    def edit_event(self, ev: Event) -> None:
        EventEditor(self, ev).open()

    def edit_task(self, task: Task | None) -> None:
        TaskEditor(self, task, self.selected if (task is None and self.tab == "calendar") else None).open()

    def _safe(self, fn, what: str) -> bool:
        try:
            fn()
        except sqlite3.Error as e:
            message("Ошибка", f"{what}:\n{e}")
            return False
        self.refresh()
        return True

    def save_event(self, ev: Event) -> bool:
        problem = validate_event(ev)
        if problem:
            message("Проверьте данные", problem)
            return False
        ok = self._safe(lambda: self.db.update_event(ev) if ev.id else self.db.add_event(ev),
                        "Не удалось сохранить событие")
        if ok:
            self.selected = ev.start.date()
            self.refresh()
        return ok

    def delete_event(self, event_id: int) -> None:
        self._safe(lambda: self.db.delete_event(event_id), "Не удалось удалить событие")

    def save_task(self, t: Task) -> bool:
        return self._safe(lambda: self.db.update_task(t) if t.id else self.db.add_task(t),
                          "Не удалось сохранить задачу")

    def toggle_task(self, task_id: int, done: bool) -> None:
        self._safe(lambda: self.db.set_task_done(task_id, done), "Не удалось обновить задачу")

    def delete_task(self, task_id: int) -> None:
        self._safe(lambda: self.db.delete_task(task_id), "Не удалось удалить задачу")

    def set_theme(self, name: str) -> None:
        self.db.set_setting("theme", name)
        theme.apply(name)
        self.rebuild()

    def set_first_weekday(self, v: int) -> None:
        self.first_weekday = v
        self.db.set_setting("first_weekday", str(v))
        self.refresh()

    def _midnight_check(self) -> None:
        if date.today() != self._today:
            self._today = date.today()
            self.refresh()

    # ----------------------------------------------------- экспорт / бэкап
    def _export_dir(self) -> Path:
        base = Path(self.user_data_dir) / "export"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def export_csv(self) -> None:
        name = f"nexus_events_{date.today():%Y-%m-%d}.csv"
        target = self._export_dir() / name
        try:
            n = self.db.export_events_csv(target)
        except (OSError, sqlite3.Error) as e:
            message("Не удалось экспортировать", str(e))
            return
        self._offer_save(target, "text/csv", f"Сохранено событий: {n}.")

    def backup(self) -> None:
        name = f"nexus_backup_{datetime.now():%Y-%m-%d_%H-%M}.db"
        target = self._export_dir() / name
        try:
            self.db.backup_to(target)
        except (OSError, sqlite3.Error, ValueError) as e:
            message("Не удалось создать копию", str(e))
            return
        self._offer_save(target, "application/octet-stream", "Резервная копия создана.")

    def _offer_save(self, source: Path, mime: str, text: str) -> None:
        """На Android предлагает выбрать место сохранения (системный диалог), иначе показывает путь."""
        if platform == "android":
            try:
                self._android_save_as(source, mime)
                return
            except Exception:
                pass
        message("Готово", f"{text}\nФайл: {source}")

    def _android_save_as(self, source: Path, mime: str) -> None:
        from android import activity            # type: ignore
        from jnius import autoclass             # type: ignore
        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime)
        intent.putExtra(Intent.EXTRA_TITLE, source.name)
        code = 4242

        def on_result(request, result, data):
            activity.unbind(on_activity_result=on_result)
            if request != code or result != -1 or data is None:
                return
            try:
                stream = PythonActivity.mActivity.getContentResolver().openOutputStream(data.getData())
                payload = source.read_bytes()
                stream.write(payload, 0, len(payload))
                stream.close()
                Clock.schedule_once(lambda dt: message("Готово", "Файл сохранён."), 0)
            except Exception as e:                       # noqa: BLE001
                Clock.schedule_once(lambda dt: message("Не удалось сохранить", str(e)), 0)

        activity.bind(on_activity_result=on_result)
        PythonActivity.mActivity.startActivityForResult(intent, code)

    # -------------------------------------------------------- напоминания
    def _request_android_permissions(self) -> None:
        try:
            from android.permissions import request_permissions        # type: ignore
            request_permissions(["android.permission.POST_NOTIFICATIONS"])
        except Exception:
            pass

    def check_reminders(self, *_):
        if self.db.get_setting("notifications", "1") != "1":
            return
        now = datetime.now()
        try:
            occs = self.db.events_in_range(now.date() - timedelta(days=1), now.date() + timedelta(days=2))
            for o in occs:
                ev = o.event
                if ev.reminder < 0 or ev.id is None:
                    continue
                trigger = o.start - timedelta(minutes=ev.reminder)
                finish = max(o.end, o.start + timedelta(minutes=5))
                if trigger <= now <= finish and not self.db.reminder_sent(ev.id, o.start):
                    self.db.mark_reminder_sent(ev.id, o.start)
                    delta = (o.start - now).total_seconds()
                    hint = ("Уже идёт" if delta <= -60 else "Начинается сейчас" if delta < 60
                            else f"Начнётся через {int(round(delta / 60))} мин")
                    self.notify(ev.title, f"{hint} · {o.start:%H:%M}" + (f" · {ev.location}" if ev.location else ""),
                                ev.display_color)
        except sqlite3.Error:
            pass

    def notify(self, title: str, body: str, color: str = "#4D8DFF") -> None:
        self.toast(title, body, color)
        try:
            from plyer import notification
            notification.notify(title=title, message=body, app_name="NEXUS Calendar", timeout=8)
        except Exception:
            pass

    def toast(self, title: str, body: str, color: str = "#4D8DFF") -> None:
        card = Card(fill="surface", radius=18, orientation="vertical", size_hint=(.92, None), height=dp(78),
                    padding=[dp(16), dp(10)], pos_hint={"center_x": .5})
        card.add_widget(Lbl(title, 15, bold=True, shorten=True, shorten_from="right"))
        card.add_widget(Lbl(body, 12, "muted", shorten=True, shorten_from="right"))
        card.y = Window.height + dp(10)
        self.root_box.add_widget(card)
        target = Window.height - dp(96)
        anim = Animation(y=target, d=.3, t="out_cubic") + Animation(d=6) + Animation(y=Window.height + dp(10), d=.3)
        anim.bind(on_complete=lambda *_: self.root_box.remove_widget(card))
        anim.start(card)

    # ------------------------------------------------------- кнопка «назад»
    def _on_key(self, window, key, *args):
        if key != 27:                                       # 27 = Esc / «Назад» на Android
            return False
        if Sheet.stack:
            Sheet.stack[-1].dismiss()
            return True
        if self.tab != "calendar":
            self.goto("calendar")
            return True
        return False


if __name__ == "__main__":
    NexusApp().run()
