"""Передача данных виджетам рабочего стола: приложение пишет widget.txt, виджеты (Java) его читают."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

DAYS_AHEAD = 45
PACKAGE = "org.nexus.nexuscalendar"
# класс виджета -> вид (то же соответствие в NexusWidgets.java)
PROVIDERS = {"NexusWidgetProvider": "today", "NexusWidgetSmall": "small", "NexusWidgetAgenda": "agenda",
             "NexusWidgetTasks": "tasks", "NexusWidgetMonth": "month"}


def _clean(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def build_lines(db, today: date | None = None, theme: str = "dark", first_weekday: int = 0) -> list[str]:
    """Строки данных: события с начала текущего месяца и на 45 дней вперёд, активные задачи, цвета темы."""
    from ui_kit import PALETTES                        # палитры тем (чтобы виджет совпадал с приложением)
    today = today or date.today()
    pal = PALETTES.get(theme, PALETTES["dark"])
    start, end = today.replace(day=1), today + timedelta(days=DAYS_AHEAD)
    lines = [f"V|{today.isoformat()}",
             f"C|{theme}|{pal['text']}|{pal['muted']}|{pal['accent']}|{pal['accent2']}",
             f"D|{pal['danger']}", f"S|{6 if first_weekday == 6 else 0}"]
    events = []
    for o in db.events_in_range(start, end):
        title = _clean(o.event.title)
        d = max(o.first_day, start)
        while d <= min(o.last_day, end):
            time_txt = "" if o.event.all_day else f"{o.start:%H:%M}"
            events.append((d.isoformat(), 0 if o.event.all_day else 1, time_txt, title))
            d += timedelta(days=1)
    events.sort()
    for d, timed, time_txt, title in events:
        lines.append(f"E|{d}|{time_txt}|{0 if timed else 1}|{title}")
    tasks = [t for t in db.all_tasks() if not t.done]
    tasks.sort(key=lambda t: (t.due is None, t.due or date.max, -t.priority))
    for t in tasks[:40]:
        overdue = 1 if t.due and t.due < today else 0
        lines.append(f"T|{t.due.isoformat() if t.due else '-'}|{overdue}|{_clean(t.title)}")
    return lines


def sync(app) -> None:
    """Записывает данные и просит Android перерисовать все виджеты. Ошибки не должны ломать приложение."""
    try:
        from ui_kit import theme
        lines = build_lines(app.db, theme=theme.name, first_weekday=app.first_weekday)
        text = "\n".join(lines)
        try:
            from jnius import autoclass          # type: ignore  (есть только на Android)
        except Exception:
            Path(app.user_data_dir, "widget.txt").write_text(text, encoding="utf-8")
            return
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        ctx = PythonActivity.mActivity
        Path(ctx.getFilesDir().getAbsolutePath(), "widget.txt").write_text(text, encoding="utf-8")
        AppWidgetManager = autoclass("android.appwidget.AppWidgetManager")
        ComponentName = autoclass("android.content.ComponentName")
        Widgets = autoclass(f"{PACKAGE}.NexusWidgets")
        mgr = AppWidgetManager.getInstance(ctx)
        for cls, kind in PROVIDERS.items():
            ids = mgr.getAppWidgetIds(ComponentName(ctx, f"{PACKAGE}.{cls}"))
            if ids is not None and len(ids) > 0:
                mgr.updateAppWidget(ids, Widgets.build(ctx, kind))
    except Exception:
        pass
