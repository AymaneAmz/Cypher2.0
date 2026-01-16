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

# Couleurs CYPHER - Fond noir + Bleu doux
CYPHER_BG = "#000000"  # Fond noir pur
CYPHER_PANEL_BG = "#0a0a0a"  # Panneaux légèrement plus clairs
CYPHER_NEON_BLUE = "#00bfff"  # Bleu cyan doux (Sky Blue)
CYPHER_NEON_BLUE_BRIGHT = "#40d9ff"  # Bleu cyan plus clair mais doux
CYPHER_NEON_BLUE_DIM = "#0080cc"  # Bleu atténué
CYPHER_NEON_BLUE_DARK = "#002244"  # Bleu foncé pour backgrounds
CYPHER_TEXT = "#ffffff"  # Texte blanc
CYPHER_TEXT_DIM = "#888888"  # Texte gris
CYPHER_BORDER = "#1a1a1a"  # Bordures subtiles
CYPHER_GREEN = "#00ff88"  # Vert néon
CYPHER_ORANGE = "#ff6b35"  # Orange
CYPHER_RED = "#ff3333"  # Rouge
CYPHER_PURPLE = "#a855f7"  # Violet
CYPHER_YELLOW = "#ffff00"  # Jaune néon

# Alias pour compatibilité
JARVIS_BG = CYPHER_BG
JARVIS_PANEL_BG = CYPHER_PANEL_BG
JARVIS_CYAN = CYPHER_NEON_BLUE
JARVIS_CYAN_DIM = CYPHER_NEON_BLUE_DARK
JARVIS_TEXT = CYPHER_TEXT
JARVIS_TEXT_DIM = CYPHER_TEXT_DIM
JARVIS_BORDER = CYPHER_BORDER
JARVIS_GREEN = CYPHER_GREEN
JARVIS_ORANGE = CYPHER_ORANGE
JARVIS_RED = CYPHER_RED
JARVIS_PURPLE = CYPHER_PURPLE
JARVIS_YELLOW = CYPHER_YELLOW

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
        self.is_sleeping = True  # Au démarrage, Cypher est en veille
        self.animation_angle = 0
        self.wave_offset = 0
        self.current_radius = 150
        self.target_radius = 150
        
        # Transitions d'état (interpolation)
        self.current_status_color = CYPHER_NEON_BLUE
        self.target_status_color = CYPHER_NEON_BLUE
        self.current_status_text = "Online"
        self.target_status_text = "Online"
        
        # Animation de transition pour les onglets
        self.tab_transition_active = False
        
        # Données
        self.message_widgets = []
        self.conversation_history = deque(maxlen=100)  # Historique limité
        self.commands_count = 0
        self.session_start = datetime.now()
        self._weather_images = {}
        
        # Système de notifications
        self.notifications = deque(maxlen=10)  # Historique des notifications
        self.notification_widgets = []  # Widgets de notifications actives
        self.notification_container = None  # Container pour les notifications toast
        
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
        
        # Dashboard Analytics
        self.analytics_window = None
        self.analytics_tabs = None
        
        # Workspace multi-panneaux
        self.workspace_mode = False
        self.workspace_tabs = None
        self.left_tabview = None  # Onglets pour le panneau gauche
        
        # Mode immersif
        self.immersive_mode = False
        self.original_geometry = None
        
        # Visualisations de données
        self.visualizations_window = None
        self.timeline_canvas = None
        self.mindmap_canvas = None
        
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
                    elif content == "sleeping":
                        self.is_sleeping = True
                        self._update_sleep_button()
                    elif content == "awake":
                        self.is_sleeping = False
                        self._update_sleep_button()
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
        
        # Container pour notifications toast (overlay en haut à droite)
        self.notification_container = ctk.CTkFrame(self, fg_color="transparent")
        self.notification_container.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=80)
        
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
                                   text_color=CYPHER_NEON_BLUE)
        title_label.pack(side="left", padx=(0, 15))
        
        status_frame = ctk.CTkFrame(left_frame, fg_color=JARVIS_CYAN_DIM, corner_radius=15,
                                    border_width=1, border_color=JARVIS_CYAN)
        status_frame.pack(side="left")
        
        self.status_dot = ctk.CTkLabel(status_frame, text="●", font=("Arial", 12), 
                                      text_color=CYPHER_NEON_BLUE)
        self.status_dot.pack(side="left", padx=(12, 6), pady=6)
        
        self.status_header_text = ctk.CTkLabel(status_frame, text="Online", 
                                              font=("Arial", 13, "bold"), 
                                              text_color=CYPHER_NEON_BLUE)
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
        
        # Les boutons sont maintenant dans la zone centrale, on retire cette section

    def _build_left_panel(self):
        left_container = ctk.CTkFrame(self, fg_color="transparent")
        left_container.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=10)
        left_container.grid_rowconfigure(0, weight=1)
        left_container.grid_columnconfigure(0, weight=1)
        
        # Système d'onglets pour le panneau gauche (Workspace)
        self.left_tabview = ctk.CTkTabview(left_container, 
                                          fg_color=CYPHER_PANEL_BG,
                                          border_width=1,
                                          border_color=CYPHER_BORDER,
                                          corner_radius=15)
        self.left_tabview.pack(fill="both", expand=True)
        
        # Onglet 1: Dashboard (vue par défaut)
        dashboard_tab = self.left_tabview.add("📊 Dashboard")
        self._build_dashboard_tab(dashboard_tab)
        
        # Onglet 2: Système
        system_tab = self.left_tabview.add("⚙ Système")
        self._build_system_tab(system_tab)
        
        # Onglet 3: Terminal (nouveau)
        terminal_tab = self.left_tabview.add("💻 Terminal")
        self._build_terminal_tab(terminal_tab)

    def _build_dashboard_tab(self, parent):
        """Onglet Dashboard avec toutes les infos principales"""
        # Scrollable pour contenir tous les widgets
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Weather Widget
        self._build_weather_widget(scroll_frame)
        
        # Camera Widget
        self._build_camera_widget(scroll_frame)
    
    def _build_system_tab(self, parent):
        """Onglet Système avec détails avancés"""
        # Scrollable frame pour le contenu
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # System Stats détaillés
        self._build_system_stats(scroll_frame)
        
        # Performance détaillée
        self._build_stats_dashboard(scroll_frame)
        
        # Informations système supplémentaires
        info_frame = ctk.CTkFrame(scroll_frame, fg_color=CYPHER_PANEL_BG, 
                                 corner_radius=20, border_width=1, 
                                 border_color=CYPHER_BORDER)
        info_frame.pack(fill="x", pady=(0, 15))
        
        header = ctk.CTkFrame(info_frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(15, 10))
        
        ctk.CTkLabel(header, text="ℹ", font=("Arial", 28), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="Informations Système", font=("Arial", 22, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left")
        
        content = ctk.CTkFrame(info_frame, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=(0, 15))
        
        # Infos système
        try:
            import platform
            sys_info = [
                ("OS", platform.system() + " " + platform.release()),
                ("Processeur", platform.processor()[:50] if platform.processor() else "N/A"),
                ("Python", platform.python_version()),
            ]
            
            for label, value in sys_info:
                row = ctk.CTkFrame(content, fg_color="transparent")
                row.pack(fill="x", pady=5)
                
                ctk.CTkLabel(row, text=f"{label}:", font=("Arial", 14, "bold"), 
                            text_color=CYPHER_TEXT_DIM).pack(side="left")
                ctk.CTkLabel(row, text=value, font=("Consolas", 12), 
                            text_color=CYPHER_TEXT).pack(side="left", padx=(10, 0))
        except:
            pass
    
    def _build_terminal_tab(self, parent):
        """Onglet Terminal interactif"""
        # Header
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(header, text="💻", font=("Arial", 28), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(header, text="Terminal", font=("Arial", 22, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left")
        
        # Zone de terminal
        terminal_frame = ctk.CTkFrame(parent, fg_color=CYPHER_BG, 
                                     corner_radius=12, border_width=1, 
                                     border_color=CYPHER_BORDER)
        terminal_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Scrollbar pour le terminal
        scrollbar = ctk.CTkScrollbar(terminal_frame)
        scrollbar.pack(side="right", fill="y")
        
        # Text widget pour le terminal (style console)
        self.terminal_text = tk.Text(
            terminal_frame,
            bg=CYPHER_BG,
            fg=CYPHER_NEON_BLUE,
            font=("Consolas", 11),
            wrap="word",
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=0,
            insertbackground=CYPHER_NEON_BLUE
        )
        self.terminal_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.configure(command=self.terminal_text.yview)
        
        # Input pour commandes
        input_frame = ctk.CTkFrame(parent, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.terminal_entry = ctk.CTkEntry(input_frame, 
                                          placeholder_text="Entrez une commande...",
                                          fg_color=CYPHER_NEON_BLUE_DARK, 
                                          border_width=0,
                                          text_color=CYPHER_TEXT, 
                                          height=35, 
                                          corner_radius=15, 
                                          font=("Consolas", 12))
        self.terminal_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.terminal_entry.bind("<Return>", lambda e: self._execute_terminal_command())
        
        exec_btn = ctk.CTkButton(input_frame, text="▶", width=50, height=35,
                                fg_color=CYPHER_NEON_BLUE, 
                                hover_color=CYPHER_NEON_BLUE_BRIGHT,
                                text_color=CYPHER_BG, 
                                font=("Arial", 16, "bold"),
                                corner_radius=15, 
                                command=self._execute_terminal_command)
        exec_btn.pack(side="left")
        
        # Message initial
        self._add_terminal_output("Cypher Terminal v1.0", "info")
        self._add_terminal_output("Tapez 'help' pour voir les commandes disponibles", "info")
        self._add_terminal_output("", "info")
    
    def _add_terminal_output(self, text: str, output_type: str = "info"):
        """Ajoute du texte au terminal avec couleur"""
        if not hasattr(self, 'terminal_text'):
            return
        
        colors = {
            "info": CYPHER_NEON_BLUE,
            "success": CYPHER_GREEN,
            "error": CYPHER_RED,
            "warning": CYPHER_ORANGE
        }
        color = colors.get(output_type, CYPHER_NEON_BLUE)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        prompt = f"[{timestamp}] " if output_type != "prompt" else ""
        
        self.terminal_text.insert("end", f"{prompt}{text}\n")
        
        # Colorer la ligne
        start_line = self.terminal_text.index("end-2l")
        end_line = self.terminal_text.index("end-1l")
        tag_name = f"term_{len(self.terminal_text.get('1.0', 'end').split('\n'))}"
        self.terminal_text.tag_add(tag_name, start_line, end_line)
        self.terminal_text.tag_config(tag_name, foreground=color)
        
        # Scroll automatique
        self.terminal_text.see("end")
    
    def _execute_terminal_command(self):
        """Exécute une commande dans le terminal"""
        if not hasattr(self, 'terminal_entry'):
            return
        
        command = self.terminal_entry.get().strip()
        if not command:
            return
        
        # Afficher la commande
        self._add_terminal_output(f"> {command}", "prompt")
        self.terminal_entry.delete(0, "end")
        
        # Commandes internes
        if command.lower() == "help":
            self._add_terminal_output("Commandes disponibles:", "info")
            self._add_terminal_output("  help - Affiche cette aide", "info")
            self._add_terminal_output("  clear - Efface le terminal", "info")
            self._add_terminal_output("  stats - Affiche les stats système", "info")
            self._add_terminal_output("  tasks - Ouvre le Task Master", "info")
            self._add_terminal_output("  analytics - Ouvre le Dashboard Analytics", "info")
        elif command.lower() == "clear":
            self.terminal_text.delete("1.0", "end")
            self._add_terminal_output("Terminal effacé", "success")
        elif command.lower() == "stats":
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                self._add_terminal_output(f"CPU: {cpu:.1f}%", "info")
                self._add_terminal_output(f"RAM: {ram.percent:.1f}% ({ram.used / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB)", "info")
            except Exception as e:
                self._add_terminal_output(f"Erreur: {e}", "error")
        elif command.lower() == "tasks":
            self._show_tasks_dashboard()
            self._add_terminal_output("Task Master ouvert", "success")
        elif command.lower() == "analytics":
            self._show_analytics_dashboard()
            self._add_terminal_output("Dashboard Analytics ouvert", "success")
        else:
            self._add_terminal_output(f"Commande inconnue: '{command}'. Tapez 'help' pour l'aide.", "error")

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
        
        self.orb_canvas = Canvas(orb_frame, width=500, height=500, bg=CYPHER_BG, 
                                 highlightthickness=0)
        self.orb_canvas.pack(expand=True)
        
        # Title and status améliorés
        title_frame = ctk.CTkFrame(center, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="s", pady=(0, 160))
        
        self.jarvis_title = ctk.CTkLabel(title_frame, text="C.Y.P.H.E.R", 
                                         font=("Consolas", 56, "bold"), 
                                         text_color=CYPHER_NEON_BLUE)
        self.jarvis_title.pack()
        
        status_container = ctk.CTkFrame(title_frame, fg_color=CYPHER_NEON_BLUE_DARK, 
                                       corner_radius=18, border_width=2, 
                                       border_color=CYPHER_NEON_BLUE)
        status_container.pack(pady=(60, 0))
        
        status_inner = ctk.CTkFrame(status_container, fg_color="transparent")
        status_inner.pack(padx=20, pady=10)
        
        self.listening_dot = ctk.CTkLabel(status_inner, text="●", font=("Arial", 12), 
                                         text_color=CYPHER_NEON_BLUE)
        self.listening_dot.pack(side="left", padx=(0, 10))
        
        self.status_text = ctk.CTkLabel(status_inner, text="Listening for wake word...", 
                                       font=("Arial", 22, "bold"), 
                                       text_color=JARVIS_CYAN)
        self.status_text.pack(side="left")
        
        # Contrôles interactifs - BOUTONS EN BAS DU PANNEAU CENTRAL
        # Créer un frame pour les boutons en bas avec 50px de marge
        controls_frame = ctk.CTkFrame(center, fg_color="transparent")
        controls_frame.grid(row=1, column=0, sticky="s", pady=(0, 50))
        
        # Boutons de contrôle - UNE SEULE LIGNE CENTRÉE
        btn_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        btn_frame.pack()
        
        # Style de base pour tous les boutons (fond transparent, bordure)
        base_btn_style = {
            "width": 50,
            "height": 50,
            "corner_radius": 25,
            "font": ("Arial", 20),
            "fg_color": "transparent",  # Fond transparent
            "hover_color": JARVIS_BORDER,  # Hover légèrement visible
            "border_width": 2,  # Contour visible
        }
        
        # Bouton Sleep/Wake - VERT (bascule entre veille et réveil)
        sleep_wake_style = base_btn_style.copy()
        sleep_wake_style["text_color"] = JARVIS_GREEN
        sleep_wake_style["border_color"] = JARVIS_GREEN
        self.sleep_wake_btn = ctk.CTkButton(
            btn_frame, 
            text="⏻",  # Icône power pour réveiller (Cypher est en veille au démarrage)
            command=self._toggle_sleep_wake,
            **sleep_wake_style
        )
        self.sleep_wake_btn.pack(side="left", padx=10)
        
        # Bouton Analytics - BLEU CYAN
        analytics_style = base_btn_style.copy()
        analytics_style["text_color"] = JARVIS_CYAN
        analytics_style["border_color"] = JARVIS_CYAN
        analytics_btn = ctk.CTkButton(
            btn_frame, 
            text="📈", 
            command=self._show_analytics_dashboard,
            **analytics_style
        )
        analytics_btn.pack(side="left", padx=10)
        
        # Bouton Task Master - VIOLET
        tasks_style = base_btn_style.copy()
        tasks_style["text_color"] = JARVIS_PURPLE
        tasks_style["border_color"] = JARVIS_PURPLE
        tasks_btn = ctk.CTkButton(
            btn_frame, 
            text="✓", 
            command=self._show_tasks_dashboard,
            **tasks_style
        )
        tasks_btn.pack(side="left", padx=10)
        
        # Bouton Visualisations - ORANGE
        viz_style = base_btn_style.copy()
        viz_style["text_color"] = JARVIS_ORANGE
        viz_style["border_color"] = JARVIS_ORANGE
        viz_btn = ctk.CTkButton(
            btn_frame, 
            text="📊", 
            command=self._show_visualizations,
            **viz_style
        )
        viz_btn.pack(side="left", padx=10)
        
        # Bouton Mode Immersif - JAUNE
        immersive_style = base_btn_style.copy()
        immersive_style["text_color"] = JARVIS_YELLOW
        immersive_style["border_color"] = JARVIS_YELLOW
        immersive_btn = ctk.CTkButton(
            btn_frame, 
            text="⛶", 
            command=self._toggle_immersive_mode,
            **immersive_style
        )
        immersive_btn.pack(side="left", padx=10)

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
        
        # Le bouton Task Master est maintenant dans le header, on le retire d'ici
        
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
        
        # Déterminer l'état et les couleurs (BLEU NÉON)
        if self.is_interrupted:
            ring_color = CYPHER_RED
            inner_color = "#ff6666"
            glow_color = "#ff0000"
            pulse_base = math.sin(self.animation_angle * 2) * 8
            self.animation_angle += 0.25
            audio_modifier = 0
        elif self.is_processing:
            ring_color = CYPHER_ORANGE
            inner_color = "#ffb833"
            glow_color = "#ff8800"
            pulse_base = math.sin(self.animation_angle * 1.5) * 12
            self.animation_angle += 0.2
            audio_modifier = self.audio_level_smooth * 8
        elif self.is_speaking:
            ring_color = CYPHER_NEON_BLUE
            inner_color = CYPHER_NEON_BLUE_BRIGHT
            glow_color = CYPHER_NEON_BLUE
            pulse_base = math.sin(self.animation_angle * 1.0) * 15
            self.animation_angle += 0.15
            audio_modifier = self.audio_level_smooth * 10
        elif self.is_listening:
            ring_color = CYPHER_NEON_BLUE
            inner_color = CYPHER_NEON_BLUE_BRIGHT
            glow_color = CYPHER_NEON_BLUE
            pulse_base = math.sin(self.animation_angle * 0.6) * 6
            # Réaction au volume quand l'utilisateur parle
            audio_modifier = self.audio_level_smooth * 25
            self.animation_angle += 0.1
        else:  # IDLE
            ring_color = CYPHER_NEON_BLUE_DIM
            inner_color = CYPHER_NEON_BLUE
            glow_color = CYPHER_NEON_BLUE_DARK
            pulse_base = 0
            audio_modifier = 0
            self.animation_angle = 0
        
        # Base radius avec pulse et réaction audio
        base_radius = 150 + pulse_base + audio_modifier
        
        # UN SEUL anneau épais - BLEU NÉON
        ring_width = 8 + int(self.audio_level_smooth * 4)  # Anneau plus épais
        self.orb_canvas.create_oval(
            cx - base_radius, cy - base_radius,
            cx + base_radius, cy + base_radius,
            outline=ring_color, width=ring_width
        )
        
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
        
        # Grille avec style néon
        for i in range(5):
            y = h - (i * h // 4)
            canvas.create_line(30, y, w - 10, y, fill=CYPHER_BORDER, width=1)
            canvas.create_text(25, y, text=f"{100 - i * 25}%", 
                             fill=CYPHER_TEXT_DIM, font=("Arial", 8), anchor="e")
        
        # Graphiques avec BLEU NÉON
        max_samples = len(self.cpu_history)
        if max_samples < 2:
            return
        
        step_x = (w - 40) / max(max_samples - 1, 1)
        
        # CPU line - BLEU NÉON avec glow
        cpu_points = []
        for i, val in enumerate(self.cpu_history):
            x = 30 + i * step_x
            y = h - 10 - (val / 100) * (h - 20)
            cpu_points.append((x, y))
        
        if len(cpu_points) > 1:
            # Ligne principale avec glow (effet néon)
            for i in range(len(cpu_points) - 1):
                # Glow (ligne plus épaisse en dessous)
                canvas.create_line(cpu_points[i][0], cpu_points[i][1],
                                 cpu_points[i + 1][0], cpu_points[i + 1][1],
                                 fill=CYPHER_NEON_BLUE_DARK, width=4)
                # Ligne principale néon
                canvas.create_line(cpu_points[i][0], cpu_points[i][1],
                                 cpu_points[i + 1][0], cpu_points[i + 1][1],
                                 fill=CYPHER_NEON_BLUE, width=2)
        
        # RAM line - VERT NÉON
        ram_points = []
        for i, val in enumerate(self.ram_history):
            x = 30 + i * step_x
            y = h - 10 - (val / 100) * (h - 20)
            ram_points.append((x, y))
        
        if len(ram_points) > 1:
            for i in range(len(ram_points) - 1):
                # Glow
                canvas.create_line(ram_points[i][0], ram_points[i][1],
                                 ram_points[i + 1][0], ram_points[i + 1][1],
                                 fill="#003300", width=4)
                # Ligne principale
                canvas.create_line(ram_points[i][0], ram_points[i][1],
                                 ram_points[i + 1][0], ram_points[i + 1][1],
                                 fill=CYPHER_GREEN, width=2)

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
            
            # Rafraîchir les graphiques analytics si la fenêtre est ouverte
            if self.analytics_window and self.analytics_window.winfo_viewable():
                if hasattr(self, 'analytics_cpu_canvas'):
                    self._draw_analytics_cpu_graph()
                if hasattr(self, 'analytics_ram_canvas'):
                    self._draw_analytics_ram_graph()
            
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
            self._animate_status_transition("Listening...", CYPHER_NEON_BLUE, "Active")
        else:
            if not self.is_speaking and not self.is_processing:
                self.is_interrupted = False
            if not self.is_speaking and not self.is_processing:
                self._animate_status_transition("Listening for wake word...", CYPHER_NEON_BLUE, "Online")

    def set_speaking(self, state: bool):
        self.is_speaking = state
        if state:
            self.is_interrupted = False
            self.is_processing = False
            self._animate_status_transition("Speaking...", CYPHER_ORANGE, "Speaking")
        else:
            if not self.is_listening and not self.is_processing:
                self._animate_status_transition("Listening for wake word...", CYPHER_NEON_BLUE, "Online")

    def set_interrupted(self):
        self.is_listening = False
        self.is_speaking = False
        self.is_processing = False
        self.is_interrupted = True
        
        self._animate_status_transition("⛔ Interrupted !", CYPHER_RED, "Interrupted")

    def set_processing(self, state: bool):
        self.is_processing = state
        if state:
            self._animate_status_transition("⚙ Processing...", CYPHER_ORANGE, "Processing")
        else:
            if not self.is_speaking and not self.is_listening:
                self._animate_status_transition("Listening for wake word...", CYPHER_NEON_BLUE, "Online")

    def set_reconnecting(self, state: bool):
        self.is_reconnecting = state
        if state:
            self._animate_status_transition("🔄 Reconnecting...", CYPHER_TEXT_DIM, "Reconnecting")
        else:
            self._animate_status_transition("Listening for wake word...", CYPHER_NEON_BLUE, "Online")
    
    # ========================================
    # ANIMATIONS ET TRANSITIONS
    # ========================================
    
    def _animate_status_transition(self, text: str, color: str, header_text: str):
        """Anime la transition de statut avec interpolation de couleur"""
        self.target_status_text = text
        self.target_status_color = color
        self.target_header_text = header_text
        
        # Interpolation de couleur fluide
        def interpolate_color(start_color, end_color, progress):
            """Interpole entre deux couleurs hex"""
            def hex_to_rgb(hex_color):
                hex_color = hex_color.lstrip('#')
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            
            def rgb_to_hex(rgb):
                return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            
            start_rgb = hex_to_rgb(start_color)
            end_rgb = hex_to_rgb(end_color)
            
            new_rgb = tuple(
                int(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * progress)
                for i in range(3)
            )
            return rgb_to_hex(new_rgb)
        
        # Animation en plusieurs étapes
        steps = 10
        current_step = [0]
        
        def animate_step():
            if current_step[0] < steps:
                progress = current_step[0] / steps
                # Easing function (ease-out)
                eased = 1 - (1 - progress) ** 3
                
                interp_color = interpolate_color(self.current_status_color, self.target_status_color, eased)
                
                self.status_text.configure(text=self.target_status_text, text_color=interp_color)
                self.listening_dot.configure(text_color=interp_color)
                self.status_header_text.configure(text=self.target_header_text, text_color=interp_color)
                
                self.current_status_color = interp_color
                current_step[0] += 1
                self.after(20, animate_step)
            else:
                # Finaliser
                self.status_text.configure(text=self.target_status_text, text_color=self.target_status_color)
                self.listening_dot.configure(text_color=self.target_status_color)
                self.status_header_text.configure(text=self.target_header_text, text_color=self.target_status_color)
                self.current_status_color = self.target_status_color
        
        animate_step()
    
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
        self.agent_vision_window.focus_force()
        # Forcer le premier plan temporairement
        self.agent_vision_window.attributes('-topmost', True)
        self.after(100, lambda: self.agent_vision_window.attributes('-topmost', False))
    
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
        self.tasks_dashboard_window.focus_force()
        # Forcer le premier plan temporairement
        self.tasks_dashboard_window.attributes('-topmost', True)
        self.after(100, lambda: self.tasks_dashboard_window.attributes('-topmost', False))
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
    
    # ========================================
    # SYSTÈME DE NOTIFICATIONS TOAST
    # ========================================
    
    def show_notification(self, title: str, message: str, notification_type: str = "info", duration: int = 3000):
        """
        Affiche une notification toast avec style néon
        
        Args:
            title: Titre de la notification
            message: Message de la notification
            notification_type: "info", "success", "warning", "error"
            duration: Durée d'affichage en ms
        """
        if not self.notification_container:
            return
        
        # Couleurs selon le type (BLEU NÉON par défaut)
        colors = {
            "info": CYPHER_NEON_BLUE,
            "success": CYPHER_GREEN,
            "warning": CYPHER_ORANGE,
            "error": CYPHER_RED
        }
        color = colors.get(notification_type, CYPHER_NEON_BLUE)
        
        # Créer le widget de notification
        notif_frame = ctk.CTkFrame(
            self.notification_container,
            fg_color=CYPHER_PANEL_BG,
            corner_radius=12,
            border_width=2,
            border_color=color,
            width=350
        )
        notif_frame.pack(fill="x", padx=5, pady=5)
        
        # Header avec titre et icône
        header = ctk.CTkFrame(notif_frame, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 5))
        
        # Icône selon le type
        icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✗"
        }
        icon = icons.get(notification_type, "ℹ")
        
        ctk.CTkLabel(header, text=icon, font=("Arial", 16), 
                    text_color=color).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text=title, font=("Arial", 14, "bold"), 
                    text_color=CYPHER_TEXT).pack(side="left", fill="x", expand=True)
        
        # Message
        msg_label = ctk.CTkLabel(notif_frame, text=message, font=("Arial", 12), 
                                text_color=CYPHER_TEXT_DIM, wraplength=320,
                                justify="left")
        msg_label.pack(fill="x", padx=12, pady=(0, 10))
        
        # Ajouter à la liste
        self.notification_widgets.append(notif_frame)
        
        # Animation d'entrée (fade in + slide)
        notif_frame.pack_forget()
        
        def animate_in():
            try:
                if not notif_frame.winfo_exists():
                    return
                # Slide in depuis la droite
                notif_frame.pack(fill="x", padx=5, pady=5)
            except:
                pass
        
        self.after(50, animate_in)
        
        # Auto-dismiss après duration
        def dismiss():
            if notif_frame.winfo_exists():
                # Animation de sortie (fade out + slide)
                opacity_steps = [1.0, 0.8, 0.6, 0.4, 0.2, 0.0]
                step = [0]
                
                def animate_out():
                    try:
                        if not notif_frame.winfo_exists() or step[0] >= len(opacity_steps):
                            notif_frame.destroy()
                            if notif_frame in self.notification_widgets:
                                self.notification_widgets.remove(notif_frame)
                            return
                        
                        # Fade out progressif
                        step[0] += 1
                        self.after(30, animate_out)
                    except:
                        if notif_frame in self.notification_widgets:
                            self.notification_widgets.remove(notif_frame)
                
                animate_out()
        
        self.after(duration, dismiss)
        
        # Stocker dans l'historique
        self.notifications.append({
            "title": title,
            "message": message,
            "type": notification_type,
            "timestamp": datetime.now()
        })
    
    # ========================================
    # DASHBOARD ANALYTICS AVANCÉ
    # ========================================
    
    def _create_analytics_dashboard(self):
        """Crée la fenêtre du dashboard analytics complet"""
        if self.analytics_window is not None:
            return
        
        self.analytics_window = ctk.CTkToplevel(self)
        self.analytics_window.title("Analytics Dashboard - Cypher")
        self.analytics_window.geometry("1400x900")
        self.analytics_window.configure(fg_color=CYPHER_BG)
        
        # Empêcher la fermeture complète
        self.analytics_window.protocol("WM_DELETE_WINDOW", self._hide_analytics_dashboard)
        
        # Header
        header = ctk.CTkFrame(self.analytics_window, fg_color=CYPHER_PANEL_BG, 
                             corner_radius=0, border_width=0)
        header.pack(fill="x", padx=0, pady=0)
        
        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=15)
        header_inner.grid_columnconfigure(1, weight=1)
        
        # Logo et titre
        title_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(title_frame, text="📈", font=("Arial", 32, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_frame, text="ANALYTICS DASHBOARD", 
                    font=("Consolas", 28, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left")
        
        # Boutons header
        btn_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")
        
        refresh_btn = ctk.CTkButton(btn_frame, text="🔄", width=40, height=40,
                                    fg_color=CYPHER_NEON_BLUE_DARK, 
                                    hover_color=CYPHER_BORDER,
                                    text_color=CYPHER_NEON_BLUE, 
                                    font=("Arial", 16),
                                    corner_radius=8, 
                                    command=self._refresh_analytics)
        refresh_btn.pack(side="left", padx=(0, 5))
        
        close_btn = ctk.CTkButton(btn_frame, text="✕", width=40, height=40,
                                 fg_color=CYPHER_NEON_BLUE_DARK, 
                                 hover_color=CYPHER_RED,
                                 text_color=CYPHER_TEXT, 
                                 font=("Arial", 16),
                                 corner_radius=8, 
                                 command=self._hide_analytics_dashboard)
        close_btn.pack(side="left")
        
        # Contenu principal avec onglets
        main_container = ctk.CTkFrame(self.analytics_window, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Système d'onglets
        self.analytics_tabs = ctk.CTkTabview(main_container, 
                                            fg_color=CYPHER_PANEL_BG,
                                            border_width=1,
                                            border_color=CYPHER_BORDER,
                                            corner_radius=15)
        self.analytics_tabs.pack(fill="both", expand=True)
        
        # Onglet 1: Performance Système
        perf_tab = self.analytics_tabs.add("Performance")
        self._build_performance_tab(perf_tab)
        
        # Onglet 2: Productivité
        prod_tab = self.analytics_tabs.add("Productivité")
        self._build_productivity_tab(prod_tab)
        
        # Onglet 3: Interactions
        inter_tab = self.analytics_tabs.add("Interactions")
        self._build_interactions_tab(inter_tab)
    
    def _build_performance_tab(self, parent):
        """Construit l'onglet Performance avec graphiques système"""
        # Graphiques CPU/RAM/Disk en temps réel
        graphs_frame = ctk.CTkFrame(parent, fg_color="transparent")
        graphs_frame.pack(fill="both", expand=True, padx=10, pady=10)
        graphs_frame.grid_columnconfigure((0, 1), weight=1)
        graphs_frame.grid_rowconfigure((0, 1), weight=1)
        
        # CPU Graph
        cpu_frame = ctk.CTkFrame(graphs_frame, fg_color=CYPHER_PANEL_BG, 
                                 corner_radius=12, border_width=1, 
                                 border_color=CYPHER_BORDER)
        cpu_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        ctk.CTkLabel(cpu_frame, text="CPU Usage", font=("Arial", 18, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(pady=(15, 10))
        
        cpu_canvas = Canvas(cpu_frame, bg=CYPHER_PANEL_BG, highlightthickness=0)
        cpu_canvas.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.analytics_cpu_canvas = cpu_canvas
        
        # RAM Graph
        ram_frame = ctk.CTkFrame(graphs_frame, fg_color=CYPHER_PANEL_BG, 
                                 corner_radius=12, border_width=1, 
                                 border_color=CYPHER_BORDER)
        ram_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        ctk.CTkLabel(ram_frame, text="RAM Usage", font=("Arial", 18, "bold"), 
                    text_color=CYPHER_GREEN).pack(pady=(15, 10))
        
        ram_canvas = Canvas(ram_frame, bg=CYPHER_PANEL_BG, highlightthickness=0)
        ram_canvas.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.analytics_ram_canvas = ram_canvas
        
        # Stats globales
        stats_frame = ctk.CTkFrame(graphs_frame, fg_color=CYPHER_PANEL_BG, 
                                   corner_radius=12, border_width=1, 
                                   border_color=CYPHER_BORDER)
        stats_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_inner.pack(fill="x", padx=20, pady=15)
        stats_inner.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # Stats cards
        stats_data = [
            ("Uptime", f"{(datetime.now() - self.session_start).total_seconds() / 3600:.1f}h", "⏱"),
            ("Commands", str(self.commands_count), "📊"),
            ("Avg CPU", f"{sum(self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0:.1f}%", "💻"),
            ("Avg RAM", f"{sum(self.ram_history) / len(self.ram_history) if self.ram_history else 0:.1f}%", "🧠")
        ]
        
        for i, (label, value, icon) in enumerate(stats_data):
            card = ctk.CTkFrame(stats_inner, fg_color=CYPHER_NEON_BLUE_DARK, 
                               corner_radius=10)
            card.grid(row=0, column=i, sticky="nsew", padx=10)
            
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(padx=15, pady=15)
            
            ctk.CTkLabel(inner, text=icon, font=("Arial", 20), 
                        text_color=CYPHER_NEON_BLUE).pack()
            ctk.CTkLabel(inner, text=value, font=("Consolas", 24, "bold"), 
                        text_color=CYPHER_TEXT).pack(pady=(5, 0))
            ctk.CTkLabel(inner, text=label, font=("Arial", 12), 
                        text_color=CYPHER_TEXT_DIM).pack()
    
    def _build_productivity_tab(self, parent):
        """Construit l'onglet Productivité avec stats des tâches"""
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Stats des tâches
        try:
            from modules.task_manager import get_task_manager
            task_mgr = get_task_manager()
            tasks = task_mgr.list_tasks()
            
            todo_count = sum(1 for t in tasks if t.get('status') == 'todo')
            in_progress_count = sum(1 for t in tasks if t.get('status') == 'in_progress')
            done_count = sum(1 for t in tasks if t.get('status') == 'done')
            total_count = len(tasks)
            
            # Cards de stats
            stats_grid = ctk.CTkFrame(content, fg_color="transparent")
            stats_grid.pack(fill="x", pady=(0, 20))
            stats_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)
            
            stats_cards = [
                ("Total", str(total_count), CYPHER_NEON_BLUE),
                ("À faire", str(todo_count), CYPHER_ORANGE),
                ("En cours", str(in_progress_count), CYPHER_YELLOW),
                ("Terminées", str(done_count), CYPHER_GREEN)
            ]
            
            for i, (label, value, color) in enumerate(stats_cards):
                card = ctk.CTkFrame(stats_grid, fg_color=CYPHER_NEON_BLUE_DARK, 
                                   corner_radius=12, border_width=2, 
                                   border_color=color)
                card.grid(row=0, column=i, sticky="nsew", padx=10)
                
                inner = ctk.CTkFrame(card, fg_color="transparent")
                inner.pack(padx=20, pady=20)
                
                ctk.CTkLabel(inner, text=value, font=("Consolas", 36, "bold"), 
                           text_color=color).pack()
                ctk.CTkLabel(inner, text=label, font=("Arial", 14), 
                           text_color=CYPHER_TEXT_DIM).pack(pady=(5, 0))
            
        except Exception as e:
            ctk.CTkLabel(content, text=f"Erreur: {e}", 
                        text_color=CYPHER_RED).pack()
    
    def _build_interactions_tab(self, parent):
        """Construit l'onglet Interactions avec historique"""
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Timeline des interactions
        ctk.CTkLabel(content, text="Historique des Interactions", 
                    font=("Arial", 20, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(anchor="w", pady=(0, 15))
        
        # Liste scrollable
        scroll_frame = ctk.CTkScrollableFrame(content, fg_color=CYPHER_PANEL_BG, 
                                             corner_radius=12, 
                                             border_width=1, 
                                             border_color=CYPHER_BORDER)
        scroll_frame.pack(fill="both", expand=True)
        
        # Afficher les dernières interactions
        for i, (msg_type, text, timestamp) in enumerate(list(self.conversation_history)[-20:]):
            interaction_frame = ctk.CTkFrame(scroll_frame, 
                                           fg_color=CYPHER_NEON_BLUE_DARK, 
                                           corner_radius=8)
            interaction_frame.pack(fill="x", padx=10, pady=5)
            
            inner = ctk.CTkFrame(interaction_frame, fg_color="transparent")
            inner.pack(fill="x", padx=15, pady=10)
            
            ctk.CTkLabel(inner, text=f"[{timestamp}] {msg_type}:", 
                        font=("Consolas", 11, "bold"), 
                        text_color=CYPHER_NEON_BLUE).pack(anchor="w")
            ctk.CTkLabel(inner, text=text[:100] + ("..." if len(text) > 100 else ""), 
                        font=("Arial", 12), 
                        text_color=CYPHER_TEXT, 
                        wraplength=800,
                        justify="left").pack(anchor="w", pady=(5, 0))
    
    def _show_analytics_dashboard(self):
        """Affiche le dashboard analytics"""
        if self.analytics_window is None:
            self._create_analytics_dashboard()
        self.analytics_window.deiconify()
        self.analytics_window.lift()
        self.analytics_window.focus_force()
        # Forcer le premier plan temporairement
        self.analytics_window.attributes('-topmost', True)
        self.after(100, lambda: self.analytics_window.attributes('-topmost', False))
        self._refresh_analytics()
    
    def _hide_analytics_dashboard(self):
        """Masque le dashboard analytics"""
        if self.analytics_window:
            self.analytics_window.withdraw()
    
    def _refresh_analytics(self):
        """Rafraîchit les données analytics"""
        # Mise à jour des graphiques si les canvas existent
        if hasattr(self, 'analytics_cpu_canvas'):
            self._draw_analytics_cpu_graph()
        if hasattr(self, 'analytics_ram_canvas'):
            self._draw_analytics_ram_graph()
    
    def _draw_analytics_cpu_graph(self):
        """Dessine le graphique CPU détaillé"""
        canvas = self.analytics_cpu_canvas
        canvas.delete("all")
        
        w = canvas.winfo_width() or 600
        h = canvas.winfo_height() or 300
        
        if not self.cpu_history:
            return
        
        # Grille
        for i in range(5):
            y = h - (i * h // 4)
            canvas.create_line(40, y, w - 20, y, fill=CYPHER_BORDER, width=1)
            canvas.create_text(35, y, text=f"{100 - i * 25}%", 
                             fill=CYPHER_TEXT_DIM, font=("Arial", 10), anchor="e")
        
        # Graphique avec zone remplie
        max_samples = len(self.cpu_history)
        step_x = (w - 60) / max(max_samples - 1, 1)
        
        points = []
        for i, val in enumerate(self.cpu_history):
            x = 40 + i * step_x
            y = h - 20 - (val / 100) * (h - 40)
            points.append((x, y))
        
        if len(points) > 1:
            # Zone remplie (gradient effect)
            fill_points = [(points[0][0], h - 20)] + points + [(points[-1][0], h - 20)]
            canvas.create_polygon(fill_points, fill=CYPHER_NEON_BLUE_DARK, 
                                 outline="", stipple="gray25")
            
            # Ligne principale
            for i in range(len(points) - 1):
                canvas.create_line(points[i][0], points[i][1],
                                 points[i + 1][0], points[i + 1][1],
                                 fill=CYPHER_NEON_BLUE, width=3)
    
    def _draw_analytics_ram_graph(self):
        """Dessine le graphique RAM détaillé"""
        canvas = self.analytics_ram_canvas
        canvas.delete("all")
        
        w = canvas.winfo_width() or 600
        h = canvas.winfo_height() or 300
        
        if not self.ram_history:
            return
        
        # Grille
        for i in range(5):
            y = h - (i * h // 4)
            canvas.create_line(40, y, w - 20, y, fill=CYPHER_BORDER, width=1)
            canvas.create_text(35, y, text=f"{100 - i * 25}%", 
                             fill=CYPHER_TEXT_DIM, font=("Arial", 10), anchor="e")
        
        # Graphique avec zone remplie
        max_samples = len(self.ram_history)
        step_x = (w - 60) / max(max_samples - 1, 1)
        
        points = []
        for i, val in enumerate(self.ram_history):
            x = 40 + i * step_x
            y = h - 20 - (val / 100) * (h - 40)
            points.append((x, y))
        
        if len(points) > 1:
            # Zone remplie
            fill_points = [(points[0][0], h - 20)] + points + [(points[-1][0], h - 20)]
            canvas.create_polygon(fill_points, fill="#003300", 
                                 outline="", stipple="gray25")
            
            # Ligne principale
            for i in range(len(points) - 1):
                canvas.create_line(points[i][0], points[i][1],
                                 points[i + 1][0], points[i + 1][1],
                                 fill=CYPHER_GREEN, width=3)
    
    # ========================================
    # MODE IMMERSIF PLEIN ÉCRAN
    # ========================================
    
    def _toggle_immersive_mode(self):
        """Active/désactive le mode immersif plein écran"""
        if not self.immersive_mode:
            # Sauvegarder la géométrie actuelle
            self.original_geometry = self.geometry()
            # Passer en plein écran
            self.attributes('-fullscreen', True)
            self.immersive_mode = True
            self.show_notification("Mode Immersif", "Mode plein écran activé", "info", 2000)
        else:
            # Restaurer la géométrie
            if self.original_geometry:
                self.geometry(self.original_geometry)
            self.attributes('-fullscreen', False)
            self.immersive_mode = False
            self.show_notification("Mode Immersif", "Mode plein écran désactivé", "info", 2000)
    
    # ========================================
    # VISUALISATIONS DE DONNÉES
    # ========================================
    
    def _create_visualizations_window(self):
        """Crée la fenêtre de visualisations de données"""
        if self.visualizations_window is not None:
            return
        
        self.visualizations_window = ctk.CTkToplevel(self)
        self.visualizations_window.title("Visualisations - Cypher")
        self.visualizations_window.geometry("1400x900")
        self.visualizations_window.configure(fg_color=CYPHER_BG)
        
        self.visualizations_window.protocol("WM_DELETE_WINDOW", self._hide_visualizations)
        
        # Header
        header = ctk.CTkFrame(self.visualizations_window, fg_color=CYPHER_PANEL_BG, 
                             corner_radius=0, border_width=0)
        header.pack(fill="x", padx=0, pady=0)
        
        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=15)
        header_inner.grid_columnconfigure(1, weight=1)
        
        # Logo et titre
        title_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(title_frame, text="📊", font=("Arial", 32, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_frame, text="VISUALISATIONS", 
                    font=("Consolas", 28, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(side="left")
        
        # Boutons header
        btn_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")
        
        close_btn = ctk.CTkButton(btn_frame, text="✕", width=40, height=40,
                                 fg_color=CYPHER_NEON_BLUE_DARK, 
                                 hover_color=CYPHER_RED,
                                 text_color=CYPHER_TEXT, 
                                 font=("Arial", 16),
                                 corner_radius=8, 
                                 command=self._hide_visualizations)
        close_btn.pack(side="left")
        
        # Contenu avec onglets
        main_container = ctk.CTkFrame(self.visualizations_window, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        viz_tabs = ctk.CTkTabview(main_container, 
                                 fg_color=CYPHER_PANEL_BG,
                                 border_width=1,
                                 border_color=CYPHER_BORDER,
                                 corner_radius=15)
        viz_tabs.pack(fill="both", expand=True)
        
        # Onglet Timeline
        timeline_tab = viz_tabs.add("⏱ Timeline")
        self._build_timeline_tab(timeline_tab)
        
        # Onglet Carte Mentale
        mindmap_tab = viz_tabs.add("🧠 Carte Mentale")
        self._build_mindmap_tab(mindmap_tab)
    
    def _build_timeline_tab(self, parent):
        """Construit l'onglet Timeline avec historique des interactions"""
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        ctk.CTkLabel(content, text="Timeline des Interactions", 
                    font=("Arial", 20, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(anchor="w", pady=(0, 15))
        
        # Canvas pour la timeline
        timeline_canvas = Canvas(content, bg=CYPHER_PANEL_BG, highlightthickness=0)
        timeline_canvas.pack(fill="both", expand=True)
        timeline_canvas._tab_type = 'timeline'
        
        # Dessiner la timeline
        self._draw_timeline(timeline_canvas)
    
    def _draw_timeline(self, canvas):
        """Dessine la timeline des interactions"""
        canvas.delete("all")
        
        # Forcer le calcul de la taille du canvas
        canvas.update_idletasks()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        
        if w <= 1 or h <= 1:
            w, h = 1200, 600
        
        if not self.conversation_history:
            canvas.create_text(w//2, h//2, text="Aucune interaction pour le moment", 
                             fill=CYPHER_TEXT_DIM, font=("Arial", 16))
            return
        
        # Ligne centrale de la timeline
        center_y = h // 2
        canvas.create_line(50, center_y, w - 50, center_y, 
                          fill=CYPHER_NEON_BLUE, width=3)
        
        # Points sur la timeline
        history_list = list(self.conversation_history)
        num_points = len(history_list)
        
        if num_points > 0:
            step_x = (w - 100) / max(num_points, 1)
            
            for i, (msg_type, text, timestamp) in enumerate(history_list):
                x = 50 + i * step_x
                
                # Couleur selon le type
                color = CYPHER_NEON_BLUE if msg_type == "USER" else CYPHER_GREEN
                
                # Point sur la timeline
                canvas.create_oval(x - 8, center_y - 8, x + 8, center_y + 8, 
                                  fill=color, outline=CYPHER_BG, width=2)
                
                # Ligne verticale
                line_height = 60 if i % 2 == 0 else -60
                canvas.create_line(x, center_y, x, center_y + line_height, 
                                  fill=color, width=2)
                
                # Texte (première ligne seulement)
                if i % 2 == 0:
                    canvas.create_text(x, center_y + line_height + 15, 
                                      text=timestamp, 
                                      fill=CYPHER_TEXT_DIM, 
                                      font=("Arial", 9))
                    canvas.create_text(x, center_y + line_height + 30, 
                                      text=text[:20] + ("..." if len(text) > 20 else ""), 
                                      fill=CYPHER_TEXT, 
                                      font=("Arial", 10))
    
    def _build_mindmap_tab(self, parent):
        """Construit l'onglet Carte Mentale"""
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        ctk.CTkLabel(content, text="Carte Mentale des Conversations", 
                    font=("Arial", 20, "bold"), 
                    text_color=CYPHER_NEON_BLUE).pack(anchor="w", pady=(0, 15))
        
        # Canvas pour la carte mentale
        mindmap_canvas = Canvas(content, bg=CYPHER_PANEL_BG, highlightthickness=0)
        mindmap_canvas.pack(fill="both", expand=True)
        mindmap_canvas._tab_type = 'mindmap'
        
        # Stocker la référence pour le rafraîchissement
        self.mindmap_canvas = mindmap_canvas
        
        # Dessiner la carte mentale après un court délai pour que le canvas soit affiché
        self.after(300, lambda: self._draw_mindmap(mindmap_canvas))
    
    def _draw_mindmap(self, canvas):
        """Dessine la carte mentale des sujets de conversation"""
        canvas.delete("all")
        
        # Forcer le calcul de la taille du canvas
        canvas.update_idletasks()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        
        if w <= 1 or h <= 1:
            w, h = 1200, 600
        
        if not self.conversation_history:
            canvas.create_text(w//2, h//2, text="Aucune conversation pour générer la carte", 
                             fill=CYPHER_TEXT_DIM, font=("Arial", 16))
            return
        
        # Centre de la carte
        center_x, center_y = w // 2, h // 2
        
        # Noeud central
        canvas.create_oval(center_x - 40, center_y - 40, center_x + 40, center_y + 40, 
                          fill=CYPHER_NEON_BLUE_DARK, outline=CYPHER_NEON_BLUE, width=3)
        canvas.create_text(center_x, center_y, text="Cypher", 
                          fill=CYPHER_NEON_BLUE, font=("Arial", 16, "bold"))
        
        # Extraire les mots-clés des conversations (simplifié)
        keywords = {}
        for msg_type, text, timestamp in self.conversation_history:
            words = text.lower().split()
            for word in words:
                if len(word) > 4:  # Mots de plus de 4 caractères
                    keywords[word] = keywords.get(word, 0) + 1
        
        # Trier et prendre les top 8
        top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:8]
        
        # Dessiner les noeuds autour du centre
        import math
        num_nodes = len(top_keywords)
        if num_nodes > 0:
            angle_step = (2 * math.pi) / num_nodes
            radius = min(w, h) // 3
            
            for i, (keyword, count) in enumerate(top_keywords):
                angle = i * angle_step
                node_x = center_x + radius * math.cos(angle)
                node_y = center_y + radius * math.sin(angle)
                
                # Ligne de connexion
                canvas.create_line(center_x, center_y, node_x, node_y, 
                                  fill=CYPHER_NEON_BLUE_DIM, width=2)
                
                # Noeud
                node_size = 30 + (count * 5)  # Taille selon fréquence
                canvas.create_oval(node_x - node_size, node_y - node_size, 
                                  node_x + node_size, node_y + node_size, 
                                  fill=CYPHER_NEON_BLUE_DARK, 
                                  outline=CYPHER_NEON_BLUE, width=2)
                
                # Texte
                canvas.create_text(node_x, node_y, text=keyword[:10], 
                                  fill=CYPHER_NEON_BLUE, font=("Arial", 10, "bold"))
                canvas.create_text(node_x, node_y + 20, text=f"({count})", 
                                  fill=CYPHER_TEXT_DIM, font=("Arial", 8))
    
    def _show_visualizations(self):
        """Affiche la fenêtre de visualisations"""
        if self.visualizations_window is None:
            self._create_visualizations_window()
        self.visualizations_window.deiconify()
        self.visualizations_window.lift()
        self.visualizations_window.focus_force()
        # Forcer le premier plan temporairement
        self.visualizations_window.attributes('-topmost', True)
        self.after(100, lambda: self.visualizations_window.attributes('-topmost', False))
        # Rafraîchir les visualisations après que la fenêtre soit affichée
        self.after(200, lambda: self._refresh_visualizations())
    
    def _hide_visualizations(self):
        """Masque la fenêtre de visualisations"""
        if self.visualizations_window:
            self.visualizations_window.withdraw()
    
    def _refresh_visualizations(self):
        """Rafraîchit les visualisations"""
        if self.visualizations_window and self.visualizations_window.winfo_viewable():
            # Forcer la mise à jour de la fenêtre
            self.visualizations_window.update_idletasks()
            
            # Redessiner les canvas stockés
            if self.timeline_canvas:
                self._draw_timeline(self.timeline_canvas)
            if self.mindmap_canvas:
                self._draw_mindmap(self.mindmap_canvas)
    
    def _toggle_sleep_wake(self):
        """Bascule entre veille et réveil de Cypher"""
        if self.is_sleeping:
            # Réveiller Cypher (il est actuellement en veille)
            self.is_sleeping = False
            self.sleep_wake_btn.configure(text="⏸", text_color=JARVIS_CYAN, border_color=JARVIS_CYAN)  # Icône pause pour mettre en veille
            # Envoyer commande de réveil au backend
            try:
                self.data_queue.put(("GUI_COMMAND", "WAKE"))
            except Exception as e:
                print(f"Erreur envoi WAKE: {e}")
        else:
            # Mettre Cypher en veille (il est actuellement réveillé)
            self.is_sleeping = True
            self.sleep_wake_btn.configure(text="⏻", text_color=JARVIS_GREEN, border_color=JARVIS_GREEN)  # Icône power pour réveiller
            # Envoyer commande de veille au backend
            try:
                self.data_queue.put(("GUI_COMMAND", "SLEEP"))
            except Exception as e:
                print(f"Erreur envoi SLEEP: {e}")
    
    def _update_sleep_button(self):
        """Met à jour l'apparence du bouton selon l'état actuel"""
        if hasattr(self, 'sleep_wake_btn'):
            if self.is_sleeping:
                # Cypher est en veille -> bouton power vert pour réveiller
                self.sleep_wake_btn.configure(text="⏻", text_color=JARVIS_GREEN, border_color=JARVIS_GREEN)
            else:
                # Cypher est réveillé -> bouton pause bleu pour mettre en veille
                self.sleep_wake_btn.configure(text="⏸", text_color=JARVIS_CYAN, border_color=JARVIS_CYAN)


# Pour tests sans le main.py
if __name__ == "__main__":
    test_queue = queue.Queue()
    app = CypherGUI(test_queue)
    app.mainloop()
