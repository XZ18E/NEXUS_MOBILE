package org.nexus.nexuscalendar;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.Locale;

/** Виджет «Сегодня»: читает файл widget.txt, который записывает приложение (Python). */
public class NexusWidgetProvider extends AppWidgetProvider {
    private static final String[] DAYS = {"воскресенье", "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота"};
    private static final String[] MONTHS = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля",
            "августа", "сентября", "октября", "ноября", "декабря"};

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) {
            mgr.updateAppWidget(id, build(ctx));
        }
    }

    private static int rid(Context c, String name, String type) {
        return c.getResources().getIdentifier(name, type, c.getPackageName());
    }

    /** Формат строк файла: E|дата|время|весь_день|название  и  T|дата|название (задача). */
    public static RemoteViews build(Context ctx) {
        RemoteViews v = new RemoteViews(ctx.getPackageName(), rid(ctx, "nexus_widget", "layout"));
        Calendar cal = Calendar.getInstance();
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(cal.getTime());

        List<String> items = new ArrayList<String>();
        String next = null;
        int tasks = 0;
        File f = new File(ctx.getFilesDir(), "widget.txt");
        if (f.exists()) {
            try {
                BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(f), "UTF-8"));
                String line;
                while ((line = r.readLine()) != null) {
                    String[] p = line.split("\\|", 5);
                    if (p.length >= 5 && p[0].equals("E")) {
                        if (p[1].equals(today)) {
                            items.add(("1".equals(p[3]) ? "Весь день" : p[2]) + "   " + p[4]);
                        } else if (p[1].compareTo(today) > 0 && next == null) {
                            String[] d = p[1].split("-");
                            int m = Integer.parseInt(d[1]) - 1;
                            next = Integer.parseInt(d[2]) + " " + MONTHS[m].substring(0, 3) + " · " + p[4];
                        }
                    } else if (p.length >= 3 && p[0].equals("T") && p[1].equals(today)) {
                        tasks++;
                    }
                }
                r.close();
            } catch (Exception e) {
                items.add("Откройте приложение, чтобы обновить");
            }
        }

        v.setTextViewText(rid(ctx, "nx_title", "id"), "Сегодня");
        v.setTextViewText(rid(ctx, "nx_date", "id"), DAYS[cal.get(Calendar.DAY_OF_WEEK) - 1] + ", "
                + cal.get(Calendar.DAY_OF_MONTH) + " " + MONTHS[cal.get(Calendar.MONTH)]);

        StringBuilder body = new StringBuilder();
        if (items.isEmpty()) {
            body.append("Свободный день");
        } else {
            int shown = Math.min(items.size(), 4);
            for (int i = 0; i < shown; i++) {
                if (i > 0) body.append("\n");
                body.append(items.get(i));
            }
            if (items.size() > shown) body.append("\n+").append(items.size() - shown).append(" ещё");
        }
        v.setTextViewText(rid(ctx, "nx_body", "id"), body.toString());

        StringBuilder foot = new StringBuilder();
        if (tasks > 0) foot.append("Задач на сегодня: ").append(tasks);
        if (next != null) {
            if (foot.length() > 0) foot.append("  ·  ");
            foot.append("Далее: ").append(next);
        }
        v.setTextViewText(rid(ctx, "nx_footer", "id"), foot.toString());

        Intent launch = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (launch != null) {
            PendingIntent pi = PendingIntent.getActivity(ctx, 0, launch,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            v.setOnClickPendingIntent(rid(ctx, "nx_root", "id"), pi);
        }
        return v;
    }
}
