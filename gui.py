import customtkinter as ctk
from tkinter import Canvas
import math
from datetime import datetime
import queue
import requests
import threading
import psutil
import json
import os

# Configuration du thème
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class CypherGUI(ctk.CTk):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self.title("CYPHER - AI Assistant")
        self.geometry("1400x900")
        self.configure(fg_color="#000000")
        
        self.is_listening = False
        self.is_speaking = False
        self.animation_angle = 0
        self.current_radius = 120
        self.target_radius = 120
        
        self.message_widgets = [] 

        # Mapping Simplifié (4 états uniquement)
        # Codes WMO : https://open-meteo.com/en/docs
        self.weather_map = {
            0: "sun", 1: "sun",             # Ciel dégagé
            2: "partly", 3: "partly",       # Partiellement nuageux
            45: "cloud", 48: "cloud",       # Brouillard -> Nuage
            51: "rain", 53: "rain", 55: "rain", # Bruine
            61: "rain", 63: "rain", 65: "rain", # Pluie
            71: "rain", 73: "rain", 75: "rain", # Neige -> Pluie (visuel simple)
            80: "rain", 81: "rain", 82: "rain",
            95: "rain", 96: "rain", 99: "rain"  # Orage -> Pluie (visuel simple)
        }

        self._build_ui()
        self._animate_microphone()
        self._update_time_weather_loop()
        self._update_insights_loop()
        self.check_queue()
        
        # Test au démarrage
        self.after(1000, lambda: self.add_assistant_message("Initialisation de l'interface terminée."))

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
                elif msg_type == "ASSISTANT_TEXT":
                    self.add_assistant_message(content)
                elif msg_type == "USER_TEXT":
                    self.add_user_message(content)
        except queue.Empty:
            pass
        self.after(50, self.check_queue)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # HEADER
        header = ctk.CTkFrame(self, fg_color="#0a0a0a", height=70)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(header, text="◈ CYPHER", font=("Consolas", 45, "bold"), text_color="#00d4ff").pack(side="left", padx=30, pady=15)
        
        # GAUCHE - CHAT
        chat_container = ctk.CTkFrame(self, fg_color="#000000")
        chat_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=15)
        
        chat_header = ctk.CTkFrame(chat_container, fg_color="#0f0f0f", height=40, corner_radius=10)
        chat_header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(chat_header, text="💬 Conversation", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(pady=8)

        self.chat_scroll = ctk.CTkScrollableFrame(chat_container, fg_color="#000000")
        self.chat_scroll.pack(fill="both", expand=True)
        
        # CENTRE - MICRO
        center_frame = ctk.CTkFrame(self, fg_color="#000000")
        center_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.mic_canvas = Canvas(center_frame, width=550, height=550, bg="#000000", highlightthickness=0)
        self.mic_canvas.pack(expand=True)
        self.status_label = ctk.CTkLabel(center_frame, text="Je vous écoute...", font=("Arial", 15, "bold"), text_color="#00d4ff")
        self.status_label.pack(pady=20)
        
        # DROITE - WIDGETS
        right_container = ctk.CTkFrame(self, fg_color="#000000")
        right_container.grid(row=1, column=2, sticky="nsew", padx=15, pady=15)
        
        # Météo
        self.weather_widget = self._create_weather_widget(right_container)
        self.weather_widget.pack(pady=(0, 20), padx=10, fill="x")
        
        # Tableau de bord (CPU/RAM/Agenda/Projets)
        self.insights_widget = self._create_insights_widget(right_container)
        self.insights_widget.pack(pady=0, padx=10, fill="both", expand=True)
    
    def _create_weather_widget(self, parent):
        widget = ctk.CTkFrame(parent, fg_color="#000000", corner_radius=20, border_width=1, border_color="#00d4ff") # Bordure Cyan comme screenshot
        top_frame = ctk.CTkFrame(widget, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        self.weather_canvas = Canvas(top_frame, width=100, height=100, bg="#000000", highlightthickness=0)
        self.weather_canvas.pack(side="left")
        
        info_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        info_frame.pack(side="right", padx=(0, 10))
        self.temp_label = ctk.CTkLabel(info_frame, text="--°", font=("Arial", 50), text_color="white")
        self.temp_label.pack(anchor="e")
        self.location_label = ctk.CTkLabel(info_frame, text="Localisation...", font=("Arial", 18), text_color="#888888")
        self.location_label.pack(anchor="e")

        bottom_frame = ctk.CTkFrame(widget, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=30, pady=(0, 20))
        self.date_label = ctk.CTkLabel(bottom_frame, text="...", font=("Arial", 12), text_color="#aaaaaa")
        self.date_label.pack(side="left")
        self.time_label = ctk.CTkLabel(bottom_frame, text="...", font=("Arial", 12), text_color="#aaaaaa")
        self.time_label.pack(side="right")

        return widget

    def _draw_weather_icon(self, icon_type):
        """Dessine uniquement les 4 icônes demandées."""
        c = self.weather_canvas
        c.delete("all")
        
        color_sun = "#FFFFFF" # Blanc comme sur ton screen
        color_cloud = "#FFFFFF"
        color_rain = "#00d4ff" # Cyan pour la pluie
        
        # --- 1. SOLEIL ---
        if icon_type == "sun":
            # Centre
            c.create_oval(30, 30, 70, 70, fill=color_sun, outline="")
            # Rayons
            for i in range(0, 360, 45):
                angle = math.radians(i)
                x1, y1 = 50 + 25 * math.cos(angle), 50 + 25 * math.sin(angle)
                x2, y2 = 50 + 35 * math.cos(angle), 50 + 35 * math.sin(angle)
                c.create_line(x1, y1, x2, y2, width=3, fill=color_sun, capstyle="round")

        # --- 2. SOLEIL NUAGEUX ---
        elif icon_type == "partly":
            # Petit soleil derrière
            c.create_oval(40, 25, 70, 55, fill=color_sun, outline="")
            # Rayons partiels
            for i in range(0, 360, 45):
                angle = math.radians(i)
                x1, y1 = 55 + 20 * math.cos(angle), 40 + 20 * math.sin(angle)
                x2, y2 = 55 + 28 * math.cos(angle), 40 + 28 * math.sin(angle)
                c.create_line(x1, y1, x2, y2, width=2, fill=color_sun, capstyle="round")
            # Nuage devant
            c.create_oval(25, 50, 65, 80, fill=color_cloud, outline="") 
            c.create_oval(45, 40, 85, 80, fill=color_cloud, outline="")
            c.create_oval(60, 50, 95, 80, fill=color_cloud, outline="")

        # --- 3. NUAGE ---
        elif icon_type == "cloud":
            c.create_oval(25, 50, 65, 80, fill=color_cloud, outline="") 
            c.create_oval(45, 40, 85, 80, fill=color_cloud, outline="")
            c.create_oval(60, 50, 95, 80, fill=color_cloud, outline="")

        # --- 4. PLUIE (Nuage + Lignes) ---
        elif icon_type == "rain":
            # Nuage
            c.create_oval(25, 45, 65, 75, fill=color_cloud, outline="") 
            c.create_oval(45, 35, 85, 75, fill=color_cloud, outline="")
            c.create_oval(60, 45, 95, 75, fill=color_cloud, outline="")
            # Gouttes
            for i in range(3):
                ox = 45 + i*15
                c.create_line(ox, 80, ox-5, 95, width=3, fill=color_rain, capstyle="round")

    def _update_weather_ui(self, temp, code):
        self.temp_label.configure(text=f"{int(round(temp))}°")
        
        # Sélection stricte parmi les 4 types
        icon_type = self.weather_map.get(code, "cloud")
        self._draw_weather_icon(icon_type)
        self.location_label.configure(text="Petit-Couronne")

    def _update_weather_ui_error(self):
        self.temp_label.configure(text="--°")
        self._draw_weather_icon("cloud")

    def _create_insights_widget(self, parent):
        widget = ctk.CTkFrame(parent, fg_color="#0a0a0a", corner_radius=20, border_width=1, border_color="#00d4ff")
        
        # --- SECTION SYSTEME ---
        title_sys = ctk.CTkLabel(widget, text="📊 Tableau de Bord", font=("Arial", 24, "bold"), text_color="#00d4ff")
        title_sys.pack(pady=(15, 10))
        
        sys_frame = ctk.CTkFrame(widget, fg_color="transparent")
        sys_frame.pack(fill="x", padx=20)
        
        self.cpu_label = ctk.CTkLabel(sys_frame, text="CPU: 0%", font=("Arial", 18), text_color="#aaaaaa")
        self.cpu_label.pack(anchor="w")
        self.cpu_bar = ctk.CTkProgressBar(sys_frame, height=6, progress_color="#00d4ff")
        self.cpu_bar.pack(fill="x", pady=(2, 10))
        
        self.ram_label = ctk.CTkLabel(sys_frame, text="RAM: 0%", font=("Arial", 18), text_color="#aaaaaa")
        self.ram_label.pack(anchor="w")
        self.ram_bar = ctk.CTkProgressBar(sys_frame, height=6, progress_color="#d400ff")
        self.ram_bar.pack(fill="x", pady=(2, 10))
        
        # Séparateur
        ctk.CTkFrame(widget, height=1, fg_color="#333333").pack(fill="x", padx=15, pady=10)
        
        # --- SECTION AGENDA ---
        ctk.CTkLabel(widget, text="📅 Prochains RDV", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(pady=(5, 5))
        self.agenda_label = ctk.CTkLabel(widget, text="Chargement...", font=("Arial", 18), text_color="#cccccc", justify="center")
        self.agenda_label.pack(fill="x", padx=10, pady=(0, 10))

        # Séparateur
        ctk.CTkFrame(widget, height=1, fg_color="#333333").pack(fill="x", padx=15, pady=10)

        # --- SECTION PROJETS ACTIFS ---
        ctk.CTkLabel(widget, text="🚀 Projets Actifs", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(pady=(5, 5))
        self.projects_frame = ctk.CTkFrame(widget, fg_color="transparent")
        self.projects_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        # Le contenu sera rempli par _update_insights_loop
        self.projects_labels = []

        return widget

    def _animate_microphone(self):
        self.mic_canvas.delete("all")
        cx, cy = 275, 275
        base_radius = 120
        
        if self.is_listening:
            color = "#00d4ff"
            self.target_radius = 170
            speed = 0.15
        elif self.is_speaking:
            color = "#ff6b35"
            pulse = math.sin(self.animation_angle * 0.8) * 20
            self.target_radius = base_radius + 15 + pulse
            speed = 0.2
            self.animation_angle += 0.2
        else:
            color = "#333333"
            self.target_radius = base_radius
            speed = 0.05
            self.animation_angle = 0
            
        diff = self.target_radius - self.current_radius
        self.current_radius += diff * speed
        
        # Cercles
        self.mic_canvas.create_oval(cx - self.current_radius, cy - self.current_radius, cx + self.current_radius, cy + self.current_radius, outline=color, width=3)
        self.mic_canvas.create_oval(cx - 90, cy - 90, cx + 90, cy + 90, outline=color, width=1)
        
        # Icone Micro
        self.mic_canvas.create_line(cx, cy-35, cx, cy+15, width=42, capstyle="round", fill=color)
        self.mic_canvas.create_line(cx, cy-35, cx, cy+15, width=32, capstyle="round", fill="#000000") # Vide intérieur
        self.mic_canvas.create_arc(cx-38, cy-20, cx+38, cy+38, start=180, extent=180, style="arc", outline=color, width=5)
        self.mic_canvas.create_line(cx, cy+38, cx, cy+65, width=5, fill=color)
        self.mic_canvas.create_line(cx-25, cy+65, cx+25, cy+65, width=5, fill=color, capstyle="round")

        self.after(20, self._animate_microphone)

    def _manage_chat_limit(self):
        while len(self.message_widgets) > 10:
            old_widget = self.message_widgets.pop(0)
            old_widget.destroy()

    def add_user_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=5)
        
        # Bulle alignée à DROITE (Cyan)
        bubble = ctk.CTkFrame(container, fg_color="#00d4ff", corner_radius=15)
        bubble.pack(side="right", padx=(50, 5))
        
        ctk.CTkLabel(bubble, text=text, font=("Arial", 12), text_color="#000000", wraplength=260, justify="left").pack(padx=12, pady=8)
        
        self.message_widgets.append(container)
        self._manage_chat_limit()
        self.chat_scroll._parent_canvas.yview_moveto(1.0)
    
    def add_assistant_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=5)
        
        # Bulle alignée à GAUCHE (Gris/Bleu foncé)
        bubble = ctk.CTkFrame(container, fg_color="#1a1a1a", corner_radius=15, border_width=1, border_color="#333333")
        bubble.pack(side="left", padx=(0, 50))
        
        ctk.CTkLabel(bubble, text=text, font=("Arial", 12), text_color="#ffffff", wraplength=260, justify="left").pack(padx=12, pady=8)
        
        self.message_widgets.append(container)
        self._manage_chat_limit()
        self.chat_scroll._parent_canvas.yview_moveto(1.0)
    
    def set_listening(self, state: bool):
        self.is_listening = state
        if state: self.status_label.configure(text="🎤 Je vous écoute...", text_color="#00d4ff", font=("Arial", 18))
        else: self.status_label.configure(text="💤 En veille...", text_color="#666666", font=("Arial", 18))
    
    def set_speaking(self, state: bool):
        self.is_speaking = state
        if state: self.status_label.configure(text="🔊 Je parle...", text_color="#ff6b35", font=("Arial", 18))

    def _update_time_weather_loop(self):
        now = datetime.now()
        self.date_label.configure(text=now.strftime("%d %b %Y"), font=("Arial", 18))
        self.time_label.configure(text=now.strftime("%H:%M"), font=("Arial", 18))
        
        if not hasattr(self, "_last_weather_check"):
            self._last_weather_check = 0
        if (datetime.now().timestamp() - self._last_weather_check) > 1800:
            self._last_weather_check = datetime.now().timestamp()
            threading.Thread(target=self._fetch_weather, daemon=True).start()
        
        self.after(1000, self._update_time_weather_loop)

    def _fetch_weather(self):
        try:
            # Petit-Couronne
            lat, lon = 49.41, 1.03
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            temp = data["current_weather"]["temperature"]
            code = data["current_weather"]["weathercode"]
            
            self.after(0, lambda: self._update_weather_ui(temp, code))
        except:
            self.after(0, lambda: self._update_weather_ui_error())

    def _update_insights_loop(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.cpu_label.configure(text=f"CPU: {cpu}%")
            self.cpu_bar.set(cpu / 100)
            self.ram_label.configure(text=f"RAM: {ram}%")
            self.ram_bar.set(ram / 100)
            
            # --- Lecture AGENDA ---
            script_dir = os.path.dirname(os.path.abspath(__file__))
            agenda_path = os.path.join(script_dir, "cypher_agenda.json")
            if os.path.exists(agenda_path):
                with open(agenda_path, 'r', encoding='utf-8') as f:
                    agenda = json.load(f)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                upcoming = [e for e in agenda if e["date"] >= now_str]
                if upcoming:
                    next_evt = upcoming[0]
                    dt = datetime.strptime(next_evt["date"], "%Y-%m-%d %H:%M")
                    self.agenda_label.configure(text=f"{dt.strftime('%H:%M')} - {next_evt['description']}")
                else:
                    self.agenda_label.configure(text="Aucun événement prévu.")
            else:
                self.agenda_label.configure(text="Agenda vide.")

            # --- Lecture PROJETS (Depuis Mémoire ou Défaut) ---
            memory_path = os.path.join(script_dir, "cypher_memory_cortex.json")
            projects = []
            
            # Valeurs par défaut du screenshot
            default_projects = ["Objectif carriere long terme", "Premier emploi cible", "Developpement cypher"]
            
            if os.path.exists(memory_path):
                try:
                    with open(memory_path, 'r', encoding='utf-8') as f:
                        memory = json.load(f)
                        # On cherche dans "projets_actifs"
                        if "projets_actifs" in memory:
                            for key, data in memory["projets_actifs"].items():
                                val = data["value"] if isinstance(data, dict) else data
                                projects.append(val)
                except:
                    pass
            
            if not projects:
                projects = default_projects
            
            # Mise à jour des labels (on efface et on recrée pour faire simple)
            for lbl in self.projects_labels:
                lbl.destroy()
            self.projects_labels = []
            
            for proj in projects[:5]: # Max 5 projets
                lbl = ctk.CTkLabel(self.projects_frame, text=f"▶ {proj}", font=("Arial", 18), text_color="white", anchor="w")
                lbl.pack(fill="x", pady=7)
                self.projects_labels.append(lbl)
                
        except Exception:
            pass
        self.after(5000, self._update_insights_loop)

# Helper pour coins arrondis dans Canvas
def create_rounded_rectangle(self, x1, y1, x2, y2, radius=25, **kwargs):
    points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
    return self.create_polygon(points, **kwargs, smooth=True)
Canvas.create_rounded_rectangle = create_rounded_rectangle