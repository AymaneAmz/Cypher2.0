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
import azure.cognitiveservices.speech as speechsdk



from google import genai
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION") # ex: "francecentral"
AZURE_VOICE_NAME = "fr-FR-HenriNeural" # Ou "fr-FR-HenriNeural" pour un homme

PENDING_PYTHON_CODE = None  # Stockage du code en attente de confirmation
PYTHON_EXECUTION_LOG = []   # Historique des exécutions



USER_HOME = os.path.expanduser("~")
ONEDRIVE_BASE = os.path.join(USER_HOME, "OneDrive")

# Chemins réels
DESKTOP_REAL   = os.path.join(ONEDRIVE_BASE, "Desktop")
DOCUMENTS_REAL = os.path.join(ONEDRIVE_BASE, "Documents")
IMAGES_REAL    = os.path.join(ONEDRIVE_BASE, "Images")

# Si l'utilisateur a renommé son dossier OneDrive (cas rare)
if not os.path.exists(DESKTOP_REAL):
    DESKTOP_REAL = os.path.join(USER_HOME, "Desktop")

if not os.path.exists(DOCUMENTS_REAL):
    DOCUMENTS_REAL = os.path.join(USER_HOME, "Documents")

if not os.path.exists(IMAGES_REAL):
    IMAGES_REAL = os.path.join(USER_HOME, "Images")

if not GEMINI_API_KEY:
    sys.exit("Error: GEMINI_API_KEY not found. Please set it in your .env file.")
if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
    sys.exit("Error: AZURE keys not found. Please set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in your .env file.")

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
        
        import pvporcupine
        self.porcupine = None
        try:
            keyword_path = os.getenv("PICOVOICE_KEYWORD_PATH")
            access_key = os.getenv("PICOVOICE_ACCESS_KEY")
            
            # Vérification basique
            if not access_key:
                raise ValueError("La clé PICOVOICE_ACCESS_KEY est vide dans le .env")

            if keyword_path and os.path.exists(keyword_path):
                self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=[keyword_path])
                print(f">>> [INIT] Wake Word 'Cypher' chargé depuis {keyword_path}")
            else:
                # Si pas de fichier PPN, on tente le mot par défaut pour tester la clé
                print(f">>> [WARNING] Fichier .ppn introuvable à : {keyword_path}. Tentative avec 'porcupine' par défaut.")
                self.porcupine = pvporcupine.create(access_key=access_key, keywords=['porcupine'])
                print(">>> [INIT] Wake Word par défaut 'Porcupine' chargé.")
                
        except Exception as e:
            # 🛑 STOP IMMÉDIAT pour voir l'erreur
            print(f"\n>>> [ERREUR FATALE PICOVOICE] : {e}")
            print(">>> Vérifiez votre clé API et le chemin du fichier .ppn dans le .env")
            sys.exit(1)

        # Variables d'état pour la conversation
        self.conversation_active = False
        self.last_interaction_time = 0
        self.CONVERSATION_TIMEOUT = 15.0 # 15 secondes

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
        
        file_manager = {
            "name": "file_manager",
            "description": (
                "Gère toutes les manipulations de fichiers et de dossiers : créer, déplacer, copier, "
                "supprimer, renommer, lister, ouvrir, scanner des répertoires et des fichiers, calculer les tailles, archiver et désarchiver."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "L'action à effectuer : 'create_dir', 'delete', 'copy', 'move', 'list_files', 'calculate_size', 'find_duplicates'.",
                        "enum": ["create_dir", "delete", "copy", "move", "rename", "list_files", "calculate_size", "find_duplicates", "archive", "unarchive"],
                    },
                    "source_path": {
                        "type": "string",
                        "description": "Chemin du fichier ou dossier source (obligatoire pour copy/move/delete/list/calculate)."
                    },
                    "destination_path": {
                        "type": "string",
                        "description": "Chemin de destination (obligatoire pour copy/move/rename). Si l'action est 'rename', c'est le nouveau nom du fichier/dossier."
                    }
                },
                "required": ["action", "source_path"],
            },
        }
        
        window_manager = {
            "name": "window_manager",
            "description": "Gère les fenêtres ouvertes : maximiser, réduire, fermer, mettre au premier plan (focus), lister les fenêtres, trouver la fenêtre active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["minimize", "maximize", "restore", "close", "focus", "list", "active"],
                        "description": "Action à effectuer sur la fenêtre."
                    },
                    "target_window": {
                        "type": "string",
                        "description": "Nom (ou partie du nom) de la fenêtre visée. Obligatoire sauf pour 'list' et 'active'."
                    }
                },
                "required": ["action"]
            }
        }

        system_control = {
            "name": "system_control",
            "description": "Contrôle les paramètres matériels du PC (Volume, Luminosité) et le presse-papier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {
                        "type": "string",
                        "enum": ["volume", "mute", "brightness", "clipboard_get", "clipboard_set"],
                        "description": "Paramètre à modifier."
                    },
                    "value": {
                        "type": "string",
                        "description": "Valeur cible (ex: '50', '+10', '-20', ou texte pour le presse-papier). Laisser vide pour lire la valeur actuelle."
                    }
                },
                "required": ["feature"]
            }
        }

        process_manager = {
            "name": "process_manager",
            "description": "Gère les processus système et l'état du PC (CPU/RAM). Permet de lister les applis gourmandes ou de tuer un programme bloqué.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["system_info", "list", "kill"],
                        "description": "Action : info système, lister processus, tuer processus."
                    },
                    "target": {
                        "type": "string",
                        "description": "Nom du processus à tuer (ex: 'chrome', 'notepad'). Obligatoire pour 'kill'."
                    }
                },
                "required": ["action"]
            }
        }
        
        power_control = {
            "name": "power_control",
            "description": "Contrôle l'alimentation du PC : mettre en veille, verrouiller, redémarrer ou éteindre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["sleep", "lock", "shutdown", "restart", "abort"],
                        "description": "Action d'alimentation."
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Forcer la fermeture des applications (DANGER de perte de données).",
                        "default": False
                    }
                },
                "required": ["action"]
            }
        }

        system_optimize = {
            "name": "system_optimize",
            "description": "Outils de nettoyage système : vider les fichiers temporaires ou tenter de libérer de la RAM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["clean_temp", "clean_ram"],
                        "description": "Action d'optimisation."
                    }
                },
                "required": ["action"]
            }
        }
        
        network_manager = {
            "name": "network_manager",
            "description": "Gère les connexions réseaux : Wi-Fi (lister, connecter, déconnecter), Bluetooth (statut, paramètres) et Mode Avion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list_networks", "connect_wifi", "disconnect_wifi", "wifi_status", 
                            "airplane_mode", 
                            "bluetooth_status", "bluetooth_settings", "connect_bluetooth"
                        ],
                        "description": "Action réseau à effectuer."
                    },
                    "target": {
                        "type": "string",
                        "description": "Nom (SSID) du réseau Wi-Fi pour la connexion."
                    }
                },
                "required": ["action"]
            }
        }

        memory_manager = {
            "name": "memory_manager",
            "description": (
                "Accède à la mémoire longue durée (Cerveau) de Cypher. "
                "Utilise cet outil pour stocker (remember), récupérer (recall) ou oublier (forget) des informations. "
                "Tu DOIS classer l'information dans l'une des catégories suivantes : "
                "'profil_utilisateur' (infos sur Monsieur), 'gouts_et_preferences', 'projets_actifs', "
                "'environnement_systeme' (config PC), 'entourage', 'base_de_connaissances' (faits appris), 'journal_evenements'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["remember", "recall", "forget", "list_categories"],
                        "description": "Action à effectuer."
                    },
                    "category": {
                        "type": "string",
                        "description": "La sphère cognitive concernée (ex: 'projets_actifs', 'profil_utilisateur')."
                    },
                    "key": {
                        "type": "string",
                        "description": "Le sujet précis ou la clé de l'information (ex: 'deadline_cypher', 'couleur_preferee')."
                    },
                    "value": {
                        "type": "string",
                        "description": "L'information à stocker (obligatoire pour 'remember'). Sois précis et complet."
                    }
                },
                "required": ["action", "category"]
            }
        }

        error_history_tool = {
            "name": "error_history",
            "description": "Permet de consulter les dernières erreurs système ou Python rencontrées par Cypher pour ne pas les reproduire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Nom du module ou tool, ex: 'execute_python', 'file_manager'. Laisser vide pour tout.",
                    }
                },
                "required": []
            }
        }

        agenda_tool = {
            "name": "manage_agenda",
            "description": "Gère l'agenda personnel : ajouter, consulter ou supprimer des événements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "list", "delete"],
                        "description": "Action à effectuer."
                    },
                    "date_iso": {
                        "type": "string",
                        "description": "Date et heure de l'événement au format EXACT 'YYYY-MM-DD HH:MM'. Calcule-la toi-même par rapport à la date actuelle."
                    },
                    "description": {
                        "type": "string",
                        "description": "Description de l'événement."
                    },
                    "alarm": {
                        "type": "boolean",
                        "description": "Si True, Cypher parlera vocalement à l'heure dite.",
                        "default": False
                    }
                },
                "required": ["action"]
            }
        }

        email_tool = {
            "name": "email_manager",
            "description": "Gère l'application Outlook locale : lire les mails non lus, chercher un mail, ou envoyer un e-mail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read_recent", "search", "send"],
                        "description": "Action : lire les nouveaux (read_recent), chercher (search), envoyer (send)."
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Adresse email du destinataire (pour action 'send')."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Objet de l'e-mail (pour action 'send')."
                    },
                    "body": {
                        "type": "string",
                        "description": "Contenu du message (pour action 'send')."
                    },
                    "query": {
                        "type": "string",
                        "description": "Mots-clés pour la recherche (sujet ou expéditeur)."
                    }
                },
                "required": ["action"]
            }
        }


        tools = [
            {"function_declarations": [
                open_app,
                file_manager,
                execute_python,
                get_time,
                get_date,
                get_weather,
                manage_stopwatch,
                manage_timer,
                open_website,
                window_manager,
                system_control,
                process_manager,
                power_control,
                system_optimize,
                network_manager,
                memory_manager,
                error_history_tool,
                agenda_tool,
                email_tool,
            ]},
            google_search_tool
        ]

        # --- CHARGEMENT DU CERVEAU AU DÉMARRAGE ---
        memory_content = ""
        
        # 🟢 CORRECTION : Chemin relatif au fichier script (juste à côté de main.py)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mem_path = os.path.join(script_dir, "cypher_memory_cortex.json") 
        
        if os.path.exists(mem_path):
            try:
                with open(mem_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    memory_str = json.dumps(data, ensure_ascii=False, indent=2)
                    memory_content = f"\n\n[MEMOIRE LONGUE DURÉE - CONTEXTE PERMANENT] :\n{memory_str}\nUtilise ces informations pour personnaliser tes réponses."
            except:
                print(">>> [WARNING] Impossible de lire la mémoire au démarrage.")


        now = datetime.now()
        current_context = f"NOUS SOMMES LE {now.strftime('%d/%m/%Y')} à {now.strftime('%H:%M')}."

        self.config = {
            "response_modalities": ["TEXT"],
            "system_instruction": f"""
{current_context}

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
    
    - Par défaut, tu DOIS utiliser le tool `open_app` pour ouvrir les applications sinon si l'application demandé n'est pas dans la liste d'application que je t'ai donné utilise execute_python.
      Dès que je dis « ouvre », « lance », « démarre » suivi d’un nom d’application,
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
    
    
    Règles pour ouvrir des sites web :
    
    - Par défaut, tu n’utilises PAS le tool `open_website`.
    
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
      QUE si tu as une erreur avec execute_python.
      
    Règles pour la recherche Web (`Google Search`) :
    - Si la réponse repose sur des faits récents ou changeants (personnes, postes, produits, versions, prix, actualité, lois, examens, docs officiels, etc.) → tu DOIS appeler google_search avant de répondre.
    - Si la question est purement conceptuelle ou intemporelle (maths, physique fondamentale, chimie générale, anatomie de base, logique, programmation générique) → tu peux répondre sans google_search, sauf si tu veux vérifier un détail précis.
    - Tu peux combiner google_search avec les autres tools (file_manager, execute_python, etc.) si ça améliore la précision de ce que tu fais.
    - **NE MENTIONNE PAS** les sources ni les URLs dans ta réponse vocale, sauf si je te le demande explicitement.
    - **CONCENTRE-TOI** uniquement sur le résumé vocal clair de la réponse.
    
    Règle pour file_manager :
    - Utilise cette outil en priorité pour :
        - Créer, déplacer, copier-coller, supprimer, renommer des fichiers/dossiers
        - Scanner un dossier entier (ou plusieurs)
        - Générer un rapport avec la liste complète des fichiers
        - Détecter les doublons (même nom / même taille)
        - Créer des structures de projets (Documents/Scripts/Data/etc.)
        - Archiver, compresser, organiser proprement
        - Calculer les tailles de dossiers et identifier ce qui prend le plus de place
        - Ouvrir des dossiers, fichiers spécifiques
    
    Règle pour window_manager :
    - Utilise cette outil en priorité pour :
        Gère les fenêtres ouvertes :
        - Maximiser
        - Réduire
        - Fermer
        - Mettre au premier plan (focus)
        - Lister les fenêtres
        - Trouver la fenêtre active
        
    Règle pour system_control :
    - Utilise cette outil en priorité pour :
        - Monter/Baisser le volume
        - Monter/baisser la luminosité
        - Gérer le presse papier
        
    Règle pour process_manager :
    - Utilise cette outil en priorité pour :
        - Gère les processus système et l'état du PC (CPU/RAM) 
        - Lister les applis gourmandes ou de tuer un programme bloqué.
    
    Règle pour power_control :
    - Utilise cette outil en priorité pour :
        - Mettre en veille le pc
        - Verrouiller le pc
        - Redémarrer ou éteindre le pc
        
    Règle pour system_optimize :
    - Utilise cette outil en priorité pour :
        - Vider les fichiers temporaires ou tenter de libérer de la RAM.
        
    Règle pour network_manager :
    - Utilise cette outil en priorité pour :
        - Lister, se connecter ou se deconnecter au Wi-Fi
        - Se connecter ou déconnecter au Bluetooth (statut, paramètres)
        - Activer ou désactiver le Mode Avion.
    
    Règle pour execute_python :

    • Tu utilises execute_python en cas de dernier recours dès que Monsieur demande une action réelle sur le PC.  
    • Si aucun des autres outils proposé te permette d'accomplir la tâche demandé tu peux utiliser execute_python pour toute tâche nécessitant d’exécuter, organiser, modifier, analyser, créer, ouvrir, automatiser ou contrôler quelque chose localement.  
    • Tu dois toujours employer execute_python en deux étapes :  
    1) `confirmed=False` (prévisualisation interne)  
    2) immédiatement après, `confirmed=True` (exécution réelle)  
    → Sans jamais demander la permission à Monsieur.
    • Pour les contenu textuels que tu me propose je veux toujours qu'il soit dans un format tres beau visuellement avec des titres, sous titres, listes a puces, etc.


    Règle pour manage_agenda :
    - Utilise cet outil dès que je parle de temps, de rendez-vous, de rappel, de planning ou d'emploi du temps.
    - CALCUL OBLIGATOIRE : L'outil attend une `date_iso` au format strict 'YYYY-MM-DD HH:MM'. Tu DOIS calculer cette date toi-même en te basant sur la date et l'heure actuelles fournies dans le contexte ({current_context}).
    - RAPPELS : Si je dis "Rappelle-moi de [faire X] dans [Y] minutes/heures", calcule l'heure future et appelle l'outil avec `action='add'`, la description et `alarm=True`.
    - CONSULTATION : Si je demande "Qu'est-ce que j'ai de prévu ?", utilise `action='list'`.
    - SUPPRESSION : Si je demande d'annuler quelque chose, utilise `action='delete'`.


    =======================================================
    RÈGLES D'AGENT EXÉCUTIF ET PRIORITÉ D'ACTION
    =======================================================
    
    1.  PRIORITÉ D'OUTIL (DU PLUS RAPIDE AU DERNIER RECOURS) :
        
        a.  TÂCHES SPÉCIFIQUES : Utilise les outils déjà proposé comme `get_time`, `get_date`, `get_weather`, `manage_timer`, `manage_stopwatch`, etc.
        b.  LANCEMENT APPLI/SITE : Utilise `open_app` ou `open_website` (si l'application ou le site à lancer n'est pas répertorier utilise execute_python).
        
        c.  CONTROLE PC : Utilise `file_manager` (Gestion Fichiers).
        
        d.  RECHERCHE : Utilise `Google Search` pour toute information factuelle non connue.
        
        e.  DERNIER RECOURS/LOGIQUE : Utilise `execute_python` uniquement si les outils ci-dessus échouent ou si la tâche nécessite une logique de programmation complexe ou une librairie externe (fpdf, pandas, etc.).

        f. AGENDA :
       - Pour ajouter un événement, tu DOIS calculer la date future au format 'YYYY-MM-DD HH:MM' en te basant sur la date actuelle ({current_context}).
       - Si je dis "Rappelle-moi de sortir les poubelles ce soir à 20h", tu calcules la date d'aujourd'hui + 20:00 et tu appelles manage_agenda avec alarm=True.

       g. GESTION EMAILS (Outlook) :
       - Utilise `email_manager` pour lire, chercher ou envoyer des mails.
       - Pour l'envoi, sois professionnel dans la rédaction du `body` et du `subject`.
       - Si je demande "J'ai reçu des mails ?", utilise `action='read_recent'`.
    
    2.  RÈGLES D'EXÉCUTION AUTOMATIQUE :
        
        •   Tu ne demandes JAMAIS de confirmation verbale pour lancer une action (`open_app`, `open_website`, `file_manager`, `system_diagnostics`).
        •   Pour les actions simples (`open_app`, `get_time`, etc.), tu ne réponds qu'avec le résultat final.
        •   Pour `execute_python`, tu respectes le processus en deux étapes (confirmed=False/True) SANS demander de permission à Monsieur.
    
    3.  GESTION DE execute_python :
        
        •   Si un script est exécuté, tu dois raccourcir ta réponse vocale au strict minimum (statut d'exécution).
        •   Si tu as besoin d'installer une lib pour un script python installe la sans me demander.
    
    4.  RÈGLES D'AUTONOMIE :
        
        •   Tu ne poses qu'une seule question COURTE si la demande est ambiguë avant d'agir.
        •   IMPORTANT : Quand l'utilisateur te donne une information personnelle (âge, ville, goûts), tu DOIS IMMÉDIATEMENT appeler l'outil `memory_manager` avec l'action 'remember' pour la sauvegarder. NE DIS PAS que tu l'as fait si tu n'as pas appelé l'outil.
    

DONNE DES REPONSES CLAIRES ET CONCISES, EN ÉVITANT LES DÉTAILS TECHNIQUES INUTILES. (SAUF SI JE TE LE DEMANDE EXPLICITEMENT).

{memory_content}

""",
            "tools": tools,
        }
    

    @staticmethod
    def _email_manager(action: str, recipient: str | None = None, subject: str | None = None, body: str | None = None, query: str | None = None) -> str:
        """
        Gère l'application locale Outlook (Lecture, Recherche, Envoi).
        Nécessite qu'Outlook soit installé et configuré sur le PC.
        """
        import win32com.client
        import pythoncom
        
        # Initialisation du contexte COM (nécessaire pour le multithreading)
        pythoncom.CoInitialize()

        try:
            # Connexion à Outlook
            outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            # 6 = Inbox (Boîte de réception)
            inbox = outlook.GetDefaultFolder(6)
        except Exception as e:
            return f"Erreur de connexion à Outlook. Est-il installé ? Erreur : {e}"

        action = action.lower()

        # --- LIRE LES NON-LUS ---
        if action == "read_recent":
            messages = inbox.Items
            messages.Sort("[ReceivedTime]", True) # Plus récents d'abord
            
            unread_messages = []
            count = 0
            
            # On scanne les 50 derniers pour trouver les non-lus
            for message in messages:
                if count >= 5: break # On s'arrête à 5 résumés
                try:
                    if message.UnRead:
                        sender = message.SenderName
                        subj = message.Subject
                        # On nettoie un peu le corps
                        preview = message.Body[:100].replace('\r', ' ').replace('\n', ' ')
                        unread_messages.append(f"- De {sender} | Objet : {subj} | Aperçu : {preview}...")
                        count += 1
                    if count >= 50: break # Sécurité pour ne pas scanner 10k mails
                except:
                    continue
            
            if not unread_messages:
                return "Vous n'avez aucun nouvel e-mail non lu dans les 50 derniers reçus."
            
            return "Voici vos derniers e-mails non lus :\n" + "\n".join(unread_messages)

        # --- RECHERCHER ---
        if action == "search":
            if not query: return "Que dois-je chercher ?"
            
            messages = inbox.Items
            messages.Sort("[ReceivedTime]", True)
            
            found_messages = []
            count = 0
            
            # Recherche simple dans les 100 derniers mails
            for message in messages:
                try:
                    if query.lower() in message.Subject.lower() or query.lower() in message.SenderName.lower():
                        found_messages.append(f"- [{message.ReceivedTime}] De {message.SenderName} : {message.Subject}")
                        count += 1
                    if count >= 5: break
                    if count >= 100: break
                except: continue
                
            if not found_messages:
                return f"Je n'ai rien trouvé pour '{query}' dans les 100 derniers e-mails."
            return f"Résultats pour '{query}' :\n" + "\n".join(found_messages)

        # --- ENVOYER ---
        if action == "send":
            if not recipient or not subject or not body:
                return "Pour envoyer un mail, il me faut : destinataire, objet et corps du message."
            
            try:
                # 0 = MailItem
                mail = win32com.client.Dispatch("Outlook.Application").CreateItem(0)
                mail.To = recipient
                mail.Subject = subject
                mail.Body = body
                mail.Send()
                return f"E-mail envoyé avec succès à {recipient}."
            except Exception as e:
                return f"Erreur lors de l'envoi : {e}"

        return "Action Outlook inconnue."

    async def agenda_watcher(self):
        """
        Vérifie chaque minute si un événement de l'agenda avec alarme est arrivé.
        """
        import json
        import os
        from datetime import datetime

        script_dir = os.getcwd()
        AGENDA_FILE = os.path.join(script_dir, "cypher_agenda.json")

        print(">>> [INFO] Agenda Watcher activé.")

        while True:
            try:
                # Vérification toutes les 30 secondes
                await asyncio.sleep(30)
                
                if not os.path.exists(AGENDA_FILE):
                    continue

                with open(AGENDA_FILE, 'r', encoding='utf-8') as f:
                    agenda = json.load(f)

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                modified = False

                for event in agenda:
                    # Si l'heure correspond ET qu'il y a une alarme ET qu'elle n'a pas déjà sonné
                    if event.get("alarm") and event["date"] == now_str and event.get("status") == "pending":
                        
                        # 🔔 DÉCLENCHEMENT DE L'ALARME
                        print(f">>> [ALARM] {event['description']}")
                        
                        # Message vocal prioritaire
                        alert_text = f"Monsieur ! Rappel agenda : {event['description']}."
                        self.is_speaking = True
                        await self.response_queue_tts.put(alert_text)
                        await self.response_queue_tts.put(None)
                        
                        # Marquer comme "notified" pour ne pas répéter en boucle
                        event["status"] = "notified"
                        modified = True

                # Sauvegarder si on a notifié quelqu'un
                if modified:
                    with open(AGENDA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(agenda, f, indent=4, ensure_ascii=False)

            except Exception as e:
                print(f">>> [ERROR Agenda Watcher] : {e}")

    @staticmethod
    def _manage_agenda(action: str, date_iso: str | None = None, description: str | None = None, alarm: bool = False) -> str:
        """
        Gère l'agenda personnel (RDV, rappels).
        Stockage dans cypher_agenda.json.
        """
        import json
        import os
        from datetime import datetime, timedelta

        script_dir = os.getcwd()
        AGENDA_FILE = os.path.join(script_dir, "cypher_agenda.json")

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
                "id": str(int(time.time())), # ID simple basé sur le timestamp
                "date": date_iso, # Format attendu: YYYY-MM-DD HH:MM
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
    
    @staticmethod
    def _error_history(source: str | None = None) -> str:
        import os, json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        error_file = os.path.join(script_dir, "cypher_memory_cortex.json")

        if not os.path.exists(error_file):
            return "Je n'ai encore enregistré aucune erreur importante, Monsieur."

        with open(error_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if source:
            s = source.lower()
            entries = data.get(s, [])
            if not entries:
                return f"Je n'ai pas d'erreur enregistrée pour '{source}', Monsieur."
            subset = entries[-5:]
            rep = [f"Dernières erreurs pour {s} :"]
        else:
            # On prend les 5 dernières toutes sources confondues
            rep = ["Dernières erreurs enregistrées (toutes sources) :"]
            subset = []
            for src, lst in data.items():
                for e in lst[-3:]:
                    e["_src"] = src
                    subset.append(e)
            subset = sorted(subset, key=lambda x: x["timestamp"])[-5:]

        for e in subset:
            src = e.get("_src", source or "?")
            rep.append(f"- [{src}] {e['timestamp']} : {e['message']}")

        return "\n".join(rep)

    @staticmethod
    def _memory_manager(action: str, category: str, key: str | None = None, value: str | None = None) -> str:
        """
        Gère la MÉMOIRE LONGUE DURÉE.
        """
        import json
        import os
        from datetime import datetime

        
        script_dir = os.getcwd() 
        MEMORY_FILE = os.path.join(script_dir, "cypher_memory_cortex.json")
        
        # 1. Chargement de la mémoire
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                    memory = json.load(f)
            except json.JSONDecodeError:
                memory = {}
        else:
            memory = {}

        action = action.lower()
        
        # Liste des catégories valides pour guider (mais on accepte les nouvelles)
        VALID_CATEGORIES = [
            "profil_utilisateur", "gouts_et_preferences", "projets_actifs", 
            "environnement_systeme", "entourage", "base_de_connaissances", "journal_evenements"
        ]

        # --- ACTION : MÉMORISER (Remember) ---
        if action == "remember":
            if not key or not value:
                return "Erreur : Pour mémoriser, il me faut un sujet (key) et une information (value)."
            
            # Normalisation
            category_slug = category.lower().replace(" ", "_")
            
            if category_slug not in memory:
                memory[category_slug] = {}
            
            # Ajout d'un timestamp pour savoir quand on a appris ça
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            memory_entry = {
                "value": value,
                "updated_at": timestamp
            }
            
            memory[category_slug][key.lower()] = memory_entry
            
            # Sauvegarde atomique
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(memory, f, indent=4, ensure_ascii=False)
            
            return f"🧠 Mémoire enregistrée dans [{category_slug}] : J'ai noté que '{key}' est '{value}'."

        # --- ACTION : SE RAPPELER (Recall) ---
        if action == "recall":
            category_slug = category.lower().replace(" ", "_")
            
            # Si on veut tout savoir sur une catégorie
            if not key:
                if category_slug not in memory:
                    return f"Je n'ai aucune information dans la catégorie '{category}'."
                
                content = []
                for k, v in memory[category_slug].items():
                    # On gère le format ancien (juste str) et nouveau (dict avec timestamp)
                    val = v["value"] if isinstance(v, dict) and "value" in v else v
                    content.append(f"- **{k.title()}** : {val}")
                
                return f"📂 **Contenu de la mémoire '{category}'** :\n" + "\n".join(content)

            # Si on cherche une clé précise
            key_lower = key.lower()
            if category_slug in memory and key_lower in memory[category_slug]:
                data = memory[category_slug][key_lower]
                val = data["value"] if isinstance(data, dict) and "value" in data else data
                return f"💡 **Souvenir retrouvé** ({category}) : {val}"
            else:
                return f"Je n'ai pas de mémoire précise pour '{key}' dans '{category}'."

        # --- ACTION : OUBLIER (Forget) ---
        if action == "forget":
            category_slug = category.lower().replace(" ", "_")
            if category_slug in memory:
                if key:
                    if key.lower() in memory[category_slug]:
                        del memory[category_slug][key.lower()]
                        save = True
                    else:
                        return f"Je ne connaissais pas '{key}' dans cette catégorie."
                else:
                    # Oublier toute la catégorie
                    del memory[category_slug]
                    save = True
                
                if save:
                    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                        json.dump(memory, f, indent=4, ensure_ascii=False)
                    return f"🗑️ Mémoire effacée avec succès."
            return "Rien à effacer."

        # --- ACTION : LISTER LES CATÉGORIES (Map) ---
        if action == "list_categories":
            cats = list(memory.keys())
            return f"🗂️ Catégories actuelles de mon cerveau : {', '.join(cats)}"

        return "Action mémoire inconnue."

    @staticmethod
    def _power_control(action: str, force: bool = False) -> str:
        """
        Contrôle l'alimentation du PC : veille, redémarrage, arrêt, verrouillage.
        """
        import os
        import subprocess
        
        action = action.lower()
        
        # Commande de base pour shutdown
        # /s = shutdown, /r = restart, /l = logoff, /h = hibernate
        # /t 0 = temps 0s, /f = force (si force=True)
        
        force_flag = "/f" if force else ""
        
        try:
            if action == "sleep":
                # La mise en veille se fait via rundll32
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                return "Mise en veille du système..."
            
            elif action == "lock":
                os.system("rundll32.exe user32.dll,LockWorkStation")
                return "Session verrouillée."
            
            elif action == "shutdown":
                os.system(f"shutdown /s /t 5 {force_flag}")
                return "Arrêt du système dans 5 secondes."
            
            elif action == "restart":
                os.system(f"shutdown /r /t 5 {force_flag}")
                return "Redémarrage du système dans 5 secondes."
                
            elif action == "abort":
                os.system("shutdown /a")
                return "Annulation de l'arrêt/redémarrage planifié."
                
        except Exception as e:
            return f"Erreur lors de l'action d'alimentation : {e}"
            
        return "Action d'alimentation inconnue."
    
    @staticmethod
    def _system_optimize(action: str) -> str:
        """
        Outils d'optimisation : vider la RAM (via EmptyStandbyList si dispo, sinon garbage collector), vider les temp.
        """
        import gc
        import os
        import shutil
        import tempfile
        
        action = action.lower()
        
        if action == "clean_ram":
            # 1. Force le Garbage Collector de Python
            gc.collect()
            
            # 2. Sous Windows, on ne peut pas vraiment "vider la RAM" sans droits admin et outils tiers.
            # On peut suggérer de fermer les apps gourmandes via process_manager.
            return "Garbage Collector Python exécuté. Pour libérer plus de RAM système, utilisez `process_manager` pour fermer les applications gourmandes."

        if action == "clean_temp":
            temp_dir = tempfile.gettempdir()
            deleted_count = 0
            total_size = 0
            
            try:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_count += 1
                            total_size += size
                        except:
                            pass # Fichier utilisé, on ignore
            except Exception as e:
                return f"Erreur lors du nettoyage : {e}"
            
            size_mb = total_size / (1024 * 1024)
            return f"Nettoyage terminé. {deleted_count} fichiers temporaires supprimés (~{size_mb:.2f} MB libérés)."
            
        return "Action d'optimisation inconnue."

    @staticmethod
    def _network_manager(action: str, target: str | None = None) -> str:
        """
        Gère le Wi-Fi, le Bluetooth et le Mode Avion.
        Utilise netsh pour le Wi-Fi et Powershell/Commandes pour le reste.
        """
        import subprocess
        
        action = action.lower()
        
        def run_command(args):
            try:
                # encoding='cp850' est souvent nécessaire pour la console Windows FR
                result = subprocess.run(args, capture_output=True, text=True, encoding='cp850', shell=True)
                return result.stdout.strip()
            except Exception as e:
                return str(e)

        # --- WI-FI ---
        if action == "list_networks":
            output = run_command("netsh wlan show networks mode=bssid")
            networks = []
            for line in output.split('\n'):
                if "SSID" in line and ":" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        networks.append(parts[1].strip())
            unique_networks = list(set(networks))
            return "Réseaux Wi-Fi visibles :\n" + "\n".join(unique_networks[:10])

        if action == "wifi_status":
            return f"État de l'interface Wi-Fi :\n{run_command('netsh wlan show interfaces')}"

        if action == "disconnect_wifi":
            run_command("netsh wlan disconnect")
            return "Déconnexion du réseau Wi-Fi effectuée."

        if action == "connect_wifi":
            if not target:
                return "Quel réseau Wi-Fi dois-je rejoindre ?"
            output = run_command(f'netsh wlan connect name="{target}"')
            if "réussie" in output or "successfully" in output:
                return f"Tentative de connexion au réseau '{target}'..."
            else:
                return f"Erreur : {output}. (Le profil doit exister dans Windows)."

        # --- MODE AVION ---
        if action == "airplane_mode":
            # Windows 10/11 ne permet pas de toggle le mode avion facilement par ligne de commande
            # sans scripts PowerShell complexes ou droits admin. On ouvre la page dédiée.
            subprocess.Popen("start ms-settings:network-airplanemode", shell=True)
            return "J'ouvre les paramètres du Mode Avion (Windows restreint l'accès direct)."

        # --- BLUETOOTH ---
        if action == "bluetooth_status":
            # Utilise PowerShell pour lister les périphériques Bluetooth connectés/appairés
            ps_script = "Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -eq 'OK'} | Select-Object -ExpandProperty FriendlyName"
            output = run_command(f'powershell -Command "{ps_script}"')
            if output:
                return f"Périphériques Bluetooth actifs/détectés :\n{output}"
            return "Aucun périphérique Bluetooth actif détecté ou erreur de lecture."

        if action == "bluetooth_settings" or action == "connect_bluetooth":
            # La connexion Bluetooth spécifique en ligne de commande est très instable sur Windows.
            # Le mieux est d'ouvrir la page d'appairage.
            subprocess.Popen("start ms-settings:bluetooth", shell=True)
            return "J'ouvre les paramètres Bluetooth pour gérer les connexions."

        return f"Action réseau non reconnue : {action}"                                                                                      
                                                                                              
    @staticmethod
    def _window_manager(action: str, target_window: str | None = None) -> str:
        """
        Gère les fenêtres Windows : minimiser, maximiser, fermer, lister, focus.
        Utilise pygetwindow.
        """
        import pygetwindow as gw
        
        action = action.lower()

        # Lister les fenêtres visibles
        if action == "list":
            titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
            return f"Fenêtres ouvertes :\n" + "\n".join(titles[:15])

        # Récupérer la fenêtre active
        if action == "active":
            try:
                win = gw.getActiveWindow()
                if win:
                    return f"La fenêtre active est : {win.title}"
                return "Aucune fenêtre active détectée."
            except:
                return "Impossible de détecter la fenêtre active."

        # Pour les actions suivantes, il faut une cible
        if not target_window:
            return "Quelle fenêtre dois-je cibler ?"

        # Recherche floue de la fenêtre (ex: "Chrome" trouve "Google Chrome...")
        target_window = target_window.lower()
        windows = [w for w in gw.getAllWindows() if target_window in w.title.lower()]

        if not windows:
            return f"Je ne trouve aucune fenêtre contenant '{target_window}'."
        
        win = windows[0] # On prend la première correspondance

        try:
            if action == "minimize":
                win.minimize()
                return f"Fenêtre '{win.title}' réduite."
            elif action == "maximize":
                win.maximize()
                return f"Fenêtre '{win.title}' maximisée."
            elif action == "restore":
                win.restore()
                return f"Fenêtre '{win.title}' restaurée."
            elif action == "close":
                win.close()
                return f"Fenêtre '{win.title}' fermée."
            elif action == "focus" or action == "activate":
                try:
                    win.activate()
                    return f"Je bascule sur '{win.title}'."
                except:
                    # Parfois Windows bloque le focus forcé, on tente de minimiser/restaurer
                    win.minimize()
                    win.restore()
                    return f"Tentative de focus sur '{win.title}'."
        except Exception as e:
            return f"Erreur lors de l'action sur la fenêtre : {e}"
        
        return "Action de fenêtre inconnue." 

    @staticmethod
    def _system_control(feature: str, value: str | int | None = None) -> str:
        """
        Contrôle le volume, la luminosité, et le presse-papier.
        Feature: volume, brightness, mute, clipboard_get, clipboard_set.
        """
        import screen_brightness_control as sbc
        import pyperclip
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import math

        feature = feature.lower()

        # --- PRESSE-PAPIER (Bonus) ---
        if feature == "clipboard_get":
            content = pyperclip.paste()
            return f"Contenu du presse-papier : {content}" if content else "Le presse-papier est vide."
        
        if feature == "clipboard_set":
            if not value: return "Aucun texte fourni pour le presse-papier."
            pyperclip.copy(str(value))
            return "Texte copié dans le presse-papier."

        # --- LUMINOSITÉ ---
        if feature == "brightness":
            if value is None:
                current = sbc.get_brightness()
                return f"Luminosité actuelle : {current[0]}%." if current else "Impossible de lire la luminosité."
            
            try:
                # Gérer "+10", "-10" ou "50"
                val_str = str(value).strip()
                if val_str.startswith("+") or val_str.startswith("-"):
                    current = sbc.get_brightness()[0]
                    new_val = current + int(val_str)
                else:
                    new_val = int(val_str)
                
                # Borner entre 0 et 100
                new_val = max(0, min(100, new_val))
                sbc.set_brightness(new_val)
                return f"Luminosité réglée à {new_val}%."
            except Exception as e:
                return f"Erreur de luminosité : {e}"

        # --- VOLUME (PyCaw) ---
        if feature in ["volume", "mute"]:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                
                if feature == "mute":
                    # Basculer le mute
                    current_mute = volume.GetMute()
                    volume.SetMute(not current_mute, None)
                    return "Son coupé." if not current_mute else "Son réactivé."

                if feature == "volume":
                    # Convertir pourcentage en dB (échelle logarithmique approximative pour Windows)
                    # Note: Pycaw utilise SetMasterVolumeLevelScalar pour le % (0.0 à 1.0)
                    if value is None:
                        current = round(volume.GetMasterVolumeLevelScalar() * 100)
                        return f"Volume actuel : {current}%."

                    val_str = str(value).strip()
                    current_vol = volume.GetMasterVolumeLevelScalar() * 100
                    
                    if val_str.startswith("+") or val_str.startswith("-"):
                        target = current_vol + int(val_str)
                    else:
                        target = int(val_str)
                    
                    target = max(0.0, min(100.0, target))
                    volume.SetMasterVolumeLevelScalar(target / 100.0, None)
                    return f"Volume réglé à {int(target)}%."

            except Exception as e:
                return f"Erreur de volume : {e}"

        return "Fonctionnalité système inconnue."

    @staticmethod
    def _process_manager(action: str, target: str | None = None) -> str:
        """
        Gère les processus : lister (top CPU/RAM), tuer un processus, infos système.
        Utilise psutil.
        """
        import psutil
        import platform

        action = action.lower()

        # Infos Globales
        if action == "system_info":
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            batt_status = f"{batt.percent}%" if batt else "Secteur/Inconnu"
            return (f"📊 État du Système :\n"
                    f"- OS : {platform.system()} {platform.release()}\n"
                    f"- CPU : {cpu}%\n"
                    f"- RAM : {ram}%\n"
                    f"- Batterie : {batt_status}")

        # Lister les processus gourmands
        if action == "list":
            # Top 5 par utilisation mémoire
            procs = []
            for p in psutil.process_iter(['name', 'memory_percent']):
                try:
                    procs.append(p.info)
                except:
                    pass
            # Trier et prendre le top 5
            top_5 = sorted(procs, key=lambda x: x['memory_percent'] or 0, reverse=True)[:5]
            
            report = "🚀 Top 5 Processus (RAM) :\n"
            for p in top_5:
                report += f"- {p['name']} : {p['memory_percent']:.1f}%\n"
            return report

        # Tuer un processus
        if action == "kill":
            if not target:
                return "Quel processus dois-je fermer ?"
            
            killed_count = 0
            target = target.lower()
            if not target.endswith(".exe"): 
                target_exe = target + ".exe"
            else:
                target_exe = target

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    # Correspondance nom exact ou partiel
                    if proc.info['name'].lower() == target_exe or target in proc.info['name'].lower():
                        proc.kill()
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if killed_count > 0:
                return f"J'ai arrêté {killed_count} processus correspondant à '{target}'."
            else:
                return f"Je n'ai pas trouvé de processus nommé '{target}'."

        return "Action de processus inconnue."                                                                                         
                                                                                              
    @staticmethod
    def _get_folder_size(start_path='.'):
        """Calcule récursivement la taille d'un dossier."""
        import os
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(start_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except:
             return -1
        return total_size
    
    @staticmethod
    def _format_bytes(bytes_size):
        """Formate la taille en B, KB, MB, GB."""
        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024**2:
            return f"{bytes_size/1024:.2f} KB"
        elif bytes_size < 1024**3:
            return f"{bytes_size/1024**2:.2f} MB"
        else:
            return f"{bytes_size/1024**3:.2f} GB"
    
    @staticmethod
    def _file_manager(action: str, source_path: str, destination_path: str | None = None) -> str:
        """
        Tool Python pour la gestion de fichiers/dossiers.
        Utilise shutil pour les opérations complexes.
        """
        import os
        import shutil
        
        action = action.lower()

        # Remplacement du chemin OneDrive dans les paramètres entrants
        # (Pour ne pas avoir à écrire la logique dans Gemini)
        if "~" in source_path:
             source_path = source_path.replace("~", os.path.expanduser("~")).replace("Desktop", DESKTOP_REAL.split(os.path.sep)[-1])
        if destination_path and "~" in destination_path:
             destination_path = destination_path.replace("~", os.path.expanduser("~")).replace("Desktop", DESKTOP_REAL.split(os.path.sep)[-1])

        
        # --- 1. Créer un Dossier/Structure ---
        if action == "create_dir":
            try:
                os.makedirs(source_path, exist_ok=True)
                return f"Le dossier/structure '{source_path}' a été créé avec succès."
            except Exception as e:
                return f"Erreur lors de la création de '{source_path}': {e}"
        
        # --- 2. Lister les Fichiers/Scanner ---
        if action == "list_files":
            try:
                if not os.path.isdir(source_path):
                    return f"Le chemin '{source_path}' n'est pas un répertoire."
                
                # Lister les 10 premiers fichiers/dossiers
                items = os.listdir(source_path)
                if not items:
                    return f"Le répertoire '{source_path}' est vide."
                
                report = f"Contenu de '{source_path}' (Top 10) :\n" + "\n".join(items[:10])
                return report
            except Exception as e:
                return f"Erreur lors de la lecture du répertoire '{source_path}': {e}"

        # --- 3. Déplacer / Renommer ---
        if action == "move" or action == "rename":
            # Renommer est un cas de move où destination_path est le nouveau nom
            if action == "rename" and destination_path:
                destination_path = os.path.join(os.path.dirname(source_path), destination_path)
            
            if not destination_path:
                return "Le chemin de destination est manquant pour l'action move/rename."

            try:
                shutil.move(source_path, destination_path)
                return f"'{source_path}' a été déplacé/renommé vers '{destination_path}'."
            except FileNotFoundError:
                return f"Erreur: Fichier/Dossier source '{source_path}' non trouvé."
            except Exception as e:
                return f"Erreur lors du déplacement/renommage: {e}"

        # --- 4. Copier ---
        if action == "copy":
            if not destination_path:
                return "Le chemin de destination est manquant pour la copie."
            try:
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, destination_path)
                else:
                    shutil.copy2(source_path, destination_path) # copy2 preserve metadata
                return f"'{source_path}' a été copié vers '{destination_path}'."
            except FileNotFoundError:
                return f"Erreur: Fichier/Dossier source '{source_path}' non trouvé."
            except Exception as e:
                return f"Erreur lors de la copie: {e}"

        # --- 5. Supprimer ---
        if action == "delete":
            try:
                if os.path.isdir(source_path):
                    shutil.rmtree(source_path)
                    return f"Dossier '{source_path}' et son contenu supprimés avec succès."
                else:
                    os.remove(source_path)
                    return f"Fichier '{source_path}' supprimé avec succès."
            except FileNotFoundError:
                return f"Erreur: Fichier/Dossier '{source_path}' non trouvé."
            except Exception as e:
                return f"Erreur lors de la suppression: {e}"

        # --- 6. Calculer la Taille ---
        if action == "calculate_size":
            try:
                size_bytes = AudioLoop._get_folder_size(source_path)
                if size_bytes == -1:
                    return f"Erreur lors du calcul de la taille de '{source_path}'."
                return f"La taille de '{source_path}' est : {AudioLoop._format_bytes(size_bytes)}."
            except Exception as e:
                return f"Erreur lors du calcul de la taille : {e}"

        # --- 7. Détecter les Doublons (Simplifié) ---
        if action == "find_duplicates":
            return "Cette fonction est trop complexe pour un appel direct. Veuillez utiliser `execute_python` pour écrire un script d'analyse de fichiers si nécessaire."
        
        if action == "archive":
            if not destination_path:
                return "Le chemin de destination est manquant pour l'archivage."
            try:
                # shutil.make_archive(nom_archive_sans_extension, format, dossier_source)
                # On utilise la destination comme nom de base, en la séparant du chemin.
                base_name = os.path.basename(destination_path)
                root_dir = os.path.dirname(source_path)
                
                # Créer le chemin pour la destination de l'archive (ex: C:\Users\archive.zip)
                archive_path = shutil.make_archive(
                    base_name=destination_path,
                    format='zip',
                    root_dir=root_dir,
                    base_dir=os.path.basename(source_path) if os.path.isdir(source_path) else source_path
                )
                
                return f"'{source_path}' a été archivé au format ZIP avec succès : {archive_path}"
            except Exception as e:
                return f"Erreur lors de l'archivage de '{source_path}': {e}"

        # --- 8. Désarchiver / Décompresser ---
        if action == "unarchive":
            if not destination_path:
                return "Le chemin de destination (où décompresser) est manquant."
            
            try:
                # Utiliser shutil.unpack_archive (supporte zip, tar, gztar, etc.)
                shutil.unpack_archive(
                    filename=source_path,
                    extract_dir=destination_path
                )
                return f"'{source_path}' a été décompressé avec succès dans '{destination_path}'."
            except FileNotFoundError:
                return f"Erreur: Le fichier d'archive '{source_path}' n'a pas été trouvé."
            except shutil.ReadError:
                return "Erreur: Le fichier d'archive est corrompu ou le format n'est pas supporté (doit être zip, tar, etc.)."
            except Exception as e:
                return f"Erreur lors de la désarchivage: {e}"

        return f"Action de gestion de fichiers non prise en charge : {action}"                                                                                          
                                                                                              
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
    def _execute_python(code: str, confirmed: bool = False) -> str:
        """
        Exécute du code Python avec confirmation obligatoire et sécurité maximale.
        """
        # ⚠️ CRITIQUE : Déclarer les variables globales EN PREMIER
        global PENDING_PYTHON_CODE, PYTHON_EXECUTION_LOG

        def _record_error(source: str, message: str, code_snippet: str | None = None):
        
            import os, json
            from datetime import datetime
            import hashlib

            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                error_file = os.path.join(script_dir, "cypher_memory_cortex.json")

                # Charger l'existant
                if os.path.exists(error_file):
                    try:
                        with open(error_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}
                else:
                    data = {}

                # Normalisation
                source = source.lower()
                if source not in data:
                    data[source] = []

                # On compress un peu l’info
                msg = (message or "").strip()
                if len(msg) > 400:
                    msg = msg[:400] + "… (tronqué)"

                # petit hash pour reconnaître les erreurs récurrentes
                base = (source + "|" + msg).encode("utf-8", errors="ignore")
                err_hash = hashlib.sha1(base).hexdigest()[:12]

                entry = {
                    "hash": err_hash,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "message": msg,
                    "code_excerpt": (code_snippet[:400] + "…") if code_snippet else None,
                }

                # On évite de stocker 200 fois la même erreur : si même hash déjà présent on ne rajoute pas
                if not any(e.get("hash") == err_hash for e in data[source]):
                    data[source].append(entry)

                with open(error_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            except Exception:
                # Surtout ne jamais faire planter Cypher à cause de la mémoire d'erreurs
                pass
        
        import subprocess
        import tempfile
        import os
        import re
        from datetime import datetime
        
        # ==========================================
        # CORRECTION AUTOMATIQUE DES CHEMINS UTILISATEUR (OneDrive)
        # ==========================================
        # On force les dossiers vers OneDrive pour ton user
        
        # 4) Helper : os.path.join(os.path.expanduser("~"), "Dossier")
        def _replace_join_home_folder(code_str, folder_names, target_path):
            pattern = (
                r'os\.path\.join\(\s*os\.path\.expanduser\(["\']~["\']\)\s*,\s*["\']('
                + "|".join(folder_names) +
                r')["\']\s*\)'
            )
            # IMPORTANT : utiliser une fonction pour que re.sub ne réinterprète pas les backslashes
            return re.sub(pattern, lambda m: repr(target_path), code_str)

        code = _replace_join_home_folder(code, ["Desktop", "Bureau"], DESKTOP_REAL)
        code = _replace_join_home_folder(code, ["Documents"],        DOCUMENTS_REAL)
        code = _replace_join_home_folder(code, ["Images", "Pictures"], IMAGES_REAL)

        # 5) Helper : os.path.expanduser("~") + "\\Dossier" ou "/Dossier"
        def _replace_concat_home_folder(code_str, folder_names, target_path):
            pattern = (
                r'os\.path\.expanduser\(["\']~["\']\)\s*\+\s*["\'][\\/]+('
                + "|".join(folder_names) +
                r')["\']'
            )
            return re.sub(pattern, lambda m: repr(target_path), code_str)

        code = _replace_concat_home_folder(code, ["Desktop", "Bureau"], DESKTOP_REAL)
        code = _replace_concat_home_folder(code, ["Documents"],        DOCUMENTS_REAL)
        code = _replace_concat_home_folder(code, ["Images", "Pictures"], IMAGES_REAL)
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
                    f"EXECUTION_FINALE_OK\n" # <-- MARQUEUR
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

                # 🔴 Enregistrer dans la mémoire d'erreurs
                try:
                    _record_error(
                        source="execute_python",
                        message=error,
                        code_snippet=code_to_execute
                    )
                except Exception:
                    pass

                return (
                    "EXECUTION_FINALE_ERREUR\n"
                    f"❌ ERREUR LORS DE L'EXÉCUTION (après {execution_time:.2f}s)\n\n"
                    f"{error}"
                )
        
        except subprocess.TimeoutExpired:
            try:
                os.unlink(temp_file)
            except:
                pass

            # 🔴 Log timeout
            try:
                _record_error(
                    source="execute_python",
                    message="Timeout (30s) lors de l'exécution du script.",
                    code_snippet=code_to_execute
                )
            except Exception:
                pass

            return "⏱️ TIMEOUT : Le code a dépassé la limite de 30 secondes, Monsieur."


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
    
    

    async def listen_audio(self):
        import struct  # <--- AJOUT IMPORTANT
        
        # On utilise les paramètres de Porcupine (souvent 512 frames)
        frame_length = self.porcupine.frame_length
        mic_info = pya.get_default_input_device_info()
        
        # Remplacez votre ouverture de stream actuelle par celle-ci :
        self.audio_stream = await asyncio.to_thread(
            pya.open, format=FORMAT, channels=CHANNELS, 
            rate=self.porcupine.sample_rate,  # <--- Utilise le taux de Porcupine
            input=True, input_device_index=mic_info["index"], 
            frames_per_buffer=frame_length    # <--- Utilise la taille de Porcupine
        )
        
        print(">>> [VEILLE] En attente du mot clé...")
        while True:
            # 1. Si Cypher parle, on met en pause l'écoute (anti-écho)
            if self.is_speaking:
                await asyncio.sleep(0.05)
                # On repousse le timeout pour ne pas couper pendant qu'il parle
                self.last_interaction_time = time.time()
                continue

            # 2. Lecture du micro
            pcm = await asyncio.to_thread(self.audio_stream.read, frame_length, exception_on_overflow=False)

            # --- ÉTAT : CONVERSATION ACTIVE (Micro ouvert vers Gemini) ---
            if self.conversation_active:
                # Vérification du Timeout (15s)
                if time.time() - self.last_interaction_time > self.CONVERSATION_TIMEOUT:
                    print(">>> [SLEEP] Silence prolongé -> Retour en veille.")
                    self.conversation_active = False
                    continue

                # Envoi du son à Gemini
                await self.out_queue_gemini.put({"data": pcm, "mime_type": "audio/pcm"})

            # --- ÉTAT : VEILLE (Analyse Porcupine uniquement) ---
            else:
                # Porcupine a besoin d'un tuple de 'shorts', pas de bytes bruts
                pcm_unpacked = struct.unpack_from("h" * frame_length, pcm)
                keyword_index = self.porcupine.process(pcm_unpacked)

                if keyword_index >= 0:
                    print(">>> [WAKE] 'Cypher' détecté ! Je vous écoute.")
                    self.conversation_active = True
                    self.last_interaction_time = time.time()
                    # (Optionnel : Vous pouvez ajouter ici un play_sound("bip.wav"))

    @staticmethod
    def _shorten_for_tts(text: str) -> str:
        """Retourne une version courte du texte pour la voix (première phrase ou troncation)."""
        if not text:
            return ""
        txt = text.strip().replace("\n", " ")
        # Chercher la fin de la première phrase
        end_idx = None
        for i, ch in enumerate(txt):
            if ch in ".?!":
                if i >= 20:  # Éviter de couper sur une abréviation ultra courte
                    end_idx = i + 1
                    break
        if end_idx is None:
            end_idx = min(len(txt), 150) # Tronquer à 150 caractères maximum si pas de point
        spoken = txt[:end_idx].strip()
        return spoken

    async def receive_text(self):
        """
        Version optimisée pour Azure : Découpe le flux en phrases complètes
        pour réduire la latence sans casser l'intonation.
        """
        # Buffer pour stocker les bouts de phrases en attendant la ponctuation
        text_buffer = "" 

        while True:
            try:
                if self.is_speaking:
                    await asyncio.sleep(0.1)
                    continue

                turn = self.session.receive() 

                tool_responses = []
                web_search_urls = set()

                async for chunk in turn:
                    # --- 1. GESTION DES TOOLS (Inchangé) ---
                    if hasattr(chunk, "tool_call") and chunk.tool_call:
                        function_calls = chunk.tool_call.function_calls
                        if function_calls:
                            for fc in function_calls:
                                fname = fc.name
                                args = dict(fc.args or {})
                                if fname not in FUNCTION_MAP:
                                    tool_responses.append({
                                        "id": fc.id,
                                        "name": fname,
                                        "response": {"error": f"Function {fname} not implemented"}
                                    })
                                    continue
                                try:
                                    result = await asyncio.to_thread(FUNCTION_MAP[fname], **args)
                                    tool_responses.append({
                                        "id": fc.id,
                                        "name": fname,
                                        "response": {"result": result}
                                    })
                                except Exception as e:
                                    tool_responses.append({
                                        "id": fc.id,
                                        "name": fname,
                                        "response": {"error": str(e)}
                                    })
                        if tool_responses:
                            await self.session.send_tool_response(function_responses=tool_responses)
                        continue

                    # --- 2. GESTION DU SERVEUR (Code execution / Web search) (Inchangé) ---
                    if hasattr(chunk, "server_content") and chunk.server_content:
                        if (hasattr(chunk.server_content, 'grounding_metadata') and
                                chunk.server_content.grounding_metadata and
                                chunk.server_content.grounding_metadata.grounding_chunks):
                            for grounding_chunk in chunk.server_content.grounding_metadata.grounding_chunks:
                                if grounding_chunk.web and grounding_chunk.web.uri:
                                    web_search_urls.add(grounding_chunk.web.uri)
                        
                        model_turn = chunk.server_content.model_turn
                        if model_turn:
                            for part in model_turn.parts:
                                if part.code_execution_result is not None:
                                    # On peut logger le résultat du code ici si besoin
                                    pass

                    # --- 3. GESTION DU TEXTE (LE CHANGEMENT EST ICI) ---
                    if getattr(chunk, "text", None):
                        current_text = chunk.text
                        print(current_text, end="", flush=True)
                        
                        # Ajout au buffer
                        text_buffer += current_text
                        
                        # --- DÉTECTION DE FIN DE PHRASE ---
                        # On cherche les ponctuations fortes : . ? ! ou retour à la ligne
                        # On évite de couper sur "M." ou "Dr." (simplification ici)
                        import re
                        # Regex : Cherche une ponctuation (.?!) suivie d'un espace ou fin de ligne
                        split_pattern = r'([.?!;])\s+'
                        
                        parts = re.split(split_pattern, text_buffer)
                        
                        # Si on a plus d'un élément, c'est qu'on a trouvé une séparation
                        if len(parts) > 1:
                            # On reconstitue les phrases complètes
                            # parts ressemble à ["Bonjour", "!", "Comment ça va", "?", "Reste"]
                            
                            # On parcourt par paire (Phrase + Ponctuation)
                            for i in range(0, len(parts) - 1, 2):
                                # Si c'est le dernier élément et qu'il n'y a pas de ponctuation après, c'est le reste
                                if i + 1 >= len(parts):
                                    text_buffer = parts[i]
                                    break
                                
                                sentence = parts[i] + parts[i+1] # Texte + Ponctuation
                                
                                # Envoi immédiat au TTS
                                if sentence.strip():
                                    self.is_speaking = True
                                    await self.response_queue_tts.put(sentence.strip())
                            
                            # Le dernier morceau devient le nouveau buffer
                            text_buffer = parts[-1]


                # --- 4. FIN DU TOUR ---
                # S'il reste du texte dans le buffer à la fin de la réponse de Gemini
                if text_buffer.strip():
                    # Cas spécial Kill Switch
                    text_lower = text_buffer.lower()
                    if "au revoir" in text_lower or "bonne nuit" in text_lower:
                         self.conversation_active = False

                    self.is_speaking = True
                    await self.response_queue_tts.put(text_buffer.strip())
                    text_buffer = "" # Reset du buffer
                
                # Signal de fin pour ce tour (optionnel selon ta logique TTS)
                await self.response_queue_tts.put(None)
                self.last_interaction_time = time.time()

            except Exception as e:
                print(f"\n>>> [ERROR in receive_text]: {e}")
                await asyncio.sleep(0.1)

    async def tts(self):
        """
        Génère le TTS via Azure AI Speech.
        CORRECTION : Gestion correcte du signal de fin + libération du micro.
        """
        # --- CONFIG AZURE ---
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        speech_config.speech_synthesis_voice_name = AZURE_VOICE_NAME
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
        )
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    
        print(f">>> [INIT] Azure TTS prêt ({AZURE_VOICE_NAME})")
    
        while True:
            full_text = await self.response_queue_tts.get()
            
            # --- GESTION DU SIGNAL DE FIN ---
            if full_text is None:
                # ✅ CORRECTION : On transmet le signal de fin AU PLAYER
                await self.audio_in_queue_player.put(None)
                self.response_queue_tts.task_done()
                continue  # ⚠️ On ne libère PAS is_speaking ici (le player le fait)
    
            try:
                # --- GÉNÉRATION AZURE ---
                def _generate_audio_blocking():
                    return synthesizer.speak_text_async(full_text).get()
    
                result = await asyncio.to_thread(_generate_audio_blocking)
    
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    audio_data = result.audio_data
                    if audio_data:
                        # ✅ Envoi du chunk audio au player
                        await self.audio_in_queue_player.put(audio_data)
                
                elif result.reason == speechsdk.ResultReason.Canceled:
                    print(f">>> [ERREUR AZURE] : {result.cancellation_details.reason}")
    
            except Exception as e:
                print(f">>> [EXCEPTION TTS] : {e}")
            
            finally:
                self.response_queue_tts.task_done()
                # ⚠️ ON NE TOUCHE PLUS À self.is_speaking ICI !


    async def play_audio(self):
        """
        Joue l'audio et libère le micro (is_speaking = False) UNIQUEMENT quand tout est fini.
        ✅ VERSION CORRIGÉE
        """
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
                # On récupère le paquet audio (ou le signal de fin)
                bytestream = await self.audio_in_queue_player.get()
                
                # --- SIGNAL DE FIN REÇU ---
                if bytestream is None:
                    # ✅ C'EST ICI qu'on libère le micro car on est sûr que tout le son d'avant est joué
                    self.is_speaking = False
                    print(">>> [INFO] ✅ Micro libéré (is_speaking = False)")
                    self.audio_in_queue_player.task_done()
                    continue
    
                # --- LECTURE AUDIO ---
                if bytestream:
                    # On joue le son (c'est bloquant le temps de la lecture, donc parfait)
                    await asyncio.to_thread(stream.write, bytestream)
                
                self.audio_in_queue_player.task_done()
                
            except Exception as e:
                print(f">>> [ERROR] Error in audio playback loop: {e}")
                # Sécurité : en cas d'erreur, on rend la parole
                self.is_speaking = False

    

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
                tg.create_task(self.agenda_watcher())

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
    "execute_python": AudioLoop._execute_python,
    "get_python_execution_history": AudioLoop._get_python_execution_history,
    "file_manager": AudioLoop._file_manager,
    "window_manager": AudioLoop._window_manager,
    "system_control": AudioLoop._system_control,
    "process_manager": AudioLoop._process_manager,
    "power_control": AudioLoop._power_control,
    "system_optimize": AudioLoop._system_optimize,
    "network_manager": AudioLoop._network_manager,
    "memory_manager": AudioLoop._memory_manager,
    "error_history_tool": AudioLoop._error_history,
    "manage_agenda": AudioLoop._manage_agenda,
    "email_manager": AudioLoop._email_manager,
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