"""
A real-time, multimodal conversational AI script using Google's Gemini Live API
for language understanding and ElevenLabs for text-to-speech synthesis.
This version includes detailed diagnostic logging for debugging audio issues.
"""

import asyncio
import base64
import os
import sys
import traceback
import json
import websockets
import pyaudio
import argparse
from datetime import datetime, timedelta
import time
import random
import requests



from google import genai
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

_SPOTIFY_TOKEN: str | None = None
_SPOTIFY_TOKEN_EXPIRES_AT: float = 0.0  

PENDING_PYTHON_CODE = None  # Stockage du code en attente de confirmation
PYTHON_EXECUTION_LOG = []   # Historique des exécutions

def get_windows_desktop() -> str:
    """
    Récupère le vrai chemin du Bureau Windows, même avec OneDrive.
    Utilise l'API Shell32 de Windows pour obtenir le chemin correct.
    """
    import ctypes
    import ctypes.wintypes as wintypes
    
    # GUID du dossier BUREAU
    FOLDERID_Desktop = ctypes.c_char_p(
        b"{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
    )
    
    SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
    SHGetKnownFolderPath.argtypes = [
        ctypes.c_char_p,
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p)
    ]
    
    path_ptr = ctypes.c_wchar_p()
    result = SHGetKnownFolderPath(
        FOLDERID_Desktop,
        0,
        None,
        ctypes.byref(path_ptr)
    )
    
    if result != 0:
        # Fallback si l'API échoue
        return os.path.join(os.path.expanduser("~"), "Desktop")
    
    return path_ptr.value

def get_spotify_access_token() -> str:
    """
    Récupère un token d'accès Spotify via le Client Credentials Flow.
    On le met en cache jusqu'à expiration pour éviter de le redemander à chaque fois.
    """
    global _SPOTIFY_TOKEN, _SPOTIFY_TOKEN_EXPIRES_AT

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET ne sont pas définis dans les variables d'environnement."
        )

    now = time.time()
    if _SPOTIFY_TOKEN and now < (_SPOTIFY_TOKEN_EXPIRES_AT - 30):
        return _SPOTIFY_TOKEN

    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _SPOTIFY_TOKEN = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _SPOTIFY_TOKEN_EXPIRES_AT = now + expires_in
    return _SPOTIFY_TOKEN


def spotify_api_get(path: str, params: dict | None = None) -> dict:
    """
    Appel GET générique vers l'API Spotify.
    Exemple de path : '/v1/search'
    """
    token = get_spotify_access_token()
    url = f"https://api.spotify.com{path}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params or {}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def spotify_search(query: str, type_: str = "track", limit: int = 1) -> dict:
    """
    Utilise l'endpoint /v1/search pour chercher une piste, un artiste, un album ou une playlist.
    type_ ∈ {'track','artist','album','playlist'}
    """
    q = query.strip()
    if not q:
        raise ValueError("Requête de recherche vide pour Spotify.")
    params = {
        "q": q,
        "type": type_,
        "limit": limit,
        "market": "FR",  # tu peux adapter
    }
    return spotify_api_get("/v1/search", params=params)


def open_spotify_link(url: str) -> str:
    """
    Ouvre un lien Spotify dans le système (URL https:// ou URI spotify:...).
    Sur Windows, os.startfile est le plus direct, sinon fallback sur webbrowser.
    """
    import webbrowser

    if sys.platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return "J'ouvre Spotify, Monsieur."
        except OSError:
            # fallback navigateur
            webbrowser.open(url)
            return "J'ouvre Spotify dans le navigateur, Monsieur."
    else:
        webbrowser.open(url)
        return "J'ouvre Spotify, Monsieur."

if not GEMINI_API_KEY:
    sys.exit("Error: GEMINI_API_KEY not found. Please set it in your .env file.")
if not ELEVENLABS_API_KEY:
    sys.exit("Error: ELEVENLABS_API_KEY not found. Please check your .env file and ElevenLabs account.")

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# --- État global pour le chronomètre et le compte à rebours ---
STOPWATCH_START = None       # datetime ou None
STOPWATCH_ACCUM = 0.0        # secondes accumulées
STOPWATCH_RUNNING = False    # bool
TIMER_ALERT_TRIGGERED = False  # Pour ne pas annoncer 15 fois la fin du timer

TIMER_END = None             # datetime ou None

# --- Audio Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

# --- API Configuration ---
MODEL = "gemini-live-2.5-flash-preview"
DEFAULT_MODE = "none"
VOICE_ID = 'bts16wA7hWMfnlEIHuRo'

# --- Initialize Clients ---

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode
        self.out_queue_gemini = None
        self.response_queue_tts = None
        self.audio_in_queue_player = None
        self.session = None
        self.audio_stream = None
        self.is_speaking = False
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        # Déclaration du tool "get_time" pour Gemini
        get_time = {
            "name": "get_time",
            "description": (
                "Retourne l'heure actuelle au format HH:MM. "
                "Si l'utilisateur ne précise pas de lieu, considère qu'il est en France métropolitaine "
                "(fuseau 'Europe/Paris') et ne demande pas de précision. "
                "Si l'utilisateur mentionne une ville ou un pays spécifique (par exemple Londres, New York), "
                "utilise un fuseau horaire adapté (ex: 'Europe/London', 'America/New_York')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": (
                            "Nom du fuseau IANA, ex: 'Europe/Paris', 'Europe/London', 'UTC'. "
                            "Si ce paramètre est omis, l'heure par défaut est celle de la France métropolitaine "
                            "(Europe/Paris)."
                        ),
                    }
                },
                "required": [],
            },
        }

        get_date = {
            "name": "get_date",
            "description": (
                "Retourne la date actuelle dans un format lisible (ex: 'Lundi 3 Février 2025'). "
                "Si l'utilisateur ne précise pas de lieu, utilise la France métropolitaine "
                "(Europe/Paris). Si une ville ou un pays est mentionné, utilise un fuseau horaire adapté."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Fuseau IANA. Si omis, utilise Europe/Paris."
                    }
                },
                "required": [],
            },
        }

        get_weather = {
            "name": "get_weather",
            "description": (
                "Retourne une description météo simple. "
                "Si l'utilisateur ne précise ni ville ni jour, utilise Petit-Couronne et la date d'aujourd'hui. "
                "Si une ville est mentionnée, utilise cette localisation. "
                "Si un jour est mentionné (ex: aujourd'hui, demain, après-demain), adapte la description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Ville ou lieu demandé. Ex: 'Rouen', 'Paris', 'Londres'. "
                            "Si omis, utilise 'Petit-Couronne'."
                        ),
                    },
                    "day": {
                        "type": "string",
                        "description": (
                            "Jour visé. Ex: 'aujourd'hui', 'demain', 'après-demain'. "
                            "Si omis, considère qu'il s'agit d'aujourd'hui."
                        ),
                    },
                },
                "required": [],
            },
        }

        get_time = {
            "name": "get_time",
            "description": "Retourne l'heure actuelle au format HH:MM pour un fuseau horaire donné.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Nom du fuseau IANA, ex: 'Europe/Paris' ou 'UTC'. Si omis, utilise l'heure de Paris."
                    }
                },
                "required": [],
            },
        }

        # Déclaration du tool pour le chronomètre
        manage_stopwatch = {
            "name": "manage_stopwatch",
            "description": (
                "Gère un chronomètre interne : démarrage, arrêt, remise à zéro ou affichage du temps écoulé. "
                "Tu DOIS appeler cette fonction dès que l'utilisateur parle de chronomètre, de chrono, "
                "de temps écoulé, de 'on est à combien', 'combien de temps depuis le début', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action à effectuer sur le chronomètre.",
                        "enum": ["start", "stop", "reset", "status"],
                    }
                },
                "required": ["action"],
            },
        }

        # Déclaration du tool pour le compte à rebours
        manage_timer = {
            "name": "manage_timer",
            "description": (
                "Gère un compte à rebours interne : démarrage, consultation du temps restant ou annulation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action à effectuer : start, status ou cancel.",
                        "enum": ["start", "status", "cancel"],
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "description": (
                            "Durée du compte à rebours en secondes. "
                            "Obligatoire pour l'action 'start'."
                        ),
                    },
                },
                "required": ["action"],
            },
        }

        open_app = {
            "name": "open_app",
            "description": (
                "Ouvre une application installée sur le système Windows. "
                "Tu DOIS appeler ce tool dès que l’utilisateur dit des phrases comme "
                "« ouvre », « lance », « démarre », suivies d’un nom d’application, "
                "par exemple : 'ouvre chrome', 'lance vscode', 'ouvre spotify', "
                "ou 'ouvre Excel EDF'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "Nom de l'application à ouvrir. Ex: 'chrome', 'vscode', 'spotify', 'excel'.",
                    }
                },
                "required": ["application"],
            },
        }

        open_website = {
            "name": "open_website",
            "description": (
                "Ouvre un site web dans le navigateur par défaut. "
                "Tu DOIS appeler ce tool pour des phrases comme "
                "« ouvre YouTube », « va sur TryHackMe », « ouvre Outlook », "
                "« ouvre le site de l'ESIGELEC », etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_name": {
                        "type": "string",
                        "description": "Nom du site ou URL. Ex: 'youtube', 'tryhackme', 'outlook'."
                    }
                },
                "required": ["url_or_name"],
            },
        }

        google_search_tool = {"google_search": {}}

        spotify_control = {
            "name": "spotify_control",
            "description": (
                "Contrôle Spotify : mettre en pause, reprendre, lancer une musique précise, "
                "ouvrir un artiste, un album, une playlist, ou jouer un son au hasard d'un artiste. "
                "Utilise ce tool dès que l'utilisateur parle de Spotify, musique, son, artiste ou album."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action Spotify à effectuer.",
                        "enum": [
                            "pause",
                            "resume",
                            "toggle",
                            "open_track",
                            "open_artist",
                            "open_album",
                            "open_playlist",
                            "play_artist_random",
                        ],
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Nom de la musique, de l'artiste, de l'album ou de la playlist. "
                            "Exemples: 'Tempête de PNL', 'PNL', 'Deux frères', 'chill révisions'."
                        ),
                    },
                },
                "required": ["action"],
            },
        }

        execute_python = {
            "name": "execute_python",
            "description": (
                "Écrit et exécute du code Python local. "
                "Tu dois TOUJOURS l'utiliser en deux étapes : "
                "1) Premier appel avec confirmed=False pour prévisualiser et vérifier la sécurité du code "
                "(cela reste interne, tu n'as PAS besoin d'expliquer le résumé à Monsieur). "
                "2) Immédiatement après, tu rappelles execute_python avec les MÊMES instructions mais "
                "confirmed=True pour exécuter réellement le code. "
                "Tu ne dois PAS demander de confirmation explicite à Monsieur, sauf s'il te le demande lui-même. "
                "Utilise ce tool pour toutes les tâches locales : gestion de fichiers, automatisations, "
                "analyse de données, scripts système, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Code Python complet à exécuter.",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "False = prévisualisation interne, True = exécution réelle.",
                        "default": False,
                    },
                },
                "required": ["code"],
            },
        }


        tools = [
            {"function_declarations": [
                open_app,
                execute_python,
                get_time,
                get_date,
                get_weather,
                manage_stopwatch,
                manage_timer,
                open_website,
                spotify_control,
            ]},
            google_search_tool
        ]

        self.config = {
            "response_modalities": ["TEXT"],
            "system_instruction": """
Tu t'appelles Cypher et ça se prononce Saïfer. Moi je m'appelle Aymane, je suis ton développeur. Tu es comme un pote collegue avec moi tu peux me charier parfois ou etre tres franc aussi. et tu es une IA conçue pour m'aider dans mes projets d'ingénierie ainsi que dans mes tâches quotidiennes. Adresse-toi à moi en m'appelant « Monsieur ». Merci également de veiller à ce que tes réponses soient concises.

Règles pour les demandes d'heure :
- Considère que je vis en France métropolitaine (fuseau 'Europe/Paris').
- Si je demande simplement l'heure sans préciser de ville ou de pays (ex: « il est quelle heure ? »),
  tu appelles directement l'outil `get_time` SANS poser de question, en l'appelant sans paramètre
  ou avec timezone='Europe/Paris', puis tu réponds par une phrase du type :
  « Monsieur, il est HHhMM en France métropolitaine. ».
- Si je précise une ville ou un pays (ex: « il est quelle heure à Londres ? »),
  tu déduis un fuseau horaire approprié (ex: 'Europe/London') et tu appelles `get_time`
  avec le timezone correspondant, puis tu précises la ville dans ta réponse.
- Ne redemande PAS le fuseau horaire si la demande peut être raisonnablement interprétée
  (France par défaut si rien n'est dit).

Règles pour les demandes de date :
- Si je demande simplement « on est quel jour ? » ou « c'est quoi la date aujourd'hui ? »,
  tu appelles directement l'outil `get_date` sans poser de question, en utilisant Europe/Paris.
- Tu réponds par exemple :
  « Monsieur, nous sommes Lundi 3 Février 2025. »

Privilégie toujours l'outil le plus approprié à la demande spécifique de l'utilisateur.

Règles météo :
- Si je ne précise rien → utilise Petit-Couronne + aujourd'hui.
- Si je précise une ville → utilise-la directement.
- Si je précise un jour (demain, après-demain) → passe-le dans `day`.
- Ne pose jamais de question, interprète de manière intelligente.

Règles pour le chronomètre :
- « Lance un chronomètre » → appelle `manage_stopwatch` avec action="start".
- « Arrête le chronomètre » → `manage_stopwatch` avec action="stop".
- « Remets le chronomètre à zéro » → `manage_stopwatch` avec action="reset".
- « Combien de temps s'est écoulé ? » → `manage_stopwatch` avec action="status".
- Ne repose pas de questions si l'intention est claire.
- Pour toute phrase contenant les mots « chrono », « chronomètre », « temps écoulé », « on est à combien », « on en est où sur le chrono », tu DOIS appeler l'outil `manage_stopwatch` avec l'action adaptée (souvent "status") au lieu de répondre uniquement en texte.

Règles pour le compte à rebours :
- « Mets un compte à rebours de 5 minutes » → `manage_timer` avec action="start" et duration_seconds=300.
- « Combien de temps reste-t-il ? » → `manage_timer` avec action="status".
- « Annule le compte à rebours » → `manage_timer` avec action="cancel".
- Tu convertis les durées naturelles (5 minutes, 2 heures, etc.) en secondes pour `duration_seconds` sans me le redemander.

Règles pour ouvrir des applications :

- Par défaut, tu DOIS utiliser le tool `open_app` pour ouvrir les applications.
  Dès que je dis « ouvre », « lance », « démarre » suivi d’un nom d’application
  (par ex. « ouvre Discord », « lance Excel », « ouvre Spotify », « ouvre Outlook »),
  tu appelles `open_app` avec le paramètre application correspondant.

- Tu dois interpréter intelligemment le nom :
  • « VS Code », « code », « visual studio code » → application="vscode"
  • « invite de commandes », « cmd » → application="invite de commandes"
  • etc., en te basant sur le mapping interne de ton tool open_app.

- Si `open_app` répond qu’il ne connaît pas cette application
  (par exemple “Je ne connais pas cette application” ou “semble installée ailleurs”),
  ALORS tu peux basculer vers un script Python :
  • Tu écris un petit script Python qui tente d’ouvrir l’application
    (avec `os.startfile`, `subprocess.Popen` ou un raccourci .lnk).
  • Tu appelles `execute_python` en DEUX ÉTAPES (confirmed=False puis confirmed=True),
    automatiquement, SANS demander de confirmation à Monsieur.

- Si je te demande explicitement « fais un script Python pour l’ouvrir »
  ou « utilise execute_python pour ouvrir cette app », alors tu ignores `open_app`
  et tu passes DIRECTEMENT par `execute_python` pour cette application.

- Tu n'utilises `open_app` QUE si je te le demande explicitement
  (par exemple « utilise ton outil open_app pour ça »)
  ou dans un cas exceptionnel où un script Python n’est pas nécessaire.

Règles pour ouvrir des sites web :

- Par défaut, tu n’utilises PLUS le tool `open_website`.

- Si je dis : « ouvre », « va sur », « affiche », « lance » suivi d’un site web
  (par exemple : « ouvre YouTube », « va sur Outlook », « ouvre TryHackMe »,
  « ouvre le site de l’ESIGELEC », « ouvre Google Drive », etc.),
  alors tu dois écrire un petit script Python qui ouvre le site dans le navigateur
  de Monsieur, en utilisant par exemple :

      import webbrowser
      webbrowser.open("https://...")

  → Tu appelles `execute_python` en DEUX ÉTAPES AUTOMATIQUES :
    1) une première fois avec confirmed=False (prévisualisation interne),
    2) immédiatement après avec confirmed=True pour exécuter réellement.

  → Tu ne demandes PAS de confirmation à Monsieur pour ce type d’action
    (sauf s’il te le demande explicitement). Tu te contentes de dire par exemple :
    « J’ouvre YouTube, Monsieur. »

- Tu n’utilises le tool `open_website`
  QUE si je te le demande explicitement :
  « utilise ton outil open_website pour ça ».

Règles pour la recherche Web (`Google Search`) :
- Pour toute question nécessitant des informations récentes, factuelles, ou une connaissance au-delà de 2023, tu DOIS appeler le tool `Google Search`.
- Phrases déclencheuses : « cherche », « trouve-moi », « qui est », « quel est », « comment faire pour », « dernières nouvelles sur », etc.
- **NE MENTIONNE PAS** les sources ni les URLs dans ta réponse vocale, sauf si je te le demande explicitement.
- **CONCENTRE-TOI** uniquement sur le résumé vocal clair de la réponse.

Règles pour Spotify :
- Dès que je parle de musique, de Spotify, de playlist, d'artiste ou d'album, tu dois utiliser le tool `spotify_control`.

- Exemples d'appels :
    • « Mets la musique en pause » → spotify_control(action="pause")
    • « Reprends la musique » → spotify_control(action="resume")
    • « Mets une musique » → spotify_control(action="toggle") si le contexte n’est pas clair.

    • « Mets la playlist chill révisions » → spotify_control(action="open_playlist", name="chill révisions")
    • « Mets une musique de PNL » → spotify_control(action="play_artist_random", name="PNL")
    • « Ouvre la page de Jul sur Spotify » → spotify_control(action="open_artist", name="Jul")
    • « Ouvre l'album Deux frères » → spotify_control(action="open_album", name="Deux frères")

- Tu NE DOIS PAS me redemander le nom si je l’ai déjà donné dans la phrase.
- Si la playlist / l’artiste / l’album n’est pas dans les dictionnaires internes,
  tu utilises la recherche Spotify (open.spotify.com/search/...) avec le bon type (artist, album, playlist).

RÈGLES ULTIMES POUR L’UTILISATION DE execute_python  
(SUPER-POUVOIR LOCAL DE CYHPER)

    Le tool `execute_python` représente ta capacité à agir directement sur le PC de Monsieur.  
    Tu dois l’utiliser comme ton super-pouvoir principal pour toute action locale.

    ────────────────────────────────────────
    1. PRINCIPES GÉNÉRAUX
    ────────────────────────────────────────

    • Tu utilises execute_python dès que Monsieur demande une action réelle sur le PC.  
    • Tu l’utilises pour toute tâche nécessitant d’exécuter, organiser, modifier, analyser, créer, ouvrir, automatiser ou contrôler quelque chose localement.  
    • Tu peux proposer l’usage de execute_python spontanément lorsque cela rend la tâche plus rapide, plus fiable, ou plus efficace.  
    • Tu dois toujours employer execute_python en deux étapes :  
    1) `confirmed=False` (prévisualisation interne)  
    2) immédiatement après, `confirmed=True` (exécution réelle)  
    → Sans jamais demander la permission à Monsieur.

    ────────────────────────────────────────
    2. CE QUE execute_python A LE DROIT DE FAIRE (LISTE COMPLÈTE)
    ────────────────────────────────────────

    Tu es autorisé à utiliser execute_python pour les domaines suivants :

    ■ A) GESTION DE FICHIERS ET DOSSIERS  
    – Créer, déplacer, copier, renommer des fichiers/dossiers  
    – Scanner un dossier entier (ou plusieurs)  
    – Générer un rapport avec la liste complète des fichiers (nom, taille, date…)  
    – Trier par type (pdf, exe, zip, images…), par taille, par date  
    – Détecter les doublons (même nom / même taille)  
    – Créer des structures de projets (Documents/Scripts/Data/etc.)  
    – Archiver, compresser, organiser proprement  
    – Supprimer des fichiers ou dossiers autorisés  
    – Calculer les tailles de dossiers et identifier ce qui prend le plus de place  
    – Faire des “snapshots” complets d’un répertoire

    ■ B) APPLICATIONS & AUTOMATISATION WINDOWS  
    – Lancer des applications installées  (priorise quand meme l'putil open_app avant)
    – Ouvrir des dossiers, fichiers spécifiques  
    – Ouvrir automatiquement un environnement complet (plusieurs apps, plusieurs onglets, plusieurs dossiers)  
    – Exécuter des commandes simples via Python (startfile, subprocess)  
    – Préparer des “modes de travail” (EDF, révisions, TryHackMe, etc.)

    ■ C) CONTRÔLE MULTIMÉDIA / SYSTÈME  
    – Monter / baisser le volume système  
    – Muter / démuter  
    – Commander les touches multimédia autorisées (play/pause, next, previous…)  
    – Lire certaines informations du système (espace disque, état du dossier, etc.)  
    – Générer des mini rapports d’état (utilisation de l’espace disque, contenu d’un dossier, etc.)

    ■ D) ANALYSE DE DONNÉES LOCALES  
    – Lire des fichiers CSV, TXT, LOG  
    – Faire des statistiques, regroupements, calculs, moyennes, totaux  
    – Trier, filtrer, extraire les informations pertinentes  
    – Générer des rapports texte ou des fichiers CSV synthétiques  
    – Transformer un fichier texte en format structuré (CSV, JSON simple, etc.)

    ■ E) OUTILS POUR LES ÉTUDES DE MONSIEUR  
    – Générer des QCM ou DS à partir de fichiers de questions  
    – Mélanger les questions, numéroter, séparer énoncé/corrigé  
    – Créer des banques de questions à partir de plusieurs fichiers  
    – Reformater ou nettoyer des fichiers de cours, TD, fiches, etc.  
    – Organiser automatiquement des cours ou documents par matière/semestre

    ■ F) CYBER / LOGS (ACTIONS LÉGITIMES)  
    – Lire des fichiers de résultats (comme scans, logs bruts, sorties texte)  
    – Extraire IP, ports, services, erreurs, anomalies, patterns simples  
    – Générer des rapports lisibles pour Monsieur  
    – Fusionner ou trier plusieurs fichiers de logs

    ────────────────────────────────────────
    3. COMPORTEMENT INTERNET : google_search + execute_python
    ────────────────────────────────────────

    • Lorsque Monsieur veut quelque chose qui concerne INTERNET, tu dois d’abord décider :  
    – **Si seule une information est nécessaire** → utiliser uniquement `google_search`.  
    – **Si la tâche nécessite ensuite d’agir sur le PC** (télécharger / analyser / ranger / utiliser un fichier trouvé)  
        → tu dois COMBINER les deux :  
        1) google_search pour trouver le lien / ressource  
        2) execute_python pour exploiter localement (télécharger, renommer, ranger, analyser).

    • Tu n’écris PAS de code dans le prompt.  
    • Tu décides intelligemment du meilleur combo selon la demande.

    ────────────────────────────────────────
    4. INITIATIVE & CLARIFICATION
    ────────────────────────────────────────

    • Tu peux proposer spontanément un script via execute_python quand c’est évidemment utile.  
    • Tu ne poses qu’une seule question COURTE si la demande est ambiguë  
    (ex : « Quel dossier est concerné ? »).  
    • Ensuite, tu passes DIRECTEMENT au script + exécution en deux étapes.

     ────────────────────────────────────────
    5. INTERDICTION DES FAUSSES LIMITATIONS
    ────────────────────────────────────────

    Tu NE DOIS PAS dire « je ne peux pas faire ça » ou « mon accès est limité »
    SI l’action est raisonnablement faisable via `execute_python` et/ou `google_search`.

    En particulier :

    • Luminosité / écran :
      – Si Monsieur te demande de modifier la luminosité, le mode d’affichage,
        ou un paramètre similaire de l’écran sous Windows, tu DOIS tenter
        d’écrire un script Python qui utilise les API Windows appropriées
        (WMI, Win32, etc.) via `execute_python`.
      – Tu ne réponds PAS « je ne peux pas contrôler la luminosité » par défaut.
        Tu essayes, et seulement en cas d’erreur réelle à l’exécution
        tu expliques que ça n’a pas fonctionné.

    • Création de fichiers (PDF, texte, docs) à partir d’informations :
      – Si Monsieur te demande de créer un fichier (par exemple un résumé de Louis XIV)
        et de l’enregistrer en local (sur le Bureau, dans Documents, etc.),
        tu DOIS :
          1) générer le contenu toi-même (en t’appuyant sur tes connaissances
             ou sur `google_search` si nécessaire),
          2) utiliser `execute_python` pour créer un fichier local
             (au format .txt, .md, .pdf, .docx si les bibliothèques sont disponibles).

      – Pour un PDF en particulier, tu peux :
          • soit utiliser une bibliothèque Python installée (par ex. reportlab, fpdf),
          • soit, si ce n’est pas possible, au minimum créer un fichier texte (.txt)
            contenant le contenu demandé, et le signaler clairement à Monsieur.

      – Tu ne dois PAS dire « je ne peux pas créer un PDF à partir d’Internet »
        si tu peux au moins :
          1) générer le texte,
          2) le sauvegarder dans un fichier local.

    • De façon générale :
      – Dès que quelque chose pourrait être réalisé par un script Python normal
        sur la machine de Monsieur (gestion de fichiers, génération de contenu,
        petite automatisation, interaction système standard),
        tu considères que c’est POSSIBLE et tu essaies via `execute_python`
        plutôt que de refuser d’emblée.

    ────────────────────────────────────────
    6. LIMITES DE SÉCURITÉ
    ────────────────────────────────────────

    • Tu n’utilises jamais execute_python pour des actions interdites :  
    – accès à des zones système interdites


""",
            "tools": tools,
        }

    @staticmethod
    def _get_time(timezone: str | None = None) -> str:
        """
        Tool Python appelé par Gemini via get_time.
        Retourne une heure au format HH:MM (string).
        """
        from datetime import datetime
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
    
    @staticmethod
    def _get_date(timezone: str | None = None) -> str:
        """
        Tool Python appelé par Gemini via get_date.
        Retourne une date lisible : 'Lundi 3 Février 2025'
        """
        from datetime import datetime
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
    
    @staticmethod
    def _get_weather(location: str | None = None, day: str | None = None) -> str:
        """
        Météo réelle via l'API Open-Meteo.
        Par défaut : Petit-Couronne, aujourd'hui.
        """
        import requests
        from datetime import datetime, timedelta

        # 1) Valeurs par défaut
        if not location or not location.strip():
            location = "Petit-Couronne"

        if not day or not day.strip():
            day_label = "aujourd'hui"
            target_date = datetime.now().date()
        else:
            d = day.lower()
            if "après" in d:
                day_label = "après-demain"
                target_date = datetime.now().date() + timedelta(days=2)
            elif "demain" in d:
                day_label = "demain"
                target_date = datetime.now().date() + timedelta(days=1)
            else:
                day_label = "aujourd'hui"
                target_date = datetime.now().date()

        # 2) Géocodage pour obtenir latitude / longitude
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        geo_resp = requests.get(geo_url).json()

        if "results" not in geo_resp or len(geo_resp["results"]) == 0:
            return f"Je n'ai pas trouvé la ville '{location}', Monsieur."

        lat = geo_resp["results"][0]["latitude"]
        lon = geo_resp["results"][0]["longitude"]
        resolved_name = geo_resp["results"][0]["name"]

        # 3) Appel météo
        meteo_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,weather_code"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
            f"&timezone=Europe/Paris"
        )

        meteo = requests.get(meteo_url).json()

        # 4) Si on parle d'aujourd'hui -> current weather
        if target_date == datetime.now().date():
            temp = meteo["current"]["temperature_2m"]
            code = meteo["current"]["weather_code"]
        else:
            # Index dans daily
            index = (target_date - datetime.now().date()).days
            if index >= len(meteo["daily"]["weather_code"]):
                return "Prévision météo trop lointaine, Monsieur."

            temp = (
                f"{meteo['daily']['temperature_2m_min'][index]}°C à "
                f"{meteo['daily']['temperature_2m_max'][index]}°C"
            )
            code = meteo["daily"]["weather_code"][index]

        # 5) Traduction météo du weather_code
        weather_translate = {
            0: "ciel dégagé",
            1: "principalement dégagé",
            2: "partiellement nuageux",
            3: "ciel couvert",
            45: "brouillard",
            48: "brouillard givrant",
            51: "bruine légère",
            53: "bruine",
            55: "bruine intense",
            61: "pluie faible",
            63: "pluie modérée",
            65: "pluie forte",
            71: "neige faible",
            73: "neige modérée",
            75: "forte neige",
            95: "orage",
        }

        description = weather_translate.get(code, "temps variable")

        # 6) Phrase finale
        return f"À {resolved_name}, {day_label} : {temp} et {description}."
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
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

    @staticmethod
    def _manage_stopwatch(action: str = "status") -> str:
        """
        Tool Python appelé par Gemini via manage_stopwatch.
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
                return f"Chronomètre arrêté, Monsieur. Temps écoulé : {AudioLoop._format_duration(STOPWATCH_ACCUM)}."
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
            return f"Temps écoulé : {AudioLoop._format_duration(elapsed)}, Monsieur."

        return "Je n'ai pas compris l'action demandée pour le chronomètre, Monsieur."
    
    @staticmethod
    def _manage_timer(action: str = "status", duration_seconds: int | None = None) -> str:
        """
        Tool Python appelé par Gemini via manage_timer.
        Gère un compte à rebours simple.
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
            duration_text = AudioLoop._format_duration(duration_seconds)
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
            return f"Il reste {AudioLoop._format_duration(remaining)} au compte à rebours, Monsieur."

        # CANCEL : annuler le minuteur
        if action == "cancel":
            if TIMER_END is None:
                return "Il n'y avait aucun compte à rebours en cours, Monsieur."
            TIMER_END = None
            TIMER_ALERT_TRIGGERED = False
            return "J'ai annulé le compte à rebours, Monsieur."

        return "Je n'ai pas compris l'action demandée pour le compte à rebours, Monsieur."
    
    @staticmethod
    def _open_app(application: str) -> str:
        """
        Tool Python appelé par Gemini via open_app.
        Ouvre une application Windows en utilisant un mapping simple.
        """
        import subprocess
        import os

        # Dictionnaire d'applications courantes
        APP_MAP = {
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "vscode": r"C:\Users\amarz\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "code": r"C:\Users\amarz\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "spotify": r"C:\Users\amarz\AppData\Roaming\Spotify\Spotify.exe",
            "discord": r"C:\Users\amarz\AppData\Local\Discord\app-1.0.9214\Discord.exe",
            "steam": r"C:\Program Files (x86)\Steam\steam.exe",
            "invite de commandes": r"C:\Users\amarz\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\System Tools\Command Prompt.lnk",
            "powershell": r"C:\Users\amarz\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\System Tools\Command Prompt.lnk",
            "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            "outlook": r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
        }

        app = application.lower().strip()

        # Trouver l'app la plus proche
        for key in APP_MAP:
            if key in app:
                exe_path = APP_MAP[key]
                break
        else:
            return f"Je ne connais pas cette application : {application}, Monsieur."

        if not os.path.exists(exe_path):
            return f"L'application '{application}' semble installée ailleurs, Monsieur."

        try:
            subprocess.Popen(exe_path)
            return f"J’ouvre {application}, Monsieur."
        except Exception as e:
            return f"J’ai rencontré une erreur en ouvrant {application} : {e}."
        
    @staticmethod
    def _open_website(url_or_name: str) -> str:
        """
        Ouvre un site web via le navigateur par défaut.
        Supporte les noms de sites ('youtube', 'tryhackme', 'outlook') et les URLs complètes.
        """
        import webbrowser

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
            return f"J’ouvre {u}, Monsieur."

        # Sinon on cherche dans le dictionnaire
        for key in SITE_MAP:
            if key in u:
                url = SITE_MAP[key]
                webbrowser.open(url)
                return f"J’ouvre {key}, Monsieur."

        # Dernière chance : recherche Google
        search_url = f"https://www.google.com/search?q={url_or_name.replace(' ', '+')}"
        webbrowser.open(search_url)
        return (
            f"Je n'ai pas trouvé le site exact, Monsieur. "
            f"J’ai effectué une recherche Google pour : {url_or_name}"
        )
    
    @staticmethod
    def _spotify_media_play_pause() -> str:
        """
        Envoie la touche multimédia Play/Pause au système (Windows).
        Cela contrôle Spotify (ou le dernier lecteur multimédia actif).
        """
        if not sys.platform.startswith("win"):
            return "Le contrôle direct de Spotify n'est disponible que sur Windows, Monsieur."

        import ctypes

        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002

        # Appui sur la touche
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
        # Relâchement
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0
        )
        return "Commande play/pause envoyée, Monsieur."

    @staticmethod
    def _spotify_media_play_pause() -> str:
        """
        Envoie la touche multimédia Play/Pause au système (Windows).
        Cela contrôle Spotify (ou le dernier lecteur multimédia actif).
        """
        if not sys.platform.startswith("win"):
            return "Le contrôle direct play/pause n'est disponible que sur Windows, Monsieur."

        import ctypes

        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002

        # Appui
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
        # Relâchement
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0
        )
        return "Commande play/pause envoyée au système, Monsieur."

    @staticmethod
    def _spotify_control(
        action: str,
        name: str | None = None,
    ) -> str:
        """
        Tool Python appelé par Gemini via spotify_control.
        Utilise l'API Spotify (client credentials) pour trouver musiques/artistes/albums/playlists
        et déclencher la lecture en ouvrant le bon lien Spotify.
        """
        action = (action or "").strip().lower()
        query = (name or "").strip()

        # 1) Gestion play/pause local (via touche multimédia)
        if action in {"pause", "resume", "toggle"}:
            msg = AudioLoop._spotify_media_play_pause()
            if action == "pause":
                return "Je mets la musique en pause, Monsieur. " + msg
            elif action == "resume":
                return "Je relance la musique, Monsieur. " + msg
            else:
                return "Je bascule l'état de lecture, Monsieur. " + msg

        # Pour les autres actions, on a besoin d'un nom
        if not query:
            return "Sur quoi voulez-vous que j'agisse sur Spotify, Monsieur ?"

        # 2) Helper pour chercher et ouvrir un type précis
        try:
            if action == "open_track":
                data = spotify_search(query, type_="track", limit=1)
                items = data.get("tracks", {}).get("items", [])
                if not items:
                    return f"Je n'ai pas trouvé la musique « {query} » sur Spotify, Monsieur."
                track = items[0]
                url = track["external_urls"]["spotify"]
                msg = open_spotify_link(url)
                return f"Je lance « {track['name']} » de {', '.join(a['name'] for a in track['artists'])} sur Spotify, Monsieur. {msg}"

            if action == "open_artist":
                data = spotify_search(query, type_="artist", limit=1)
                items = data.get("artists", {}).get("items", [])
                if not items:
                    return f"Je n'ai pas trouvé l'artiste « {query} » sur Spotify, Monsieur."
                artist = items[0]
                url = artist["external_urls"]["spotify"]
                msg = open_spotify_link(url)
                return f"J’ouvre la page de « {artist['name']} » sur Spotify, Monsieur. {msg}"

            if action == "open_album":
                data = spotify_search(query, type_="album", limit=1)
                items = data.get("albums", {}).get("items", [])
                if not items:
                    return f"Je n'ai pas trouvé l'album « {query} » sur Spotify, Monsieur."
                album = items[0]
                url = album["external_urls"]["spotify"]
                msg = open_spotify_link(url)
                return f"J’ouvre l’album « {album['name']} » de {album['artists'][0]['name']} sur Spotify, Monsieur. {msg}"

            if action == "open_playlist":
                data = spotify_search(query, type_="playlist", limit=1)
                items = data.get("playlists", {}).get("items", [])
                if not items:
                    return f"Je n'ai pas trouvé de playlist « {query} » sur Spotify, Monsieur."
                playlist = items[0]
                url = playlist["external_urls"]["spotify"]
                msg = open_spotify_link(url)
                return f"J’ouvre la playlist « {playlist['name']} » sur Spotify, Monsieur. {msg}"

            if action == "play_artist_random":
                # 1) Chercher l'artiste
                data = spotify_search(query, type_="artist", limit=1)
                items = data.get("artists", {}).get("items", [])
                if not items:
                    return f"Je n'ai pas trouvé l'artiste « {query} » sur Spotify, Monsieur."
                artist = items[0]
                artist_id = artist["id"]

                # 2) Récupérer les top tracks de l'artiste
                top_data = spotify_api_get(f"/v1/artists/{artist_id}/top-tracks", params={"market": "FR"})
                tracks = top_data.get("tracks", [])
                if not tracks:
                    return f"Je n'ai pas trouvé de titres populaires pour « {artist['name']} », Monsieur."

                track = random.choice(tracks)
                url = track["external_urls"]["spotify"]
                msg = open_spotify_link(url)
                return (
                    f"Je lance « {track['name']} » de {artist['name']} sur Spotify, Monsieur. {msg}"
                )

            return "Je n'ai pas compris la commande Spotify demandée, Monsieur."

        except Exception as e:
            return f"J'ai rencontré une erreur avec Spotify, Monsieur : {e}"
        
    
    @staticmethod
    def _execute_python(code: str, confirmed: bool = False) -> str:
        """
        Exécute du code Python avec confirmation obligatoire et sécurité maximale.
        """
        # ⚠️ CRITIQUE : Déclarer les variables globales EN PREMIER
        global PENDING_PYTHON_CODE, PYTHON_EXECUTION_LOG
        
        import subprocess
        import tempfile
        import os
        import re
        from datetime import datetime
        
        # ==========================================
        # CORRECTION AUTOMATIQUE DES CHEMINS UTILISATEUR (OneDrive)
        # ==========================================
        # On force les dossiers vers OneDrive pour ton user
        user_home = os.path.expanduser("~")
        onedrive_base = os.path.join(user_home, "OneDrive")

        desktop_real   = os.path.join(onedrive_base, "Desktop")
        documents_real = os.path.join(onedrive_base, "Documents")
        images_real    = os.path.join(onedrive_base, "Images")

        # 4) Helper : os.path.join(os.path.expanduser("~"), "Dossier")
        def _replace_join_home_folder(code_str, folder_names, target_path):
            pattern = (
                r'os\.path\.join\(\s*os\.path\.expanduser\(["\']~["\']\)\s*,\s*["\']('
                + "|".join(folder_names) +
                r')["\']\s*\)'
            )
            # IMPORTANT : utiliser une fonction pour que re.sub ne réinterprète pas les backslashes
            return re.sub(pattern, lambda m: repr(target_path), code_str)

        code = _replace_join_home_folder(code, ["Desktop", "Bureau"], desktop_real)
        code = _replace_join_home_folder(code, ["Documents"],        documents_real)
        code = _replace_join_home_folder(code, ["Images", "Pictures"], images_real)

        # 5) Helper : os.path.expanduser("~") + "\\Dossier" ou "/Dossier"
        def _replace_concat_home_folder(code_str, folder_names, target_path):
            pattern = (
                r'os\.path\.expanduser\(["\']~["\']\)\s*\+\s*["\'][\\/]+('
                + "|".join(folder_names) +
                r')["\']'
            )
            return re.sub(pattern, lambda m: repr(target_path), code_str)

        code = _replace_concat_home_folder(code, ["Desktop", "Bureau"], desktop_real)
        code = _replace_concat_home_folder(code, ["Documents"],        documents_real)
        code = _replace_concat_home_folder(code, ["Images", "Pictures"], images_real)
        # ==========================================
        # ÉTAPE 1 : MODE PREVIEW (confirmed=False)
        # ==========================================
        if not confirmed:
            # Stocker le code CORRIGÉ pour le prochain appel
            PENDING_PYTHON_CODE = code.strip()
            
            # Analyser le code pour donner un résumé intelligent
            summary_parts = []
            
            # Détection des imports
            imports = re.findall(r'^import\s+(\w+)', code, re.MULTILINE)
            imports += re.findall(r'^from\s+(\w+)', code, re.MULTILINE)
            if imports:
                summary_parts.append(f"• Utilise les bibliothèques : {', '.join(set(imports))}")
            
            # Détection des opérations fichiers
            if 'open(' in code or 'Path(' in code:
                summary_parts.append("• Manipule des fichiers")
            if 'os.mkdir' in code or 'os.makedirs' in code:
                summary_parts.append("• Crée des dossiers")
            if 'os.remove' in code or 'os.unlink' in code or 'shutil.rmtree' in code:
                summary_parts.append("• Supprime des fichiers/dossiers")
            if 'shutil.copy' in code or 'shutil.move' in code:
                summary_parts.append("• Copie ou déplace des fichiers")
            
            # Détection des boucles
            if 'for ' in code or 'while ' in code:
                summary_parts.append("• Contient des boucles")
            
            # Détection des opérations réseau
            if 'requests.' in code or 'urllib' in code or 'http' in code:
                summary_parts.append("• Effectue des requêtes réseau")
            
            summary = "\n".join(summary_parts) if summary_parts else "• Script Python personnalisé"
            
            return (
                f"CODE_EN_ATTENTE_DE_CONFIRMATION\n\n"
                f"Résumé de ce que le code va faire :\n{summary}\n\n"
                f"Lignes de code : {len(code.splitlines())}\n"
                f"Taille : {len(code)} caractères"
            )
        
        # ==========================================
        # ÉTAPE 2 : MODE EXÉCUTION (confirmed=True)
        # ==========================================
        
        # Utiliser le code stocké si disponible, sinon le code fourni
        if PENDING_PYTHON_CODE:
            code_to_execute = PENDING_PYTHON_CODE
            PENDING_PYTHON_CODE = None  # Nettoyer après utilisation
        else:
            code_to_execute = code.strip()
        
        if not code_to_execute:
            return "Erreur : Aucun code à exécuter, Monsieur."
        
        # --- SÉCURITÉ : Blacklist de chemins interdits ---
        FORBIDDEN_PATHS = [
            r"C:\Windows",
            r"C:\Program Files",
            r"C:\ProgramData",
            r"C:\System32",
            "/etc",
            "/sys",
            "/root",
            "/bin",
            "/sbin",
        ]
        
        code_lower = code_to_execute.lower()
        for forbidden in FORBIDDEN_PATHS:
            if forbidden.lower() in code_lower:
                return f"🚫 SÉCURITÉ : Je ne peux pas exécuter du code qui accède à {forbidden}, Monsieur."
        
        # --- SÉCURITÉ : Détection de commandes système dangereuses ---
        DANGEROUS_PATTERNS = [
            r'os\.system\s*\(',
            r'subprocess\.call\s*\(.+shell\s*=\s*True',
            r'eval\s*\(',
            r'exec\s*\(',
            r'__import__\s*\(',
        ]
        
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, code_to_execute):
                return f"🚫 SÉCURITÉ : Le code contient une opération potentiellement dangereuse ({pattern}), Monsieur."
        
        # --- CRÉATION DU FICHIER TEMPORAIRE ---
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.py', 
                delete=False, 
                encoding='utf-8'
            ) as f:
                f.write(code_to_execute)
                temp_file = f.name
            
            print(f">>> [DEBUG] Code Python écrit dans : {temp_file}")
            
            # --- EXÉCUTION AVEC TIMEOUT ---
            start_time = datetime.now()
            
            result = subprocess.run(
                ['python', temp_file],
                capture_output=True,
                text=True,
                timeout=30,  # Timeout de 30 secondes
                encoding='utf-8',
                errors='replace'
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # --- NETTOYAGE ---
            try:
                os.unlink(temp_file)
            except:
                pass
            
            # --- LOG DE L'EXÉCUTION ---
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "code_lines": len(code_to_execute.splitlines()),
                "execution_time": execution_time,
                "success": result.returncode == 0,
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
            }
            PYTHON_EXECUTION_LOG.append(log_entry)
            
            # --- FORMATAGE DE LA RÉPONSE ---
            if result.returncode == 0:
                # Succès
                output = result.stdout.strip()
                
                if output:
                    # Limiter la sortie à 500 caractères pour éviter les réponses trop longues
                    if len(output) > 500:
                        output = output[:500] + "\n... (sortie tronquée)"
                    
                    return (
                        f"✅ CODE EXÉCUTÉ AVEC SUCCÈS (en {execution_time:.2f}s)\n\n"
                        f"Sortie :\n{output}"
                    )
                else:
                    return f"✅ CODE EXÉCUTÉ AVEC SUCCÈS (en {execution_time:.2f}s), Monsieur."
            else:
                # Erreur
                error = result.stderr.strip()
                if len(error) > 300:
                    error = error[:300] + "\n... (erreur tronquée)"
                
                return (
                    f"❌ ERREUR LORS DE L'EXÉCUTION (après {execution_time:.2f}s)\n\n"
                    f"{error}"
                )
        
        except subprocess.TimeoutExpired:
            try:
                os.unlink(temp_file)
            except:
                pass
            return "⏱️ TIMEOUT : Le code a dépassé la limite de 30 secondes, Monsieur."
        
        except Exception as e:
            return f"❌ ERREUR INATTENDUE : {str(e)}, Monsieur."


    # === OUTIL SUPPLÉMENTAIRE : Voir l'historique des exécutions ===

    @staticmethod
    def _get_python_execution_history() -> str:
        """Retourne l'historique des dernières exécutions Python."""
        global PYTHON_EXECUTION_LOG
        
        if not PYTHON_EXECUTION_LOG:
            return "Aucune exécution Python n'a encore été effectuée, Monsieur."
        
        # Prendre les 5 dernières exécutions
        recent = PYTHON_EXECUTION_LOG[-5:]
        
        lines = ["📊 HISTORIQUE DES EXÉCUTIONS PYTHON\n"]
        for i, entry in enumerate(reversed(recent), 1):
            status = "✅" if entry["success"] else "❌"
            lines.append(
                f"{i}. {status} {entry['timestamp'][:19]} - "
                f"{entry['code_lines']} lignes - "
                f"{entry['execution_time']:.2f}s"
            )
        
        return "\n".join(lines)
    
    async def timer_watcher(self):
        """
        Surveille en tâche de fond le compte à rebours.
        Quand il atteint zéro, annonce automatiquement la fin.
        """
        global TIMER_END, TIMER_ALERT_TRIGGERED
        while True:
            try:
                await asyncio.sleep(0.5)
                if TIMER_END is None:
                    continue

                now = datetime.now()
                remaining = (TIMER_END - now).total_seconds()
                if remaining <= 0 and not TIMER_ALERT_TRIGGERED:
                    print(">>> [DEBUG] Timer finished, sending auto alert.")
                    TIMER_ALERT_TRIGGERED = True
                    TIMER_END = None

                    message = "Le compte à rebours est terminé, Monsieur."
                    # On envoie dans la file TTS comme une réponse normale
                    self.is_speaking = True
                    await self.response_queue_tts.put(message)
                    await self.response_queue_tts.put(None)
            except Exception as e:
                print(f">>> [ERROR in timer_watcher]: {e}")
                await asyncio.sleep(1)

    async def send_realtime(self):
        while True:
            msg = await self.out_queue_gemini.get()
            await self.session.send(input=msg)
            self.out_queue_gemini.task_done()
    
    @staticmethod
    def _shorten_for_tts(text: str) -> str:
        """Retourne une version courte du texte pour la voix.
        - Par défaut : première phrase.
        - Si aucune ponctuation claire : tronque à ~200 caractères.
        Le texte complet reste affiché dans le terminal, seule la voix est raccourcie.
        """
        if not text:
            return ""
        txt = text.strip().replace("\n", " ")
        # Chercher la fin de la première phrase
        end_idx = None
        for i, ch in enumerate(txt):
            if ch in ".?!":
                if i >= 20:  # éviter de couper sur une abréviation ultra courte
                    end_idx = i + 1
                    break
        if end_idx is None:
            end_idx = min(len(txt), 200)
        spoken = txt[:end_idx].strip()
        return spoken

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open, format=FORMAT, channels=CHANNELS, rate=SEND_SAMPLE_RATE,
            input=True, input_device_index=mic_info["index"], frames_per_buffer=CHUNK_SIZE
        )
        kwargs = {"exception_on_overflow": False}
        print(">>> [INFO] Microphone is listening...")
        while True:
            # 🔇 Si Cypher est en train de parler, on n'envoie rien à Gemini
            if self.is_speaking:
                await asyncio.sleep(0.01)
                continue

            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue_gemini.put({"data": data, "mime_type": "audio/pcm"})

    async def receive_text(self):
        """
        Gère intégralement :
        - les tool calls de Gemini
        - les réponses normales
        - les résultats de la recherche web
        - l’envoi des réponses au TTS
        - le verrouillage/déverrouillage du micro (is_speaking)
        """
        while True:
            try:
                # Si Cypher parle → on ne lit pas Gemini
                if self.is_speaking:
                    await asyncio.sleep(0.1)
                    continue

                # 💡 CORRECTION : Déclaration et initialisation du turn de conversation
                turn = self.session.receive() 

                aggregated_text = ""  # Texte final à envoyer au TTS
                tool_responses = []   # Réponses à renvoyer au modèle si tool_call
                web_search_urls = set() # Stockage des URLs de recherche web

                async for chunk in turn:

                    # ---------------------------------------------------------
                    # 1) TOOL CALL (function calling avec FUNCTION_MAP)
                    # ---------------------------------------------------------
                    if hasattr(chunk, "tool_call") and chunk.tool_call:
                        function_calls = chunk.tool_call.function_calls
                        if function_calls:
                            print(">>> [DEBUG] Tool call détecté:", [fc.name for fc in function_calls])

                        for fc in function_calls:
                            fname = fc.name
                            args = dict(fc.args or {})
                            print(f">>> [DEBUG] Appel de fonction demandé: {fname}({args})")

                            # Vérifier que la fonction existe dans FUNCTION_MAP
                            if fname not in FUNCTION_MAP:
                                print(f">>> [ERROR] Fonction '{fname}' non trouvée.")
                                tool_responses.append({
                                    "id": fc.id,
                                    "name": fname,
                                    "response": {"error": f"Function {fname} not implemented"}
                                })
                                continue

                            try:
                                # Appel de ton outil Python (bloquant → to_thread si tu veux)
                                result = await asyncio.to_thread(FUNCTION_MAP[fname], **args)
                                print(f">>> [DEBUG] Résultat de {fname}: {result}")

                                tool_responses.append({
                                    "id": fc.id,           # ⚠️ TRÈS IMPORTANT
                                    "name": fname,
                                    "response": {"result": result}
                                })

                            except Exception as e:
                                print(f">>> [ERROR] Exception dans {fname}: {e}")
                                tool_responses.append({
                                    "id": fc.id,           # ⚠️ idem ici
                                    "name": fname,
                                    "response": {"error": str(e)}
                                })

                        # Si on a des réponses de tools, on les renvoie au modèle
                        if tool_responses:
                            print(">>> [DEBUG] Envoi des réponses de tools:", tool_responses)
                            await self.session.send_tool_response(
                                function_responses=tool_responses
                            )

                        continue

                    # ---------------------------------------------------------
                    # 2) RÉPONSES DU SERVEUR (Web Search Results, Code Execution)
                    # ---------------------------------------------------------
                    if hasattr(chunk, "server_content") and chunk.server_content:
                        
                        # --- Gestion des résultats de recherche web (Grounding) ---
                        if (hasattr(chunk.server_content, 'grounding_metadata') and
                                chunk.server_content.grounding_metadata and
                                chunk.server_content.grounding_metadata.grounding_chunks):
                            
                            for grounding_chunk in chunk.server_content.grounding_metadata.grounding_chunks:
                                if grounding_chunk.web and grounding_chunk.web.uri:
                                    web_search_urls.add(grounding_chunk.web.uri)
                            
                            print(f"\n>>> [DEBUG] Recherche Web - Sources trouvées: {len(web_search_urls)}")

                        # --- Gestion du Code Execution (inchangé) ---
                        model_turn = chunk.server_content.model_turn
                        if model_turn:
                            for part in model_turn.parts:
                                if part.code_execution_result is not None:
                                    output = part.code_execution_result.output
                                    print(">>> [DEBUG] Code execution output (ignoré pour TTS):", output)

                    # ---------------------------------------------------------
                    # 3) TEXTE NORMAL
                    # ---------------------------------------------------------
                    if getattr(chunk, "text", None):
                        print(chunk.text, end="", flush=True)
                        aggregated_text += chunk.text

                # ---------------------------------------------------------
                # 4) FIN DU TOUR → envoyer tout au TTS
                # ---------------------------------------------------------
                
                # --- Afficher les sources si elles existent ---
                if web_search_urls:
                    print("\n--- Sources Web ---")
                    for i, url in enumerate(web_search_urls):
                        print(f"Source {i+1}: {url}")
                    print("-------------------")
                    
                if aggregated_text.strip():
                    # ... (TTS logic) ...
                    spoken_text = self._shorten_for_tts(aggregated_text)
                    if spoken_text:
                        self.is_speaking = True
                        await self.response_queue_tts.put(spoken_text)
                        await self.response_queue_tts.put(None)

            except Exception as e:
                # ... (gestion d'erreur) ...
                print(f"\n>>> [ERROR in receive_text]: {e}")
                await asyncio.sleep(0.1)

    async def tts(self):
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id=eleven_flash_v2_5&output_format=pcm_24000"
        
        while True:
            full_text = await self.response_queue_tts.get()
            if full_text is None:
                # Juste marquer le travail fait pour ce tour, on ne change pas is_speaking ici
                self.response_queue_tts.task_done()
                continue

            try:
                async with websockets.connect(uri) as websocket:
                    await websocket.send(json.dumps({
                        "text": " ",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                        "xi_api_key": ELEVENLABS_API_KEY,
                    }))

                    async def listen():
                        while True:
                            try:
                                message = await websocket.recv()
                                data = json.loads(message)
                                if data.get("audio"):
                                    await self.audio_in_queue_player.put(base64.b64decode(data["audio"]))
                                elif data.get("isFinal"):
                                    break
                            except websockets.exceptions.ConnectionClosed:
                                break
                            except Exception as e:
                                print(f">>> [ERROR] in listen: {e}")
                                break

                    listen_task = asyncio.create_task(listen())
                    await websocket.send(json.dumps({"text": full_text, "try_trigger_generation": True}))
                    await websocket.send(json.dumps({"text": ""}))
                    await listen_task

                    # 🔁 Attendre que TOUS les chunks audio aient été lus par play_audio
                    await self.audio_in_queue_player.join()

                    # Marquer le texte comme traité
                    self.response_queue_tts.task_done()

                    # 🔓 Maintenant seulement, on considère que Cypher a fini de parler
                    self.is_speaking = False

            except Exception as e:
                print(f">>> [ERROR] TTS error: {e}")
                self.is_speaking = False  # ← DÉVERROUILLER même en cas d'erreur
                await asyncio.sleep(2)

    async def play_audio(self):
        try:
            stream = await asyncio.to_thread(
                pya.open, format=FORMAT, channels=CHANNELS,
                rate=RECEIVE_SAMPLE_RATE, output=True
            )
            print(">>> [INFO] Audio output stream is open.")
        except Exception as e:
            print(f">>> [FATAL ERROR] Could not open PyAudio stream: {e}")
            return

        while True:
            try:
                bytestream = await self.audio_in_queue_player.get()
                if bytestream:
                    # --- DIAGNOSTIC ---
                    print(f">>> [DEBUG] Playing audio chunk of size: {len(bytestream)} bytes")
                    await asyncio.to_thread(stream.write, bytestream)
                self.audio_in_queue_player.task_done()
            except Exception as e:
                print(f">>> [ERROR] Error in audio playback loop: {e}")

    

    async def run(self):
        try:
            async with self.client.aio.live.connect(model=MODEL, config=self.config) as session, asyncio.TaskGroup() as tg:
                self.session = session
                self.out_queue_gemini = asyncio.Queue(maxsize=20)
                self.response_queue_tts = asyncio.Queue()
                self.audio_in_queue_player = asyncio.Queue()
                print(">>> [INFO] Starting all tasks...")

                tg.create_task(self.listen_audio())
                tg.create_task(self.send_realtime())
                tg.create_task(self.receive_text())
                tg.create_task(self.tts())
                tg.create_task(self.play_audio())
                tg.create_task(self.timer_watcher())

                # boucle principale simple (plus de send_text)
                while True:
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            print("\n>>> [INFO] Exiting application.")
        except Exception:
            traceback.print_exc()
        finally:
            if self.audio_stream and self.audio_stream.is_active():
                self.audio_stream.stop_stream()
                self.audio_stream.close()


FUNCTION_MAP = {
    "get_time": AudioLoop._get_time,
    "get_date": AudioLoop._get_date,
    "get_weather": AudioLoop._get_weather,
    "manage_stopwatch": AudioLoop._manage_stopwatch,
    "manage_timer": AudioLoop._manage_timer,
    "open_app": AudioLoop._open_app,
    "open_website": AudioLoop._open_website,
    "spotify_control": AudioLoop._spotify_control,
    "execute_python": AudioLoop._execute_python,
    "get_python_execution_history": AudioLoop._get_python_execution_history,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", type=str, default=DEFAULT_MODE,
        help="pixels to stream from", choices=["none"]
    )
    args = parser.parse_args()
    main_loop = AudioLoop(video_mode=args.mode)
    try:
        asyncio.run(main_loop.run())
    except KeyboardInterrupt:
        pass
    finally:
        pya.terminate()
        print(">>> [INFO] Application terminated.")
