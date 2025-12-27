"""
Module pour lancer des applications et ouvrir des sites web
"""

import subprocess
import os
import webbrowser
from typing import Optional
from core.logger import get_logger

logger = get_logger("app_launcher")


def open_app(application: str) -> str:
    """
    Ouvre une application Windows en utilisant un mapping simple.
    """
    # Dictionnaire d'applications courantes
    APP_MAP = {
        "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "vscode": r"C:\Users\amarz\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "code": r"C:\Users\amarz\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "spotify": r"C:\Users\amarz\AppData\Roaming\Spotify\Spotify.exe",
        "discord": r"C:\Users\amarz\AppData\Local\Discord\app-1.0.9217\Discord.exe",
        "steam": r"C:\Program Files (x86)\Steam\steam.exe",
        "invite de commandes": r"C:\Users\amarz\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\System Tools\Command Prompt.lnk",
        "powershell": r"C:\Users\amarz\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\System Tools\Command Prompt.lnk",
        "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        "outlook": r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
    }

    app = application.lower().strip()

    # Trouver l'app la plus proche
    exe_path = None
    for key in APP_MAP:
        if key in app:
            exe_path = APP_MAP[key]
            break
    
    if not exe_path:
        return f"Je ne connais pas cette application : {application}, Monsieur."

    if not os.path.exists(exe_path):
        return f"L'application '{application}' semble installée ailleurs, Monsieur."

    try:
        subprocess.Popen(exe_path)
        return f"J'ouvre {application}, Monsieur."
    except Exception as e:
        logger.error(f"Erreur lors de l'ouverture de l'application {application}: {e}")
        return f"J'ai rencontré une erreur en ouvrant {application} : {e}."


def open_website(url_or_name: str) -> str:
    """
    Ouvre un site web via le navigateur par défaut.
    Supporte les noms de sites ('youtube', 'tryhackme', 'outlook') et les URLs complètes.
    """
    SITE_MAP = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "tryhackme": "https://tryhackme.com",
        "outlook": "https://outlook.office.com",
        "esigelec": "https://www.esigelec.fr",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com/",
        "github": "https://github.com",
        "wikipedia": "https://wikipedia.org",
        "gemini": "https://gemini.google.com/app?hl=fr",
    }

    u = url_or_name.lower().strip()

    # Si l'utilisateur donne une URL complète :
    if u.startswith("http://") or u.startswith("https://"):
        webbrowser.open(u)
        return f"J'ouvre {u}, Monsieur."

    # Sinon on cherche dans le dictionnaire
    for key in SITE_MAP:
        if key in u:
            url = SITE_MAP[key]
            webbrowser.open(url)
            return f"J'ouvre {key}, Monsieur."

    # Dernière chance : recherche Google
    search_url = f"https://www.google.com/search?q={url_or_name.replace(' ', '+')}"
    webbrowser.open(search_url)
    return (
        f"Je n'ai pas trouvé le site exact, Monsieur. "
        f"J'ai effectué une recherche Google pour : {url_or_name}"
    )

