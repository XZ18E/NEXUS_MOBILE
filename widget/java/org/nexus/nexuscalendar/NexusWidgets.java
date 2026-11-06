package org.nexus.nexuscalendar;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.text.SpannableString;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.graphics.Typeface;
import android.widget.RemoteViews;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Рисует все виджеты NEXUS из файла widget.txt, который записывает приложение (Python).
 * Строки файла:
 *   V|дата_записи
 *   C|тема|цвет_текста|цвет_приглушённый|акцент|акцент2|опасность   (цвета вида #RRGGBB)
 *   S|первый_день_недели (0 — понедельник, 6 — воскресенье)
 *   E|дата|время|весь_день(0/1)|название
 *   T|дата|просрочена(0/1)|название
 */
public final class NexusWidgets {
    private static final String[] DAYS = {"воскресенье", "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота"};
    private static final String[] DAYS_SHORT = {"вс", "пн", "вт", "ср", "чт", "пт", "сб"};
    private static final String[] WEEK_HEAD = {"ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"};
    private static final String[] MONTHS = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля",
            "августа", "сентября", "октября", "ноября", "декабря"};
    private static final String[] MONTHS_NOM = {"Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
            "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"};

    private NexusWidgets() {}

    private static final class Ev {
        String date, time, title;
        boolean allDay;
    }

    private static final class Tk {
        String date, title;
        boolean overdue;
    }

    private static final class Data {
        String theme = "dark";
        int text = Color.parseColor("#E9EBF3");
        int muted = Color.parseColor("#A0A6BC");
        int accent = Color.parseColor("#4D8DFF");
        int accent2 = Color.parseColor("#8B5CF6");
        int danger = Color.parseColor("#F43F5E");
        int firstWeekday = 0;
        boolean loaded = false;
        List<Ev> events = new ArrayList<Ev>();
        List<Tk> tasks = new ArrayList<Tk>();
    }

    private static int rid(Context c, String name, String type) {
        return c.getResources().getIdentifier(name, type, c.getPackageName());
    }

    private static String fmt(Calendar c) {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(c.getTime());
    }

    private static Data load(Context ctx) {
        Data d = new Data();
        File f = new File(ctx.getFilesDir(), "widget.txt");
        if (!f.exists()) return d;
        try {
            BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(f), "UTF-8"));
            String line;
            while ((line = r.readLine()) != null) {
                String[] p = line.split("\\|", 6);
                if (p.length == 0) continue;
                try {
                    if (p[0].equals("C") && p.length >= 6) {
                        d.theme = p[1];
                        d.text = Color.parseColor(p[2]);
                        d.muted = Color.parseColor(p[3]);
                        d.accent = Color.parseColor(p[4]);
                        d.accent2 = Color.parseColor(p[5]);
                    } else if (p[0].equals("D") && p.length >= 2) {
                        d.danger = Color.parseColor(p[1]);
                    } else if (p[0].equals("S") && p.length >= 2) {
                        d.firstWeekday = p[1].equals("6") ? 6 : 0;
                    } else if (p[0].equals("E") && p.length >= 5) {
                        String[] q = line.split("\\|", 5);
                        Ev e = new Ev();
                        e.date = q[1];
                        e.time = q[2];
                        e.allDay = q[3].equals("1");
                        e.title = q[4];
                        d.events.add(e);
                    } else if (p[0].equals("T") && p.length >= 4) {
                        String[] q = line.split("\\|", 4);
                        Tk t = new Tk();
                        t.date = q[1];
                        t.overdue = q[2].equals("1");
                        t.title = q[3];
                        d.tasks.add(t);
                    }
                } catch (Exception ignore) {
                    // одна повреждённая строка не должна ломать весь виджет
                }
            }
            r.close();
            d.loaded = true;
        } catch (Exception e) {
            d.loaded = false;
        }
        return d;
    }

    public static RemoteViews build(Context ctx, String kind) {
        Data d = load(ctx);
        String layout = kind.equals("small") ? "nexus_widget_small"
                : kind.equals("month") ? "nexus_widget_month" : "nexus_widget";
        RemoteViews v = new RemoteViews(ctx.getPackageName(), rid(ctx, layout, "layout"));
        int root = rid(ctx, "nx_root", "id");
        int bg = rid(ctx, "nx_bg_" + d.theme, "drawable");
        if (bg != 0) v.setInt(root, "setBackgroundResource", bg);

        if (kind.equals("small")) {
            small(ctx, v, d);
        } else if (kind.equals("month")) {
            month(ctx, v, d);
        } else if (kind.equals("agenda")) {
            agenda(ctx, v, d);
        } else if (kind.equals("tasks")) {
            tasks(ctx, v, d);
        } else {
            today(ctx, v, d);
        }

        Intent launch = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (launch != null) {
            PendingIntent pi = PendingIntent.getActivity(ctx, 0, launch,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            v.setOnClickPendingIntent(root, pi);
        }
        return v;
    }

    private static void setText(Context ctx, RemoteViews v, String id, CharSequence text, int color) {
        int rid = rid(ctx, id, "id");
        v.setTextViewText(rid, text);
        v.setTextColor(rid, color);
    }

    private static String plural(int n, String one, String few, String many) {
        int a = Math.abs(n) % 100;
        int b = a % 10;
        if (a >= 11 && a <= 14) return many;
        if (b == 1) return one;
        if (b >= 2 && b <= 4) return few;
        return many;
    }

    private static String shortDate(String iso) {
        String[] p = iso.split("-");
        return Integer.parseInt(p[2]) + " " + MONTHS[Integer.parseInt(p[1]) - 1].substring(0, 3);
    }

    private static String eventLine(Ev e) {
        return (e.allDay ? "весь день" : e.time) + "   " + e.title;
    }

    // ---------------------------------------------------------------- Сегодня
    private static void today(Context ctx, RemoteViews v, Data d) {
        Calendar cal = Calendar.getInstance();
        String today = fmt(cal);
        List<String> items = new ArrayList<String>();
        String next = null;
        for (Ev e : d.events) {
            if (e.date.equals(today)) {
                items.add(eventLine(e));
            } else if (e.date.compareTo(today) > 0 && next == null) {
                next = shortDate(e.date) + " · " + e.title;
            }
        }
        int tasks = 0;
        for (Tk t : d.tasks) if (t.date.equals(today)) tasks++;

        setText(ctx, v, "nx_title", "Сегодня", d.text);
        setText(ctx, v, "nx_date", DAYS[cal.get(Calendar.DAY_OF_WEEK) - 1] + ", "
                + cal.get(Calendar.DAY_OF_MONTH) + " " + MONTHS[cal.get(Calendar.MONTH)], d.muted);

        StringBuilder body = new StringBuilder();
        if (!d.loaded) {
            body.append("Откройте приложение, чтобы обновить");
        } else if (items.isEmpty()) {
            body.append("Свободный день");
        } else {
            int shown = Math.min(items.size(), 6);
            for (int i = 0; i < shown; i++) {
                if (i > 0) body.append("\n");
                body.append(items.get(i));
            }
            if (items.size() > shown) body.append("\n+").append(items.size() - shown).append(" ещё");
        }
        setText(ctx, v, "nx_body", body.toString(), d.text);

        StringBuilder foot = new StringBuilder();
        if (tasks > 0) foot.append("Задач на сегодня: ").append(tasks);
        if (next != null) {
            if (foot.length() > 0) foot.append("  ·  ");
            foot.append("Далее: ").append(next);
        }
        setText(ctx, v, "nx_footer", foot.toString(), d.accent);
    }

    // ------------------------------------------------------------- Маленький
    private static void small(Context ctx, RemoteViews v, Data d) {
        Calendar cal = Calendar.getInstance();
        String today = fmt(cal);
        int count = 0;
        String nextToday = null;
        String nextLater = null;
        String nowTime = new SimpleDateFormat("HH:mm", Locale.US).format(cal.getTime());
        for (Ev e : d.events) {
            if (e.date.equals(today)) {
                count++;
                if (nextToday == null && (e.allDay || e.time.compareTo(nowTime) >= 0)) {
                    nextToday = (e.allDay ? "весь день" : e.time) + " " + e.title;
                }
            } else if (e.date.compareTo(today) > 0 && nextLater == null) {
                nextLater = shortDate(e.date) + " · " + e.title;
            }
        }
        setText(ctx, v, "nx_wd", DAYS[cal.get(Calendar.DAY_OF_WEEK) - 1] + ", "
                + MONTHS[cal.get(Calendar.MONTH)], d.muted);
        setText(ctx, v, "nx_day", String.valueOf(cal.get(Calendar.DAY_OF_MONTH)), d.text);
        setText(ctx, v, "nx_count", count == 0 ? "Свободно"
                : count + " " + plural(count, "событие", "события", "событий"), d.accent);
        String next = nextToday != null ? nextToday : (nextLater != null ? "Далее: " + nextLater : "");
        setText(ctx, v, "nx_next", next, d.muted);
    }

    // ----------------------------------------------------------------- Неделя
    private static void agenda(Context ctx, RemoteViews v, Data d) {
        Calendar cal = Calendar.getInstance();
        String today = fmt(cal);
        Calendar endCal = (Calendar) cal.clone();
        endCal.add(Calendar.DAY_OF_MONTH, 7);
        String end = fmt(endCal);

        setText(ctx, v, "nx_title", "Ближайшие дни", d.text);
        setText(ctx, v, "nx_date", "7 дней", d.muted);

        SpannableStringBuilder sb = new SpannableStringBuilder();
        String lastDate = "";
        int lines = 0;
        int total = 0;
        for (Ev e : d.events) {
            if (e.date.compareTo(today) < 0 || e.date.compareTo(end) > 0) continue;
            total++;
            if (lines >= 11) continue;
            if (!e.date.equals(lastDate)) {
                lastDate = e.date;
                if (sb.length() > 0) sb.append("\n");
                String[] p = e.date.split("-");
                Calendar c = Calendar.getInstance();
                c.set(Integer.parseInt(p[0]), Integer.parseInt(p[1]) - 1, Integer.parseInt(p[2]));
                String head = e.date.equals(today) ? "Сегодня" : DAYS_SHORT[c.get(Calendar.DAY_OF_WEEK) - 1]
                        + ", " + Integer.parseInt(p[2]) + " " + MONTHS[Integer.parseInt(p[1]) - 1];
                int start = sb.length();
                sb.append(head);
                sb.setSpan(new ForegroundColorSpan(d.accent), start, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                sb.setSpan(new StyleSpan(Typeface.BOLD), start, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                lines++;
                if (lines >= 11) continue;
            }
            sb.append("\n").append(eventLine(e));
            lines++;
        }
        if (!d.loaded) {
            sb.append("Откройте приложение, чтобы обновить");
        } else if (total == 0) {
            sb.append("Ничего не запланировано");
        }
        setText(ctx, v, "nx_body", sb, d.text);
        setText(ctx, v, "nx_footer", total > 0 ? "Всего событий: " + total : "", d.accent);
    }

    // ----------------------------------------------------------------- Задачи
    private static void tasks(Context ctx, RemoteViews v, Data d) {
        Calendar cal = Calendar.getInstance();
        int overdue = 0;
        for (Tk t : d.tasks) if (t.overdue) overdue++;
        setText(ctx, v, "nx_title", "Задачи", d.text);
        setText(ctx, v, "nx_date", d.tasks.size() + " " + plural(d.tasks.size(), "активная", "активные", "активных"),
                d.muted);

        SpannableStringBuilder sb = new SpannableStringBuilder();
        int shown = Math.min(d.tasks.size(), 9);
        for (int i = 0; i < shown; i++) {
            Tk t = d.tasks.get(i);
            if (i > 0) sb.append("\n");
            int start = sb.length();
            sb.append(t.overdue ? "! " : "• ").append(t.title);
            if (t.overdue) {
                sb.setSpan(new ForegroundColorSpan(d.danger), start, start + 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                sb.setSpan(new StyleSpan(Typeface.BOLD), start, start + 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
        }
        if (d.tasks.size() > shown) sb.append("\n+").append(String.valueOf(d.tasks.size() - shown)).append(" ещё");
        if (!d.loaded) sb.append("Откройте приложение, чтобы обновить");
        else if (d.tasks.isEmpty()) sb.append("Все задачи выполнены");
        setText(ctx, v, "nx_body", sb, d.text);
        setText(ctx, v, "nx_footer", overdue > 0 ? "Просрочено: " + overdue : "", d.danger);
    }

    // ------------------------------------------------------------------ Месяц
    private static void month(Context ctx, RemoteViews v, Data d) {
        Calendar now = Calendar.getInstance();
        String today = fmt(now);
        int curMonth = now.get(Calendar.MONTH);

        Map<String, Boolean> busy = new HashMap<String, Boolean>();
        for (Ev e : d.events) busy.put(e.date, Boolean.TRUE);
        for (Tk t : d.tasks) if (!busy.containsKey(t.date)) busy.put(t.date, Boolean.TRUE);

        setText(ctx, v, "nx_mtitle", MONTHS_NOM[curMonth] + " " + now.get(Calendar.YEAR), d.text);
        for (int i = 0; i < 7; i++) {
            int idx = (d.firstWeekday + i) % 7;
            setText(ctx, v, "nx_w" + i, WEEK_HEAD[idx], idx >= 5 ? d.accent2 : d.muted);
        }

        Calendar first = (Calendar) now.clone();
        first.set(Calendar.DAY_OF_MONTH, 1);
        int dow = (first.get(Calendar.DAY_OF_WEEK) + 5) % 7;          // понедельник = 0
        int offset = (dow - d.firstWeekday + 7) % 7;
        Calendar cell = (Calendar) first.clone();
        cell.add(Calendar.DAY_OF_MONTH, -offset);

        int todayBg = rid(ctx, "nx_today_" + d.theme, "drawable");
        for (int i = 0; i < 42; i++) {
            int id = rid(ctx, "nx_c" + i, "id");
            String key = fmt(cell);
            boolean inMonth = cell.get(Calendar.MONTH) == curMonth;
            boolean isToday = key.equals(today);
            SpannableString s = new SpannableString(String.valueOf(cell.get(Calendar.DAY_OF_MONTH)));
            int color = inMonth ? d.text : d.muted;
            if (isToday) {
                color = Color.WHITE;
                s.setSpan(new StyleSpan(Typeface.BOLD), 0, s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                if (todayBg != 0) v.setInt(id, "setBackgroundResource", todayBg);
            } else {
                v.setInt(id, "setBackgroundResource", 0);
                if (inMonth && busy.containsKey(key)) {
                    s.setSpan(new StyleSpan(Typeface.BOLD), 0, s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                    s.setSpan(new ForegroundColorSpan(d.accent), 0, s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                }
            }
            v.setTextViewText(id, s);
            v.setTextColor(id, color);
            cell.add(Calendar.DAY_OF_MONTH, 1);
        }
    }
}
