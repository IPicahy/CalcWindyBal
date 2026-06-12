import customtkinter as ctk
import tkinter as tk
import math
import json
import os
import platform
import socket
import threading
from datetime import datetime

# Цветовая палитра
COLOR_BG = "#000000"
COLOR_CARD = "#0D0D0D"
COLOR_BORDER = "#4F4F4F"
COLOR_ACCENT = "#838383"
COLOR_TEXT_MUTED = "#9B9B9B"
COLOR_TEXT = "#EAECEE"
COLOR_HUD = "#2ECC71"  # Зеленый цвет для HUD стрелка

CREATE_NEW_STR = "[Создать новый профиль]"


# Класс всплывающих подсказок с таймером
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.timer = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None

        if not self.tw:
            x = self.widget.winfo_rootx() + 35
            y = self.widget.winfo_rooty() + 15

            self.tw = tk.Toplevel(self.widget)
            self.tw.wm_overrideredirect(True)
            self.tw.attributes("-topmost", True)
            self.tw.wm_geometry(f"+{x}+{y}")

            frame = ctk.CTkFrame(self.tw, corner_radius=0, border_width=2, border_color=COLOR_BORDER,
                                 fg_color=COLOR_CARD)
            frame.pack(fill="both", expand=True)

            label = ctk.CTkLabel(frame, text=self.text, justify='left', text_color=COLOR_TEXT, padx=15, pady=10,
                                 font=ctk.CTkFont(family="Segoe UI", size=13))
            label.pack()

    def leave(self, event=None):
        self.timer = self.widget.after(500, self.close)

    def close(self):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# База профилей по умолчанию
DEFAULT_PROFILES = {
    "M40A5 (.308 Win / M61)": {
        "v0": 845.0,
        "k_drag": 0.22,
        "wind_factor": 1.752,
        "gravity_factor": 1.0,
        "scope_table": {
            "100": 0.0, "200": 0.2, "300": 0.6, "400": 1.1, "500": 2.0,
            "600": 3.0, "700": 4.0, "800": 5.3, "900": 6.6, "1000": 8.0, "1100": 9.9
        }
    },
    "M200 Intervention (.408 CheyTac)": {
        "v0": 915.0,
        "k_drag": 0.12,
        "wind_factor": 3.296,
        "gravity_factor": 1.0,
        "scope_table": {
            "100": 0.0, "200": 0.0, "300": 0.0, "400": 0.1, "500": 0.6,
            "600": 1.0, "700": 1.4, "800": 2.1, "900": 2.5, "1000": 3.2,
            "1100": 3.8, "1200": 4.2, "1300": 4.8, "1400": 5.5, "1500": 6.4,
            "1600": 7.2, "1700": 8.0
        }
    },
    "DVL-10 (.308 Win / M61)": {
        "v0": 845.0,
        "k_drag": 0.22,
        "wind_factor": 3.662,
        "gravity_factor": 1.0,
        "scope_table": {
            "100": 0.0, "200": 0.3, "300": 0.8, "400": 151, "500": 2.0,
            "600": 3.2, "700": 4.2, "800": 5.5, "900": 6.7, "1000": 8.3, "1100": 10.2
        }
    }
}

PROFILES_FILE = "profiles.json"
SESSION_LOGS_FILE = "session_logs.json"


class UniversalBallisticStation:
    def __init__(self, root):
        self.root = root
        self.root.title("Баллистическая Станция")
        self.root.geometry("1000x950")
        self.root.minsize(950, 850)
        self.root.configure(fg_color=COLOR_BG)
        self.root.after(10, self.set_title_bar_color)

        # Привязка системного Ctrl+V (безопасный метод)
        self.root.bind('<Control-v>', self.paste_clipboard)
        self.root.bind('<Control-V>', self.paste_clipboard)

        # Перехват русской "М" через общее нажатие клавиш
        def catch_russian_paste(event):
            if (event.state & 0x0004) and event.keysym.lower() in ('м', 'v'):
                self.paste_clipboard()

        self.root.bind('<Key>', catch_russian_paste, add="+")

        self.font_title = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        self.font_label = ctk.CTkFont(family="Segoe UI", size=13)
        self.font_result = ctk.CTkFont(family="Consolas", size=15)

        self.profiles = self.load_profiles()
        self.logs = self.load_logs()

        initial_weapon = list(self.profiles.keys())[0] if self.profiles else ""
        initial_azimuth = str(self.logs[0].get("base_azimuth", "186")) if self.logs else "186"

        self.var_weapon = ctk.StringVar(value=initial_weapon)
        self.var_zero = ctk.StringVar(value="100")
        self.var_dist = ctk.StringVar(value="1000")
        self.var_delta_h = ctk.StringVar(value="0")
        self.var_shooter_h = ctk.StringVar(value="0")
        self.var_target_h = ctk.StringVar(value="0")
        self.var_target_desc = ctk.StringVar(value="")

        self.var_shoot_dir = ctk.StringVar(value=initial_azimuth)
        self.var_wind_speed = ctk.StringVar(value="0")
        self.var_wind_dir = ctk.StringVar(value="105")

        self.var_crosswind = ctk.StringVar(value="0")
        self.var_cross_dir = ctk.StringVar(value="СЛЕВА →")

        self.var_kac_total = ctk.StringVar(value="0")
        self.var_kac_cross = ctk.StringVar(value="0")
        self.var_kac_cross_dir = ctk.StringVar(value="<< Сносит ВЛЕВО")
        self.var_kac_head = ctk.StringVar(value="0")
        self.var_kac_head_dir = ctk.StringVar(value="↑ Встречный (В лицо)")

        # Сетевые переменные
        self.net_role = ctk.StringVar(value="Одиночка (Сеть выкл)")
        self.net_ip = ctk.StringVar(value="26.")
        self.is_listening = False
        self.sock = None

        self.hud_toplevel = None
        self.hud_label = None

        self.var_delete_target = ctk.StringVar(value="Нет целей")

        ctk.CTkLabel(self.root, text="Тактический Калькулятор", font=self.font_title, text_color=COLOR_TEXT).pack(
            pady=(15, 10))

        self.main_tabs = ctk.CTkTabview(
            self.root, fg_color=COLOR_BG, segmented_button_fg_color=COLOR_CARD,
            segmented_button_selected_color=COLOR_BORDER, segmented_button_selected_hover_color=COLOR_BORDER,
            segmented_button_unselected_color=COLOR_CARD, segmented_button_unselected_hover_color=COLOR_BG,
            text_color=COLOR_TEXT
        )
        self.main_tabs.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.tab_calc = self.main_tabs.add("Калькулятор")
        self.tab_calib = self.main_tabs.add("Авто-Калибровка")
        self.tab_edit = self.main_tabs.add("Редактор оружия")

        self.build_calc_tab()
        self.build_calib_tab()
        self.build_editor_tab()

    def paste_clipboard(self, event=None):
        try:
            widget = self.root.focus_get()
            if isinstance(widget, tk.Entry) or isinstance(widget, ctk.CTkEntry):
                widget.event_generate('<<Paste>>')
        except Exception:
            pass

    def set_title_bar_color(self):
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(0x00000000)), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
            except Exception:
                pass

    def load_profiles(self):
        if os.path.exists(PROFILES_FILE):
            try:
                with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return DEFAULT_PROFILES.copy()
        return DEFAULT_PROFILES.copy()

    def save_profiles(self):
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, ensure_ascii=False, indent=4)

    def load_logs(self):
        if os.path.exists(SESSION_LOGS_FILE):
            try:
                with open(SESSION_LOGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_logs(self, logs):
        with open(SESSION_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)

    def angle_diff(self, a, b):
        diff = abs(a - b) % 360
        return 360 - diff if diff > 180 else diff

    def refresh_dropdowns(self):
        profile_list = list(self.profiles.keys())
        self.dropdown_weapon.configure(values=profile_list)
        self.calib_dropdown_weapon.configure(values=profile_list)
        editor_list = profile_list + [CREATE_NEW_STR]
        self.edit_dropdown_weapon.configure(values=editor_list)
        if self.var_weapon.get() not in profile_list and profile_list:
            self.var_weapon.set(profile_list[0])
        current_edit = self.edit_weapon_var.get()
        if current_edit not in editor_list:
            if profile_list:
                self.edit_weapon_var.set(profile_list[0])
                self.load_profile_into_editor(profile_list[0])

    def sync_topo_tabs(self):
        self.cal_topo_tabs.set(self.topo_tabs.get())

    def sync_topo_tabs_reverse(self):
        self.topo_tabs.set(self.cal_topo_tabs.get())

    def sync_wind_tabs(self):
        self.cal_wind_tabs.set(self.wind_tabs.get())

    def sync_wind_tabs_reverse(self):
        self.wind_tabs.set(self.cal_wind_tabs.get())

    def get_mil_from_table(self, dist, table):
        dists = sorted([float(k) for k in table.keys()])
        if dist <= dists[0]:
            return float(table[str(int(dists[0]))])
        elif dist >= dists[-1]:
            d1, d2 = dists[-2], dists[-1]
            m1, m2 = float(table[str(int(d1))]), float(table[str(int(d2))])
            return m1 + (m2 - m1) * (dist - d1) / (d2 - d1)
        else:
            for i in range(len(dists) - 1):
                if dists[i] <= dist <= dists[i + 1]:
                    d1, d2 = dists[i], dists[i + 1]
                    m1, m2 = float(table[str(int(d1))]), float(table[str(int(d2))])
                    return m1 + (m2 - m1) * (dist - d1) / (d2 - d1)
        return 0.0

    # ==========================================
    # СЕТЕВЫЕ МЕТОДЫ И ИНТЕРФЕЙС HUD
    # ==========================================
    def toggle_network(self, choice):
        if choice == "Стрелок (Прием)":
            self.net_spotter_frame.pack_forget()
            self.net_shooter_frame.pack(side="left", fill="x", expand=True)

            if not self.is_listening:
                self.start_listening()
                self.set_result_text(
                    "🎧 РЕЖИМ 'СТРЕЛОК' АКТИВИРОВАН.\nОкно HUD появится на экране автоматически, как только Споттер пришлет данные.\n─────────────────────────────\n" + self.result_textbox.get(
                        "0.0", tk.END))

        elif choice == "Споттер (Отправка)":
            self.net_shooter_frame.pack_forget()
            self.net_spotter_frame.pack(side="left", fill="x", expand=True)
            self.stop_listening()

        else:
            self.net_spotter_frame.pack_forget()
            self.net_shooter_frame.pack_forget()
            self.stop_listening()

    def start_listening(self):
        self.is_listening = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 45000))
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def stop_listening(self):
        self.is_listening = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

        self.clear_shooter_hud()

    def create_hud_window(self):
        self.hud_toplevel = tk.Toplevel(self.root)
        self.hud_toplevel.overrideredirect(True)
        self.hud_toplevel.attributes("-topmost", True)
        self.hud_toplevel.geometry("+20+20")
        # Скрываем курсор для окна
        self.hud_toplevel.configure(cursor="none")

        # Скрываем курсор для фрейма
        frame = ctk.CTkFrame(self.hud_toplevel, corner_radius=5, border_width=2, border_color=COLOR_HUD,
                             fg_color=COLOR_BG, cursor="none")
        frame.pack(fill="both", expand=True)

        # Скрываем курсор для текста
        self.hud_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
                                      text_color=COLOR_HUD, justify="left", cursor="none")
        self.hud_label.pack(padx=15, pady=15)
        self.hud_toplevel.withdraw()

    def clear_shooter_hud(self):
        if self.hud_toplevel and self.hud_toplevel.winfo_exists():
            self.hud_toplevel.withdraw()

    def listen_loop(self):
        while self.is_listening:
            try:
                data, addr = self.sock.recvfrom(8192)
                if data:
                    text = data.decode('utf-8')
                    self.root.after(0, self.update_hud, text)
            except:
                break

    def update_hud(self, text):
        try:
            data = json.loads(text)
        except:
            return

        if data.get("action") == "clear" or not data.get("content"):
            self.clear_shooter_hud()
        elif data.get("action") == "update_all":
            content = data.get("content", "")
            if not content:
                self.clear_shooter_hud()
                return

            if self.hud_toplevel is None or not self.hud_toplevel.winfo_exists():
                self.create_hud_window()

            self.hud_label.configure(text=content)
            self.hud_toplevel.deiconify()
            self.hud_toplevel.attributes("-topmost", True)

    def send_all_targets_via_net(self, display_text):
        ip = self.net_ip.get().strip()
        if not ip or ip == "26." or len(ip) < 7:
            return  # Если IP не вписан, тихо не отправляем

        payload = {"action": "update_all", "content": display_text}
        if not display_text:
            payload = {"action": "clear"}

        try:
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.settimeout(2.0)
            json_data = json.dumps(payload, ensure_ascii=False)
            send_sock.sendto(json_data.encode('utf-8'), (ip, 45000))
            send_sock.close()
        except:
            pass

    # ==========================================
    # РЕНДЕР И ОБНОВЛЕНИЕ ДАННЫХ
    # ==========================================
    def get_wind_params(self):
        shoot_dir_str = self.var_shoot_dir.get().replace(',', '.')
        return {
            "tab": self.wind_tabs.get(),
            "shoot_dir": float(shoot_dir_str) if shoot_dir_str else 0.0,
            "wind_speed": float(self.var_wind_speed.get().replace(',', '.') or 0),
            "wind_dir": float(self.var_wind_dir.get().replace(',', '.') or 0),
            "cw_speed": float(self.var_crosswind.get().replace(',', '.') or 0),
            "cw_dir": self.var_cross_dir.get(),
            "kac_cross": abs(float(self.var_kac_cross.get().replace(',', '.') or 0)),
            "kac_cross_dir": self.var_kac_cross_dir.get(),
            "kac_head": abs(float(self.var_kac_head.get().replace(',', '.') or 0)),
            "kac_head_dir": self.var_kac_head_dir.get()
        }

    def update_display(self, logs, wind_params, current_time):
        final_output = ""
        hud_blocks = []
        target_keys = []

        # Рендерим в порядке добавления (от старых к новым). Новые снизу.
        for i, tgt in enumerate(logs):
            target_num = i + 1
            res_str, compact_payload = self.compute_ballistics(tgt, wind_params, current_time, target_num)

            desc = tgt.get("description", "").strip()
            t_name = f"{target_num}. {desc if desc else 'Без пометки'} ({tgt['distance']:.0f}м)"

            target_keys.append(t_name)
            hud_blocks.append(compact_payload)
            # В UI станции выводим новые расчеты сверху
            final_output = res_str + "\n\n\n" + final_output

        if target_keys:
            self.delete_dropdown.configure(values=target_keys, state="normal")
            if self.var_delete_target.get() not in target_keys:
                self.var_delete_target.set(target_keys[-1])  # Выбираем последнюю добавленную
        else:
            self.delete_dropdown.configure(values=["Нет целей"], state="disabled")
            self.var_delete_target.set("Нет целей")

        final_output = f"Успешно загружено целей: {len(logs)}\n\n" + final_output
        self.set_result_text(final_output.strip())

        # АВТОМАТИЧЕСКАЯ ОТПРАВКА СТРЕЛКУ (если выбран режим)
        if self.net_role.get() == "Споттер (Отправка)":
            display_text = "\n────────────────────────\n".join(hud_blocks)
            self.send_all_targets_via_net(display_text)

    def delete_specific_target(self):
        sel = self.var_delete_target.get()
        if not sel or sel == "Нет целей": return

        try:
            # Извлекаем порядковый индекс (например "1. Пометка" -> индекс 0)
            idx = int(sel.split('.')[0]) - 1
            logs = self.load_logs()
            if 0 <= idx < len(logs):
                logs.pop(idx)
                self.save_logs(logs)

                # Перерисовываем UI и автоматом отправляем новую картину
                current_time = datetime.now().strftime("%H:%M:%S")
                wind_params = self.get_wind_params()
                self.update_display(logs, wind_params, current_time)
        except Exception:
            pass

    # ВКЛАДКА 1: КАЛЬКУЛЯТОР
    def build_calc_tab(self):
        top_frame = ctk.CTkFrame(self.tab_calc, corner_radius=10, border_width=2, border_color=COLOR_BORDER,
                                 fg_color=COLOR_CARD)
        top_frame.pack(fill="x", padx=10, pady=(5, 10))

        top_frame.grid_columnconfigure(0, weight=5)
        top_frame.grid_columnconfigure(1, weight=2)
        top_frame.grid_columnconfigure(2, weight=2)

        ctk.CTkLabel(top_frame, text="Профиль оружия:", text_color=COLOR_TEXT_MUTED,
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).grid(row=0, column=0, sticky="w",
                                                                                       padx=15, pady=(10, 0))
        ctk.CTkLabel(top_frame, text="Пристрелка (м):", text_color=COLOR_TEXT_MUTED,
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).grid(row=0, column=1, sticky="w",
                                                                                       padx=10, pady=(10, 0))
        ctk.CTkLabel(top_frame, text="Дистанция (м):", text_color=COLOR_TEXT_MUTED,
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).grid(row=0, column=2, sticky="w",
                                                                                       padx=15, pady=(10, 0))

        self.dropdown_weapon = ctk.CTkOptionMenu(top_frame, values=list(self.profiles.keys()), variable=self.var_weapon,
                                                 height=35, fg_color=COLOR_BORDER, button_color=COLOR_CARD,
                                                 button_hover_color=COLOR_BG, text_color=COLOR_TEXT,
                                                 dropdown_fg_color=COLOR_CARD, dropdown_text_color=COLOR_TEXT,
                                                 font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"))
        self.dropdown_weapon.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 15))

        self.dropdown_zero = ctk.CTkOptionMenu(top_frame,
                                               values=["100", "200", "300", "400", "500", "600", "700", "800", "900",
                                                       "1000", "1100", "1200", "1300", "1400", "1500", "1600", "1700",
                                                       "1800", "1900", "2000"], variable=self.var_zero, height=35,
                                               fg_color=COLOR_BORDER, button_color=COLOR_CARD,
                                               button_hover_color=COLOR_BG, text_color=COLOR_TEXT,
                                               dropdown_fg_color=COLOR_CARD, dropdown_text_color=COLOR_TEXT,
                                               font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.dropdown_zero.grid(row=1, column=1, sticky="ew", padx=10, pady=(5, 15))

        self.entry_dist = ctk.CTkEntry(top_frame, textvariable=self.var_dist, height=35, corner_radius=8,
                                       fg_color=COLOR_BG, border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.entry_dist.grid(row=1, column=2, sticky="ew", padx=15, pady=(5, 15))

        mid_frame = ctk.CTkFrame(self.tab_calc, fg_color="transparent")
        mid_frame.pack(fill="x", padx=10, pady=5)
        mid_frame.grid_columnconfigure(0, weight=1)
        mid_frame.grid_columnconfigure(1, weight=1)

        topo_container = ctk.CTkFrame(mid_frame, corner_radius=10, border_width=2, border_color=COLOR_BORDER,
                                      fg_color=COLOR_CARD)
        topo_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.topo_tabs = ctk.CTkTabview(topo_container, height=235, fg_color=COLOR_BG, command=self.sync_topo_tabs,
                                        segmented_button_fg_color=COLOR_CARD,
                                        segmented_button_selected_color=COLOR_BORDER,
                                        segmented_button_selected_hover_color=COLOR_BORDER,
                                        segmented_button_unselected_color=COLOR_CARD,
                                        segmented_button_unselected_hover_color=COLOR_BG, text_color=COLOR_TEXT)
        self.topo_tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.topo_tabs.add("Дальномер")
        self.topo_tabs.add("По карте")

        d_frame = self.topo_tabs.tab("Дальномер")
        d_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(d_frame, text="Перепад высоты (м, - ниже / + выше):", text_color=COLOR_TEXT_MUTED,
                     font=self.font_label).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.entry_delta_h = ctk.CTkEntry(d_frame, textvariable=self.var_delta_h, height=35, fg_color=COLOR_BG,
                                          border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.entry_delta_h.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 5))

        map_frame = self.topo_tabs.tab("По карте")
        map_frame.columnconfigure(0, weight=1)
        map_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(map_frame, text="Стрелок (м):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=0,
                                                                                                             column=0,
                                                                                                             sticky="w",
                                                                                                             padx=10,
                                                                                                             pady=(
                                                                                                             10, 0))
        self.entry_shooter_h = ctk.CTkEntry(map_frame, textvariable=self.var_shooter_h, height=35, fg_color=COLOR_BG,
                                            border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.entry_shooter_h.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 5))
        ctk.CTkLabel(map_frame, text="Цель (м):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=0,
                                                                                                          column=1,
                                                                                                          sticky="w",
                                                                                                          padx=10,
                                                                                                          pady=(10, 0))
        self.entry_target_h = ctk.CTkEntry(map_frame, textvariable=self.var_target_h, height=35, fg_color=COLOR_BG,
                                           border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.entry_target_h.grid(row=1, column=1, sticky="ew", padx=10, pady=(5, 5))

        wind_container = ctk.CTkFrame(mid_frame, corner_radius=10, border_width=2, border_color=COLOR_BORDER,
                                      fg_color=COLOR_CARD)
        wind_container.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self.wind_tabs = ctk.CTkTabview(wind_container, height=235, fg_color=COLOR_BG, command=self.sync_wind_tabs,
                                        segmented_button_fg_color=COLOR_CARD,
                                        segmented_button_selected_color=COLOR_BORDER,
                                        segmented_button_selected_hover_color=COLOR_BORDER,
                                        segmented_button_unselected_color=COLOR_CARD,
                                        segmented_button_unselected_hover_color=COLOR_BG, text_color=COLOR_TEXT)
        self.wind_tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.wind_tabs.add("Метеостанция")
        self.wind_tabs.add("Вектор ветра")
        self.wind_tabs.add("Боковой")

        kac_frame = self.wind_tabs.tab("Метеостанция")
        kac_frame.grid_columnconfigure((1, 2), weight=1)
        self.show_tot_calc = tk.BooleanVar(value=False)

        def toggle_tot_calc():
            if self.show_tot_calc.get():
                self.lbl_tot_calc.grid(row=1, column=0, sticky="w", padx=5, pady=(2, 2))
                self.ent_tot_calc.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
                self.btn_q_tot_calc.grid(row=1, column=3, padx=(0, 5))
            else:
                self.lbl_tot_calc.grid_remove()
                self.ent_tot_calc.grid_remove()
                self.btn_q_tot_calc.grid_remove()
                self.var_kac_total.set("0")

        cb_tot_calc = ctk.CTkCheckBox(kac_frame, text="Включить поле 'Общая скорость'", variable=self.show_tot_calc,
                                      command=toggle_tot_calc, text_color=COLOR_TEXT_MUTED)
        cb_tot_calc.grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=2)
        self.lbl_tot_calc = ctk.CTkLabel(kac_frame, text="Общая (м/с):", text_color=COLOR_TEXT_MUTED,
                                         font=self.font_label)
        self.ent_tot_calc = ctk.CTkEntry(kac_frame, textvariable=self.var_kac_total, height=26, fg_color=COLOR_BG,
                                         border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.btn_q_tot_calc = ctk.CTkButton(kac_frame, text="?", width=24, height=24, corner_radius=12,
                                            fg_color="transparent", border_width=2, border_color=COLOR_BORDER,
                                            text_color=COLOR_BORDER, hover_color=COLOR_CARD,
                                            font=ctk.CTkFont(weight="bold"))
        ToolTip(self.btn_q_tot_calc, "ДЛЯ КОРРЕКТИРОВЩИКА: Общая скорость\nОна НЕ НУЖНА для расчета выстрела.")

        ctk.CTkLabel(kac_frame, text="Азимут (°):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=2,
                                                                                                            column=0,
                                                                                                            sticky="w",
                                                                                                            padx=5,
                                                                                                            pady=(2, 2))
        ctk.CTkEntry(kac_frame, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_BG,
                     border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=2, column=1, columnspan=2, sticky="ew",
                                                                            padx=5)

        ctk.CTkLabel(kac_frame, text="Боковой (Cross):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=3,
                                                                                                                 column=0,
                                                                                                                 sticky="w",
                                                                                                                 padx=5,
                                                                                                                 pady=(
                                                                                                                 2, 2))
        ctk.CTkEntry(kac_frame, textvariable=self.var_kac_cross, width=60, height=26, fg_color=COLOR_BG,
                     border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=3, column=1, sticky="w", padx=5)
        ctk.CTkOptionMenu(kac_frame, variable=self.var_kac_cross_dir, values=["<< Сносит ВЛЕВО", "Сносит ВПРАВО >>"],
                          height=26, fg_color=COLOR_BORDER, button_color=COLOR_CARD, text_color=COLOR_TEXT).grid(row=3,
                                                                                                                 column=2,
                                                                                                                 sticky="ew",
                                                                                                                 padx=5)

        ctk.CTkLabel(kac_frame, text="Прямой (Head):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=4,
                                                                                                               column=0,
                                                                                                               sticky="w",
                                                                                                               padx=5,
                                                                                                               pady=(
                                                                                                               2, 2))
        ctk.CTkEntry(kac_frame, textvariable=self.var_kac_head, width=60, height=26, fg_color=COLOR_BG,
                     border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=4, column=1, sticky="w", padx=5)
        ctk.CTkOptionMenu(kac_frame, variable=self.var_kac_head_dir,
                          values=["↑ Встречный (В лицо)", "↓ Попутный (В спину)"], height=26, fg_color=COLOR_BORDER,
                          button_color=COLOR_CARD, text_color=COLOR_TEXT).grid(row=4, column=2, sticky="ew", padx=5)

        wv_frame = self.wind_tabs.tab("Вектор ветра")
        wv_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(wv_frame, text="Азимут стрельбы (°):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=0, column=0, sticky="w", padx=10)
        self.entry_shoot_dir = ctk.CTkEntry(wv_frame, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_BG,
                                            border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=1, column=0,
                                                                                                   sticky="ew", padx=10,
                                                                                                   pady=(0, 5))
        ctk.CTkLabel(wv_frame, text="Скорость ветра (м/с):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=2, column=0, sticky="w", padx=10)
        self.entry_wind_speed = ctk.CTkEntry(wv_frame, textvariable=self.var_wind_speed, height=26, fg_color=COLOR_BG,
                                             border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=3, column=0,
                                                                                                    sticky="ew",
                                                                                                    padx=10,
                                                                                                    pady=(0, 5))
        ctk.CTkLabel(wv_frame, text="Направление (ОТКУДА, °):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=4, column=0, sticky="w", padx=10)
        self.entry_wind_dir = ctk.CTkEntry(wv_frame, textvariable=self.var_wind_dir, height=26, fg_color=COLOR_BG,
                                           border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=5, column=0,
                                                                                                  sticky="ew", padx=10,
                                                                                                  pady=(0, 5))

        bw_frame = self.wind_tabs.tab("Боковой")
        bw_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bw_frame, text="Азимут стрельбы (°):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=0, column=0, sticky="w", padx=10)
        ctk.CTkEntry(bw_frame, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_BG, border_color=COLOR_BORDER,
                     text_color=COLOR_TEXT).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkLabel(bw_frame, text="Скорость сноса (м/с):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=2, column=0, sticky="w", padx=10)
        self.entry_crosswind = ctk.CTkEntry(bw_frame, textvariable=self.var_crosswind, height=26, fg_color=COLOR_BG,
                                            border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=3, column=0,
                                                                                                   sticky="ew", padx=10,
                                                                                                   pady=(0, 10))
        ctk.CTkLabel(bw_frame, text="Откуда дует ветер:", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=4,
                                                                                                                  column=0,
                                                                                                                  sticky="w",
                                                                                                                  padx=10)
        rb_frame_calc = ctk.CTkFrame(bw_frame, fg_color="transparent")
        rb_frame_calc.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkRadioButton(rb_frame_calc, text="СЛЕВА →", variable=self.var_cross_dir, value="СЛЕВА →",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)
        ctk.CTkRadioButton(rb_frame_calc, text="← СПРАВА", variable=self.var_cross_dir, value="← СПРАВА",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)

        ctk.CTkFrame(self.tab_calc, height=2, fg_color=COLOR_BORDER).pack(fill="x", padx=15, pady=5)

        desc_frame = ctk.CTkFrame(self.tab_calc, fg_color="transparent")
        desc_frame.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(desc_frame, text="Описание цели (пометка для логов):", text_color=COLOR_TEXT_MUTED,
                     font=self.font_label).pack(anchor="w", padx=5, pady=(0, 2))
        self.entry_desc = ctk.CTkEntry(desc_frame, textvariable=self.var_target_desc, height=35, fg_color=COLOR_BG,
                                       border_color=COLOR_BORDER, text_color=COLOR_TEXT,
                                       placeholder_text="Например: 'Снайпер на камнях'")
        self.entry_desc.pack(fill="x", expand=True, padx=5)

        # -------------------------------------------------------------
        # БЛОК ИНТЕРФЕЙСА ДЛЯ СЕТИ С НОВЫМ ДИЗАЙНОМ И АВТО-ОТПРАВКОЙ
        # -------------------------------------------------------------
        self.net_frame = ctk.CTkFrame(self.tab_calc, fg_color="transparent")
        self.net_frame.pack(fill="x", padx=10, pady=(5, 5))

        # Первый ряд: Выбор режима и IP
        net_row_1 = ctk.CTkFrame(self.net_frame, fg_color="transparent")
        net_row_1.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(net_row_1, text="Режим (VPN):", text_color=COLOR_TEXT_MUTED, font=self.font_label).pack(
            side="left", padx=5)
        ctk.CTkOptionMenu(net_row_1, variable=self.net_role,
                          values=["Одиночка (Сеть выкл)", "Стрелок (Прием)", "Споттер (Отправка)"],
                          command=self.toggle_network, width=160, height=28, fg_color=COLOR_BORDER,
                          button_color=COLOR_CARD, text_color=COLOR_TEXT).pack(side="left", padx=5)

        self.net_spotter_frame = ctk.CTkFrame(net_row_1, fg_color="transparent")
        ctk.CTkLabel(self.net_spotter_frame, text="IP Стрелка:", text_color=COLOR_TEXT_MUTED,
                     font=self.font_label).pack(side="left", padx=(10, 5))
        self.ent_ip = ctk.CTkEntry(self.net_spotter_frame, textvariable=self.net_ip, width=110, height=28,
                                   fg_color=COLOR_BG, border_color=COLOR_BORDER, text_color=COLOR_TEXT)
        self.ent_ip.pack(side="left", padx=5)
        ctk.CTkLabel(self.net_spotter_frame, text="✅ Авто-отправка активна", text_color="#2ECC71",
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=15)

        # Кнопка очистки для Стрелка
        self.net_shooter_frame = ctk.CTkFrame(net_row_1, fg_color="transparent")
        self.btn_clear_hud = ctk.CTkButton(self.net_shooter_frame, text="🗑 Очистить HUD", height=28, width=130,
                                           command=self.clear_shooter_hud, fg_color=COLOR_BG, border_width=2,
                                           border_color=COLOR_BORDER, text_color=COLOR_TEXT,
                                           font=ctk.CTkFont(weight="bold"))
        self.btn_clear_hud.pack(side="left", padx=15)

        # Второй ряд: Удаление конкретной цели
        self.net_action_row = ctk.CTkFrame(self.net_frame, fg_color="transparent")
        self.net_action_row.pack(fill="x")
        ctk.CTkLabel(self.net_action_row, text="Управление целями:", text_color=COLOR_TEXT_MUTED,
                     font=self.font_label).pack(side="left", padx=5)
        self.delete_dropdown = ctk.CTkOptionMenu(self.net_action_row, variable=self.var_delete_target,
                                                 values=["Нет целей"], height=28, width=220, fg_color=COLOR_BORDER,
                                                 button_color=COLOR_CARD, text_color=COLOR_TEXT, state="disabled")
        self.delete_dropdown.pack(side="left", padx=5)
        self.btn_delete_spec = ctk.CTkButton(self.net_action_row, text="🗑 Удалить цель", height=28,
                                             command=self.delete_specific_target, fg_color=COLOR_BG, border_width=2,
                                             border_color=COLOR_BORDER, hover_color=COLOR_BORDER, text_color=COLOR_TEXT,
                                             font=ctk.CTkFont(weight="bold"))
        self.btn_delete_spec.pack(side="left", padx=5)

        self.toggle_network(self.net_role.get())
        # -------------------------------------------------------------

        btn_frame_main = ctk.CTkFrame(self.tab_calc, fg_color="transparent")
        btn_frame_main.pack(fill="x", padx=10, pady=(5, 10))

        self.btn_calc = ctk.CTkButton(btn_frame_main, text="Рассчитать вынос", height=45, fg_color=COLOR_ACCENT,
                                      hover_color=COLOR_BORDER, text_color=COLOR_BG,
                                      font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), corner_radius=10,
                                      command=self.calculate)
        self.btn_calc.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_clear = ctk.CTkButton(btn_frame_main, text="Стереть логи", height=45, fg_color=COLOR_BG,
                                       hover_color=COLOR_BORDER, border_width=2, border_color=COLOR_BORDER,
                                       text_color=COLOR_TEXT,
                                       font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), corner_radius=10,
                                       command=self.clear_logs)
        self.btn_clear.pack(side="right", fill="x", expand=False, padx=(5, 0))

        self.result_frame = ctk.CTkFrame(self.tab_calc, corner_radius=10, border_width=2, border_color=COLOR_BORDER,
                                         fg_color=COLOR_BG)
        self.result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.result_textbox = ctk.CTkTextbox(self.result_frame, font=self.font_result, text_color=COLOR_TEXT,
                                             fg_color=COLOR_BG, wrap="word")
        self.result_textbox.pack(fill="both", expand=True, padx=15, pady=15)

        self.render_existing_logs()
        self.root.bind('<Return>', lambda event: self.calculate())

    def set_result_text(self, text):
        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("0.0", tk.END)
        self.result_textbox.insert("0.0", text)
        self.result_textbox.configure(state="disabled")

    def clear_logs(self):
        self.save_logs([])

        # Обновляем интерфейс пустой базой
        current_time = datetime.now().strftime("%H:%M:%S")
        try:
            wind_params = self.get_wind_params()
        except:
            wind_params = {}

        self.update_display([], wind_params, current_time)
        self.set_result_text("Логи очищены.\n\nНачни новый замер для формирования нового списка целей.")

        # Уведомляем стрелка об очистке
        if self.net_role.get() == "Споттер (Отправка)":
            ip = self.net_ip.get().strip()
            if ip and ip != "26." and len(ip) >= 7:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.sendto(json.dumps({"action": "clear"}).encode('utf-8'), (ip, 45000))
                    sock.close()
                except:
                    pass

    def render_existing_logs(self):
        logs = self.load_logs()
        if not logs:
            self.set_result_text("Ожидание данных...\n\nВведи параметры и нажми 'Рассчитать вынос'.")
            return

        current_time = datetime.now().strftime("%H:%M:%S")

        try:
            wind_params = self.get_wind_params()
            self.update_display(logs, wind_params, current_time)
        except ValueError:
            self.set_result_text("Ошибка ввода ветра!\nПроверьте, что в полях только цифры.")
            return

    # ВКЛАДКА 2: АВТО-КАЛИБРОВКА
    def build_calib_tab(self):
        center_frame = ctk.CTkFrame(self.tab_calib, fg_color="transparent")
        center_frame.pack(expand=True, fill="both", pady=5, padx=10)

        box = ctk.CTkFrame(center_frame, corner_radius=10, border_width=2, border_color=COLOR_BORDER,
                           fg_color=COLOR_CARD)
        box.pack(fill="both", expand=True)

        top_bar = ctk.CTkFrame(box, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=10)
        top_bar.grid_columnconfigure(0, weight=3)
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top_bar, text="Калибруемый профиль:", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=0, column=0, sticky="w", padx=10)
        ctk.CTkLabel(top_bar, text="Пристрелка (м):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=0,
                                                                                                              column=1,
                                                                                                              sticky="w",
                                                                                                              padx=10)
        ctk.CTkLabel(top_bar, text="Дистанция (м):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(row=0,
                                                                                                             column=2,
                                                                                                             sticky="w",
                                                                                                             padx=10)

        self.calib_dropdown_weapon = ctk.CTkOptionMenu(top_bar, values=list(self.profiles.keys()),
                                                       variable=self.var_weapon, height=35, fg_color=COLOR_BORDER,
                                                       button_color=COLOR_BG, button_hover_color=COLOR_CARD,
                                                       text_color=COLOR_TEXT)
        self.calib_dropdown_weapon.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 5))

        self.calib_dropdown_zero = ctk.CTkOptionMenu(top_bar,
                                                     values=["100", "200", "300", "400", "500", "600", "700", "800",
                                                             "900", "1000", "1100", "1200", "1300", "1400", "1500",
                                                             "1600", "1700", "1800", "1900", "2000"],
                                                     variable=self.var_zero, height=35, fg_color=COLOR_BORDER,
                                                     button_color=COLOR_CARD, button_hover_color=COLOR_BG,
                                                     text_color=COLOR_TEXT, dropdown_fg_color=COLOR_CARD,
                                                     dropdown_text_color=COLOR_TEXT,
                                                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.calib_dropdown_zero.grid(row=1, column=1, sticky="ew", padx=10, pady=(5, 5))

        ctk.CTkEntry(top_bar, textvariable=self.var_dist, height=35, fg_color=COLOR_BG, border_color=COLOR_BORDER,
                     text_color=COLOR_TEXT).grid(row=1, column=2, sticky="ew", padx=10, pady=(5, 5))

        mid_frame = ctk.CTkFrame(box, fg_color="transparent")
        mid_frame.pack(fill="x", padx=10, pady=0)
        mid_frame.grid_columnconfigure(0, weight=1)
        mid_frame.grid_columnconfigure(1, weight=1)

        topo_container = ctk.CTkFrame(mid_frame, corner_radius=10, border_width=1, border_color=COLOR_BORDER,
                                      fg_color=COLOR_BG)
        topo_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.cal_topo_tabs = ctk.CTkTabview(topo_container, height=210, fg_color=COLOR_BG,
                                            command=self.sync_topo_tabs_reverse, segmented_button_fg_color=COLOR_CARD,
                                            segmented_button_selected_color=COLOR_BORDER)
        self.cal_topo_tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.cal_topo_tabs.add("Дальномер")
        self.cal_topo_tabs.add("По карте")

        d_frame_c = self.cal_topo_tabs.tab("Дальномер")
        d_frame_c.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(d_frame_c, text="Перепад высоты (м):", text_color=COLOR_TEXT_MUTED, font=self.font_label).grid(
            row=0, column=0, sticky="w", padx=10)
        ctk.CTkEntry(d_frame_c, textvariable=self.var_delta_h, height=35, fg_color=COLOR_CARD,
                     border_color=COLOR_BORDER).grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        map_frame_c = self.cal_topo_tabs.tab("По карте")
        map_frame_c.grid_columnconfigure(0, weight=1)
        map_frame_c.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(map_frame_c, text="Стрелок (м):", text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w",
                                                                                         padx=10)
        ctk.CTkEntry(map_frame_c, textvariable=self.var_shooter_h, height=35, fg_color=COLOR_CARD,
                     border_color=COLOR_BORDER).grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(map_frame_c, text="Цель (м):", text_color=COLOR_TEXT_MUTED).grid(row=0, column=1, sticky="w",
                                                                                      padx=10)
        ctk.CTkEntry(map_frame_c, textvariable=self.var_target_h, height=35, fg_color=COLOR_CARD,
                     border_color=COLOR_BORDER).grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        wind_container = ctk.CTkFrame(mid_frame, corner_radius=10, border_width=1, border_color=COLOR_BORDER,
                                      fg_color=COLOR_BG)
        wind_container.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.cal_wind_tabs = ctk.CTkTabview(wind_container, height=210, fg_color=COLOR_BG,
                                            command=self.sync_wind_tabs_reverse, segmented_button_fg_color=COLOR_CARD,
                                            segmented_button_selected_color=COLOR_BORDER)
        self.cal_wind_tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.cal_wind_tabs.add("Метеостанция")
        self.cal_wind_tabs.add("Вектор ветра")
        self.cal_wind_tabs.add("Боковой")

        kac_frame_c = self.cal_wind_tabs.tab("Метеостанция")
        kac_frame_c.grid_columnconfigure((1, 2), weight=1)

        self.show_tot_calib = tk.BooleanVar(value=False)

        def toggle_tot_calib():
            if self.show_tot_calib.get():
                self.lbl_tot_calib.grid(row=1, column=0, sticky="w", padx=5, pady=(2, 2))
                self.ent_tot_calib.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
                self.btn_q_tot_calib.grid(row=1, column=3, padx=(0, 5))
            else:
                self.lbl_tot_calib.grid_remove()
                self.ent_tot_calib.grid_remove()
                self.btn_q_tot_calib.grid_remove()
                self.var_kac_total.set("0")

        cb_tot_calib = ctk.CTkCheckBox(kac_frame_c, text="Включить поле 'Общая скорость'", variable=self.show_tot_calib,
                                       command=toggle_tot_calib, text_color=COLOR_TEXT_MUTED)
        cb_tot_calib.grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=2)

        self.lbl_tot_calib = ctk.CTkLabel(kac_frame_c, text="Общая (м/с):", text_color=COLOR_TEXT_MUTED)
        self.ent_tot_calib = ctk.CTkEntry(kac_frame_c, textvariable=self.var_kac_total, height=26, fg_color=COLOR_CARD)
        self.btn_q_tot_calib = ctk.CTkButton(kac_frame_c, text="?", width=24, height=24, corner_radius=12,
                                             fg_color="transparent", border_width=2, border_color=COLOR_BORDER,
                                             text_color=COLOR_BORDER, hover_color=COLOR_CARD,
                                             font=ctk.CTkFont(weight="bold"))

        ctk.CTkLabel(kac_frame_c, text="Азимут (°):", text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w",
                                                                                        padx=5, pady=(2, 2))
        ctk.CTkEntry(kac_frame_c, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_CARD).grid(row=2, column=1,
                                                                                                        columnspan=2,
                                                                                                        sticky="ew",
                                                                                                        padx=5)
        ctk.CTkLabel(kac_frame_c, text="Crosswind:", text_color=COLOR_TEXT_MUTED).grid(row=3, column=0, sticky="w",
                                                                                       padx=5, pady=(2, 2))
        ctk.CTkEntry(kac_frame_c, textvariable=self.var_kac_cross, width=40, height=26, fg_color=COLOR_CARD).grid(row=3,
                                                                                                                  column=1,
                                                                                                                  sticky="w",
                                                                                                                  padx=5)
        ctk.CTkOptionMenu(kac_frame_c, variable=self.var_kac_cross_dir, values=["<< Сносит ВЛЕВО", "Сносит ВПРАВО >>"],
                          height=26, fg_color=COLOR_BORDER, button_color=COLOR_CARD, text_color=COLOR_TEXT).grid(row=3,
                                                                                                                 column=2,
                                                                                                                 sticky="ew",
                                                                                                                 padx=5)
        ctk.CTkLabel(kac_frame_c, text="Headwind:", text_color=COLOR_TEXT_MUTED).grid(row=4, column=0, sticky="w",
                                                                                      padx=5, pady=(2, 2))
        ctk.CTkEntry(kac_frame_c, textvariable=self.var_kac_head, width=40, height=26, fg_color=COLOR_CARD).grid(row=4,
                                                                                                                 column=1,
                                                                                                                 sticky="w",
                                                                                                                 padx=5)
        ctk.CTkOptionMenu(kac_frame_c, variable=self.var_kac_head_dir,
                          values=["↑ Встречный (В лицо)", "↓ Попутный (В спину)"], height=26, fg_color=COLOR_BORDER,
                          button_color=COLOR_CARD, text_color=COLOR_TEXT).grid(row=4, column=2, sticky="ew", padx=5)

        wv_frame_c = self.cal_wind_tabs.tab("Вектор ветра")
        wv_frame_c.grid_columnconfigure(0, weight=1);
        wv_frame_c.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(wv_frame_c, text="Азимут (°):", text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w",
                                                                                       padx=5)
        ctk.CTkEntry(wv_frame_c, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_CARD).grid(row=1, column=0,
                                                                                                       sticky="ew",
                                                                                                       padx=5)
        ctk.CTkLabel(wv_frame_c, text="Скор. (м/с):", text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w",
                                                                                        padx=5)
        ctk.CTkEntry(wv_frame_c, textvariable=self.var_wind_speed, height=26, fg_color=COLOR_CARD).grid(row=3, column=0,
                                                                                                        sticky="ew",
                                                                                                        padx=5)
        ctk.CTkLabel(wv_frame_c, text="Откуда (°):", text_color=COLOR_TEXT_MUTED).grid(row=0, column=1, sticky="w",
                                                                                       padx=5)
        ctk.CTkEntry(wv_frame_c, textvariable=self.var_wind_dir, height=26, fg_color=COLOR_CARD).grid(row=1, column=1,
                                                                                                      sticky="ew",
                                                                                                      padx=5)

        bw_frame_c = self.cal_wind_tabs.tab("Боковой")
        bw_frame_c.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bw_frame_c, text="Азимут (°):", text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w",
                                                                                       padx=10)
        ctk.CTkEntry(bw_frame_c, textvariable=self.var_shoot_dir, height=26, fg_color=COLOR_CARD).grid(row=1, column=0,
                                                                                                       sticky="ew",
                                                                                                       padx=10,
                                                                                                       pady=(0, 5))
        ctk.CTkLabel(bw_frame_c, text="Снос (м/с):", text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w",
                                                                                       padx=10)
        ctk.CTkEntry(bw_frame_c, textvariable=self.var_crosswind, height=26, fg_color=COLOR_CARD).grid(row=3, column=0,
                                                                                                       sticky="ew",
                                                                                                       padx=10,
                                                                                                       pady=(0, 5))
        rb_frame_c = ctk.CTkFrame(bw_frame_c, fg_color="transparent")
        rb_frame_c.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkRadioButton(rb_frame_c, text="СЛЕВА →", variable=self.var_cross_dir, value="СЛЕВА →",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)
        ctk.CTkRadioButton(rb_frame_c, text="← СПРАВА", variable=self.var_cross_dir, value="← СПРАВА",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)

        ctk.CTkFrame(box, height=2, fg_color=COLOR_BORDER).pack(fill="x", padx=15, pady=5)

        hit_frame = ctk.CTkFrame(box, fg_color="transparent")
        hit_frame.pack(fill="x", padx=10, pady=5)
        hit_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hit_frame, text="ПУЛЮ СДУЛО (Горизонталь)", font=ctk.CTkFont(weight="bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, pady=5)

        h_frame = ctk.CTkFrame(hit_frame, fg_color=COLOR_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        h_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        h_frame.grid_columnconfigure(1, weight=1)
        self.cal_drift_dir_var = ctk.StringVar(value="ВПРАВО →")
        rb_h_frame = ctk.CTkFrame(h_frame, fg_color="transparent")
        rb_h_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=15)
        ctk.CTkRadioButton(rb_h_frame, text="← ВЛЕВО", variable=self.cal_drift_dir_var, value="← ВЛЕВО",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)
        ctk.CTkRadioButton(rb_h_frame, text="ВПРАВО →", variable=self.cal_drift_dir_var, value="ВПРАВО →",
                           fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_TEXT).pack(side="left",
                                                                                                        expand=True)

        ctk.CTkLabel(h_frame, text="Значение (MIL):", text_color=COLOR_TEXT_MUTED).grid(row=1, column=0, sticky="w",
                                                                                        padx=10, pady=(0, 10))
        self.cal_actual_drift = ctk.StringVar(value="2.4")
        ctk.CTkEntry(h_frame, textvariable=self.cal_actual_drift, width=80).grid(row=1, column=1, sticky="e", padx=10,
                                                                                 pady=(0, 10))

        btn_frame = ctk.CTkFrame(box, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Вычислить и Сохранить множитель ветра", height=45, fg_color=COLOR_ACCENT,
                      hover_color=COLOR_BORDER, text_color=COLOR_BG, font=ctk.CTkFont(weight="bold"),
                      command=self.run_auto_calibration).pack(fill="x")
        self.calib_status_label = ctk.CTkLabel(box, text="", text_color=COLOR_TEXT_MUTED, font=self.font_label)
        self.calib_status_label.pack(pady=(0, 10))

    def run_auto_calibration(self):
        try:
            profile_name = self.var_weapon.get()
            if profile_name not in self.profiles: return
            p = self.profiles[profile_name]

            dist = float(self.var_dist.get().replace(',', '.'))
            zero = float(self.var_zero.get().replace(',', '.'))

            if dist <= 0 or zero <= 0:
                self.calib_status_label.configure(text="Ошибка: Неверная дистанция!", text_color=COLOR_BORDER)
                return

            active_wind = self.cal_wind_tabs.get()
            headwind = 0.0

            if active_wind == "Вектор ветра":
                s_dir = float(self.var_shoot_dir.get().replace(',', '.'))
                w_spd = float(self.var_wind_speed.get().replace(',', '.'))
                w_dir = float(self.var_wind_dir.get().replace(',', '.'))
                rel_angle = (w_dir - s_dir) % 360
                crosswind = w_spd * math.sin(math.radians(rel_angle))
                headwind = w_spd * math.cos(math.radians(rel_angle))
            elif active_wind == "Боковой":
                cw_spd = float(self.var_crosswind.get().replace(',', '.'))
                crosswind = cw_spd if self.var_cross_dir.get() == "← СПРАВА" else -cw_spd
            else:
                cw_str = self.var_kac_cross.get().replace(',', '.')
                hw_str = self.var_kac_head.get().replace(',', '.')
                cw_speed = abs(float(cw_str)) if cw_str else 0.0
                hw_speed = abs(float(hw_str)) if hw_str else 0.0
                crosswind = cw_speed if "<< Сносит ВЛЕВО" in self.var_kac_cross_dir.get() else -cw_speed
                headwind = hw_speed if "Встречный" in self.var_kac_head_dir.get() else -hw_speed

            abs_actual_drift = abs(float(self.cal_actual_drift.get().replace(',', '.')))

            v0 = p.get("v0", 850.0)
            k_drag = p.get("k_drag", 0.2)

            k_aero = k_drag / 1000.0
            if k_aero < 0.000001: k_aero = 0.000001

            v0_eff = v0 - headwind
            if v0_eff < 100: v0_eff = 100

            time_of_flight = (math.exp(k_aero * dist) - 1) / (k_aero * v0_eff)

            new_wind_factor = p.get("wind_factor", 1.0)
            if abs_actual_drift > 0:
                base_drift_meters = crosswind * (time_of_flight - (dist / v0))
                base_drift_mil = (base_drift_meters * 1000) / dist
                if abs(base_drift_mil) > 0.001:
                    new_wind_factor = abs_actual_drift / abs(base_drift_mil)

            p["wind_factor"] = round(new_wind_factor, 3)
            self.save_profiles()

            if self.edit_weapon_var.get() == profile_name:
                self.load_profile_into_editor(profile_name)

            success_msg = f"Сохранено для '{profile_name}': Новый Ветер = {p['wind_factor']}"
            self.calib_status_label.configure(text=success_msg, text_color="#2ECC71")

        except ValueError:
            self.calib_status_label.configure(text="Ошибка: В полях должны быть только цифры!",
                                              text_color=COLOR_BORDER)

    # ВКЛАДКА 3: РЕДАКТОР ПРОФИЛЕЙ
    def build_editor_tab(self):
        center_frame = ctk.CTkFrame(self.tab_edit, fg_color="transparent")
        center_frame.pack(expand=True, fill="y", pady=20)

        ed_box = ctk.CTkFrame(center_frame, corner_radius=15, border_width=2, border_color=COLOR_BORDER,
                              fg_color=COLOR_CARD, width=650)
        ed_box.pack(pady=10, padx=20, fill="both", expand=True)

        top_bar = ctk.CTkFrame(ed_box, fg_color="transparent")
        top_bar.pack(fill="x", padx=30, pady=20)

        ctk.CTkLabel(top_bar, text="Выберите профиль:", text_color=COLOR_TEXT_MUTED, font=self.font_label).pack(
            side="left", padx=(0, 10))

        initial_weapon = list(self.profiles.keys())[0] if self.profiles else ""
        self.edit_weapon_var = ctk.StringVar(value=initial_weapon)
        editor_list = list(self.profiles.keys()) + [CREATE_NEW_STR]

        self.edit_dropdown_weapon = ctk.CTkOptionMenu(top_bar, values=editor_list, variable=self.edit_weapon_var,
                                                      height=35, command=self.load_profile_into_editor,
                                                      fg_color=COLOR_BORDER, button_color=COLOR_BG,
                                                      button_hover_color=COLOR_CARD, text_color=COLOR_TEXT,
                                                      dropdown_fg_color=COLOR_CARD, dropdown_text_color=COLOR_TEXT)
        self.edit_dropdown_weapon.pack(side="left", fill="x", expand=True)

        ctk.CTkFrame(ed_box, height=2, fg_color=COLOR_BORDER).pack(fill="x", padx=20, pady=5)

        grid_frame = ctk.CTkFrame(ed_box, fg_color="transparent")
        grid_frame.pack(fill="x", padx=30, pady=10)
        grid_frame.grid_columnconfigure(1, weight=1)

        self.var_name = ctk.StringVar()
        self.var_v0 = ctk.StringVar()
        self.var_drag = ctk.StringVar()
        self.var_wind = ctk.StringVar()

        tt_name = "Название профиля, которое будет отображаться\nв выпадающем списке калькулятора."
        tt_v0 = "Скорость, с которой пуля вылетает из ствола.\nОна влияет на общее время полета для ветра."
        tt_drag = "Сопротивление воздуха. Чем меньше число, тем прямее пуля."
        tt_wind = "Множитель восприимчивости пули к боковому ветру."

        self.add_edit_row(grid_frame, 0, "Название оружия:", self.var_name, tt_name)
        self.add_edit_row(grid_frame, 1, "v0 (Скорость пули, м/с):", self.var_v0, tt_v0)
        self.add_edit_row(grid_frame, 2, "k_drag (Сопротивление воздуха):", self.var_drag, tt_drag)
        self.add_edit_row(grid_frame, 3, "wind_factor (Влияние ветра):", self.var_wind, tt_wind)

        ctk.CTkFrame(ed_box, height=2, fg_color=COLOR_BORDER).pack(fill="x", padx=20, pady=5)

        btn_frame = ctk.CTkFrame(ed_box, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=20)

        self.editor_action_var = ctk.StringVar(value="Сохранить профиль")
        self.action_menu = ctk.CTkOptionMenu(btn_frame, variable=self.editor_action_var,
                                             values=["Сохранить профиль", "Удалить профиль"], height=40,
                                             fg_color=COLOR_BORDER, button_color=COLOR_CARD, text_color=COLOR_TEXT)
        self.action_menu.pack(side="left", expand=True, padx=5, fill="x")

        ctk.CTkButton(btn_frame, text="Выполнить", fg_color=COLOR_ACCENT, hover_color=COLOR_BORDER, text_color=COLOR_BG,
                      height=40, font=ctk.CTkFont(weight="bold"), command=self.execute_editor_action).pack(side="left",
                                                                                                           expand=True,
                                                                                                           padx=5,
                                                                                                           fill="x")

        self.edit_status_label = ctk.CTkLabel(ed_box, text="Вертикальное падение жестко зашито в таблицу LUT.",
                                              text_color=COLOR_TEXT_MUTED, font=self.font_label)
        self.edit_status_label.pack(pady=(0, 15))

        if initial_weapon:
            self.load_profile_into_editor(initial_weapon)

    def add_edit_row(self, parent, row, label_text, string_var, tooltip_text):
        ctk.CTkLabel(parent, text=label_text, text_color=COLOR_TEXT, font=self.font_label).grid(row=row, column=0,
                                                                                                sticky="w", pady=12,
                                                                                                padx=(10, 5))
        ctk.CTkEntry(parent, textvariable=string_var, width=160, height=35, fg_color=COLOR_BG,
                     border_color=COLOR_BORDER, text_color=COLOR_TEXT).grid(row=row, column=1, sticky="e", pady=12,
                                                                            padx=(5, 10))
        help_btn = ctk.CTkButton(parent, text="?", width=28, height=28, corner_radius=14, fg_color="transparent",
                                 border_width=2, border_color=COLOR_BORDER, text_color=COLOR_BORDER,
                                 hover_color=COLOR_BG, font=ctk.CTkFont(weight="bold"))
        help_btn.grid(row=row, column=2, sticky="e", padx=(0, 10))
        ToolTip(help_btn, tooltip_text)

    def load_profile_into_editor(self, profile_name):
        if profile_name == CREATE_NEW_STR:
            self.var_name.set("Новая Винтовка")
            self.var_v0.set("850.0")
            self.var_drag.set("0.20")
            self.var_wind.set("1.0")
            self.edit_status_label.configure(text="Выберите действие и нажмите 'Выполнить'.",
                                             text_color=COLOR_TEXT_MUTED)
            return

        if profile_name not in self.profiles: return
        data = self.profiles[profile_name]
        self.var_name.set(profile_name)
        self.var_v0.set(str(data.get("v0", "")))
        self.var_drag.set(str(data.get("k_drag", "")))
        self.var_wind.set(str(data.get("wind_factor", "")))
        self.edit_status_label.configure(text=f"Профиль '{profile_name}' загружен.", text_color=COLOR_TEXT)

    def execute_editor_action(self):
        action = self.editor_action_var.get()
        if "Сохранить" in action:
            self.save_current_profile()
        elif "Удалить" in action:
            self.delete_profile()

    def save_current_profile(self):
        old_name = self.edit_weapon_var.get()
        new_name = self.var_name.get().strip()

        if not new_name or new_name == CREATE_NEW_STR:
            self.edit_status_label.configure(text="Введите корректное имя профиля!", text_color=COLOR_TEXT)
            return

        try:
            profile_data = {
                "v0": float(self.var_v0.get().replace(',', '.')),
                "k_drag": float(self.var_drag.get().replace(',', '.')),
                "wind_factor": float(self.var_wind.get().replace(',', '.'))
            }
            profile_data["scope_table"] = self.profiles.get(old_name, {}).get("scope_table", DEFAULT_PROFILES[
                "M40A5 (.308 Win / M61)"]["scope_table"])

        except ValueError:
            self.edit_status_label.configure(text="Ошибка: В полях должны быть только цифры!", text_color=COLOR_TEXT)
            return

        if old_name != new_name and old_name in self.profiles and old_name != CREATE_NEW_STR:
            del self.profiles[old_name]

        self.profiles[new_name] = profile_data
        self.save_profiles()
        self.refresh_dropdowns()
        self.edit_weapon_var.set(new_name)
        self.edit_status_label.configure(text="Профиль успешно сохранен!", text_color=COLOR_TEXT)

    def delete_profile(self):
        name = self.edit_weapon_var.get()
        if name == CREATE_NEW_STR: return
        if name in self.profiles:
            if len(self.profiles) <= 1:
                self.edit_status_label.configure(text="Нельзя удалить последний профиль!", text_color=COLOR_TEXT)
                return
            del self.profiles[name]
            self.save_profiles()
            self.refresh_dropdowns()
            self.edit_status_label.configure(text=f"Профиль '{name}' удален.", text_color=COLOR_TEXT)

    # Логика расчета
    def compute_ballistics(self, target, wind_params, current_time, target_num):
        distance = target["distance"]
        zero_dist = target["zero_dist"]
        delta_h = target["delta_h"]
        selected_weapon = target["weapon"]
        profile = self.profiles.get(selected_weapon, DEFAULT_PROFILES["M40A5 (.308 Win / M61)"])

        v0 = profile.get("v0", 850.0)
        k_drag = profile.get("k_drag", 0.2)
        wind_factor = profile.get("wind_factor", 1.0)

        scope_table = profile.get("scope_table", DEFAULT_PROFILES["M40A5 (.308 Win / M61)"]["scope_table"])
        base_target_mil = self.get_mil_from_table(distance, scope_table)
        base_zero_mil = self.get_mil_from_table(zero_dist, scope_table)

        horiz_distance = math.sqrt(max(0, distance ** 2 - delta_h ** 2))
        cos_angle = horiz_distance / distance if distance > 0 else 1.0
        angle_deg = math.degrees(math.acos(cos_angle))

        headwind = 0.0
        crosswind = 0.0

        if wind_params["tab"] == "Вектор ветра":
            rel_angle = (wind_params["wind_dir"] - wind_params["shoot_dir"]) % 360
            crosswind = wind_params["wind_speed"] * math.sin(math.radians(rel_angle))
            headwind = wind_params["wind_speed"] * math.cos(math.radians(rel_angle))
        elif wind_params["tab"] == "Боковой":
            crosswind = wind_params["cw_speed"] if wind_params["cw_dir"] == "← СПРАВА" else -wind_params["cw_speed"]
        else:
            crosswind = wind_params["kac_cross"] if "<< Сносит ВЛЕВО" in wind_params["kac_cross_dir"] else -wind_params[
                "kac_cross"]
            headwind = wind_params["kac_head"] if "Встречный" in wind_params["kac_head_dir"] else -wind_params[
                "kac_head"]

        v0_eff = v0 - headwind
        if v0_eff < 100: v0_eff = 100
        headwind_drop_modifier = (v0 / v0_eff) ** 2

        drop_mil = (base_target_mil - base_zero_mil) * cos_angle * headwind_drop_modifier

        k_aero = k_drag / 1000.0
        if k_aero < 0.000001: k_aero = 0.000001
        time_of_flight = (math.exp(k_aero * distance) - 1) / (k_aero * v0_eff)

        drift_meters = crosswind * (time_of_flight - (distance / v0)) * wind_factor
        drift_mil = (drift_meters * 1000) / distance if distance > 0 else 0.0

        # Формирование данных для интерфейса станции (подробно) и HUD (компактно)
        if drop_mil > 0.05:
            target_pos_y = f"↓ Цель ВНИЗ на {drop_mil:.1f} MIL"
            y_aim = f"спустись по сетке на {drop_mil:.1f} MIL вниз"
            hud_y = f"↓ {drop_mil:.1f} MIL"
        elif drop_mil < -0.05:
            target_pos_y = f"↑ Цель ВВЕРХ на {abs(drop_mil):.1f} MIL"
            y_aim = f"поднимись по сетке на {abs(drop_mil):.1f} MIL вверх"
            hud_y = f"↑ {abs(drop_mil):.1f} MIL"
        else:
            target_pos_y = "БЕЗ ПАДЕНИЯ (Ноль)"
            y_aim = "оставайся на горизонтальной оси"
            hud_y = "↕  0.0 MIL"

        if crosswind > 0.05:
            wind_info = "Справа налево ←"
            target_pos_x = f"← Цель ВЛЕВО на {abs(drift_mil):.1f} MIL"
            aim_text = f"отведи мишень на {abs(drift_mil):.1f} MIL влево"
            hud_x = f"← {abs(drift_mil):.1f} MIL"
        elif crosswind < -0.05:
            wind_info = "Слева направо →"
            target_pos_x = f"→ Цель ВПРАВО на {abs(drift_mil):.1f} MIL"
            aim_text = f"отведи мишень на {abs(drift_mil):.1f} MIL вправо"
            hud_x = f"→ {abs(drift_mil):.1f} MIL"
        else:
            wind_info = "По ветру / Против / Штиль"
            target_pos_x = "БЕЗ БОКОВОГО СМЕЩЕНИЯ"
            aim_text = "строго по вертикальной линии"
            hud_x = "↔  0.0 MIL"

        if headwind > 0.5:
            hw_info = f"Встречный {abs(headwind):.1f} м/с"
        elif headwind < -0.5:
            hw_info = f"Попутный {abs(headwind):.1f} м/с"
        else:
            hw_info = "Прямого ветра нет"

        angle_info = f"Уклон {angle_deg:.1f}°" if angle_deg > 0.5 else "Равнина"

        target_name = f"ЦЕЛЬ {target_num}"
        pad = (40 - len(target_name) - 4) // 2
        block_str = "█" * pad
        target_header = f"{block_str} [ {target_name} ] {block_str}"

        instruction_text = (f"Где должна быть мишень на стекле:\nОт центрального креста {y_aim},\nзатем {aim_text}.\n")

        desc_text = ""
        desc = target.get("description", "")
        if desc: desc_text = f"Пометка: {desc}\n"

        res = (
            f"{target_header}\n"
            f"{desc_text}"
            f"Пересчет: {current_time} (Дистанция: {distance:.0f}м)\n"
            f"─────────────────────────────\n"
            f"{selected_weapon.split(' ')[0]}\n"
            f"Пристрелка: {zero_dist:.0f}м | {angle_info}\n"
            f"Время полета: {time_of_flight:.2f} сек\n"
            f"Ветер: {wind_info} | {hw_info}\n"
            f"─────────────────────────────\n"
            f"ПОЛОЖЕНИЕ ЦЕЛИ НА СЕТКЕ:\n"
            f"   {target_pos_y}\n"
        )
        if target_pos_x != "БЕЗ БОКОВОГО СМЕЩЕНИЯ": res += f"   {target_pos_x}\n"
        res += f"─────────────────────────────\n{instruction_text}"

        # Формирование супер-компактного пакета для пересылки
        desc_str = f" | {desc}" if desc else f" | {distance:.0f}м"
        compact_payload = f"[{target_name}{desc_str}] ⏱ {time_of_flight:.2f}с\n    {hud_y}   |   {hud_x}"

        return res, compact_payload

    def calculate(self):
        try:
            current_time = datetime.now().strftime("%H:%M:%S")

            z_str = self.var_zero.get()
            d_str = self.var_dist.get().replace(',', '.')
            zero_dist = float(z_str)
            distance = float(d_str) if d_str else 0.0

            active_topo_tab = self.topo_tabs.get()
            if active_topo_tab == "Дальномер":
                dh_str = self.var_delta_h.get().replace(',', '.')
                delta_h = float(dh_str) if dh_str else 0.0
            else:
                sh_str = self.var_shooter_h.get().replace(',', '.')
                th_str = self.var_target_h.get().replace(',', '.')
                shooter_h = float(sh_str) if sh_str else 0.0
                target_h = float(th_str) if th_str else 0.0
                delta_h = target_h - shooter_h

            if distance <= 0 or zero_dist <= 0:
                self.set_result_text("Ошибка:\nДистанции должны быть больше нуля.")
                return

            if abs(delta_h) >= distance:
                self.set_result_text("Ошибка геометрии:\nПерепад высот не может быть\nбольше самой дистанции.")
                return

            selected_weapon = self.var_weapon.get()
            if selected_weapon not in self.profiles:
                return

            shoot_dir_str = self.var_shoot_dir.get().replace(',', '.')
            current_azimuth = float(shoot_dir_str) if shoot_dir_str else 0.0

            target_desc = self.var_target_desc.get().strip()

            current_target = {
                "distance": distance,
                "zero_dist": zero_dist,
                "delta_h": delta_h,
                "weapon": selected_weapon,
                "description": target_desc
            }

            try:
                wind_params = self.get_wind_params()
            except ValueError:
                self.set_result_text("Ошибка ввода ветра!\nПроверьте, что в полях только цифры.")
                return

            logs = self.load_logs()

            if logs:
                base_azimuth = logs[0].get("base_azimuth", current_azimuth)
                if self.angle_diff(current_azimuth, base_azimuth) > 10:
                    logs = []

            # ЛОГИКА УНИКАЛЬНОСТИ ЦЕЛИ
            found = False
            for tgt in logs:
                # Если введена пометка и она совпадает -> обновляем эту цель
                if target_desc and tgt.get("description") == target_desc:
                    tgt["distance"] = distance
                    tgt["zero_dist"] = zero_dist
                    tgt["delta_h"] = delta_h
                    tgt["weapon"] = selected_weapon
                    found = True
                    break
                # Если пометка пустая, ищем точное совпадение по параметрам
                elif not target_desc and not tgt.get("description") and tgt["distance"] == distance and tgt[
                    "delta_h"] == delta_h and tgt["weapon"] == selected_weapon:
                    found = True
                    break

            if not found:
                current_target["base_azimuth"] = current_azimuth
                logs.append(current_target)

            for tgt in logs:
                if "base_azimuth" not in tgt:
                    tgt["base_azimuth"] = current_azimuth

            self.save_logs(logs)
            self.update_display(logs, wind_params, current_time)

        except ValueError:
            self.set_result_text("Ошибка ввода!\nПроверьте, что в полях только цифры.")


if __name__ == "__main__":
    root = ctk.CTk()
    app = UniversalBallisticStation(root)
    root.mainloop()
