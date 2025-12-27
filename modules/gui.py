import customtkinter as ctk
import tkinter as tk
from tkinter import Canvas, ttk
import math
from datetime import datetime, timedelta
import queue
import requests
import threading
import psutil
import json
import os
from collections import deque
from typing import Dict, Any
import time
import base64
from PIL import Image, ImageTk
from io import BytesIO

# Configuration du thème
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Couleurs JARVIS améliorées avec gradients
JARVIS_BG = "#0a1628"
JARVIS_PANEL_BG = "#0d1f35"
JARVIS_CYAN = "#00d4ff"
JARVIS_CYAN_DIM = "#0a3d4d"
JARVIS_TEXT = "#ffffff"
JARVIS_TEXT_DIM = "#6b8fa3"
JARVIS_BORDER = "#1a4a5c"
JARVIS_GREEN = "#00ff88"
JARVIS_ORANGE = "#ff6b35"
JARVIS_RED = "#ff3333"
JARVIS_PURPLE = "#a855f7"
JARVIS_YELLOW = "#fbbf24"

class CypherGUI(ctk.CTk):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.title("C.Y.P.H.E.R - AI Assistant")
        self.geometry("1800x1000")
        self.configure(fg_color=JARVIS_BG)
        
        # État
        self.is_listening = False
        self.is_interrupted = False
        self.is_speaking = False
        self.is_processing = False
        self.is_reconnecting = False
        self.animation_angle = 0
        self.wave_offset = 0
        self.current_radius = 150
        self.target_radius = 150
        self.particle_system = []  # Pour les effets de particules
        
        # Données
        self.message_widgets = []
        self.conversation_history = deque(maxlen=100)  # Historique limité
        self.commands_count = 0
        self.session_start = datetime.now()
        self._weather_images = {}
        
        # Agent Vision (Web Navigator)
        self.agent_vision_window = None
        self.agent_vision_canvas = None
        self.agent_vision_log_text = None  # Text widget pour la console
        self.agent_vision_image = None
        self.agent_vision_photo = None
        self.agent_vision_logs = deque(maxlen=50)  # Historique des logs
        
        # Task Master Dashboard
        self.tasks_dashboard_window = None
        self.tasks_scrollable_frame = None
        self.tasks_widgets = {}  # Dictionnaire pour stocker les widgets de tâches
        
        # Statistiques pour graphiques
        self.cpu_history = deque(maxlen=50)
        self.ram_history = deque(maxlen=50)
        self.commands_history = deque(maxlen=30)  # Dernières 30 commandes
        
        # Audio level pour animation de l'orb
        self.audio_level = 0.0  # Niveau audio actuel (0.0 à 1.0)
        self.audio_level_smooth = 0.0  # Niveau lissé pour animation fluide
        self.audio_history = deque(maxlen=30)  # Historique pour visualisation
        
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
                    elif content == "processing":
                        self.set_processing(True)
                    elif content == "interrupted":
                        self.set_interrupted()
                    elif content == "reconnecting":
                        self.set_reconnecting(True)
                elif msg_type == "ASSISTANT_TEXT":
                    self.add_assistant_message(content)
                elif msg_type == "USER_TEXT":
                    self.add_user_message(content)
                    self.commands_count += 1
                    self.commands_history.append(time.time())
                elif msg_type == "AUDIO_LEVEL":
                    # Reçoit le niveau audio (0.0 à 1.0)
                    self.audio_level = max(0.0, min(1.0, float(content)))
                    self.audio_history.append(self.audio_level)
                elif msg_type == "AGENT_VIEW_UPDATE":
                    # Reçoit une mise à jour de l'agent web (streaming optimisé)
                    self._update_agent_vision(content)
                elif msg_type == "TASKS_UPDATE":
                    # Reçoit une mise à jour des tâches
                    self._update_tasks_dashboard(content)
        except queue.Empty:
            pass
        self.after(50, self.check_queue)

    def _build_ui(self):
        # Configuration grille principale
        self.grid_columnconfigure(0, weight=1, minsize=400)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1, minsize=420)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        
        self._build_header()
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent", height=70)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(15, 5))
        header.grid_columnconfigure(1, weight=1)
        
        # Logo JARVIS + Status amélioré
        left_frame = ctk.CTkFrame(header, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w")
        
        title_label = ctk.CTkLabel(left_frame, text="C.Y.P.H.E.R", 
                                   font=("Consolas", 32, "bold"), 
                                   text_color=JARVIS_CYAN)
        title_label.pack(side="left", padx=(0, 15))
        
        status_frame = ctk.CTkFrame(left_frame, fg_color=JARVIS_CYAN_DIM, corner_radius=15,
                                    border_width=1, border_color=JARVIS_CYAN)
        status_frame.pack(side="left")
        
        self.status_dot = ctk.CTkLabel(status_frame, text="●", font=("Arial", 12), 
                                      text_color=JARVIS_GREEN)
        self.status_dot.pack(side="left", padx=(12, 6), pady=6)
        
        self.status_header_text = ctk.CTkLabel(status_frame, text="Online", 
                                              font=("Arial", 13, "bold"), 
                                              text_color=JARVIS_GREEN)
        self.status_header_text.pack(side="left", padx=(0, 12), pady=6)
        
        # Centre - Horloge + Date améliorée
        center_frame = ctk.CTkFrame(header, fg_color=JARVIS_PANEL_BG, corner_radius=25,
                                    border_width=1, border_color=JARVIS_BORDER)
        center_frame.grid(row=0, column=1)
        
        clock_inner = ctk.CTkFrame(center_frame, fg_color="transparent")
        clock_inner.pack(padx=25, pady=10)
        
        ctk.CTkLabel(clock_inner, text="◷", font=("Arial", 18), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 10))
        self.time_label = ctk.CTkLabel(clock_inner, text="00:00:00", 
                                       font=("Consolas", 18, "bold"), 
                                       text_color=JARVIS_TEXT)
        self.time_label.pack(side="left")
        
        ctk.CTkLabel(clock_inner, text="  |  ", font=("Arial", 16), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        
        self.date_label = ctk.CTkLabel(clock_inner, text="January 1, 2025", 
                                       font=("Arial", 16), text_color=JARVIS_TEXT)
        self.date_label.pack(side="left")
        
        # Droite - Météo + Session info
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e")
        
        # Session uptime
        session_frame = ctk.CTkFrame(right_frame, fg_color=JARVIS_PANEL_BG, 
                                     corner_radius=12, border_width=1, 
                                     border_color=JARVIS_BORDER)
        session_frame.pack(side="left", padx=(0, 10))
        
        session_inner = ctk.CTkFrame(session_frame, fg_color="transparent")
        session_inner.pack(padx=10, pady=6)
        
        ctk.CTkLabel(session_inner, text="⏱", font=("Arial", 14), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 6))
        self.uptime_label = ctk.CTkLabel(session_inner, text="00:00:00", 
                                         font=("Consolas", 13), 
                                         text_color=JARVIS_TEXT)
        self.uptime_label.pack(side="left")
        
        # Météo
        self.header_temp = ctk.CTkLabel(right_frame, text="--°C", 
                                       font=("Arial", 16, "bold"), 
                                       text_color=JARVIS_TEXT)
        self.header_temp.pack(side="left", padx=(0, 8))
        
        self.header_location = ctk.CTkLabel(right_frame, text="Loading...", 
                                           font=("Arial", 13), 
                                           text_color=JARVIS_CYAN)
        self.header_location.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(right_frame, text="⚙", font=("Arial", 20), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")

    def _build_left_panel(self):
        left_container = ctk.CTkFrame(self, fg_color="transparent")
        left_container.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=10)
        left_container.grid_rowconfigure(4, weight=1)
        
        # System Stats amélioré
        self._build_system_stats(left_container)
        
        # Weather Widget
        self._build_weather_widget(left_container)
        
        # Stats Dashboard avec graphiques
        self._build_stats_dashboard(left_container)
        
        # Camera Widget
        self._build_camera_widget(left_container)

    def _build_system_stats(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=20, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="x", pady=(0, 15))
        
        # Header avec bouton refresh
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(15, 10))
        
        ctk.CTkLabel(header, text="⚙", font=("Arial", 28), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="System Stats", font=("Arial", 22, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=(0, 15))
        
        # CPU Usage avec graphique mini
        cpu_frame = ctk.CTkFrame(content, fg_color="transparent")
        cpu_frame.pack(fill="x", pady=4)
        
        cpu_label_frame = ctk.CTkFrame(cpu_frame, fg_color="transparent")
        cpu_label_frame.pack(side="left")
        ctk.CTkLabel(cpu_label_frame, text="CPU Usage", font=("Arial", 16), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(cpu_label_frame, text=" 💻", font=("Arial", 14), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        self.cpu_pct_label = ctk.CTkLabel(cpu_frame, text="0%", 
                                          font=("Consolas", 15, "bold"), 
                                          text_color=JARVIS_CYAN)
        self.cpu_pct_label.pack(side="right")
        
        self.cpu_bar = ctk.CTkProgressBar(content, height=6, 
                                          progress_color=JARVIS_CYAN, 
                                          fg_color=JARVIS_CYAN_DIM)
        self.cpu_bar.pack(fill="x", pady=(4, 10))
        self.cpu_bar.set(0)
        
        # RAM Usage
        ram_frame = ctk.CTkFrame(content, fg_color="transparent")
        ram_frame.pack(fill="x", pady=4)
        
        ram_label_frame = ctk.CTkFrame(ram_frame, fg_color="transparent")
        ram_label_frame.pack(side="left")
        ctk.CTkLabel(ram_label_frame, text="RAM Usage", font=("Arial", 16), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(ram_label_frame, text=" 🧠", font=("Arial", 14), 
                    text_color=JARVIS_GREEN).pack(side="left")
        
        self.ram_label = ctk.CTkLabel(ram_frame, text="0 GB / 0 GB", 
                                      font=("Consolas", 15, "bold"), 
                                      text_color=JARVIS_GREEN)
        self.ram_label.pack(side="right")
        
        self.ram_bar = ctk.CTkProgressBar(content, height=6, 
                                          progress_color=JARVIS_GREEN, 
                                          fg_color=JARVIS_CYAN_DIM)
        self.ram_bar.pack(fill="x", pady=(4, 10))
        self.ram_bar.set(0)
        
        # Disk Usage
        disk_frame = ctk.CTkFrame(content, fg_color="transparent")
        disk_frame.pack(fill="x", pady=4)
        
        disk_label_frame = ctk.CTkFrame(disk_frame, fg_color="transparent")
        disk_label_frame.pack(side="left")
        ctk.CTkLabel(disk_label_frame, text="Disk Usage", font=("Arial", 16), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(disk_label_frame, text=" 💾", font=("Arial", 14), 
                    text_color=JARVIS_ORANGE).pack(side="left")
        
        self.disk_label = ctk.CTkLabel(disk_frame, text="0 GB / 0 GB", 
                                       font=("Consolas", 15, "bold"), 
                                       text_color=JARVIS_ORANGE)
        self.disk_label.pack(side="right")
        
        self.disk_bar = ctk.CTkProgressBar(content, height=6, 
                                           progress_color=JARVIS_ORANGE, 
                                           fg_color=JARVIS_CYAN_DIM)
        self.disk_bar.pack(fill="x", pady=(4, 15))
        self.disk_bar.set(0)
        
        # Stats grid améliorée
        stats_grid = ctk.CTkFrame(content, fg_color="transparent")
        stats_grid.pack(fill="x")
        stats_grid.grid_columnconfigure((0, 1, 2), weight=1)
        
        stats_data = [
            ("Commands", "commands_stat", "📊"),
            ("Uptime", "uptime_stat", "⏱"),
            ("Status", "status_stat", "✅")
        ]
        
        for i, (label, key, icon) in enumerate(stats_data):
            stat_frame = ctk.CTkFrame(stats_grid, fg_color=JARVIS_CYAN_DIM, 
                                     corner_radius=10)
            stat_frame.grid(row=0, column=i, sticky="nsew", padx=4)
            
            inner = ctk.CTkFrame(stat_frame, fg_color="transparent")
            inner.pack(padx=8, pady=8)
            
            ctk.CTkLabel(inner, text=icon, font=("Arial", 16), 
                        text_color=JARVIS_CYAN).pack()
            ctk.CTkLabel(inner, text=label, font=("Arial", 11), 
                        text_color=JARVIS_TEXT_DIM).pack(pady=(2, 0))
            lbl = ctk.CTkLabel(inner, text="0", font=("Consolas", 16, "bold"), 
                              text_color=JARVIS_CYAN)
            lbl.pack()
            setattr(self, key, lbl)

    def _build_weather_widget(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=20, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="x", pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(15, 10))
        
        ctk.CTkLabel(header, text="☁", font=("Arial", 28), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="Météo", font=("Arial", 22, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=(0, 15))
        
        # Main weather info
        main_row = ctk.CTkFrame(content, fg_color="transparent")
        main_row.pack(fill="x")
        
        left_info = ctk.CTkFrame(main_row, fg_color="transparent")
        left_info.pack(side="left")
        
        self.temp_label = ctk.CTkLabel(left_info, text="--°C", 
                                       font=("Consolas", 36, "bold"), 
                                       text_color=JARVIS_TEXT)
        self.temp_label.pack(anchor="w")
        
        self.location_label = ctk.CTkLabel(left_info, text="Loading...", 
                                          font=("Arial", 14), 
                                          text_color=JARVIS_TEXT_DIM)
        self.location_label.pack(anchor="w")
        
        self.condition_label = ctk.CTkLabel(left_info, text="", 
                                           font=("Arial", 12), 
                                           text_color=JARVIS_TEXT_DIM)
        self.condition_label.pack(anchor="w")
        
        # Weather icon
        self.weather_canvas = Canvas(main_row, width=110, height=110, 
                                    bg=JARVIS_PANEL_BG, highlightthickness=0)
        self.weather_canvas.pack(side="right", padx=10)
        self._draw_weather_icon("cloud")
        
        # Details row
        details = ctk.CTkFrame(content, fg_color="transparent")
        details.pack(fill="x", pady=(12, 0))
        details.grid_columnconfigure((0, 1, 2), weight=1)
        
        for i, (label, key, icon) in enumerate([
            ("Humidité", "humidity_label", "💧"),
            ("Vent", "wind_label", "🌪"),
            ("Ressenti", "feels_label", "🌡")
        ]):
            det_frame = ctk.CTkFrame(details, fg_color=JARVIS_CYAN_DIM, 
                                    corner_radius=10)
            det_frame.grid(row=0, column=i, sticky="nsew", padx=4)
            
            inner = ctk.CTkFrame(det_frame, fg_color="transparent")
            inner.pack(padx=8, pady=8)
            
            ctk.CTkLabel(inner, text=icon, font=("Arial", 16), 
                        text_color=JARVIS_CYAN).pack()
            ctk.CTkLabel(inner, text=label, font=("Arial", 11), 
                        text_color=JARVIS_TEXT_DIM).pack(pady=(2, 0))
            lbl = ctk.CTkLabel(inner, text="--", font=("Consolas", 14, "bold"), 
                              text_color=JARVIS_TEXT)
            lbl.pack()
            setattr(self, key, lbl)

    def _build_stats_dashboard(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=20, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(15, 10))
        
        ctk.CTkLabel(header, text="📊", font=("Arial", 28), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="Performance", font=("Arial", 22, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        # Graphiques mini
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=18, pady=(0, 15))
        
        # Canvas pour graphiques
        self.stats_canvas = Canvas(content, width=350, height=200, 
                                   bg=JARVIS_PANEL_BG, highlightthickness=0)
        self.stats_canvas.pack(fill="both", expand=True)
        
        # Légende
        legend = ctk.CTkFrame(content, fg_color="transparent")
        legend.pack(fill="x", pady=(8, 0))
        
        legend_items = [
            ("CPU", JARVIS_CYAN),
            ("RAM", JARVIS_GREEN)
        ]
        
        for label, color in legend_items:
            item = ctk.CTkFrame(legend, fg_color="transparent")
            item.pack(side="left", padx=10)
            ctk.CTkLabel(item, text="●", font=("Arial", 12), 
                        text_color=color).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(item, text=label, font=("Arial", 11), 
                        text_color=JARVIS_TEXT_DIM).pack(side="left")

    def _build_camera_widget(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=JARVIS_PANEL_BG, corner_radius=20, 
                            border_width=1, border_color=JARVIS_BORDER)
        frame.pack(fill="both", expand=True)
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(15, 8))
        
        ctk.CTkLabel(header, text="📷", font=("Arial", 28), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="Camera", font=("Arial", 22, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        # Camera preview area améliorée
        preview = ctk.CTkFrame(frame, fg_color=JARVIS_CYAN_DIM, 
                              corner_radius=15, border_width=1, 
                              border_color=JARVIS_BORDER)
        preview.pack(fill="both", expand=True, padx=18, pady=(0, 15))
        
        preview_inner = ctk.CTkFrame(preview, fg_color="transparent")
        preview_inner.pack(expand=True)
        
        ctk.CTkLabel(preview_inner, text="🎥", font=("Arial", 40), 
                    text_color=JARVIS_TEXT_DIM).pack(pady=20)
        ctk.CTkLabel(preview_inner, text="Camera Off", font=("Arial", 14, "bold"), 
                    text_color=JARVIS_CYAN).pack(pady=(0, 8))
        ctk.CTkLabel(preview_inner, text="Camera is inactive", 
                    font=("Arial", 11), text_color=JARVIS_TEXT_DIM).pack(pady=(0, 15))

    def _build_center_panel(self):
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        center.grid_rowconfigure(0, weight=1)
        center.grid_rowconfigure(1, weight=0)
        center.grid_columnconfigure(0, weight=1)
        
        # Orb container avec effet de profondeur
        orb_frame = ctk.CTkFrame(center, fg_color="transparent")
        orb_frame.grid(row=0, column=0, sticky="nsew")
        
        self.orb_canvas = Canvas(orb_frame, width=500, height=500, bg=JARVIS_BG, 
                                 highlightthickness=0)
        self.orb_canvas.pack(expand=True)
        
        # Title and status améliorés
        title_frame = ctk.CTkFrame(center, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="s", pady=(0, 160))
        
        self.jarvis_title = ctk.CTkLabel(title_frame, text="C.Y.P.H.E.R", 
                                         font=("Consolas", 56, "bold"), 
                                         text_color=JARVIS_CYAN)
        self.jarvis_title.pack()
        
        status_container = ctk.CTkFrame(title_frame, fg_color=JARVIS_CYAN_DIM, 
                                       corner_radius=18, border_width=1, 
                                       border_color=JARVIS_CYAN)
        status_container.pack(pady=(60, 0))
        
        status_inner = ctk.CTkFrame(status_container, fg_color="transparent")
        status_inner.pack(padx=20, pady=10)
        
        self.listening_dot = ctk.CTkLabel(status_inner, text="●", font=("Arial", 12), 
                                         text_color=JARVIS_GREEN)
        self.listening_dot.pack(side="left", padx=(0, 10))
        
        self.status_text = ctk.CTkLabel(status_inner, text="Listening for wake word...", 
                                       font=("Arial", 22, "bold"), 
                                       text_color=JARVIS_CYAN)
        self.status_text.pack(side="left")
        
        # Contrôles interactifs
        controls_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        controls_frame.pack(pady=(20, 0))
        
        # Boutons de contrôle
        btn_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        btn_frame.pack()
        
        # Styles de boutons
        btn_style = {
            "width": 50,
            "height": 50,
            "corner_radius": 25,
            "font": ("Arial", 18),
            "hover_color": JARVIS_GREEN
        }
        
        # Bouton Pause (placeholder - à connecter)
        pause_btn = ctk.CTkButton(btn_frame, text="⏸", fg_color=JARVIS_CYAN_DIM, 
                                  text_color=JARVIS_CYAN, **btn_style)
        pause_btn.pack(side="left", padx=5)
        
        # Bouton Stop (placeholder - à connecter)
        stop_btn = ctk.CTkButton(btn_frame, text="⏹", fg_color=JARVIS_CYAN_DIM, 
                                text_color=JARVIS_RED, **btn_style)
        stop_btn.pack(side="left", padx=5)

    def _build_right_panel(self):
        right_container = ctk.CTkFrame(self, fg_color="transparent")
        right_container.grid(row=1, column=2, sticky="nsew", padx=(10, 20), pady=10)
        right_container.grid_rowconfigure(0, weight=1)
        right_container.grid_columnconfigure(0, weight=1)
        
        # Conversation panel amélioré
        conv_frame = ctk.CTkFrame(right_container, fg_color=JARVIS_PANEL_BG, 
                                  corner_radius=20, border_width=1, 
                                  border_color=JARVIS_BORDER)
        conv_frame.pack(fill="both", expand=True)
        conv_frame.grid_rowconfigure(1, weight=1)
        conv_frame.grid_columnconfigure(0, weight=1)
        
        # Header amélioré
        header = ctk.CTkFrame(conv_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 10))
        header.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(header, text="💬", font=("Arial", 28), 
                    text_color=JARVIS_CYAN).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(header, text="Conversation", font=("Arial", 22, "bold"), 
                    text_color=JARVIS_TEXT).grid(row=0, column=1, sticky="w")
        
        btns_frame = ctk.CTkFrame(header, fg_color="transparent")
        btns_frame.grid(row=0, column=2, sticky="e")
        
        # Bouton recherche
        search_btn = ctk.CTkButton(btns_frame, text="🔍", width=35, height=35,
                                   fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                   text_color=JARVIS_CYAN, font=("Arial", 14),
                                   corner_radius=8, command=self._toggle_search)
        search_btn.pack(side="left", padx=(0, 5))
        
        # Bouton clear
        clear_btn = ctk.CTkButton(btns_frame, text="🗑", width=35, height=35,
                                  fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                  text_color=JARVIS_RED, font=("Arial", 14),
                                  corner_radius=8, command=self._clear_chat)
        clear_btn.pack(side="left", padx=(0, 5))
        
        # Bouton export
        export_btn = ctk.CTkButton(btns_frame, text="📥", width=35, height=35,
                                   fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                   text_color=JARVIS_GREEN, font=("Arial", 14),
                                   corner_radius=8, command=self._export_conversation)
        export_btn.pack(side="left", padx=(0, 5))
        
        # Bouton Task Master
        tasks_btn = ctk.CTkButton(btns_frame, text="✓", width=35, height=35,
                                  fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                  text_color=JARVIS_PURPLE, font=("Arial", 16, "bold"),
                                  corner_radius=8, command=self._show_tasks_dashboard)
        tasks_btn.pack(side="left")
        
        # Barre de recherche (cachée par défaut)
        self.search_frame = ctk.CTkFrame(conv_frame, fg_color="transparent")
        self.search_frame.grid(row=0, column=0, sticky="ew", padx=18, pady=(0, 5))
        self.search_frame.grid_remove()
        
        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Rechercher dans la conversation...",
                                         fg_color=JARVIS_CYAN_DIM, border_width=0,
                                         text_color=JARVIS_TEXT, height=35, corner_radius=15)
        self.search_entry.pack(fill="x", padx=(0, 8), side="left", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._search_conversation())
        
        close_search_btn = ctk.CTkButton(self.search_frame, text="✕", width=35, height=35,
                                         fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_RED,
                                         text_color=JARVIS_TEXT, font=("Arial", 14),
                                         corner_radius=8, command=self._toggle_search)
        close_search_btn.pack(side="left")
        
        # Chat area améliorée
        self.chat_scroll = ctk.CTkScrollableFrame(conv_frame, fg_color="transparent")
        self.chat_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        
        # Input area améliorée
        input_frame = ctk.CTkFrame(conv_frame, fg_color="transparent")
        input_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 15))
        input_frame.grid_columnconfigure(0, weight=1)
        
        self.message_entry = ctk.CTkEntry(input_frame, placeholder_text="Tapez un message...",
                                          fg_color=JARVIS_CYAN_DIM, border_width=0,
                                          text_color=JARVIS_TEXT, height=45, 
                                          corner_radius=22, font=("Arial", 13))
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.message_entry.bind("<Return>", lambda e: self._send_message())
        
        send_btn = ctk.CTkButton(input_frame, text="➤", width=50, height=45,
                                 fg_color=JARVIS_CYAN, hover_color=JARVIS_GREEN,
                                 text_color=JARVIS_BG, font=("Arial", 20, "bold"),
                                 corner_radius=22, command=self._send_message)
        send_btn.grid(row=0, column=1)
        
        # Compteur de messages
        self.message_count_label = ctk.CTkLabel(input_frame, text="0 messages", 
                                                font=("Arial", 10), 
                                                text_color=JARVIS_TEXT_DIM)
        self.message_count_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

    def _toggle_search(self):
        if self.search_frame.winfo_viewable():
            self.search_frame.grid_remove()
            self.search_entry.delete(0, "end")
            self._search_conversation()  # Reset search
        else:
            self.search_frame.grid()
            self.search_entry.focus()

    def _search_conversation(self):
        query = self.search_entry.get().lower()
        for widget in self.message_widgets:
            if query:
                # Simple search - highlight matching widgets
                for child in widget.winfo_children():
                    for grandchild in child.winfo_children():
                        if isinstance(grandchild, ctk.CTkLabel):
                            text = grandchild.cget("text").lower()
                            if query in text:
                                child.configure(fg_color=JARVIS_CYAN_DIM)
                                break
                            else:
                                child.configure(fg_color="transparent" if "user" in str(widget) else JARVIS_PANEL_BG)

    def _export_conversation(self):
        try:
            from core.paths import get_logs_dir
            logs_dir = get_logs_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = logs_dir / f"conversation_{timestamp}.txt"
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Cypher Conversation Export\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                for msg_type, content, timestamp in self.conversation_history:
                    f.write(f"[{timestamp}] {msg_type}: {content}\n\n")
            
            # Feedback visuel
            self.message_count_label.configure(text=f"✓ Exported to {filename.name}", 
                                              text_color=JARVIS_GREEN)
            self.after(3000, lambda: self.message_count_label.configure(
                text=f"{len(self.message_widgets)} messages", 
                text_color=JARVIS_TEXT_DIM))
        except Exception as e:
            self.message_count_label.configure(text=f"✗ Export failed: {e}", 
                                              text_color=JARVIS_RED)

    def _send_message(self):
        text = self.message_entry.get().strip()
        if text:
            self.data_queue.put(("USER_TEXT", text))
            self.message_entry.delete(0, "end")

    def _clear_chat(self):
        for widget in self.message_widgets:
            widget.destroy()
        self.message_widgets.clear()
        self.conversation_history.clear()
        self.message_count_label.configure(text="0 messages")

    def _animate_orb(self):
        self.orb_canvas.delete("all")
        cx, cy = 250, 240
        
        # Lissage du niveau audio pour animation fluide
        self.audio_level_smooth = self.audio_level_smooth * 0.7 + self.audio_level * 0.3
        
        # Déterminer l'état et les couleurs (simplifié)
        if self.is_interrupted:
            ring_color = JARVIS_RED
            inner_color = "#ff6666"
            pulse_base = math.sin(self.animation_angle * 2) * 8
            self.animation_angle += 0.25
            audio_modifier = 0
        elif self.is_processing:
            ring_color = JARVIS_ORANGE
            inner_color = "#ffb833"
            pulse_base = math.sin(self.animation_angle * 1.5) * 12
            self.animation_angle += 0.2
            audio_modifier = self.audio_level_smooth * 8
        elif self.is_speaking:
            ring_color = JARVIS_ORANGE
            inner_color = "#ff8c5a"
            pulse_base = math.sin(self.animation_angle * 1.0) * 15
            self.animation_angle += 0.15
            audio_modifier = self.audio_level_smooth * 10
        elif self.is_listening:
            ring_color = JARVIS_CYAN
            inner_color = "#4dd9ff"
            pulse_base = math.sin(self.animation_angle * 0.6) * 6
            # Réaction au volume quand l'utilisateur parle
            audio_modifier = self.audio_level_smooth * 25
            self.animation_angle += 0.1
        else:  # IDLE
            ring_color = JARVIS_CYAN_DIM
            inner_color = JARVIS_CYAN
            pulse_base = 0
            audio_modifier = 0
            self.animation_angle = 0
        
        # Base radius avec pulse et réaction audio
        base_radius = 150 + pulse_base + audio_modifier
        
        # UN SEUL anneau extérieur simple
        if self.is_listening or self.is_speaking or self.is_processing:
            outer_r = base_radius + 25
            self.orb_canvas.create_oval(cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r,
                                       outline=ring_color, width=1)
        
        # Main orb ring (épaisseur variable avec volume)
        ring_width = 3 + int(self.audio_level_smooth * 2)
        self.orb_canvas.create_oval(cx - base_radius, cy - base_radius,
                                   cx + base_radius, cy + base_radius,
                                   outline=ring_color, width=ring_width)
        
        # Inner circle simple
        inner_r = base_radius - 35
        self.orb_canvas.create_oval(cx - inner_r, cy - inner_r,
                                   cx + inner_r, cy + inner_r,
                                   outline=ring_color, width=1)
        
        # Barres audio simples (7 barres seulement, design épuré)
        num_bars = 7
        wave_width = 8
        wave_gap = 12
        total_width = num_bars * wave_width + (num_bars - 1) * wave_gap
        start_x = cx - total_width // 2
        
        for i in range(num_bars):
            # Hauteur de base
            base_height = 12
            # Ajout du volume audio (réaction simple et claire)
            audio_height = self.audio_level_smooth * 30
            # Légère animation
            anim_height = math.sin(self.wave_offset + i * 0.6) * 5
            height = base_height + audio_height + anim_height
            height = min(height, 50)  # Limiter la hauteur
            
            x = start_x + i * (wave_width + wave_gap)
            
            # Couleur simple (pas de gradient complexe)
            bar_color = inner_color
            
            # Dessiner la barre simple
            self.orb_canvas.create_rectangle(x, cy - height, x + wave_width, cy + height,
                                            fill=bar_color, outline="")
        
        self.wave_offset += 0.02
        
        # Pas de centre - design épuré
        
        self.after(30, self._animate_orb)  # 33 FPS suffisant pour fluidité
    
    def _blend_color(self, color1, color2, ratio):
        """Mélange deux couleurs hex"""
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        def rgb_to_hex(rgb):
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        
        rgb1 = hex_to_rgb(color1)
        rgb2 = hex_to_rgb(color2)
        blended = tuple(int(rgb1[i] * ratio + rgb2[i] * (1 - ratio)) for i in range(3))
        return rgb_to_hex(blended)
    
    def _get_bar_color(self, base_color, height, max_height):
        """Retourne une couleur variant selon la hauteur (effet gradient)"""
        if height < max_height * 0.3:
            return base_color
        elif height < max_height * 0.6:
            return JARVIS_GREEN
        else:
            return JARVIS_ORANGE

    def _draw_weather_icon(self, icon_type):
        c = self.weather_canvas
        c.delete("all")
        try:
            w = int(c.cget('width'))
            h = int(c.cget('height'))
        except Exception:
            w, h = 110, 110
        cx, cy = w // 2, h // 2

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(project_root, "assets", "weather")
        img_path = os.path.join(assets_dir, f"{icon_type}.png")
        if os.path.exists(img_path):
            try:
                img = tk.PhotoImage(file=img_path)
                self._weather_images[icon_type] = img
                c.create_image(cx, cy, image=img)
                return
            except Exception:
                pass

        emoji_map = {
            "sun": "☀️",
            "partly": "🌤️",
            "cloud": "☁️",
            "rain": "🌧️",
            "snow": "🌨️",
        }
        emoji = emoji_map.get(icon_type, "☁️")
        font_size = max(20, int(min(w, h) * 0.5))
        try:
            c.create_text(cx, cy, text=emoji, font=("Segoe UI Emoji", font_size), 
                         fill=JARVIS_CYAN)
        except Exception:
            c.create_text(cx, cy, text="☁", font=("Arial", font_size), 
                         fill=JARVIS_CYAN)

    def _update_weather_ui(self, temp, code, humidity=None, wind=None, feels=None):
        self.temp_label.configure(text=f"{temp:.1f}°C")
        self.header_temp.configure(text=f"⛅ {temp:.1f}°C", font=("Arial", 22, "bold"))
        
        icon_type = self.weather_map.get(code, "cloud")
        self._draw_weather_icon(icon_type)
        
        self.location_label.configure(text="Petit-Couronne, FR", font=("Arial", 16))
        self.header_location.configure(text="- Petit-Couronne", font=("Arial", 16))
        
        conditions = {
            "sun": "Ciel dégagé", "partly": "Partiellement nuageux",
            "cloud": "Nuageux", "rain": "Pluvieux", "snow": "Neigeux"
        }
        self.condition_label.configure(text=conditions.get(icon_type, ""))
        
        if humidity:
            self.humidity_label.configure(text=f"{humidity}%")
        if wind:
            self.wind_label.configure(text=f"{wind} m/s")
        if feels:
            self.feels_label.configure(text=f"{feels:.1f}°C")

    def _draw_stats_graph(self):
        canvas = self.stats_canvas
        canvas.delete("all")
        
        w = canvas.winfo_width() or 350
        h = canvas.winfo_height() or 200
        
        if not self.cpu_history or not self.ram_history:
            return
        
        # Grille
        for i in range(5):
            y = h - (i * h // 4)
            canvas.create_line(30, y, w - 10, y, fill=JARVIS_BORDER, width=1)
            canvas.create_text(25, y, text=f"{100 - i * 25}%", 
                             fill=JARVIS_TEXT_DIM, font=("Arial", 8), anchor="e")
        
        # Graphiques
        max_samples = len(self.cpu_history)
        if max_samples < 2:
            return
        
        step_x = (w - 40) / max(max_samples - 1, 1)
        
        # CPU line
        cpu_points = []
        for i, val in enumerate(self.cpu_history):
            x = 30 + i * step_x
            y = h - 10 - (val / 100) * (h - 20)
            cpu_points.append((x, y))
        
        if len(cpu_points) > 1:
            for i in range(len(cpu_points) - 1):
                canvas.create_line(cpu_points[i][0], cpu_points[i][1],
                                 cpu_points[i + 1][0], cpu_points[i + 1][1],
                                 fill=JARVIS_CYAN, width=2)
        
        # RAM line
        ram_points = []
        for i, val in enumerate(self.ram_history):
            x = 30 + i * step_x
            y = h - 10 - (val / 100) * (h - 20)
            ram_points.append((x, y))
        
        if len(ram_points) > 1:
            for i in range(len(ram_points) - 1):
                canvas.create_line(ram_points[i][0], ram_points[i][1],
                                 ram_points[i + 1][0], ram_points[i + 1][1],
                                 fill=JARVIS_GREEN, width=2)

    def _update_time_loop(self):
        now = datetime.now()
        self.time_label.configure(text=now.strftime("%I:%M:%S  %p"))
        self.date_label.configure(text=now.strftime("%B %d, %Y"))
        
        # Uptime
        uptime = now - self.session_start
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self.uptime_label.configure(text=time_str)
        
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
            
            # Historique pour graphiques
            self.cpu_history.append(cpu)
            self.ram_history.append(ram.percent)
            
            # Mise à jour UI
            self.cpu_pct_label.configure(text=f"{cpu:.1f}%")
            self.cpu_bar.set(cpu / 100)
            
            ram_used_gb = ram.used / (1024 ** 3)
            ram_total_gb = ram.total / (1024 ** 3)
            self.ram_label.configure(text=f"{ram_used_gb:.1f} / {ram_total_gb:.1f} GB")
            self.ram_bar.set(ram.percent / 100)
            
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)
            self.disk_label.configure(text=f"{disk_used_gb:.1f} / {disk_total_gb:.1f} GB")
            self.disk_bar.set(disk.percent / 100)
            
            # Stats grid
            self.commands_stat.configure(text=str(self.commands_count))
            
            uptime_hours = (datetime.now() - self.session_start).total_seconds() / 3600
            self.uptime_stat.configure(text=f"{uptime_hours:.1f}h")
            
            # Status
            if self.is_listening:
                status_text, status_color = "Listening", JARVIS_GREEN
            elif self.is_speaking:
                status_text, status_color = "Speaking", JARVIS_ORANGE
            elif self.is_processing:
                status_text, status_color = "Processing", JARVIS_ORANGE
            else:
                status_text, status_color = "Idle", JARVIS_TEXT_DIM
            
            self.status_stat.configure(text=status_text, text_color=status_color)
            
            # Dessiner graphiques
            self._draw_stats_graph()
            
        except Exception:
            pass
        
        self.after(2000, self._update_stats_loop)

    def add_user_message(self, text):
        timestamp = datetime.now()
        self.conversation_history.append(("USER", text, timestamp.strftime("%H:%M:%S")))
        
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", pady=6)
        
        bubble = ctk.CTkFrame(container, fg_color=JARVIS_CYAN_DIM, corner_radius=15,
                             border_width=1, border_color=JARVIS_CYAN)
        bubble.pack(side="right", padx=(60, 8))
        
        ctk.CTkLabel(bubble, text=text, font=("Arial", 15), text_color=JARVIS_TEXT,
                    wraplength=350, justify="left").pack(padx=15, pady=10)
        
        # Timestamp
        time_label = ctk.CTkLabel(bubble, text=timestamp.strftime("%H:%M"),
                                 font=("Arial", 10), text_color=JARVIS_TEXT_DIM)
        time_label.pack(anchor="e", padx=15, pady=(0, 6))
        
        self.message_widgets.append(container)
        self.message_count_label.configure(text=f"{len(self.message_widgets)} messages")
        self._scroll_to_bottom()

    def add_assistant_message(self, text):
        timestamp = datetime.now()
        self.conversation_history.append(("ASSISTANT", text, timestamp.strftime("%H:%M:%S")))
        
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", pady=6)
        
        bubble = ctk.CTkFrame(container, fg_color=JARVIS_PANEL_BG, corner_radius=15,
                             border_width=1, border_color=JARVIS_BORDER)
        bubble.pack(side="left", padx=(8, 60))
        
        ctk.CTkLabel(bubble, text=text, font=("Arial", 15), text_color=JARVIS_TEXT,
                    wraplength=350, justify="left").pack(padx=15, pady=10)
        
        # Timestamp
        time_label = ctk.CTkLabel(bubble, text=timestamp.strftime("%H:%M"),
                                 font=("Arial", 10), text_color=JARVIS_TEXT_DIM)
        time_label.pack(anchor="e", padx=15, pady=(0, 6))
        
        self.message_widgets.append(container)
        self.message_count_label.configure(text=f"{len(self.message_widgets)} messages")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_scroll._parent_canvas.update_idletasks()
        self.chat_scroll._parent_canvas.yview_moveto(1.0)

    def set_listening(self, state: bool):
        self.is_listening = state
        if state:
            self.is_interrupted = False
            self.is_processing = False
            self.status_text.configure(text="Listening...", text_color=JARVIS_CYAN)
            self.listening_dot.configure(text_color=JARVIS_GREEN)
            self.status_header_text.configure(text="Active", text_color=JARVIS_GREEN)
        else:
            if not self.is_speaking and not self.is_processing:
                self.is_interrupted = False
            self.status_text.configure(text="Listening for wake word...", 
                                     text_color=JARVIS_CYAN)
            self.listening_dot.configure(text_color=JARVIS_GREEN)
            if not self.is_speaking and not self.is_processing:
                self.status_header_text.configure(text="Online", text_color=JARVIS_GREEN)

    def set_speaking(self, state: bool):
        self.is_speaking = state
        if state:
            self.is_interrupted = False
            self.is_processing = False
            self.status_text.configure(text="Speaking...", text_color=JARVIS_ORANGE)
            self.listening_dot.configure(text_color=JARVIS_ORANGE)
            self.status_header_text.configure(text="Speaking", text_color=JARVIS_ORANGE)
        else:
            if not self.is_listening and not self.is_processing:
                self.status_text.configure(text="Listening for wake word...", 
                                         text_color=JARVIS_CYAN)
                self.listening_dot.configure(text_color=JARVIS_GREEN)
                self.status_header_text.configure(text="Online", text_color=JARVIS_GREEN)

    def set_interrupted(self):
        self.is_listening = False
        self.is_speaking = False
        self.is_processing = False
        self.is_interrupted = True
        
        self.status_text.configure(text="⛔ Interrupted !", text_color=JARVIS_RED)
        self.listening_dot.configure(text="●", text_color=JARVIS_RED)
        self.status_header_text.configure(text="Interrupted", text_color=JARVIS_RED)

    def set_processing(self, state: bool):
        self.is_processing = state
        if state:
            self.status_text.configure(text="⚙ Processing...", text_color=JARVIS_ORANGE)
            self.listening_dot.configure(text="●", text_color=JARVIS_ORANGE)
            self.status_header_text.configure(text="Processing", text_color=JARVIS_ORANGE)
        else:
            if not self.is_speaking and not self.is_listening:
                self.status_text.configure(text="Listening for wake word...", 
                                         text_color=JARVIS_CYAN)
                self.listening_dot.configure(text_color=JARVIS_GREEN)
                self.status_header_text.configure(text="Online", text_color=JARVIS_GREEN)

    def set_reconnecting(self, state: bool):
        self.is_reconnecting = state
        if state:
            self.status_text.configure(text="🔄 Reconnecting...", text_color=JARVIS_TEXT_DIM)
            self.listening_dot.configure(text="●", text_color=JARVIS_TEXT_DIM)
            self.status_header_text.configure(text="Reconnecting", text_color=JARVIS_TEXT_DIM)
    
    def _create_agent_vision_window(self):
        """Crée la fenêtre flottante pour l'Agent Vision (style WEB_AGENT_VIEW)"""
        if self.agent_vision_window is not None:
            return
        
        # Créer une fenêtre Toplevel
        self.agent_vision_window = ctk.CTkToplevel(self)
        self.agent_vision_window.title("WEB_AGENT_VIEW")
        self.agent_vision_window.geometry("1000x800")
        self.agent_vision_window.configure(fg_color=JARVIS_BG)
        
        # Empêcher la fermeture accidentelle
        self.agent_vision_window.protocol("WM_DELETE_WINDOW", self._hide_agent_vision)
        
        # Header avec icône globe et titre (style image 2)
        header = ctk.CTkFrame(self.agent_vision_window, fg_color=JARVIS_PANEL_BG, 
                             corner_radius=0, border_width=0, height=40)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=10, pady=8)
        
        # Icône globe + titre
        title_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_frame.pack(side="left")
        
        ctk.CTkLabel(title_frame, text="🌐", font=("Arial", 16), 
                    text_color=JARVIS_CYAN).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(title_frame, text="WEB_AGENT_VIEW", font=("Consolas", 14, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        
        # Bouton fermer (X)
        close_btn = ctk.CTkButton(header_inner, text="✕", width=30, height=30,
                                  fg_color="transparent", hover_color=JARVIS_RED,
                                  text_color=JARVIS_TEXT, font=("Arial", 14),
                                  corner_radius=5, command=self._hide_agent_vision)
        close_btn.pack(side="right")
        
        # Container principal avec vue web et console
        main_container = ctk.CTkFrame(self.agent_vision_window, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=0, pady=0)
        main_container.grid_rowconfigure(0, weight=10)  # Vue web prend beaucoup plus de place (10:1)
        main_container.grid_rowconfigure(1, weight=1)  # Console prend moins de place
        main_container.grid_columnconfigure(0, weight=1)
        
        # === VUE WEB (Canvas pour l'image) ===
        web_view_frame = ctk.CTkFrame(main_container, fg_color=JARVIS_CYAN_DIM, 
                                     corner_radius=0, border_width=1, border_color=JARVIS_BORDER)
        web_view_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        self.agent_vision_canvas = Canvas(web_view_frame, bg="#1a1a1a", 
                                          highlightthickness=0)
        self.agent_vision_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        # === CONSOLE/TERMINAL (Style image 2) ===
        console_frame = ctk.CTkFrame(main_container, fg_color="#0d0d0d", 
                                     corner_radius=0, border_width=1, border_color=JARVIS_BORDER)
        console_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        console_frame.grid_rowconfigure(0, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)
        
        # Prompt/Header console
        console_header = ctk.CTkFrame(console_frame, fg_color="transparent", height=30)
        console_header.pack(fill="x", padx=10, pady=(8, 0))
        console_header.pack_propagate(False)
        
        ctk.CTkLabel(console_header, text="> Enter command for Web Agent...", 
                    font=("Consolas", 11), text_color=JARVIS_TEXT_DIM).pack(side="left")
        
        # Zone de logs (Text widget avec scrollbar)
        log_container = ctk.CTkFrame(console_frame, fg_color="transparent")
        log_container.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        
        # Scrollbar
        scrollbar = ctk.CTkScrollbar(log_container)
        scrollbar.pack(side="right", fill="y")
        
        # Text widget pour les logs (style terminal)
        self.agent_vision_log_text = tk.Text(
            log_container,
            bg="#0d0d0d",
            fg=JARVIS_GREEN,
            font=("Consolas", 10),
            wrap="word",
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=0,
            insertbackground=JARVIS_CYAN
        )
        self.agent_vision_log_text.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.agent_vision_log_text.yview)
        
        # Ajouter le message initial
        self._add_log_to_console(f"[{datetime.now().strftime('%H:%M:%S')}] Web Agent Initialized", "success")
    
    def _hide_agent_vision(self):
        """Masque la fenêtre Agent Vision (sans la détruire)"""
        if self.agent_vision_window:
            self.agent_vision_window.withdraw()
    
    def _show_agent_vision(self):
        """Affiche la fenêtre Agent Vision"""
        if self.agent_vision_window is None:
            self._create_agent_vision_window()
        self.agent_vision_window.deiconify()
        self.agent_vision_window.lift()
    
    def _add_log_to_console(self, message: str, log_type: str = "info"):
        """Ajoute un message à la console avec couleur"""
        if not self.agent_vision_log_text:
            return
        
        # Couleurs selon le type
        colors = {
            "info": JARVIS_CYAN,
            "success": JARVIS_GREEN,
            "warning": JARVIS_ORANGE,
            "error": JARVIS_RED
        }
        color = colors.get(log_type, JARVIS_TEXT)
        
        # Position de départ
        start_pos = self.agent_vision_log_text.index("end")
        
        # Ajouter le message
        self.agent_vision_log_text.insert("end", message + "\n")
        
        # Position de fin
        end_pos = self.agent_vision_log_text.index("end-1c")
        
        # Créer un tag unique pour cette ligne
        tag_name = f"log_{len(self.agent_vision_logs)}"
        self.agent_vision_log_text.tag_add(tag_name, start_pos, end_pos)
        self.agent_vision_log_text.tag_config(tag_name, foreground=color)
        
        # Scroll automatique
        self.agent_vision_log_text.see("end")
        
        # Garder un historique (limiter à 50 lignes)
        self.agent_vision_logs.append((message, log_type))
        
        # Limiter le nombre de lignes dans le Text widget (performance)
        lines = int(self.agent_vision_log_text.index("end-1c").split(".")[0])
        if lines > 100:
            self.agent_vision_log_text.delete("1.0", "50.0")
    
    def _update_agent_vision(self, data: Dict[str, Any]):
        """
        Met à jour l'affichage de l'Agent Vision (streaming optimisé pour faible latence).
        
        Args:
            data: Dict avec 'image' (base64 JPEG), 'log' (str), 'action_coords' (tuple), 'timestamp', 'log_type'
        """
        # Afficher la fenêtre si elle n'existe pas
        if self.agent_vision_window is None:
            self._create_agent_vision_window()
        self._show_agent_vision()
        
        try:
            # Ajouter le log à la console (si présent)
            log_message = data.get("log")
            if log_message:
                log_type = data.get("log_type", "info")
                self._add_log_to_console(log_message, log_type)
            
            # Décoder l'image (déjà optimisée en JPEG par le backend)
            img_base64 = data.get("image", "")
            if not img_base64:
                return
            
            # Décoder rapidement (JPEG est plus rapide que PNG)
            img_bytes = base64.b64decode(img_base64)
            img = Image.open(BytesIO(img_bytes))
            
            # Obtenir les dimensions du canvas
            self.agent_vision_canvas.update_idletasks()
            canvas_width = self.agent_vision_canvas.winfo_width() or 990
            canvas_height = self.agent_vision_canvas.winfo_height() or 500
            
            # Redimensionner l'image pour s'adapter au canvas (conserver les proportions)
            img_width, img_height = img.size
            scale_x = canvas_width / img_width
            scale_y = canvas_height / img_height
            scale = min(scale_x, scale_y)  # Prendre le plus petit pour garder les proportions
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # Redimensionner l'image
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convertir en PhotoImage (optimisé)
            self.agent_vision_photo = ImageTk.PhotoImage(img_resized)
            
            # Effacer le canvas rapidement
            self.agent_vision_canvas.delete("all")
            
            # Centrer l'image
            x = (canvas_width - new_width) // 2 if canvas_width > 1 else 0
            y = (canvas_height - new_height) // 2 if canvas_height > 1 else 0
            
            # Afficher l'image (opération rapide)
            self.agent_vision_canvas.create_image(x, y, anchor="nw", image=self.agent_vision_photo)
            
            # Dessiner le feedback visuel (point rouge pour l'action) - seulement si coordonnées présentes
            action_coords = data.get("action_coords")
            if action_coords and len(action_coords) == 2:
                # Les coordonnées sont déjà dans le référentiel de l'image redimensionnée
                action_x = x + action_coords[0]
                action_y = y + action_coords[1]
                
                # Dessiner un cercle rouge pour indiquer où l'IA va cliquer
                radius = 10
                self.agent_vision_canvas.create_oval(
                    action_x - radius, action_y - radius,
                    action_x + radius, action_y + radius,
                    fill=JARVIS_RED, outline=JARVIS_TEXT, width=2
                )
                # Dessiner un cercle extérieur animé (pulsation)
                self.agent_vision_canvas.create_oval(
                    action_x - radius - 8, action_y - radius - 8,
                    action_x + radius + 8, action_y + radius + 8,
                    outline=JARVIS_RED, width=2, dash=(3, 3)
                )
            
        except Exception as e:
            # Logger optionnel (si disponible)
            try:
                from core.logger import get_logger
                logger = get_logger("gui")
                logger.error(f"Erreur mise à jour Agent Vision: {e}")
            except:
                print(f"Erreur mise à jour Agent Vision: {e}")
            if self.agent_vision_log_text:
                self._add_log_to_console(f"❌ Erreur: {e}", "error")
    
    # ========================================
    # TASK MASTER DASHBOARD
    # ========================================
    
    def _create_tasks_dashboard(self):
        """Crée la fenêtre du dashboard Task Master"""
        if self.tasks_dashboard_window is not None:
            return
        
        # Créer une fenêtre Toplevel
        self.tasks_dashboard_window = ctk.CTkToplevel(self)
        self.tasks_dashboard_window.title("TASK MASTER - Mission Control")
        self.tasks_dashboard_window.geometry("1200x800")
        self.tasks_dashboard_window.configure(fg_color=JARVIS_BG)
        
        # Empêcher la fermeture complète (juste masquer)
        self.tasks_dashboard_window.protocol("WM_DELETE_WINDOW", self._hide_tasks_dashboard)
        
        # Header
        header = ctk.CTkFrame(self.tasks_dashboard_window, fg_color=JARVIS_PANEL_BG, 
                             corner_radius=0, border_width=0, border_color=JARVIS_BORDER)
        header.pack(fill="x", padx=0, pady=0)
        header.grid_columnconfigure(1, weight=1)
        
        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=15)
        header_inner.grid_columnconfigure(1, weight=1)
        
        # Logo et titre
        title_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(title_frame, text="✓", font=("Arial", 32, "bold"), 
                    text_color=JARVIS_PURPLE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_frame, text="TASK MASTER", font=("Consolas", 28, "bold"), 
                    text_color=JARVIS_CYAN).pack(side="left")
        ctk.CTkLabel(title_frame, text="Mission Control", font=("Arial", 14), 
                    text_color=JARVIS_TEXT_DIM).pack(side="left", padx=(10, 0))
        
        # Boutons header
        btn_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")
        
        refresh_btn = ctk.CTkButton(btn_frame, text="🔄", width=40, height=40,
                                    fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_BORDER,
                                    text_color=JARVIS_CYAN, font=("Arial", 16),
                                    corner_radius=8, command=self._refresh_tasks_dashboard)
        refresh_btn.pack(side="left", padx=(0, 5))
        
        close_btn = ctk.CTkButton(btn_frame, text="✕", width=40, height=40,
                                 fg_color=JARVIS_CYAN_DIM, hover_color=JARVIS_RED,
                                 text_color=JARVIS_TEXT, font=("Arial", 16),
                                 corner_radius=8, command=self._hide_tasks_dashboard)
        close_btn.pack(side="left")
        
        # Contenu principal
        main_container = ctk.CTkFrame(self.tasks_dashboard_window, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Frame scrollable pour les tâches
        self.tasks_scrollable_frame = ctk.CTkScrollableFrame(
            main_container,
            fg_color=JARVIS_PANEL_BG,
            corner_radius=15,
            border_width=1,
            border_color=JARVIS_BORDER
        )
        self.tasks_scrollable_frame.grid(row=0, column=0, sticky="nsew")
        self.tasks_scrollable_frame.grid_columnconfigure(0, weight=1)
        
        # Charger les tâches initiales
        self._refresh_tasks_dashboard()
    
    def _hide_tasks_dashboard(self):
        """Masque la fenêtre Task Master (sans la détruire)"""
        if self.tasks_dashboard_window:
            self.tasks_dashboard_window.withdraw()
    
    def _show_tasks_dashboard(self):
        """Affiche la fenêtre Task Master"""
        if self.tasks_dashboard_window is None:
            self._create_tasks_dashboard()
        self.tasks_dashboard_window.deiconify()
        self.tasks_dashboard_window.lift()
        self._refresh_tasks_dashboard()
    
    def _refresh_tasks_dashboard(self):
        """Rafraîchit l'affichage des tâches depuis le TaskManager"""
        try:
            from modules.task_manager import get_task_manager
            task_mgr = get_task_manager()
            tasks = task_mgr.list_tasks()
            self._update_tasks_dashboard({"tasks": tasks})
        except Exception as e:
            print(f"Erreur lors du rafraîchissement des tâches: {e}")
    
    def _update_tasks_dashboard(self, data: Dict[str, Any]):
        """
        Met à jour l'affichage du dashboard avec les nouvelles tâches.
        data doit contenir {"tasks": [...]}
        """
        if not self.tasks_scrollable_frame:
            return
        
        try:
            tasks = data.get("tasks", [])
            
            # Supprimer les anciens widgets
            for widget in self.tasks_scrollable_frame.winfo_children():
                widget.destroy()
            self.tasks_widgets.clear()
            
            if not tasks:
                # Message vide
                empty_frame = ctk.CTkFrame(self.tasks_scrollable_frame, fg_color="transparent")
                empty_frame.pack(fill="x", padx=20, pady=50)
                
                ctk.CTkLabel(empty_frame, text="📋", font=("Arial", 48), 
                            text_color=JARVIS_TEXT_DIM).pack(pady=(0, 10))
                ctk.CTkLabel(empty_frame, text="Aucune tâche", 
                            font=("Arial", 18, "bold"), 
                            text_color=JARVIS_TEXT_DIM).pack()
                ctk.CTkLabel(empty_frame, text="Créez une tâche avec Cypher", 
                            font=("Arial", 12), 
                            text_color=JARVIS_TEXT_DIM).pack()
                return
            
            # Afficher chaque tâche
            for task in tasks:
                self._create_task_widget(task)
        
        except Exception as e:
            print(f"Erreur lors de la mise à jour du dashboard: {e}")
    
    def _create_task_widget(self, task: Dict[str, Any]):
        """Crée un widget pour une tâche"""
        task_id = task.get('id', '')
        
        # Couleurs selon priorité
        priority_colors = {
            "critical": JARVIS_RED,
            "high": JARVIS_ORANGE,
            "medium": JARVIS_YELLOW,
            "low": JARVIS_GREEN
        }
        priority_color = priority_colors.get(task.get('priority', 'medium'), JARVIS_YELLOW)
        
        # Frame de la tâche
        task_frame = ctk.CTkFrame(
            self.tasks_scrollable_frame,
            fg_color=JARVIS_CYAN_DIM,
            corner_radius=12,
            border_width=1,
            border_color=priority_color
        )
        task_frame.pack(fill="x", padx=10, pady=8)
        task_frame.grid_columnconfigure(1, weight=1)
        
        # Colonne gauche : Icônes et priorité
        left_col = ctk.CTkFrame(task_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="n", padx=(15, 10), pady=12)
        
        # Icône priorité
        priority_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }
        priority_icon = priority_icons.get(task.get('priority', 'medium'), "⚪")
        ctk.CTkLabel(left_col, text=priority_icon, font=("Arial", 20)).pack()
        
        # Icône récurrence
        if task.get('recurrence'):
            recur_icons = {
                "daily": "🔄",
                "weekly": "🔄",
                "monthly": "🔄",
                "yearly": "🔄"
            }
            recur_icon = recur_icons.get(task.get('recurrence'), "🔄")
            ctk.CTkLabel(left_col, text=recur_icon, font=("Arial", 16), 
                        text_color=JARVIS_CYAN).pack(pady=(5, 0))
        
        # Colonne centrale : Contenu
        center_col = ctk.CTkFrame(task_frame, fg_color="transparent")
        center_col.grid(row=0, column=1, sticky="ew", padx=10, pady=12)
        center_col.grid_columnconfigure(0, weight=1)
        
        # Titre
        status_icons = {
            "todo": "⏳",
            "in_progress": "🔄",
            "done": "✅"
        }
        status_icon = status_icons.get(task.get('status', 'todo'), "⏳")
        
        title_frame = ctk.CTkFrame(center_col, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 5))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text=f"{status_icon} {task.get('title', 'Sans titre')}",
            font=("Arial", 16, "bold"),
            text_color=JARVIS_TEXT,
            anchor="w"
        )
        title_label.pack(side="left")
        
        # Description
        if task.get('description'):
            desc_label = ctk.CTkLabel(
                center_col,
                text=task.get('description', ''),
                font=("Arial", 12),
                text_color=JARVIS_TEXT_DIM,
                anchor="w",
                wraplength=600
            )
            desc_label.pack(fill="x", pady=(0, 5))
        
        # Métadonnées (date, tags)
        meta_frame = ctk.CTkFrame(center_col, fg_color="transparent")
        meta_frame.pack(fill="x")
        
        # Date d'échéance
        if task.get('due_date'):
            from datetime import datetime
            try:
                due_dt = datetime.strptime(task['due_date'], "%Y-%m-%d %H:%M")
                now = datetime.now()
                if due_dt < now and task.get('status') != 'done':
                    overdue_text = " [EN RETARD]"
                    overdue_color = JARVIS_RED
                else:
                    overdue_text = ""
                    overdue_color = JARVIS_TEXT_DIM
            except:
                overdue_text = ""
                overdue_color = JARVIS_TEXT_DIM
            
            date_label = ctk.CTkLabel(
                meta_frame,
                text=f"📅 {task.get('due_date', '')}{overdue_text}",
                font=("Arial", 11),
                text_color=overdue_color
            )
            date_label.pack(side="left", padx=(0, 10))
        
        # Tags
        if task.get('tags'):
            tags_text = " ".join([f"#{tag}" for tag in task.get('tags', [])])
            tags_label = ctk.CTkLabel(
                meta_frame,
                text=tags_text,
                font=("Arial", 10),
                text_color=JARVIS_CYAN
            )
            tags_label.pack(side="left")
        
        # ID (petit, discret)
        id_label = ctk.CTkLabel(
            center_col,
            text=f"ID: {task_id[:8]}...",
            font=("Consolas", 9),
            text_color=JARVIS_TEXT_DIM
        )
        id_label.pack(anchor="e", pady=(5, 0))
        
        # Stocker le widget
        self.tasks_widgets[task_id] = task_frame


# Pour tests sans le main.py
if __name__ == "__main__":
    test_queue = queue.Queue()
    app = CypherGUI(test_queue)
    app.mainloop()
