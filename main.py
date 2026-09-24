# main.py — Дневник пловца (Kivy / Android)
import os
import csv
import json
import calendar
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

RU_MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
STROKES = ["Кроль", "Брасс", "Баттерфляй", "Спина", "Комплекс"]
CHART_COLORS = [(0.12, 0.53, 0.90, 1), (0.90, 0.30, 0.30, 1),
                (0.20, 0.70, 0.30, 1), (0.90, 0.60, 0.10, 1),
                (0.60, 0.30, 0.80, 1)]


# ====================== ГРАФИК ======================
class LineChart(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.series = []          # [(name, [(ordinal, value), ...]), ...]
        self.bind(pos=self._redraw, size=self._redraw)

    def set_series(self, series):
        self.series = series
        self._redraw()

    def _text(self, text, x, y, size=dp(10), color=(0.25, 0.25, 0.25, 1)):
        lbl = CoreLabel(text=text, font_size=size, color=color)
        lbl.refresh()
        tex = lbl.texture
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=tex, pos=(x, y), size=tex.size)

    def _redraw(self, *args):
        self.canvas.clear()
        if self.width < dp(80) or self.height < dp(80):
            return

        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)

        pad_l, pad_r, pad_t, pad_b = dp(45), dp(15), dp(15), dp(30)
        x0 = self.x + pad_l
        y0 = self.y + pad_b
        w = self.width - pad_l - pad_r
        h = self.height - pad_t - pad_b
        if w <= 10 or h <= 10:
            return

        with self.canvas:
            Color(0.55, 0.55, 0.55, 1)
            Line(points=[x0, y0, x0 + w, y0], width=1.1)
            Line(points=[x0, y0, x0, y0 + h], width=1.1)

        pts_all = [(x, y) for _, arr in self.series for x, y in arr]
        if not pts_all:
            self._text("Нет данных", self.center_x - dp(30), self.center_y)
            return

        xs = [p[0] for p in pts_all]
        ys = [p[1] for p in pts_all]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        if maxx == minx:
            maxx = minx + 1
        if maxy == miny:
            maxy = miny + 1
            miny = miny - 1
        span = maxy - miny
        miny -= span * 0.1
        maxy += span * 0.1

        # горизонтальная сетка и подписи Y
        for i in range(5):
            yy = y0 + h * i / 4.0
            val = miny + (maxy - miny) * i / 4.0
            with self.canvas:
                Color(0.88, 0.88, 0.88, 1)
                Line(points=[x0, yy, x0 + w, yy], width=0.8)
            self._text(f"{val:.1f}", self.x + dp(2), yy - dp(6))

        # серии
        for i, (name, arr) in enumerate(self.series):
            if not arr:
                continue
            c = CHART_COLORS[i % len(CHART_COLORS)]
            pts = []
            for (x, y) in arr:
                px = x0 + (x - minx) / (maxx - minx) * w
                py = y0 + (y - miny) / (maxy - miny) * h
                pts.extend([px, py])
            with self.canvas:
                Color(*c)
                if len(pts) >= 4:
                    Line(points=pts, width=1.8)
                for j in range(0, len(pts), 2):
                    Ellipse(pos=(pts[j] - dp(3), pts[j + 1] - dp(3)),
                            size=(dp(6), dp(6)))

        # подписи X (первая и последняя дата)
        try:
            self._text(datetime.fromordinal(int(minx)).strftime("%d.%m"),
                       x0 - dp(10), y0 - dp(18))
            self._text(datetime.fromordinal(int(maxx)).strftime("%d.%m"),
                       x0 + w - dp(25), y0 - dp(18))
        except Exception:
            pass

        # легенда
        lx = x0 + dp(6)
        ly = y0 + h - dp(14)
        for i, (name, arr) in enumerate(self.series):
            if not arr:
                continue
            c = CHART_COLORS[i % len(CHART_COLORS)]
            with self.canvas:
                Color(*c)
                Rectangle(pos=(lx, ly), size=(dp(9), dp(9)))
            self._text(name, lx + dp(13), ly - dp(2))
            ly -= dp(14)


# ====================== ПРИЛОЖЕНИЕ ======================
class DiaryApp(App):
    # ---------- старт ----------
    def build(self):
        self.title = "Дневник пловца"
        self.data_file = os.path.join(self.user_data_dir, "swimmer_data.json")
        self.competitions = set()
        self.entries = []
        self.editing_index = None

        today = datetime.today()
        self.year = today.year
        self.month = today.month
        self.selected_date = today.strftime("%Y-%m-%d")

        self.load_data()

        self.tabs = TabbedPanel(do_default_tab=False)
        cal_tab = self._build_calendar_tab()
        self.tabs.add_widget(cal_tab)
        self.tabs.add_widget(self._build_diary_tab())
        self.tabs.add_widget(self._build_stats_tab())
        self.tabs.default_tab = cal_tab

        Clock.schedule_once(self._post_init, 0.15)
        return self.tabs

    def on_start(self):
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE,
                                     Permission.READ_EXTERNAL_STORAGE])
            except Exception:
                pass

    def _post_init(self, dt):
        self.refresh_calendar()
        self.refresh_entries()
        self.refresh_stats()

    # ---------- файл ----------
    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.competitions = set(data.get("competitions", []))
                self.entries = data.get("entries", [])
            except Exception:
                self.competitions, self.entries = set(), []

    def save_data(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({"competitions": list(self.competitions),
                           "entries": self.entries},
                          f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.popup("Ошибка сохранения", str(e))
            return False

    # ---------- попап ----------
    def popup(self, title, message):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        lbl = Label(text=message, halign="center", valign="middle")
        lbl.bind(size=lambda i, v: setattr(i, "text_size", (v[0], None)))
        box.add_widget(lbl)
        btn = Button(text="OK", size_hint_y=None, height=dp(46))
        box.add_widget(btn)
        p = Popup(title=title, content=box, size_hint=(0.88, 0.5))
        btn.bind(on_release=p.dismiss)
        p.open()

    # ================= КАЛЕНДАРЬ =================
    def _build_calendar_tab(self):
        item = TabbedPanelItem(text="Календарь")
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        prev_b = Button(text="◀", size_hint_x=None, width=dp(56))
        next_b = Button(text="▶", size_hint_x=None, width=dp(56))
        prev_b.bind(on_release=lambda *a: self.change_month(-1))
        next_b.bind(on_release=lambda *a: self.change_month(1))
        self.month_label = Label(text="", bold=True, font_size=dp(17))
        top.add_widget(prev_b)
        top.add_widget(self.month_label)
        top.add_widget(next_b)
        root.add_widget(top)

        self.cal_grid = GridLayout(cols=7, spacing=dp(2),
                                   size_hint_y=None, height=dp(280))
        root.add_widget(self.cal_grid)

        self.cal_info = Label(text="Выбери дату", size_hint_y=None, height=dp(34),
                              font_size=dp(13))
        root.add_widget(self.cal_info)

        btns = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        b1 = Button(text="🏁 Отметить соревнование")
        b2 = Button(text="✅ Снять отметку")
        b1.bind(on_release=lambda *a: self.toggle_competition())
        b2.bind(on_release=lambda *a: self.remove_competition())
        btns.add_widget(b1)
        btns.add_widget(b2)
        root.add_widget(btns)

        root.add_widget(Label(text="🔴 соревнование   🔵 сегодня   ⚪ обычный день",
                              size_hint_y=None, height=dp(28), font_size=dp(11)))
        item.add_widget(root)
        return item

    def change_month(self, delta):
        self.month += delta
        if self.month < 1:
            self.month, self.year = 12, self.year - 1
        elif self.month > 12:
            self.month, self.year = 1, self.year + 1
        self.refresh_calendar()

    def refresh_calendar(self):
        self.cal_grid.clear_widgets()
        self.month_label.text = f"{RU_MONTHS[self.month - 1]} {self.year}"

        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
            self.cal_grid.add_widget(Label(text=d, bold=True, font_size=dp(11)))

        weeks = calendar.monthcalendar(self.year, self.month)
        self.cal_grid.height = (len(weeks) + 1) * dp(40)

        today_str = datetime.today().strftime("%Y-%m-%d")
        for week in weeks:
            for day in week:
                if day == 0:
                    self.cal_grid.add_widget(Widget())
                    continue
                date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
                if date_str in self.competitions:
                    bg = (1.0, 0.42, 0.42, 1)
                elif date_str == today_str:
                    bg = (0.45, 0.75, 0.99, 1)
                else:
                    bg = (0.94, 0.94, 0.94, 1)
                b = Button(text=str(day), background_normal="",
                           background_color=bg, color=(0.05, 0.05, 0.05, 1),
                           font_size=dp(13))
                b.bind(on_release=lambda inst, d=date_str: self.select_date(d))
                self.cal_grid.add_widget(b)

    def select_date(self, date_str):
        self.selected_date = date_str
        status = "🏁 СОРЕВНОВАНИЕ" if date_str in self.competitions else "обычный день"
        self.cal_info.text = f"Выбрано: {date_str} — {status}"
        if hasattr(self, "date_input"):
            self.date_input.text = date_str

    def toggle_competition(self):
        d = self.selected_date
        if d in self.competitions:
            self.competitions.remove(d)
        else:
            self.competitions.add(d)
        if self.save_data():
            self.refresh_calendar()
            self.select_date(d)

    def remove_competition(self):
        d = self.selected_date
        if d in self.competitions:
            self.competitions.remove(d)
            if self.save_data():
                self.refresh_calendar()
                self.select_date(d)

    # ================= ДНЕВНИК =================
    def _build_diary_tab(self):
        item = TabbedPanelItem(text="Дневник")
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        form = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(240),
                         spacing=dp(4))

        def row(label_text, widget):
            r = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
            r.add_widget(Label(text=label_text, size_hint_x=None,
                               width=dp(110), font_size=dp(13)))
            r.add_widget(widget)
            return r

        self.date_input = TextInput(text=datetime.today().strftime("%Y-%m-%d"),
                                    multiline=False, input_filter=None)
        self.distance_input = TextInput(text="100", multiline=False)
        self.stroke_input = Spinner(text="Кроль", values=STROKES,
                                    size_hint_y=None, height=dp(42))
        self.time_input = TextInput(text="", multiline=False)
        self.notes_input = TextInput(text="", multiline=False)

        form.add_widget(row("Дата (ГГГГ-ММ-ДД):", self.date_input))
        form.add_widget(row("Дистанция, м:", self.distance_input))
        form.add_widget(row("Стиль:", self.stroke_input))
        form.add_widget(row("Время, сек:", self.time_input))
        form.add_widget(row("Заметки:", self.notes_input))
        root.add_widget(form)

        btns = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        self.add_btn = Button(text="➕ Добавить")
        self.update_btn = Button(text="💾 Сохранить", disabled=True)
        reset_btn = Button(text="↩ Сброс")
        self.add_btn.bind(on_release=lambda *a: self.add_entry())
        self.update_btn.bind(on_release=lambda *a: self.update_entry())
        reset_btn.bind(on_release=lambda *a: self.reset_form())
        btns.add_widget(self.add_btn)
        btns.add_widget(self.update_btn)
        btns.add_widget(reset_btn)
        root.add_widget(btns)

        list_label = Label(text="Записи (тап — редактировать):", size_hint_y=None,
                           height=dp(26), font_size=dp(12))
        root.add_widget(list_label)

        sv = ScrollView()
        self.entries_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                     spacing=dp(3))
        self.entries_box.bind(minimum_height=self.entries_box.setter("height"))
        sv.add_widget(self.entries_box)
        root.add_widget(sv)

        del_btn = Button(text="🗑 Удалить текущую (редактируемую) запись",
                         size_hint_y=None, height=dp(46))
        del_btn.bind(on_release=lambda *a: self.delete_entry())
        root.add_widget(del_btn)

        item.add_widget(root)
        return item

    def _collect_form(self):
        date_str = self.date_input.text.strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.popup("Ошибка", "Дата должна быть в формате ГГГГ-ММ-ДД")
            return None

        dist = self.distance_input.text.replace(",", ".").strip()
        try:
            if float(dist) <= 0:
                raise ValueError
        except ValueError:
            self.popup("Ошибка", "Дистанция должна быть положительным числом")
            return None

        tval = self.time_input.text.replace(",", ".").strip()
        try:
            if float(tval) <= 0:
                raise ValueError
        except ValueError:
            self.popup("Ошибка", "Время должно быть положительным числом (сек)")
            return None

        return {"date": date_str,
                "distance": dist,
                "stroke": self.stroke_input.text,
                "time": tval,
                "notes": self.notes_input.text}

    def add_entry(self):
        e = self._collect_form()
        if e is None:
            return
        self.entries.append(e)
        self.entries.sort(key=lambda x: x["date"])
        if not self.save_data():
            self.entries.pop()
            return
        self.refresh_entries()
        self.refresh_stats()
        self.reset_form()

    def update_entry(self):
        if self.editing_index is None:
            return
        e = self._collect_form()
        if e is None:
            return
        old = self.entries[self.editing_index]
        self.entries[self.editing_index] = e
        self.entries.sort(key=lambda x: x["date"])
        if not self.save_data():
            self.entries[self.editing_index] = old
            return
        self.refresh_entries()
        self.refresh_stats()
        self.reset_form()

    def load_entry(self, idx):
        e = self.entries[idx]
        self.editing_index = idx
        self.date_input.text = e["date"]
        self.distance_input.text = str(e["distance"])
        self.stroke_input.text = e["stroke"]
        self.time_input.text = str(e["time"])
        self.notes_input.text = e.get("notes", "")
        self.add_btn.disabled = True
        self.update_btn.disabled = False

    def reset_form(self):
        self.editing_index = None
        self.date_input.text = datetime.today().strftime("%Y-%m-%d")
        self.distance_input.text = "100"
        self.stroke_input.text = "Кроль"
        self.time_input.text = ""
        self.notes_input.text = ""
        self.add_btn.disabled = False
        self.update_btn.disabled = True

    def refresh_entries(self):
        self.entries_box.clear_widgets()
        for i, e in enumerate(self.entries):
            txt = (f'{e["date"]}  |  {e["distance"]} м  |  {e["stroke"]}  |  '
                   f'{e["time"]} с')
            if e.get("notes"):
                txt += f'\n{e["notes"]}'
            b = Button(text=txt, halign="left", valign="middle",
                       size_hint_y=None, height=dp(58),
                       background_normal="",
                       background_color=(0.92, 0.95, 1, 1),
                       color=(0.1, 0.1, 0.1, 1), font_size=dp(12))
            b.bind(size=lambda inst, v: setattr(inst, "text_size", (v[0] - dp(10), None)))
            b.bind(on_release=lambda inst, idx=i: self.load_entry(idx))
            self.entries_box.add_widget(b)

    def delete_entry(self):
        if self.editing_index is None:
            self.popup("Внимание", "Сначала выбери запись (тапни по ней).")
            return
        removed = self.entries.pop(self.editing_index)
        if not self.save_data():
            self.entries.insert(self.editing_index, removed)
            return
        self.reset_form()
        self.refresh_entries()
        self.refresh_stats()

    # ================= АНАЛИТИКА =================
    def _build_stats_tab(self):
        item = TabbedPanelItem(text="Аналитика")
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        top.add_widget(Label(text="Стиль:", size_hint_x=None, width=dp(60)))
        self.stroke_filter = Spinner(text="Все", values=["Все"] + STROKES,
                                     size_hint_x=None, width=dp(150))
        self.stroke_filter.bind(text=lambda *a: self.refresh_stats())
        top.add_widget(self.stroke_filter)
        top.add_widget(Button(text="Обновить",
                              on_release=lambda *a: self.refresh_stats()))
        top.add_widget(Button(text="CSV",
                              on_release=lambda *a: self.export_csv()))
        root.add_widget(top)

        self.stats_label = Label(text="", size_hint_y=None, height=dp(76),
                                 halign="left", valign="top", font_size=dp(12))
        self.stats_label.bind(size=lambda i, v: setattr(i, "text_size", (v[0], None)))
        root.add_widget(self.stats_label)

        self.chart = LineChart()
        root.add_widget(self.chart)

        item.add_widget(root)
        return item

    def _filtered(self):
        f = self.stroke_filter.text
        return [e for e in self.entries if f == "Все" or e["stroke"] == f]

    def refresh_stats(self):
        if not hasattr(self, "chart"):
            return
        filtered = self._filtered()
        if not filtered:
            self.stats_label.text = "📭 Нет данных для отображения."
            self.chart.set_series([])
            return

        times, dists = [], []
        for e in filtered:
            try:
                times.append(float(str(e["time"]).replace(",", ".")))
            except (ValueError, KeyError):
                pass
            try:
                dists.append(float(str(e["distance"]).replace(",", ".")))
            except (ValueError, KeyError):
                pass

        if times:
            self.stats_label.text = (
                f"📊 Записей: {len(filtered)}\n"
                f"Общая дистанция: {sum(dists):.0f} м\n"
                f"🏆 Лучшее: {min(times):.2f} с   |   "
                f"⏱ Среднее: {sum(times)/len(times):.2f} с"
            )
        else:
            self.stats_label.text = f"📊 Записей: {len(filtered)} (нет корректного времени)"

        # формируем серии для графика
        series = []
        f = self.stroke_filter.text
        if f == "Все":
            for s in sorted(set(e["stroke"] for e in filtered)):
                pts = []
                for e in filtered:
                    if e["stroke"] != s:
                        continue
                    try:
                        t = float(str(e["time"]).replace(",", "."))
                        d = datetime.strptime(e["date"], "%Y-%m-%d")
                    except (ValueError, KeyError):
                        continue
                    pts.append((d.toordinal(), t))
                pts.sort()
                if pts:
                    series.append((s, pts))
        else:
            pts = []
            for e in filtered:
                try:
                    t = float(str(e["time"]).replace(",", "."))
                    d = datetime.strptime(e["date"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    continue
                pts.append((d.toordinal(), t))
            pts.sort()
            if pts:
                series.append((f, pts))

        self.chart.set_series(series)

    # ================= CSV =================
    def _export_path(self):
        if platform == "android":
            try:
                from android.storage import primary_external_storage_path
                dl = os.path.join(primary_external_storage_path(), "Download")
                if os.path.isdir(dl):
                    return os.path.join(dl, "swimmer_diary.csv")
            except Exception:
                pass
        return os.path.join(self.user_data_dir, "swimmer_diary.csv")

    def export_csv(self):
        data = self._filtered()
        if not data:
            self.popup("Внимание", "Нет записей для экспорта.")
            return
        path = self._export_path()
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Дата", "Дистанция, м", "Стиль", "Время, сек", "Заметки"])
                for e in data:
                    w.writerow([e["date"], e["distance"], e["stroke"],
                                e["time"], e.get("notes", "")])
            self.popup("Готово", f"Файл сохранён:\n{path}")
        except Exception as err:
            self.popup("Ошибка", f"Не удалось сохранить:\n{err}")


if __name__ == "__main__":
    DiaryApp().run()
