import customtkinter as ctk
import tkinter as tk
from tkinter import Canvas
import math
from datetime import datetime
import queue
import requests
import threading
import psutil
import json
import os
import time

# Configuration du thème
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Couleurs JARVIS
JARVIS_BG = "#0a1628"
JARVIS_PANEL_BG = "#0d1f35"
JARVIS_CYAN = "#00d4ff"
JARVIS_CYAN_DIM = "#0a3d4d"
JARVIS_TEXT = "#ffffff"
JARVIS_TEXT_DIM = "#6b8fa3"
JARVIS_BORDER = "#1a4a5c"
JARVIS_GREEN = "#00ff88"

class CypherGUI(ctk.CTk):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.title("C.Y.P.H.E.R - AI Assistant")
        self.geometry("1600x900")
        self.configure(fg_color=JARVIS_BG)
        
        self.is_listening = False
        self.is_interrupted = False
        self.is_speaking = False
        self.animation_angle = 0
        self.wave_offset = 0
        self.current_radius = 150
        self.target_radius = 150
        
        self.message_widgets = []
        self.commands_count = 0
        self.session_start = datetime.now()
        # cache for loaded weather images to avoid GC
        self._weather_images = {}
        
        # Mapping météo
        self.weather_map = {
            0: "sun", 1: "sun",
            2: "partly", 3: "partly",
            45: "cloud", 48: "cloud",
            51: "rain", 53: "rain", 55: "rain",
            61: "rain", 63: "rain", 65: "rain",
            71: "snow", 73: "snow", 75: "snow",
            80: "rain", 81: "rain", 82: "rain",
            95: "rain", 96: "rain", 99: "rain"
        }
        
        self._build_ui()
        self._animate_orb()
        self._update_time_loop()
        self._update_stats_loop()
        self.check_queue()
        
    def check_queue(self):
        try:
            while True:
                msg_type, content = self.data_queue.get_nowait()
                if msg_type == "STATUS":
                    if content == "listening":
                        self.set_listening(True)
                        self.set_speaking(False)
                    elif content == "speaking":
                        self.set_listening(False)
                        self.set_speaking(True)
                    elif content == "idle":
                        self.set_listening(False)
                        self.set_speaking(False)
                    elif content == "interrupted":
                        self.set_interrupted()
                elif msg_type == "ASSISTANT_TEXT":
                    self.add_assistant_message(content)
                elif msg_type == "USER_TEXT":
                    self.add_user_message(content)
                    self.commands_count += 1
        except queue.Empty:
            pass
        self.after(50, self.check_queue)

    def _build_ui(self):
        # Configuration grille principale
        self.grid_columnconfigure(0, weight=1, minsize=360)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1, minsize=380)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        
        self._build_header()
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(15, 5))
        header.grid_columnconfigure(1, weight=1)
        
        # Logo JARVIS + Status
        left_frame = ctk.CTkFrame(header, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w")
        
        title_label = ctk.CTkLabel(left_frame, text="C.Y.P.H.E.R", 
                                   font=("Consolas", 28, "bold"), text_color=JARVIS_TEXT)
        title_label.pack(side="left", padx=(0, 15))
        
        status_frame = ctk.CTkFrame(left_frame, fg_color=JARVIS_CYAN_DIM, corner_radius=12)
        status_frame.pack(side="left")
        
        self.status_dot = ctk.CTkLabel(status_frame, text="●", font=("Arial", 10), text_color=JARVIS_GREEN)
        self.status_dot.pack(side="left", padx=(10, 5), pady=5)
        
        ctk.CTkLabel(status_frame, text="Online", font=("Arial", 12), 
                    text_color=JARVIS_GREEN).pack(side="left", padx=(0, 10), pady=5)
        
        # Centre - Horloge + Date
        center_frame = ctk.CTkFrame(header, fg_color=JARVIS_PANEL_BG, corner_radius=20)
        center_frame.grid(row=0, column=1)
        
        clock_inner = ctk.CTkFrame(center_frame, fg_color="transparent")
        clock_inner.pack(padx=20, pady=8)
        
        ctk.CTkLabel(clock_inner, text="◷", font=("Arial", 16), text_color=JARVIS_TEXT_DIM).pack(side="left", padx=(0, 8))
        self.time_label = ctk.CTkLabel(clock_inner, text="00:00:00", 
                                        font=("Consolas", 16), text_color=JARVIS_TEXT)
        self.time_label.pack(side="left")
        
        ctk.CTkLabel(clock_inner, text="  |  ", font=("Arial", 14), text_color=JARVIS_TEXT_DIM).pack(side="left")
        
        self.date_label = ctk.CTkLabel(clock_inner, text="January 1, 2025", 
                                        font=("Arial", 14), text_color=JARVIS_TEXT)
        self.date_label.pack(side="left")
        
        # Droite - Météo
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e")
        
        self.header_temp = ctk.CTkLabel(right_frame, text="--°C", 
                                         font=("Arial", 14), text_color=JARVIS_TEXT)
        self.header_temp.pack(side="left", padx=(0, 5))
        
        self.header_location = ctk.CTkLabel(right_frame, text="Loading...", 
                                             font=("Arial", 12), text_color=JARVIS_CYAN)
        self.header_location.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(right_frame, text="⚙", font=("Arial", 18), text_color=JARVIS_TEXT_DIM).pack(side="left")

    def _build_left_panel(self):
        left_container = ctk.CTkFrame(self, fg_color="transparent")
        left_container.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=10)
        left_container.grid_rowconfigure(3, weight=1)
        
        # System Stats
        self._build_system_stats(left_container)
        
        # Weather Widget
        self._build_weather_widget(left_container)
        
        # Camera Widget
        self._build_camera_widget(left_container)
        

    def _build_system_stats(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=15, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="x", pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 8))
        
        ctk.CTkLabel(header, text="⚙", font=("Arial", 25), text_color=JARVIS_CYAN).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text="System Stats", font=("Arial", 20, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        ctk.CTkLabel(header, text="↻", font=("Arial", 14), text_color=JARVIS_TEXT_DIM).pack(side="right")
        
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=15, pady=(0, 12))
        
        # CPU Usage
        cpu_frame = ctk.CTkFrame(content, fg_color="transparent")
        cpu_frame.pack(fill="x", pady=3)
        ctk.CTkLabel(cpu_frame, text="CPU Usage", font=("Arial", 15), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        self.cpu_pct_label = ctk.CTkLabel(cpu_frame, text="0%", font=("Arial", 13), 
                                           text_color=JARVIS_TEXT)
        self.cpu_pct_label.pack(side="right")
        
        self.cpu_bar = ctk.CTkProgressBar(content, height=4, progress_color=JARVIS_CYAN, 
                                           fg_color=JARVIS_CYAN_DIM)
        self.cpu_bar.pack(fill="x", pady=(2, 8))
        self.cpu_bar.set(0)
        
        # RAM Usage
        ram_frame = ctk.CTkFrame(content, fg_color="transparent")
        ram_frame.pack(fill="x", pady=3)
        ctk.CTkLabel(ram_frame, text="RAM Usage", font=("Arial", 15), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        self.ram_label = ctk.CTkLabel(ram_frame, text="0 GB", font=("Arial", 13), 
                                       text_color=JARVIS_TEXT)
        self.ram_label.pack(side="right")
        
        self.ram_bar = ctk.CTkProgressBar(content, height=4, progress_color=JARVIS_GREEN, 
                                           fg_color=JARVIS_CYAN_DIM)
        self.ram_bar.pack(fill="x", pady=(2, 12))
        self.ram_bar.set(0)
        
        # Stats grid
        stats_grid = ctk.CTkFrame(content, fg_color="transparent")
        stats_grid.pack(fill="x")
        stats_grid.grid_columnconfigure((0, 1, 2), weight=1)
        
        for i, (label, key) in enumerate([("CPU", "cpu_stat"), ("Memory", "mem_stat"), ("Disk", "disk_stat")]):
            stat_frame = ctk.CTkFrame(stats_grid, fg_color="transparent")
            stat_frame.grid(row=0, column=i, sticky="nsew")
            ctk.CTkLabel(stat_frame, text=label, font=("Arial", 15), 
                        text_color=JARVIS_TEXT_DIM).pack()
            lbl = ctk.CTkLabel(stat_frame, text="0%", font=("Arial", 15, "bold"), 
                               text_color=JARVIS_CYAN)
            lbl.pack()
            setattr(self, key, lbl)

    def _build_weather_widget(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=15, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="x", pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 8))
        
        ctk.CTkLabel(header, text="☁", font=("Arial", 25), text_color=JARVIS_CYAN).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text="Météo", font=("Arial", 20, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        ctk.CTkLabel(header, text="↻", font=("Arial", 14), text_color=JARVIS_TEXT_DIM).pack(side="right")
        
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=15, pady=(0, 12))
        
        # Main weather info
        main_row = ctk.CTkFrame(content, fg_color="transparent")
        main_row.pack(fill="x")
        
        left_info = ctk.CTkFrame(main_row, fg_color="transparent")
        left_info.pack(side="left")
        
        self.temp_label = ctk.CTkLabel(left_info, text="--°C", font=("Consolas", 32), 
                                        text_color=JARVIS_TEXT)
        self.temp_label.pack(anchor="w")
        
        self.location_label = ctk.CTkLabel(left_info, text="Loading...", 
                                            font=("Arial", 12), text_color=JARVIS_TEXT_DIM)
        self.location_label.pack(anchor="w")
        
        self.condition_label = ctk.CTkLabel(left_info, text="", font=("Arial", 10), 
                                             text_color=JARVIS_TEXT_DIM)
        self.condition_label.pack(anchor="w")
        
        # Weather icon (larger for clarity)
        self.weather_canvas = Canvas(main_row, width=100, height=100, bg=JARVIS_PANEL_BG, 
                          highlightthickness=0)
        self.weather_canvas.pack(side="right", padx=10)
        self._draw_weather_icon("cloud")
        
        # Details row
        details = ctk.CTkFrame(content, fg_color="transparent")
        details.pack(fill="x", pady=(10, 0))
        details.grid_columnconfigure((0, 1, 2), weight=1)
        
        for i, (label, key) in enumerate([("Humidité", "humidity_label"), 
                                          ("Vent", "wind_label"), 
                                          ("Ressenti", "feels_label")]):
            det_frame = ctk.CTkFrame(details, fg_color="transparent")
            det_frame.grid(row=0, column=i, sticky="nsew")
            ctk.CTkLabel(det_frame, text=label, font=("Arial", 15), 
                        text_color=JARVIS_TEXT_DIM).pack()
            lbl = ctk.CTkLabel(det_frame, text="--", font=("Consolas", 15), 
                               text_color=JARVIS_TEXT)
            lbl.pack()
            setattr(self, key, lbl)

    def _build_camera_widget(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=15, 
                            border_width=1, border_color=JARVIS_BORDER)
        # Allow the camera panel to expand vertically to fill available space
        frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 8))
        
        ctk.CTkLabel(header, text="📷", font=("Arial", 25), text_color=JARVIS_CYAN).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text="Camera", font=("Arial", 20, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        icons_frame = ctk.CTkFrame(header, fg_color="transparent")
        icons_frame.pack(side="right")
        ctk.CTkLabel(icons_frame, text="📷", font=("Arial", 12), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left", padx=3)
        ctk.CTkLabel(icons_frame, text="⏻", font=("Arial", 12), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left", padx=3)
        
        # Camera preview area
        preview = ctk.CTkFrame(frame, fg_color=JARVIS_CYAN_DIM, height=200, corner_radius=10)
        preview.pack(fill="x", padx=15, pady=(0, 8))
        
        ctk.CTkLabel(preview, text="🎥", font=("Arial", 28), text_color=JARVIS_TEXT_DIM).pack(expand=True, pady=20)
        ctk.CTkLabel(preview, text="Camera Off", font=("Arial", 11), 
                    text_color=JARVIS_CYAN).pack(pady=(0, 15))
        
        ctk.CTkLabel(frame, text="Camera is inactive. Click the power button to start.", 
                    font=("Arial", 9), text_color=JARVIS_TEXT_DIM).pack(pady=(0, 12))

    # System Uptime widget removed per request — camera will occupy that space.

    def _build_center_panel(self):
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        center.grid_rowconfigure(0, weight=1)
        center.grid_rowconfigure(1, weight=0)
        center.grid_columnconfigure(0, weight=1)
        
        # Orb container
        orb_frame = ctk.CTkFrame(center, fg_color="transparent")
        orb_frame.grid(row=0, column=0, sticky="nsew")
        
        self.orb_canvas = Canvas(orb_frame, width=450, height=450, bg=JARVIS_BG, highlightthickness=0)
        self.orb_canvas.pack(expand=True)
        
        # Title and status
        title_frame = ctk.CTkFrame(center, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="s", pady=(0, 150))
        
        self.jarvis_title = ctk.CTkLabel(title_frame, text="C.Y.P.H.E.R", 
                                          font=("Consolas", 50, "bold"), text_color=JARVIS_TEXT)
        self.jarvis_title.pack()
        
        status_container = ctk.CTkFrame(title_frame, fg_color=JARVIS_CYAN_DIM, corner_radius=15)
        status_container.pack(pady=(50, 0))
        
        status_inner = ctk.CTkFrame(status_container, fg_color="transparent")
        status_inner.pack(padx=15, pady=8)
        
        self.listening_dot = ctk.CTkLabel(status_inner, text="●", font=("Arial", 10), text_color=JARVIS_GREEN)
        self.listening_dot.pack(side="left", padx=(0, 8))
        
        self.status_text = ctk.CTkLabel(status_inner, text="Listening for wake word...", 
                                         font=("Arial", 20), text_color=JARVIS_CYAN)
        self.status_text.pack(side="left")
        
        # Bottom controls removed — no icons under listening status per user request.

    def _build_right_panel(self):
        right_container = ctk.CTkFrame(self, fg_color="transparent")
        right_container.grid(row=1, column=2, sticky="nsew", padx=(10, 20), pady=10)
        right_container.grid_rowconfigure(0, weight=1)
        right_container.grid_columnconfigure(0, weight=1)
        
        # Conversation panel
        conv_frame = ctk.CTkFrame(right_container, fg_color=JARVIS_PANEL_BG, corner_radius=15,
                                  border_width=1, border_color=JARVIS_BORDER)
        conv_frame.pack(fill="both", expand=True)
        
        # Header
        header = ctk.CTkFrame(conv_frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 8))
        
        ctk.CTkLabel(header, text="Conversation", font=("Arial", 20, "bold"), 
                    text_color=JARVIS_TEXT).pack(side="left")
        
        btns_frame = ctk.CTkFrame(header, fg_color="transparent")
        btns_frame.pack(side="right")
        
        clear_btn = ctk.CTkButton(btns_frame, text="🗑 Clear", width=70, height=28,
                                   fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                   text_color=JARVIS_CYAN, font=("Arial", 10),
                                   corner_radius=5, command=self._clear_chat)
        clear_btn.pack(side="left", padx=(0, 8))
        
        extract_btn = ctk.CTkButton(btns_frame, text="📥 Extract Conversation", width=130, height=28,
                                     fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                     text_color=JARVIS_CYAN, font=("Arial", 10),
                                     corner_radius=5)
        extract_btn.pack(side="left")
        
        # Chat area
        self.chat_scroll = ctk.CTkScrollableFrame(conv_frame, fg_color="transparent")
        self.chat_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Input area
        input_frame = ctk.CTkFrame(conv_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=15, pady=(5, 15))
        
        self.message_entry = ctk.CTkEntry(input_frame, placeholder_text="Type a message...",
                                           fg_color=JARVIS_CYAN_DIM, border_width=0,
                                           text_color=JARVIS_TEXT, height=40, corner_radius=20)
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        send_btn = ctk.CTkButton(input_frame, text="➤", width=40, height=40,
                                  fg_color=JARVIS_CYAN, hover_color=JARVIS_GREEN,
                                  text_color=JARVIS_BG, font=("Arial", 16),
                                  corner_radius=20)
        send_btn.pack(side="right")

    def _clear_chat(self):
        for widget in self.message_widgets:
            widget.destroy()
        self.message_widgets.clear()

    def _animate_orb(self):
        self.orb_canvas.delete("all")
        cx, cy = 225, 200
        
        if self.is_interrupted:
            ring_color = "#ff3333"  # ROUGE
            inner_color = "#ff6666"
            pulse = math.sin(self.animation_angle * 2) * 5 # Battement rapide
            self.animation_angle += 0.2
            
        elif self.is_speaking:
            ring_color = "#ff6b35"  # ORANGE
            inner_color = "#ff8c5a"
            pulse = math.sin(self.animation_angle) * 15
            self.animation_angle += 0.15
            
        elif self.is_listening:
            ring_color = JARVIS_CYAN # CYAN
            inner_color = "#4dd9ff"
            pulse = math.sin(self.animation_angle * 0.5) * 8
            self.animation_angle += 0.1
            
        else: # IDLE
            ring_color = JARVIS_CYAN_DIM
            inner_color = JARVIS_CYAN
            pulse = 0
            self.animation_angle = 0
        
        base_radius = 150 + pulse
        
        # Outer rings (decorative circles)
        for i in range(3):
            r = base_radius + 20 + i * 15
            alpha = 0.3 - i * 0.1
            self.orb_canvas.create_oval(cx - r, cy - r, cx + r, cy + r, 
                                        outline=ring_color, width=1)
        
        # Main orb ring
        self.orb_canvas.create_oval(cx - base_radius, cy - base_radius, 
                                    cx + base_radius, cy + base_radius,
                                    outline=ring_color, width=3)
        
        # Inner circle
        inner_r = base_radius - 30
        self.orb_canvas.create_oval(cx - inner_r, cy - inner_r, 
                                    cx + inner_r, cy + inner_r,
                                    outline=ring_color, width=1)
        
        # Center wave visualization (5 bars)
        wave_width = 8
        wave_gap = 12
        start_x = cx - (wave_width * 5 + wave_gap * 4) // 2
        
        for i in range(5):
            if self.is_listening or self.is_speaking:
                height = 15 + math.sin(self.wave_offset + i * 0.5) * 10
                self.wave_offset += 0.02
            else:
                height = 8
            
            x = start_x + i * (wave_width + wave_gap)
            self.orb_canvas.create_rectangle(x, cy - height, x + wave_width, cy + height,
                                             fill=inner_color, outline="")
        
        # Tick marks around the circle
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            x1 = cx + (base_radius + 5) * math.cos(rad)
            y1 = cy + (base_radius + 5) * math.sin(rad)
            x2 = cx + (base_radius + 12) * math.cos(rad)
            y2 = cy + (base_radius + 12) * math.sin(rad)
            self.orb_canvas.create_line(x1, y1, x2, y2, fill=ring_color, width=2)
        
        self.after(30, self._animate_orb)

    def _draw_weather_icon(self, icon_type):
        c = self.weather_canvas
        c.delete("all")
        # determine canvas center and a font size proportional to canvas
        try:
            w = int(c.cget('width'))
            h = int(c.cget('height'))
        except Exception:
            w, h = 100, 100
        cx, cy = w // 2, h // 2

        # Prefer PNG assets in `assets/weather/{icon_type}.png` for best visuals.
        assets_dir = os.path.join(os.path.dirname(__file__), "assets", "weather")
        img_path = os.path.join(assets_dir, f"{icon_type}.png")
        if os.path.exists(img_path):
            try:
                img = tk.PhotoImage(file=img_path)
                # keep reference to avoid garbage collection
                self._weather_images[icon_type] = img
                c.create_image(cx, cy, image=img)
                return
            except Exception:
                # If image loading fails, fall through to emoji fallback
                pass

        # Fallback: render a single emoji centered in the canvas
        emoji_map = {
            "sun": "☀️",
            "partly": "🌤️",
            "cloud": "☁️",
            "rain": "🌧️",
            "snow": "🌨️",
        }
        emoji = emoji_map.get(icon_type, "☁️")
        # make emoji size proportional to canvas (approx 45% of smaller dimension)
        font_size = max(18, int(min(w, h) * 0.45))
        try:
            c.create_text(cx, cy, text=emoji, font=("Segoe UI Emoji", font_size), fill=JARVIS_CYAN)
        except Exception:
            c.create_text(cx, cy, text="☁", font=("Arial", font_size), fill=JARVIS_CYAN)

    def _update_weather_ui(self, temp, code, humidity=None, wind=None, feels=None):
        self.temp_label.configure(text=f"{temp:.1f}°C")
        self.header_temp.configure(text=f"⛅ {temp:.1f}°C", font=("Arial", 20))
        
        icon_type = self.weather_map.get(code, "cloud")
        self._draw_weather_icon(icon_type)
        
        self.location_label.configure(text="Petit-Couronne, FR", font=("Arial", 17))
        self.header_location.configure(text="- Petit-Couronne", font=("Arial", 20))
        
        conditions = {
            "sun": "clear sky", "partly": "partly cloudy", 
            "cloud": "overcast clouds", "rain": "rain", "snow": "snow"
        }
        self.condition_label.configure(text=conditions.get(icon_type, ""))
        
        if humidity: self.humidity_label.configure(text=f"{humidity}%")
        if wind: self.wind_label.configure(text=f"{wind} m/s")
        if feels: self.feels_label.configure(text=f"{feels:.1f}°C")

    def _update_time_loop(self):
        now = datetime.now()
        self.time_label.configure(text=now.strftime("%I:%M:%S  %p"))
        self.date_label.configure(text=now.strftime("%B %d, %Y"))
        
        # Update uptime (only if uptime widgets exist)
        uptime = now - self.session_start
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hasattr(self, "uptime_header"):
            self.uptime_header.configure(text=time_str)
        if hasattr(self, "running_time"):
            self.running_time.configure(text=time_str)
        if hasattr(self, "commands_label"):
            self.commands_label.configure(text=str(self.commands_count))
        
        # Fetch weather every 30 min
        if not hasattr(self, "_last_weather") or (now.timestamp() - self._last_weather) > 1800:
            self._last_weather = now.timestamp()
            threading.Thread(target=self._fetch_weather, daemon=True).start()
        
        self.after(1000, self._update_time_loop)

    def _fetch_weather(self):
        try:
            lat, lon = 49.41, 1.03
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=relativehumidity_2m,apparent_temperature"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            temp = data["current_weather"]["temperature"]
            code = data["current_weather"]["weathercode"]
            wind = data["current_weather"]["windspeed"]
            
            humidity = data.get("hourly", {}).get("relativehumidity_2m", [None])[0]
            feels = data.get("hourly", {}).get("apparent_temperature", [None])[0]
            
            self.after(0, lambda: self._update_weather_ui(temp, code, humidity, wind, feels))
        except Exception:
            pass

    def _update_stats_loop(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            self.cpu_pct_label.configure(text=f"{cpu}%")
            self.cpu_bar.set(cpu / 100)
            
            ram_gb = ram.used / (1024 ** 3)
            self.ram_label.configure(text=f"{ram_gb:.0f} GB")
            self.ram_bar.set(ram.percent / 100)
            
            self.cpu_stat.configure(text=f"{cpu}%")
            self.mem_stat.configure(text=f"{ram.percent}%")
            self.disk_stat.configure(text=f"{disk.used // (1024**3)}/{disk.total // (1024**3)}  GB")
            
            # System load
            load_avg = cpu
            if hasattr(self, "load_bar"):
                self.load_bar.set(load_avg / 100)
            if hasattr(self, "load_pct"):
                self.load_pct.configure(text=f"{load_avg:.0f}%")
            
            if load_avg < 30:
                status, color = "Low", JARVIS_GREEN
            elif load_avg < 70:
                status, color = "Moderate", JARVIS_GREEN
            else:
                status, color = "High", "#ff6b35"
            
            if hasattr(self, "load_status"):
                self.load_status.configure(text=status, text_color=color)
            if hasattr(self, "load_pct"):
                self.load_pct.configure(text_color=color)
            
        except Exception:
            pass
        
        self.after(2000, self._update_stats_loop)

    def add_user_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", pady=5)
        
        bubble = ctk.CTkFrame(container, fg_color=JARVIS_CYAN_DIM, corner_radius=12)
        bubble.pack(side="right", padx=(50, 5))
        
        # Increase user message font size for readability
        ctk.CTkLabel(bubble, text=text, font=("Arial", 14), text_color=JARVIS_TEXT,
                wraplength=320, justify="left").pack(padx=12, pady=8)
        
        self.message_widgets.append(container)
        self._scroll_to_bottom()

    def add_assistant_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", pady=5)
        
        bubble = ctk.CTkFrame(container, fg_color=JARVIS_PANEL_BG, corner_radius=12,
                             border_width=1, border_color=JARVIS_BORDER)
        bubble.pack(side="left", padx=(5, 50))
        
        # Increase assistant message font size for readability
        ctk.CTkLabel(bubble, text=text, font=("Arial", 14), text_color=JARVIS_TEXT,
                wraplength=320, justify="left").pack(padx=12, pady=8)
        
        # Timestamp
        time_label = ctk.CTkLabel(bubble, text=datetime.now().strftime("%I:%M %p"),
                      font=("Arial", 11), text_color=JARVIS_TEXT_DIM)
        time_label.pack(anchor="e", padx=12, pady=(0, 5))
        
        self.message_widgets.append(container)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_scroll._parent_canvas.yview_moveto(1.0)

    def set_listening(self, state: bool):
        self.is_listening = state
        if state:
            self.is_interrupted = False # <--- LE FIX EST ICI (On éteint le rouge)
            self.status_text.configure(text="Listening...", text_color=JARVIS_CYAN)
            self.listening_dot.configure(text_color=JARVIS_GREEN)
        else:
            # Si on passe en mode "Veille" (state=False), on éteint aussi le rouge
            if not self.is_speaking: 
                 self.is_interrupted = False 
            
            self.status_text.configure(text="Listening for wake word...", text_color=JARVIS_CYAN)
            self.listening_dot.configure(text_color=JARVIS_GREEN)

    def set_speaking(self, state: bool):
        self.is_speaking = state
        if state:
            self.is_interrupted = False # <--- LE FIX EST ICI AUSSI
            self.status_text.configure(text="Speaking...", text_color="#ff6b35")
            self.listening_dot.configure(text_color="#ff6b35")
    
    def set_interrupted(self):
        """Active le mode visuel 'Interruption'"""
        self.is_listening = False
        self.is_speaking = False
        self.is_interrupted = True
        
        self.status_text.configure(text="⛔ Parole coupée !")
        self.listening_dot.configure(text="●", text_color="#ff3333") # Point Rouge


# Pour tests sans le main.py
if __name__ == "__main__":
    test_queue = queue.Queue()
    app = CypherGUI(test_queue)
    app.mainloop()
