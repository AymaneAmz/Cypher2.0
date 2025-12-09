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
        
        # --- Connexion Backend ---
        self.data_queue = data_queue
        
        # Configuration de la fenêtre
        self.title("CYPHER - AI Assistant")
        self.geometry("1400x900")
        self.configure(fg_color="#000000")
        
        # Variables d'état
        self.is_listening = False
        self.is_speaking = False
        
        # Variables d'animation
        self.animation_angle = 0
        self.current_radius = 120 # Rayon actuel (pour les transitions fluides)
        self.target_radius = 120  # Rayon cible
        
        # Construction de l'interface
        self._build_ui()
        
        # Démarrer les animations et mises à jour
        self._animate_microphone()
        self._update_time_loop()
        self._update_weather_loop()
        self._update_insights_loop()
        
        # Démarrer la surveillance du backend
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
                
                elif msg_type == "ASSISTANT_TEXT":
                    self.add_assistant_message(content)
                
                elif msg_type == "USER_TEXT":
                    self.add_user_message(content)
                    
        except queue.Empty:
            pass
        self.after(50, self.check_queue) # Check plus rapide (50ms)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # HEADER
        header = ctk.CTkFrame(self, fg_color="#0a0a0a", height=70)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=0, pady=0)
        title = ctk.CTkLabel(header, text="◈ CYPHER", font=("Consolas", 40, "bold"), text_color="#00d4ff")
        title.pack(side="left", padx=30, pady=15)
        ctk.CTkLabel(header, text="AI Voice Assistant", font=("Arial", 24), text_color="#666666").pack(side="left", padx=(0, 20), pady=15)
        
        # GAUCHE
        chat_container = ctk.CTkFrame(self, fg_color="#000000")
        chat_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=15)
        chat_header = ctk.CTkFrame(chat_container, fg_color="#0f0f0f", height=50, corner_radius=10)
        chat_header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(chat_header, text="💬 Conversation", font=("Arial", 16, "bold"), text_color="#00d4ff").pack(pady=12)
        self.chat_scroll = ctk.CTkScrollableFrame(chat_container, fg_color="#000000")
        self.chat_scroll.pack(fill="both", expand=True)
        
        # CENTRE - MICRO
        center_frame = ctk.CTkFrame(self, fg_color="#000000")
        center_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.mic_canvas = Canvas(center_frame, width=550, height=550, bg="#000000", highlightthickness=0)
        self.mic_canvas.pack(expand=True)
        self.status_label = ctk.CTkLabel(center_frame, text="💤 En veille...", font=("Arial", 15, "bold"), text_color="#666666")
        self.status_label.pack(pady=15)
        
        # DROITE
        right_container = ctk.CTkFrame(self, fg_color="#000000")
        right_container.grid(row=1, column=2, sticky="nsew", padx=15, pady=15)
        self.weather_widget = self._create_weather_widget(right_container)
        self.weather_widget.pack(pady=(0, 20), padx=10, fill="x")
        self.insights_widget = self._create_insights_widget(right_container)
        self.insights_widget.pack(pady=0, padx=10, fill="both", expand=True)
    
    def _create_weather_widget(self, parent):
        widget = ctk.CTkFrame(parent, fg_color="#0f0f0f", corner_radius=20, border_width=2, border_color="#1a1a1a")
        self.weather_icon_label = ctk.CTkLabel(widget, text="--", font=("Arial", 60))
        self.weather_icon_label.pack(pady=(20, 5))
        self.temp_label = ctk.CTkLabel(widget, text="--°C", font=("Arial", 42, "bold"), text_color="#00d4ff")
        self.temp_label.pack(pady=5)
        ctk.CTkLabel(widget, text="📍 Petit-Couronne", font=("Arial", 20), text_color="#FFFFFF").pack(pady=5)
        self.datetime_label = ctk.CTkLabel(widget, text="...", font=("Arial", 20), text_color="#FFFFFF")
        self.datetime_label.pack(pady=(10, 20))
        return widget

    def _create_insights_widget(self, parent):
        widget = ctk.CTkFrame(parent, fg_color="#0a0a0a", corner_radius=20, border_width=2, border_color="#1a4d7a")
        
        # --- TITRE PRINCIPAL ---
        ctk.CTkLabel(widget, text="📊 Tableau de Bord", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(pady=(20, 15), anchor="center")
        
        # --- SECTION SYSTÈME ---
        sys_frame = ctk.CTkFrame(widget, fg_color="transparent")
        sys_frame.pack(fill="x", padx=25, pady=5)
        
        self.cpu_label = ctk.CTkLabel(sys_frame, text="CPU: 0%", font=("Arial", 18), text_color="#aaaaaa")
        self.cpu_label.pack(anchor="w")
        self.cpu_bar = ctk.CTkProgressBar(sys_frame, height=10, progress_color="#00d4ff")
        self.cpu_bar.set(0)
        self.cpu_bar.pack(fill="x", pady=(5, 10))
        
        self.ram_label = ctk.CTkLabel(sys_frame, text="RAM: 0%", font=("Arial", 18), text_color="#aaaaaa")
        self.ram_label.pack(anchor="w")
        self.ram_bar = ctk.CTkProgressBar(sys_frame, height=10, progress_color="#d400ff")
        self.ram_bar.set(0)
        self.ram_bar.pack(fill="x", pady=(5, 15))

        # Séparateur
        ctk.CTkFrame(widget, height=2, fg_color="#1a1a1a").pack(fill="x", padx=20, pady=10)

        # --- SECTION AGENDA ---
        # Titre Centré et Gros
        ctk.CTkLabel(widget, text="📅 Prochains RDV", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(anchor="center", pady=(10, 10))
        
        # Texte Blanc, Gros (14), avec padding
        self.agenda_label = ctk.CTkLabel(
            widget, 
            text="Chargement...", 
            font=("Arial", 18), 
            text_color="#ffffff", 
            justify="left", 
            anchor="w"
        )
        self.agenda_label.pack(fill="x", padx=25, pady=(0, 15))

        # Séparateur
        ctk.CTkFrame(widget, height=2, fg_color="#1a1a1a").pack(fill="x", padx=20, pady=10)

        # --- SECTION PROJETS ---
        # Titre Centré et Gros
        ctk.CTkLabel(widget, text="🚀 Projets Actifs", font=("Arial", 24, "bold"), text_color="#00d4ff").pack(anchor="center", pady=(10, 10))
        
        # Texte Blanc, Gros (14)
        self.projects_label = ctk.CTkLabel(
            widget, 
            text="Chargement...", 
            font=("Arial", 18), 
            text_color="#ffffff", 
            justify="left", 
            anchor="w"
        )
        self.projects_label.pack(fill="x", padx=25, pady=(0, 20))

        return widget

    # --- NOUVELLE ANIMATION & DESSIN MICRO ---
    
    def _draw_vector_mic(self, cx, cy, color):
        """Dessine un micro vectoriel style 'Line Art'"""
        # 1. Corps du micro (Capsule)
        # On utilise create_rounded_rectangle ou une ligne très épaisse avec capstyle round
        self.mic_canvas.create_line(
            cx, cy - 30, cx, cy + 10,
            width=30, capstyle="round", fill=color
        )
        # Détails intérieurs (grille) pour le style
        self.mic_canvas.create_line(cx-8, cy-20, cx-8, cy+5, width=2, fill="#000000")
        self.mic_canvas.create_line(cx, cy-20, cx, cy+5, width=2, fill="#000000")
        self.mic_canvas.create_line(cx+8, cy-20, cx+8, cy+5, width=2, fill="#000000")

        # 2. Pied du micro (le U)
        self.mic_canvas.create_arc(
            cx - 22, cy - 20, cx + 22, cy + 25,
            start=180, extent=180, style="arc", width=4, outline=color
        )
        
        # 3. La tige verticale
        self.mic_canvas.create_line(cx, cy + 25, cx, cy + 45, width=4, fill=color)
        
        # 4. La base horizontale
        self.mic_canvas.create_line(cx - 20, cy + 45, cx + 20, cy + 45, width=4, fill=color, capstyle="round")

    def _animate_microphone(self):
        """Gestion des états du cercle et de l'icône"""
        self.mic_canvas.delete("all")
        cx, cy = 275, 275
        
        base_radius = 110
        max_freeze_radius = 160 # Taille quand figé (écoute)
        
        # --- LOGIQUE D'ÉTAT ---
        
        if self.is_listening:
            # ÉTAT: JE PARLE (L'utilisateur)
            color = "#00d4ff" # Cyan
            # Objectif : Grossir et figer
            self.target_radius = max_freeze_radius
            speed = 0.2 # Grossit vite
            
        elif self.is_speaking:
            # ÉTAT: IL PARLE (Cypher)
            color = "#ff6b35" # Orange
            # Objectif : Pulser (Target change tout le temps)
            pulse = math.sin(self.animation_angle * 0.8) * 20
            self.target_radius = base_radius + 20 + pulse
            speed = 0.2 # Réactivité de la pulsation
            self.animation_angle += 0.2
            
        else:
            # ÉTAT: VEILLE
            color = "#333333"
            self.target_radius = base_radius
            speed = 0.05 # Retour lent au calme
            self.animation_angle = 0 # Reset

        # --- LISSAGE DU MOUVEMENT (Lerp) ---
        # On déplace current_radius vers target_radius progressivement
        diff = self.target_radius - self.current_radius
        self.current_radius += diff * speed

        # 1. DESSIN DU CERCLE
        self.mic_canvas.create_oval(
            cx - self.current_radius, cy - self.current_radius,
            cx + self.current_radius, cy + self.current_radius,
            outline=color, width=3
        )

        # 2. DESSIN DU MICROPHONE (Vectoriel)
        # La couleur du micro suit l'état
        mic_color = color if (self.is_listening or self.is_speaking) else "#555555"
        self._draw_vector_mic(cx, cy, mic_color)
        
        # Rappel de la boucle
        self.after(20, self._animate_microphone)

    # ... (Le reste des méthodes add_user_message, update_loops, etc. reste identique) ...
    # Je remets les méthodes essentielles pour que le copier-coller marche direct
    
    def add_user_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=5)
        bubble = ctk.CTkFrame(container, fg_color="#00d4ff", corner_radius=18)
        bubble.pack(side="right", padx=(50, 5))
        ctk.CTkLabel(bubble, text=text, font=("Arial", 12), text_color="#000000", wraplength=280, justify="left").pack(padx=15, pady=10)
        self.chat_scroll._parent_canvas.yview_moveto(1.0)
    
    def add_assistant_message(self, text):
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=5)
        bubble = ctk.CTkFrame(container, fg_color="#1a4d7a", corner_radius=18)
        bubble.pack(side="left", padx=(0, 50))
        ctk.CTkLabel(bubble, text=text, font=("Arial", 12), text_color="#ffffff", wraplength=280, justify="left").pack(padx=15, pady=10)
        self.chat_scroll._parent_canvas.yview_moveto(1.0)
    
    def set_listening(self, state: bool):
        self.is_listening = state
        if state: self.status_label.configure(text="🎤 Je vous écoute...", text_color="#00d4ff")
        else: self.status_label.configure(text="💤 En veille...", text_color="#666666")
    
    def set_speaking(self, state: bool):
        self.is_speaking = state
        if state: self.status_label.configure(text="🔊 Je parle...", text_color="#ff6b35")
        
    def _update_time_loop(self):
        now = datetime.now()
        date_str = now.strftime("%A %d %b • %H:%M")
        self.datetime_label.configure(text=date_str)
        self.after(1000, self._update_time_loop)

    def _update_weather_loop(self):
        def fetch_weather():
            try:
                lat, lon = 49.41, 1.03
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                response = requests.get(url, timeout=5)
                data = response.json()
                temp = data["current_weather"]["temperature"]
                code = data["current_weather"]["weathercode"]
                self.after(0, lambda: self._update_weather_ui(temp, code))
            except Exception as e:
                print(f"Erreur Météo GUI: {e}")
        threading.Thread(target=fetch_weather, daemon=True).start()
        self.after(1800000, self._update_weather_loop)

    def _update_weather_ui(self, temp, code):
        self.temp_label.configure(text=f"{temp}°C")
        icon = "☁️"
        if code == 0: icon = "☀️"
        elif code in [1, 2, 3]: icon = "⛅"
        elif code in [45, 48]: icon = "🌫️"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: icon = "🌧️"
        elif code in [71, 73, 75, 77, 85, 86]: icon = "❄️"
        elif code in [95, 96, 99]: icon = "⛈️"
        self.weather_icon_label.configure(text=icon)

    def _update_insights_loop(self):
        # 1. SYSTÈME
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.cpu_label.configure(text=f"CPU: {cpu}%")
            self.cpu_bar.set(cpu / 100)
            self.ram_label.configure(text=f"RAM: {ram}%")
            self.ram_bar.set(ram / 100)
        except: pass

        # 2. FICHIERS JSON
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # --- AGENDA ---
            agenda_path = os.path.join(script_dir, "cypher_agenda.json")
            if os.path.exists(agenda_path):
                try:
                    with open(agenda_path, 'r', encoding='utf-8') as f:
                        agenda = json.load(f)
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    upcoming = [e for e in agenda if e["date"] >= now_str]
                    upcoming.sort(key=lambda x: x["date"])
                    
                    if upcoming:
                        text = ""
                        for e in upcoming[:3]:
                            dt = datetime.strptime(e["date"], "%Y-%m-%d %H:%M")
                            pretty = dt.strftime("%d/%m à %Hh%M")
                            desc = e['description']
                            # AJOUT DE \n\n POUR L'AÉRATION
                            text += f"• {pretty}\n   {desc}\n\n"
                        self.agenda_label.configure(text=text.strip())
                    else:
                        self.agenda_label.configure(text="Aucun événement prévu.")
                except:
                    self.agenda_label.configure(text="Erreur lecture agenda.")
            else:
                self.agenda_label.configure(text="Agenda vide.")

            # --- PROJETS ---
            mem_path = os.path.join(script_dir, "cypher_memory_cortex.json")
            if os.path.exists(mem_path):
                try:
                    with open(mem_path, 'r', encoding='utf-8') as f:
                        mem = json.load(f)
                    projets = mem.get("projets_actifs", {})
                    if projets:
                        text = ""
                        for k in list(projets.keys())[:3]:
                            clean_name = k.replace("_", " ").capitalize()
                            # AJOUT DE \n\n POUR L'AÉRATION
                            text += f"► {clean_name}\n\n"
                        self.projects_label.configure(text=text.strip())
                    else:
                        self.projects_label.configure(text="Aucun projet actif.")
                except:
                    self.projects_label.configure(text="Erreur lecture mémoire.")
            else:
                self.projects_label.configure(text="Mémoire vide.")

        except Exception as e:
            print(f"Erreur Insights Loop: {e}")
            
        self.after(5000, self._update_insights_loop)

# Helper Canvas
def create_rounded_rectangle(self, x1, y1, x2, y2, radius=25, **kwargs):
    points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
    return self.create_polygon(points, **kwargs, smooth=True)
Canvas.create_rounded_rectangle = create_rounded_rectangle