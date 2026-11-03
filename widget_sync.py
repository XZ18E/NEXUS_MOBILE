"""Передача данных виджету рабочего стола: приложение пишет widget.txt, виджет (Java) его читает."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

DAYS_AHEAD = 30
PACKAGE = "org.nexus.nexuscalendar"


def build_lines(db, today: date | None = None) -> list[str]:
    """Строки для виджета на ближайшие 30 дней (повторяющиеся события уже развёрнуты)."""
    today = today or date.today()
    end = today + timedelta(days=DAYS_AHEAD)
    lines = [f"V|{today.isoformat()}"]
    for o in db.events_in_range(today, end):
        title = o.event.title.replace("|", "/").replace("\n", " ")
        d = max(o.first_day, today)
        while d <= min(o.last_day, end):
            time_txt = "" if o.event.all_day else f"{o.start:%H:%M}"
            lines.append(f"E|{d.isoformat()}|{time_txt}|{1 if o.event.all_day else 0}|{title}")
            d += timedelta(days=1)
    for t in db.all_tasks():
        if not t.done and t.due and t.due <= end:
            lines.append(f"T|{max(t.due, today).isoformat()}|{t.title.replace('|', '/')}")
    # События одного дня идут по времени (весь день — первыми)
    head, rest = lines[:1], lines[1:]
    rest.sort(key=lambda s: (s.split("|")[1], s.split("|")[3] != "1" if s.startswith("E") else True, s.split("|")[2]))
    return head + rest


def sync(app) -> None:
    """Записывает данные и просит Android перерисовать виджет. Ошибки не должны ломать приложение."""
    try:
        lines = build_lines(app.db)
        try:
            from jnius import autoclass          # type: ignore  (есть только на Android)
        except Exception:
            Path(app.user_data_dir, "widget.txt").write_text("\n".join(lines), encoding="utf-8")
            return
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        ctx = PythonActivity.mActivity
        path = Path(ctx.getFilesDir().getAbsolutePath()) / "widget.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        AppWidgetManager = autoclass("android.appwidget.AppWidgetManager")
        ComponentName = autoclass("android.content.ComponentName")
        Provider = autoclass(f"{PACKAGE}.NexusWidgetProvider")
        mgr = AppWidgetManager.getInstance(ctx)
        ids = mgr.getAppWidgetIds(ComponentName(ctx, f"{PACKAGE}.NexusWidgetProvider"))
        if ids is not None and len(ids) > 0:
            mgr.updateAppWidget(ids, Provider.build(ctx))
    except Exception:
        pass
