"""
Module pour la gestion du temps : chronomètre, timer, agenda, dates
Centralise toutes les fonctions liées au temps
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from core.paths import get_memory_dir
from core.logger import get_logger

logger = get_logger("time_management")

# Variables globales pour le chronomètre et le timer
STOPWATCH_START = None       # datetime ou None
STOPWATCH_ACCUM = 0.0        # secondes accumulées
STOPWATCH_RUNNING = False    # bool
TIMER_END = None             # datetime ou None
TIMER_ALERT_TRIGGERED = False  # Pour ne pas annoncer 15 fois la fin du timer


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en texte lisible (X min Y s)."""
    total = int(seconds)
    if total < 0:
        total = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    if h > 0:
        return f"{h} h {m} min {s} s"
    elif m > 0:
        return f"{m} min {s} s"
    else:
        return f"{s} secondes"


def get_time(timezone: Optional[str] = None) -> str:
    """
    Retourne l'heure actuelle au format HH:MM (string).
    """
    try:
        # On essaye d'utiliser zoneinfo si le timezone est fourni
        if timezone:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(timezone)
                now = datetime.now(tz)
            except Exception:
                # Si le timezone est invalide, fallback heure locale
                now = datetime.now()
        else:
            # Par défaut, on considère l'heure de Paris
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo("Europe/Paris")
                now = datetime.now(tz)
            except Exception:
                now = datetime.now()
    except Exception:
        now = datetime.now()

    # On renvoie une chaîne simple, Gemini formulera la phrase
    return now.strftime("%H:%M")


def get_date(timezone: Optional[str] = None) -> str:
    """
    Retourne une date lisible : 'Lundi 3 Février 2025'
    """
    import locale

    # Forcer locale FR
    try:
        locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
    except:
        pass  # Windows fallback

    try:
        if timezone:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(timezone)
                now = datetime.now(tz)
            except:
                now = datetime.now()
        else:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo("Europe/Paris")
                now = datetime.now(tz)
            except:
                now = datetime.now()
    except:
        now = datetime.now()

    # Format : Lundi 3 Février 2025
    try:
        return now.strftime("%A %d %B %Y").capitalize()
    except:
        return now.strftime("%Y-%m-%d")


def manage_stopwatch(action: str = "status") -> str:
    """
    Gère un chronomètre interne : démarrage, arrêt, remise à zéro ou affichage du temps écoulé.
    Actions : start, stop, reset, status.
    """
    global STOPWATCH_START, STOPWATCH_ACCUM, STOPWATCH_RUNNING
    now = datetime.now()
    action = (action or "status").lower()

    # START : on remet à zéro et on démarre
    if action == "start":
        STOPWATCH_START = now
        STOPWATCH_ACCUM = 0.0
        STOPWATCH_RUNNING = True
        return "Chronomètre démarré, Monsieur."

    # STOP : on fige le temps écoulé
    if action == "stop":
        if STOPWATCH_RUNNING and STOPWATCH_START is not None:
            STOPWATCH_ACCUM += (now - STOPWATCH_START).total_seconds()
            STOPWATCH_RUNNING = False
            STOPWATCH_START = None
            return f"Chronomètre arrêté, Monsieur. Temps écoulé : {format_duration(STOPWATCH_ACCUM)}."
        else:
            return "Le chronomètre n'était pas en cours, Monsieur."

    # RESET : on efface tout
    if action == "reset":
        STOPWATCH_START = None
        STOPWATCH_ACCUM = 0.0
        STOPWATCH_RUNNING = False
        return "Le chronomètre a été remis à zéro, Monsieur."

    # STATUS : temps écoulé actuel
    if action == "status":
        elapsed = STOPWATCH_ACCUM
        if STOPWATCH_RUNNING and STOPWATCH_START is not None:
            elapsed += (now - STOPWATCH_START).total_seconds()
        if elapsed <= 0:
            return "Le chronomètre est à zéro, Monsieur."
        return f"Temps écoulé : {format_duration(elapsed)}, Monsieur."

    return "Je n'ai pas compris l'action demandée pour le chronomètre, Monsieur."


def manage_timer(action: str = "status", duration_seconds: Optional[int] = None) -> str:
    """
    Gère un compte à rebours interne : démarrage, consultation du temps restant ou annulation.
    """
    global TIMER_END, TIMER_ALERT_TRIGGERED
    now = datetime.now()
    action = (action or "status").lower()

    # START : lancer un nouveau compte à rebours
    if action == "start":
        if duration_seconds is None or duration_seconds <= 0:
            return "Je n'ai pas compris la durée du compte à rebours, Monsieur."

        TIMER_END = now + timedelta(seconds=duration_seconds)
        TIMER_ALERT_TRIGGERED = False  # on réarme l'alerte
        duration_text = format_duration(duration_seconds)
        return f"Compte à rebours lancé pour {duration_text}, Monsieur."

    # STATUS : savoir où on en est
    if action == "status":
        if TIMER_END is None:
            return "Aucun compte à rebours n'est en cours, Monsieur."
        remaining = (TIMER_END - now).total_seconds()
        if remaining <= 0:
            # Il est terminé, même si le watcher l'a déjà vu
            TIMER_END = None
            TIMER_ALERT_TRIGGERED = False
            return "Le compte à rebours est terminé, Monsieur."
        return f"Il reste {format_duration(remaining)} au compte à rebours, Monsieur."

    # CANCEL : annuler le minuteur
    if action == "cancel":
        if TIMER_END is None:
            return "Il n'y avait aucun compte à rebours en cours, Monsieur."
        TIMER_END = None
        TIMER_ALERT_TRIGGERED = False
        return "J'ai annulé le compte à rebours, Monsieur."

    return "Je n'ai pas compris l'action demandée pour le compte à rebours, Monsieur."


def manage_agenda(action: str, date_iso: Optional[str] = None, description: Optional[str] = None, alarm: bool = False) -> str:
    """
    Gère l'agenda personnel (RDV, rappels).
    Stockage dans cypher_agenda.json.
    """
    AGENDA_FILE = str(get_memory_dir() / "cypher_agenda.json")

    # Charger l'agenda
    if os.path.exists(AGENDA_FILE):
        try:
            with open(AGENDA_FILE, 'r', encoding='utf-8') as f:
                agenda = json.load(f)
        except:
            agenda = []
    else:
        agenda = []

    action = action.lower()

    # --- AJOUTER UN ÉVÉNEMENT ---
    if action == "add":
        if not date_iso or not description:
            return "Il me faut une date (ISO) et une description."
        
        event = {
            "id": str(int(time.time())),  # ID simple basé sur le timestamp
            "date": date_iso,  # Format attendu: YYYY-MM-DD HH:MM
            "description": description,
            "alarm": alarm,
            "status": "pending"
        }
        agenda.append(event)
        
        # Trier par date
        agenda.sort(key=lambda x: x["date"])
        
        with open(AGENDA_FILE, 'w', encoding='utf-8') as f:
            json.dump(agenda, f, indent=4, ensure_ascii=False)
        
        alarm_msg = "avec alarme sonore" if alarm else "sans alarme"
        return f"📅 Événement ajouté : '{description}' le {date_iso} ({alarm_msg})."

    # --- CONSULTER (LISTER) ---
    if action == "list":
        if not agenda:
            return "L'agenda est vide, Monsieur."
        
        # Filtrage intelligent (si date_iso est fourni, on filtre autour, sinon tout le futur)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        upcoming = [e for e in agenda if e["date"] >= now_str]
        
        if not upcoming:
            return "Rien de prévu à l'avenir."
        
        # Si on demande "demain" ou une date précise, on peut filtrer ici,
        # mais le plus simple est de lister les 10 prochains et laisser Gemini résumer.
        report = "📅 Vos prochains événements :\n"
        for e in upcoming[:10]:
            alarm_icon = "🔔" if e.get("alarm") else ""
            report += f"- [{e['date']}] {e['description']} {alarm_icon}\n"
        
        return report

    # --- SUPPRIMER ---
    if action == "delete":
        # On cherche par description (fuzzy) ou date
        if not description:
            return "Quel événement dois-je supprimer ?"
        
        initial_len = len(agenda)
        # On garde ceux qui ne contiennent PAS la description
        agenda = [e for e in agenda if description.lower() not in e["description"].lower()]
        
        if len(agenda) < initial_len:
            with open(AGENDA_FILE, 'w', encoding='utf-8') as f:
                json.dump(agenda, f, indent=4, ensure_ascii=False)
            return f"Événement contenant '{description}' supprimé."
        else:
            return f"Je n'ai pas trouvé d'événement correspondant à '{description}'."

    return "Action agenda inconnue."


def get_timer_end():
    """Retourne TIMER_END pour les watchers externes"""
    return TIMER_END


def get_timer_alert_triggered():
    """Retourne TIMER_ALERT_TRIGGERED pour les watchers externes"""
    return TIMER_ALERT_TRIGGERED


def set_timer_alert_triggered(value: bool):
    """Définit TIMER_ALERT_TRIGGERED pour les watchers externes"""
    global TIMER_ALERT_TRIGGERED
    TIMER_ALERT_TRIGGERED = value


def set_timer_end(value):
    """Définit TIMER_END pour les watchers externes (None pour réinitialiser)"""
    global TIMER_END
    TIMER_END = value

