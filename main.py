"""
A real-time, multimodal conversational AI script using Google's Gemini Live API
for language understanding and ElevenLabs for text-to-speech synthesis.
This version includes detailed diagnostic logging for debugging audio issues.
"""

import sys

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
from typing import Dict, Any
import time
import random
import requests
import azure.cognitiveservices.speech as speechsdk
import queue
import threading
import pygame
# OpenWakeWord supprimé - on utilise uniquement SpeechBrain
import numpy as np
import torch

# PATCH pour torchaudio 2.9+ qui n'a plus list_audio_backends()
# Ce patch doit être fait AVANT l'import de SpeechBrain
try:
    import torchaudio
    if not hasattr(torchaudio, 'list_audio_backends'):
        # Ajouter une fonction factice pour SpeechBrain
        def _fake_list_audio_backends():
            return ['soundfile']  # Backend par défaut
        torchaudio.list_audio_backends = _fake_list_audio_backends
except ImportError:
    pass

# Import optionnel de SpeechBrain (peut échouer avec torchaudio sur certaines versions)
try:
    from speechbrain.inference import EncoderClassifier
    SPEECHBRAIN_AVAILABLE = True
except (ImportError, OSError, AttributeError, Exception) as e:
    SPEECHBRAIN_AVAILABLE = False
    EncoderClassifier = None
    # Logger pas encore disponible ici (import en cours), on garde print pour les erreurs d'import
    print(f"⚠️ [WARNING] SpeechBrain non disponible: {type(e).__name__}: {e}")
    print("⚠️ La détection du wake word ne fonctionnera pas. Le système continuera quand même.")
from collections import deque



from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# Import des modules core
from core.config import get_config
from core.logger import get_logger
from core.wake_word_detector import WakeWordDetector
from core.tool_executor import ToolExecutor
from core.sound_manager import get_sound_manager
from core.learning_system import get_learning_system
from core.state_manager import get_state_manager
from core.paths import get_project_root, get_sounds_dir, get_models_dir, get_vocab_dir, get_memory_dir, get_rag_db_dir

# Import des modules fonctionnels
from modules.expert_coder import expert_coder_tool, EXPERT_CODER_TOOL_DECLARATION, expert_stats, get_expert
from google import genai
from modules.spotify_controller import spotify_tool, SPOTIFY_TOOL_DECLARATION
from modules.analyze_screen import analyze_screen_tool, SCREEN_ANALYZER_TOOL_DECLARATION
from modules.web_navigator import web_navigator_tool, WEB_NAVIGATOR_TOOL_DECLARATION, get_navigator
from modules.gui import CypherGUI

# Import des nouveaux modules refactorisés
from core.tool_declarations import get_all_tool_declarations
from modules.system_tools import (
    network_manager,
    window_manager,
    system_control,
    process_manager,
    power_control,
    system_optimize
)
from modules.time_management import (
    get_time,
    get_date,
    format_duration,
    manage_stopwatch,
    manage_timer,
    manage_agenda,
    get_timer_end,
    get_timer_alert_triggered,
    set_timer_alert_triggered,
    set_timer_end
)
from core.tts_utils import generate_ssml, clean_text_for_tts, shorten_for_tts
from core.utils import get_weather, get_folder_size, format_bytes
from modules.app_launcher import open_app, open_website
from modules.python_executor import execute_python, get_python_execution_history
from modules.file_manager import file_manager
from modules.document_manager import document_manager
from modules.email_manager import email_manager
from modules.memory_manager import memory_manager

# Logger principal
logger = get_logger("main")


ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION") 
AZURE_VOICE_NAME = "fr-FR-HenriNeural" 

WAKE_WORD_SENSITIVITY = 0.5
WAKE_MIN_VOLUME = 0

TTS_RATE = "+15%"
TTS_PITCH = "default"

# Les chemins OneDrive sont maintenant dans modules/python_executor.py et modules/file_manager.py

if not GEMINI_API_KEY:
    logger.critical("GEMINI_API_KEY not found. Please set it in your .env file.")
    sys.exit("Error: GEMINI_API_KEY not found. Please set it in your .env file.")
if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
    logger.critical("AZURE keys not found. Please set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in your .env file.")
    sys.exit("Error: AZURE keys not found. Please set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in your .env file.")

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# --- État global pour le chronomètre et le compte à rebours ---
# NOTE: Ces variables ont été déplacées dans modules/time_management.py
# Utiliser les fonctions get_timer_end(), get_timer_alert_triggered(), set_timer_alert_triggered()

# --- Audio Configuration ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

# --- API Configuration ---
MODEL = "gemini-2.0-flash-exp"
DEFAULT_MODE = "none"
VOICE_ID = 'bts16wA7hWMfnlEIHuRo'

# --- Initialize Clients ---

pya = pyaudio.PyAudio()


LOADING_PHRASES = {
    "document_manager": [
        "Je consulte vos documents, un instant...",
        "Analyse de la base de connaissances en cours...",
        "Je vérifie dans vos fichiers indexés...",
        "Voyons ce que disent vos documents..."
    ],
    "google_search": [
        "Je vérifie ça sur le web...",
        "Recherche d'informations en cours...",
        "Je regarde ce qui se dit à ce sujet sur Internet..."
    ],
    "execute_python": [
        "J'écris le script, un instant...",
        "Je m'occupe de ça techniquement...",
        "Exécution du code en cours...",
        "Traitement informatique lancé..."
    ],
    "file_manager": [
        "Accès au système de fichiers...",
        "Je gère les fichiers..."
    ],
    "email_manager": [
        "Connexion à Outlook...",
        "Je vérifie vos e-mails..."
    ],
    "system_optimize": [
        "Nettoyage du système en cours...",
        "Optimisation de la mémoire..."
    ],
    "deep_research": [
        "Je lance une recherche approfondie, analyse de plusieurs sources en cours...",
        "Je compile un rapport détaillé basé sur plusieurs sites web...",
        "Je croise les informations de différentes sources, un instant...",
        "Investigation approfondie en cours..."
    ],
    "expert_coder": [
        "J'appelle mon module expert en développement, un instant...",
        "Je demande à l'architecte logiciel de générer ce code...",
        "Conception du programme en cours avec le modèle haute précision...",
        "Je rédige un code propre et optimisé, patientez..."
    ],
}


class AudioLoop:
    def __init__(self, gui_queue, video_mode=DEFAULT_MODE):
        self.gui_queue = gui_queue
        self.video_mode = video_mode
        self.out_queue_gemini = None
        self.response_queue_tts = None
        self.audio_in_queue_player = None
        self.session = None
        self.audio_stream = None
        self.is_speaking = False
        self.is_busy = False
        self._interrupted_flag = False  # Flag pour annuler les tool calls en cours
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Charger la configuration Cypher
        self.cypher_config = get_config()
        
        # Initialiser le gestionnaire de sons (utilise maintenant assets/sounds/)
        self.sound_manager = get_sound_manager()
        
        # Initialiser le WebNavigator avec la gui_queue
        try:
            navigator = get_navigator(gui_queue=gui_queue)
            logger.info("WebNavigator initialisé avec gui_queue")
        except Exception as e:
            logger.warning(f"Impossible d'initialiser WebNavigator: {e}")
        
        # Sons principaux (pour compatibilité avec code existant)
        pygame.mixer.init() # On allume le moteur audio (déjà fait par sound_manager mais gardé pour compatibilité)
        sounds_dir = get_sounds_dir()
        self.wake_sound_path = str(sounds_dir / "wake.mp3")
        self.end_sound_path = str(sounds_dir / "end_listening.mp3")

        # Chargement du modèle SpeechBrain pour la détection du wake word "Sayfeure"
        if not SPEECHBRAIN_AVAILABLE or EncoderClassifier is None:
            self.sb_classifier = None
            self.sb_target = None
            logger.warning("SpeechBrain non disponible - la détection du wake word est désactivée")
            logger.warning("Tu peux utiliser le module wake_word_detector.py comme alternative")
        else:
            try:
                self.sb_classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": "cpu"}  # Change en "cuda" si tu as une GPU
                )
                
                # Charger l'embedding du wake word (dans data/models/)
                models_dir = get_models_dir()
                embedding_path = models_dir / "wakeword_embedding.npy"
                if not embedding_path.exists():
                    vocab_dir = get_vocab_dir()
                    logger.error(f"Fichier wakeword_embedding.npy introuvable dans {models_dir}")
                    logger.error(f"Exécute train_wakeword.py pour générer l'embedding à partir des fichiers {vocab_dir}/")
                    self.sb_classifier = None
                    self.sb_target = None
                else:
                    # AMÉLIORATION 1: Cache embedding wake word - Pré-normaliser pour accélérer
                    self.sb_target = np.load(str(embedding_path)).astype(np.float32)
                    # Pré-normaliser l'embedding cible une fois pour toutes
                    target_norm = np.linalg.norm(self.sb_target)
                    if target_norm > 0:
                        self.sb_target_normalized = self.sb_target / target_norm
                    else:
                        self.sb_target_normalized = self.sb_target
                    logger.info("Embedding wake word chargé et pré-normalisé (cache activé)")
            except Exception as e:
                logger.warning(f"Erreur lors du chargement de SpeechBrain: {e}")
                self.sb_classifier = None
                self.sb_target = None
                self.sb_target_normalized = None

        # paramètres detection (à peaufiner)
        self.sb_sr = 16000
        self.sb_window_sec = 1.0
        self.sb_hop_sec = 0.25
        self.sb_trigger_threshold = 0.5      # tu l’as dit: ton Cypher est ~0.48–0.60
        self.sb_min_rms = 0.030               # ignore silence/bruit bas
        self.sb_need_hits = 3                 # “3 hits sur les derniers frames”
        self.sb_cooldown_sec = 1.2            # évite double trigger

        # états internes
        self.sb_audio_buf = deque(maxlen=int(self.sb_sr * self.sb_window_sec))
        self.sb_hits = deque(maxlen=5)
        self.sb_last_trigger = 0.0
        
        # Variables d'état pour la détection du wake word
        self._wake_hit_count = 0
        self.WAKE_THRESHOLD = 0.5  # Seuil de similitude cosine (abaissé pour meilleure détection)
        self.WAKE_MIN_RMS = 0.020   # Seuil minimum de volume (légèrement abaissé)

        # Variables d'état pour la conversation
        self.conversation_active = False
        self.last_interaction_time = 0
        self.CONVERSATION_TIMEOUT = self.cypher_config.conversation_timeout
        
        # AMÉLIORATION 4: Initialiser le StateManager pour auto-sauvegarde et résumé contexte
        self.state_manager = get_state_manager()
        # Tenter de restaurer l'état précédent
        saved_state = self.state_manager.load_state()
        if saved_state:
            logger.info("État précédent trouvé. Utilise 'restore_state' pour le restaurer si besoin.")
        
        # Initialiser le TaskManager pour la gestion de tâches professionnelle
        from modules.task_manager import get_task_manager
        self.task_manager = get_task_manager()
        # Les tâches sont automatiquement chargées depuis cypher_tasks.json au démarrage
        task_count = len(self.task_manager.tasks)
        if task_count > 0:
            logger.info(f"{task_count} tâche(s) chargée(s) depuis le fichier de persistance")
        
        # Initialiser le tool executor (sera initialisé après avoir chargé FUNCTION_MAP)
        self.tool_executor = None
        
        # Charger FUNCTION_MAP et initialiser tool_executor
        # Note: FUNCTION_MAP est défini plus bas dans le fichier, donc on le fera après 
        
        self._boost_microphone_gain()
        
        # Tools de Cypher - Utiliser les déclarations centralisées
        tools = get_all_tool_declarations()

        # --- CHARGEMENT DU CERVEAU AU DÉMARRAGE ---
        memory_content = ""
        memory_dir = get_memory_dir()
        mem_path = memory_dir / "cypher_memory_cortex.json" 
        
        if mem_path.exists():
            try:
                with open(str(mem_path), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    memory_str = json.dumps(data, ensure_ascii=False, indent=2)
                    memory_content = f"\n\n[MEMOIRE LONGUE DURÉE - CONTEXTE PERMANENT] :\n{memory_str}\nUtilise ces informations pour personnaliser tes réponses."
            except:
                logger.warning("Impossible de lire la mémoire au démarrage.")

        # --- CHARGEMENT DU SYSTÈME D'APPRENTISSAGE ---
        self.learning_system = get_learning_system()
        learning_preferences = self.learning_system.get_preferences_summary()
        
        now = datetime.now()
        current_context = f"NOUS SOMMES LE {now.strftime('%d/%m/%Y')} à {now.strftime('%H:%M')}."
        
        # Variables pour capturer l'interaction en cours (pour l'apprentissage)
        self._current_user_input = ""
        self._current_tools_used = []
        self._current_response = ""

        # AMÉLIORATION 2: Ajouter le résumé du contexte précédent si disponible
        # Note: Le résumé sera injecté dynamiquement dans la conversation si nécessaire
        context_summary = self.state_manager.get_context_summary()
        context_summary_text = f"\n{context_summary}" if context_summary else ""
        
        self.config = {
            "response_modalities": ["TEXT"],
            "system_instruction": f"""
{current_context}
{learning_preferences}{context_summary_text}

⚠️ CONFIGURATION SYSTÈME CRITIQUE :
Les chemins Desktop, Documents et Images sont automatiquement redirigés vers OneDrive si nécessaire par les outils file_manager et execute_python.
Si tu dois écrire un script Python ou chercher un fichier, utilise TOUJOURS les chemins absolus au lieu des chemins par défaut de Windows.

IMPORTANT : Le dossier "Downloads" (Téléchargements) doit utiliser le chemin standard Windows (C:\\Users\\...\\Downloads) et NON PAS le chemin OneDrive. Ne redirige PAS Downloads vers OneDrive.

Tu t'appelles Cypher et ça se prononce Saïfer. Moi je m'appelle Aymane, je suis ton développeur. Tu es comme un pote collegue avec moi tu peux me charier parfois ou etre tres franc aussi. et tu es une IA conçue pour m'aider dans mes projets d'ingénierie ainsi que dans mes tâches quotidiennes. Adresse-toi à moi en m'appelant « Monsieur ». Merci également de veiller à ce que tes réponses soient concises.
    
    Règle CRITIQUE pour la création et la MODIFICATION de Code :

    1. CRÉATION (Nouveau projet) :
       - Si je demande un nouveau programme : Utilise `expert_coder` avec une description détaillée.
       - Ensuite, pour ÉCRIRE le code sur le disque, tu appelles UNIQUEMENT le tool `expert_coder_write_file` avec `target_path` = chemin complet du fichier (ex: sur le Bureau).
       - Tu n'as JAMAIS à copier/coller le code dans les paramètres d'un tool : c'est le backend Python qui gère tout le contenu du code.

    2. MODIFICATION (Projet existant) :
       - Si je demande de changer, corriger ou améliorer un fichier existant :
         ÉTAPE A : Tu utilises `file_manager` avec action='read_file' pour lire le fichier cible.
         ÉTAPE B : ⚠️ RÈGLE DE SILENCE : Quand tu as lu le code, NE L'AFFICHE PAS dans le chat. NE LE RÉPÈTE PAS. Garde-le en mémoire uniquement. Dis juste : "J'ai lu le fichier, je transmets à l'expert."
         ÉTAPE C : Tu appelles `expert_coder`. Dans les `specifications`, tu colles le code que tu as lu + mes instructions.
         ÉTAPE D : Quand l'expert a renvoyé le nouveau code, tu écrases l'ancien fichier en appelant `expert_coder_write_file` avec `target_path` = chemin du fichier à mettre à jour (pas `file_manager.create_file`).

    3. RÈGLES GÉNÉRALES :
       - Le code reçu de l'expert est BRUT. Ne le modifie pas, ne l'affiche pas.
       - Sauvegarde-le immédiatement via `expert_coder_write_file`.
    
    4. INTERDICTION FORMELLE d'utiliser `execute_python` pour créer ou modifier un fichier contenant du code généré. Utilise `expert_coder` + `expert_coder_write_file` (et `file_manager` seulement pour lire/lister/déplacer/supprimer). 

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
       
    Règle pour web_navigator (INTERNAUTE) :
    - Utilise cet outil pour des recherches APPROFONDIES ou des actions sur le web.
    - Scénarios :
      * "Va sur le site de la NASA et dis-moi la dernière news" -> action='navigate', url='nasa.gov'
      * "Cherche des images de chatons" -> action='search_images'
      * "Télécharge ce PDF" -> action='download'
      * "Fais une recherche complète sur X" -> action='search' (mieux que google_search car plus détaillé)
    - Si l'utilisateur demande juste une info rapide ("Quelle heure est-il à Tokyo ?"), garde `Google Search`.
    - Pour lire un article complet : action='scrape'.
      
    Règle pour spotify_control (DJ Musique) :
    - Utilise cet outil dès que je parle de musique, de chansons, d'artistes ou de volume sonore.
    - Pour "Mets de la musique" ou "Joue du rock" → action='play_track' ou 'search' puis 'play'.
    - Pour "Mets pause", "Suivant", "Monte le volume" → utilise les actions correspondantes (pause, next, volume_up).
    - Si je demande une playlist spécifique ("Playlist Lo-Fi") → action='play_playlist'.
    - Tu as le contrôle total : ne demande pas confirmation pour changer de musique.
    
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

    Règle CRITIQUE pour la création de fichiers avec du code (Code, Texte, Scripts) :
    - Si je te demande de "créer un fichier", "faire un script", "enregistrer un code" :
      1. Tu génères le contenu du code.
      2. Tu utilises EXCLUSIVEMENT l'outil `file_manager` avec `action='create_file'`, `content='LE_CODE'` et `source_path='...'`.
      3. INTERDICTION FORMELLE d'utiliser `execute_python` pour créer un fichier (ne fais jamais de `with open(...)` dans un script Python).
      4. Une fois le fichier créé via `file_manager`, SI ET SEULEMENT SI je demande de l'exécuter, alors tu utilises `execute_python` pour lancer le fichier créé.
    
    Règles pour le gestionnaire de tâches (Task Master - manage_tasks) :
    - Tu disposes d'un gestionnaire de tâches professionnel avec récurrence automatique.
    - Si l'utilisateur mentionne une habitude ou une action répétitive :
        * "tous les jours", "chaque jour", "quotidiennement" → recurrence="daily"
        * "chaque semaine", "toutes les semaines", "hebdomadaire" → recurrence="weekly"
        * "chaque mois", "mensuel" → recurrence="monthly"
        * "chaque année", "annuel" → recurrence="yearly"
        * "chaque mardi", "tous les lundis" → recurrence="weekly" (avec due_date calculée)
    - Actions disponibles :
        * "Ajoute une tâche X" → action="add" avec title, priority, due_date, recurrence si mentionné
        * "Liste mes tâches" → action="list" (peut filtrer par status, priority, date_range)
        * "J'ai fini la tâche X" ou "Marque X comme terminée" → action="complete" avec fuzzy_name ou task_id
        * "Supprime la tâche X" → action="delete" avec fuzzy_name (IMPORTANT: si la tâche est récurrente, toutes les occurrences seront supprimées automatiquement)
        * "Statistiques des tâches" → action="stats"
    - IMPORTANT pour les tâches récurrentes :
        * Lorsqu'une tâche récurrente est complétée, une nouvelle occurrence est automatiquement créée.
        * Lorsqu'une tâche récurrente est supprimée par son nom (fuzzy_name), TOUTES les occurrences (passées, présentes et futures) sont supprimées automatiquement.
        * Ne fournis JAMAIS task_id pour supprimer une tâche récurrente, utilise toujours fuzzy_name pour que toutes les occurrences soient supprimées.
    - Les priorités : "low", "medium", "high", "critical" (défaut: "medium").
    - Pour les dates d'échéance, calcule-les toi-même au format "YYYY-MM-DD HH:MM" par rapport à la date actuelle.
    - Utilise fuzzy_name pour trouver une tâche par son nom partiel si task_id n'est pas fourni.
    - Format de réponse : Réponds de manière claire et concise, sans emojis ni caractères spéciaux inutiles.
    
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
        
    Règle pour analyze_screen (VISION / YEUX) :
    - Tu as maintenant la capacité de VOIR l'écran de l'utilisateur.
    - DÉCLENCHEURS : Dès que je dis "Regarde ça", "Qu'est-ce qu'il y a à l'écran", "Analyse ce bug", "Lis ce texte", "Décris l'image".
    - ACTION PAR DÉFAUT : Utilise `action='describe'` pour avoir une description textuelle rapide de ce qui est ouvert.
    - POUR LE CODE / ERREURS : Utilise `action='full_analysis'` avec `detailed_ocr=True`. Cela va lire tout le texte à l'écran (OCR) pour que tu puisses déboguer sans que je copie-colle.
    - INTERDIT : Ne dis jamais "Je suis une IA textuelle, je ne peux pas voir". Tu PEUX voir via cet outil.
        
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

    Règle pour document_manager (RAG) :

        DÉCLENCHEURS AUTOMATIQUES :
        - Dès que je pose une question sur :
          • Mes documents locaux (ex: "Qu'est-ce qui est dit dans mon PDF de maths ?")
          • Mes fiches de révision (ex: "Résume-moi le chapitre 3")
          
        WORKFLOW OBLIGATOIRE :
        1. PREMIÈRE FOIS sur un dossier :
           - Propose : "Je ne connais pas encore ce dossier. Voulez-vous que je l'analyse ?"
           - Si oui → `document_manager(action='index', source_folder='...')`
           
        2. DOSSIER DÉJÀ INDEXÉ :
           - Utilise TOUJOURS `document_manager(action='search', query='...')` AVANT de répondre
           - Utilise le résultat pour formuler une réponse précise et sourcée
           - Mentionne les fichiers sources utilisés (ex: "D'après votre cours_maths.pdf...")
        
        3. RÉINITIALISATION :
           - Si je dis "oublie mes documents" → `document_manager(action='reset')`
        
        EXEMPLE DE BON USAGE :
        Moi: "C'est quoi la loi d'Ohm ?"
        Toi: [Appelle document_manager search avec query="loi d'Ohm"]
             → Réponds avec le contenu extrait : "D'après votre cours_elec.pdf, la loi d'Ohm..."
        
        IMPORTANT : 
        - Ne réponds JAMAIS de mémoire si le document existe
        - Cherche TOUJOURS dans les docs indexés avant de répondre
        - Si rien trouvé, dis : "Je n'ai pas trouvé cette info dans vos documents indexés.

    
    Règle pour les recherches approfondies :
    - Pour les sujets complexes, utilise `google_search` EN SÉRIE (5-7 fois) :
    1. Vue d'ensemble générale
    2-3. Détails techniques/spécifiques
    4-5. Applications/cas d'usage
    - Compile ensuite un rapport structuré avec citations.


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

    

    def _generate_ssml(self, text: str) -> str:
        """Emballe le texte dans du SSML pour contrôler la vitesse et le ton."""
        return generate_ssml(text, AZURE_VOICE_NAME, TTS_RATE, TTS_PITCH)
                                                                                 
    def _boost_microphone_gain(self):
        """Augmente automatiquement le gain du micro au démarrage"""
        import subprocess
        try:
            subprocess.run([
                'powershell', '-Command',
                "Get-AudioDevice -RecordingMute | Set-AudioDevice -RecordingMute 0"
            ], capture_output=True)
            logger.info("Gain du microphone optimisé")
        except:
            logger.warning("Impossible d'ajuster le gain automatiquement")

    async def agenda_watcher(self):
        """
        Vérifie chaque minute si un événement de l'agenda avec alarme est arrivé.
        """
        import json
        import os
        from datetime import datetime

        AGENDA_FILE = str(get_memory_dir() / "cypher_agenda.json")

        logger.info("Agenda Watcher activé.")

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
                        logger.info(f"Alarme agenda : {event['description']}")
                        
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
                logger.error(f"Erreur dans agenda_watcher : {e}")

    def _manage_tasks(
        self,
        action: str,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
        recurrence: str | None = None,
        tags: list | None = None,
        task_id: str | None = None,
        fuzzy_name: str | None = None,
        filter_status: str | None = None,
        filter_priority: str | None = None,
        date_range: str | None = None
    ) -> str:
        """
        Gestionnaire de tâches professionnel (Task Master) avec récurrence automatique.
        Utilise le module task_manager pour gérer les tâches avec persistance JSON.
        """
        from modules.task_manager import get_task_manager
        
        task_mgr = get_task_manager()
        action = action.lower()
        
        # --- AJOUTER UNE TÂCHE ---
        if action == "add":
            if not title:
                return "Erreur: Le titre de la tâche est obligatoire."
            
            # Valeurs par défaut
            priority = priority or "medium"
            description = description or ""
            tags = tags or []
            
            # Ajouter la tâche
            try:
                task = task_mgr.add_task(
                    title=title,
                    description=description,
                    priority=priority,
                    due_date=due_date,
                    recurrence=recurrence,
                    tags=tags
                )
                
                # Message de confirmation (format propre, sans emojis)
                msg = f"Tâche ajoutée : {title}"
                if priority == "critical":
                    msg += " (Critique)"
                elif priority == "high":
                    msg += " (Haute priorité)"
                
                if recurrence:
                    if recurrence == "daily":
                        msg += " - Récurrente quotidienne"
                    elif recurrence == "weekly":
                        msg += " - Récurrente hebdomadaire"
                    elif recurrence == "monthly":
                        msg += " - Récurrente mensuelle"
                    elif recurrence == "yearly":
                        msg += " - Récurrente annuelle"
                
                if due_date:
                    msg += f" - Échéance : {due_date}"
                
                # Notifier la GUI
                try:
                    tasks = task_mgr.list_tasks()
                    self.gui_queue.put(("TASKS_UPDATE", {"tasks": tasks}))
                except:
                    pass
                
                return msg
            except Exception as e:
                return f"Erreur lors de l'ajout de la tâche: {e}"
        
        # --- LISTER LES TÂCHES ---
        if action == "list":
            try:
                tasks = task_mgr.list_tasks(
                    filter_status=filter_status,
                    filter_priority=filter_priority,
                    date_range=date_range
                )
                
                if not tasks:
                    return "Aucune tâche trouvée avec ces critères."
                
                # Construire le rapport (format propre, sans emojis)
                report = f"Liste des tâches ({len(tasks)} trouvée(s)):\n\n"
                
                for task in tasks:
                    # Priorité en texte
                    priority_text = ""
                    if task.get('priority') == "critical":
                        priority_text = " [CRITIQUE]"
                    elif task.get('priority') == "high":
                        priority_text = " [HAUTE]"
                    elif task.get('priority') == "low":
                        priority_text = " [BASSE]"
                    
                    # Récurrence
                    recur_text = ""
                    if task.get('recurrence'):
                        recur_text = " (Récurrente)"
                    
                    # Statut
                    status_text = ""
                    if task.get('status') == "in_progress":
                        status_text = " [EN COURS]"
                    elif task.get('status') == "done":
                        status_text = " [TERMINÉE]"
                    
                    # Vérifier si en retard
                    overdue_text = ""
                    if task.get('due_date') and task.get('status') != 'done':
                        from datetime import datetime
                        due_dt = task_mgr._parse_due_date(task.get('due_date'))
                        if due_dt and due_dt < datetime.now():
                            overdue_text = " [EN RETARD]"
                    
                    # Format simple et propre
                    report += f"{task['title']}{priority_text}{recur_text}{status_text}{overdue_text}\n"
                    
                    if task.get('description'):
                        report += f"  Description: {task['description']}\n"
                    if task.get('due_date'):
                        report += f"  Échéance: {task['due_date']}\n"
                    if task.get('tags'):
                        report += f"  Tags: {', '.join(task['tags'])}\n"
                    
                    report += "\n"
                
                return report
            except Exception as e:
                return f"Erreur lors de la récupération des tâches: {e}"
        
        # --- COMPLÉTER UNE TÂCHE ---
        if action == "complete":
            try:
                result = task_mgr.mark_as_done(task_id=task_id, fuzzy_name=fuzzy_name)
                
                if not result.get("success"):
                    return f"Erreur: {result.get('message', 'Erreur inconnue')}"
                
                msg = result['message']
                
                # Si récurrence créée, mentionner la nouvelle tâche
                if result.get("recurrence_created") and result.get("new_task"):
                    new_task = result["new_task"]
                    msg += f". Nouvelle occurrence créée pour {new_task.get('due_date', 'N/A')}"
                
                # Notifier la GUI
                try:
                    tasks = task_mgr.list_tasks()
                    self.gui_queue.put(("TASKS_UPDATE", {"tasks": tasks}))
                except:
                    pass
                
                return msg
            except Exception as e:
                return f"Erreur lors de la complétion de la tâche: {e}"
        
        # --- SUPPRIMER UNE TÂCHE ---
        if action == "delete":
            try:
                # Si on a un fuzzy_name, vérifier si c'est une tâche récurrente
                # Si oui, supprimer toutes les occurrences
                if fuzzy_name and not task_id:
                    # Trouver la tâche pour vérifier si elle est récurrente
                    task = task_mgr.find_task_by_name(fuzzy_name)
                    if task and task.get('recurrence'):
                        # Supprimer toutes les occurrences de cette tâche récurrente
                        result = task_mgr.delete_recurring_task_by_title(task['title'])
                    else:
                        # Tâche unique, suppression normale
                        result = task_mgr.delete_task(fuzzy_name=fuzzy_name)
                else:
                    # Suppression par ID ou normale
                    result = task_mgr.delete_task(task_id=task_id, fuzzy_name=fuzzy_name)
                
                if not result.get("success"):
                    return f"Erreur: {result.get('message', 'Erreur inconnue')}"
                
                # Notifier la GUI
                try:
                    tasks = task_mgr.list_tasks()
                    self.gui_queue.put(("TASKS_UPDATE", {"tasks": tasks}))
                except:
                    pass
                
                return result['message']
            except Exception as e:
                return f"Erreur lors de la suppression de la tâche : {e}"
        
        # --- STATISTIQUES ---
        if action == "stats":
            try:
                stats = task_mgr.get_stats()
                
                report = "Statistiques des tâches:\n\n"
                report += f"Total: {stats['total']} tâches\n"
                report += f"À faire: {stats['todo']}\n"
                report += f"En cours: {stats['in_progress']}\n"
                report += f"Terminées: {stats['done']}\n"
                report += f"En retard: {stats['overdue']}\n"
                report += f"Récurrentes: {stats['recurring']}\n\n"
                
                report += "Par priorité (non terminées):\n"
                report += f"  Critique: {stats['by_priority']['critical']}\n"
                report += f"  Haute: {stats['by_priority']['high']}\n"
                report += f"  Moyenne: {stats['by_priority']['medium']}\n"
                report += f"  Basse: {stats['by_priority']['low']}\n"
                
                return report
            except Exception as e:
                return f"❌ Erreur lors du calcul des statistiques : {e}"
        
        return f"❌ Action inconnue : {action}"
    
    @staticmethod
    def _user_preferences(action: str) -> str:
        """Gère les préférences utilisateur apprises par le système d'apprentissage"""
        from core.learning_system import get_learning_system
        
        learning = get_learning_system()
        
        if action == "view":
            prefs = learning.preferences
            
            result = ["📊 PRÉFÉRENCES APPRISES PAR CYPHER\n"]
            
            # Outils préférés
            preferred_tools = prefs.get("preferred_tools", {})
            if preferred_tools:
                result.append("\n🔧 Outils fréquemment utilisés:")
                for tool, freq in sorted(preferred_tools.items(), key=lambda x: x[1], reverse=True)[:5]:
                    percentage = freq * 100
                    result.append(f"  - {tool}: {percentage:.1f}%")
            
            # Commandes fréquentes
            frequent = prefs.get("frequent_commands", {})
            if frequent:
                result.append("\n💬 Types de commandes fréquentes:")
                for pattern, freq in sorted(frequent.items(), key=lambda x: x[1], reverse=True)[:5]:
                    percentage = freq * 100
                    pattern_name = {
                        "music": "Musique/Spotify",
                        "file_management": "Gestion de fichiers",
                        "coding": "Développement de code",
                        "time_queries": "Questions sur l'heure/date",
                        "weather": "Météo"
                    }.get(pattern, pattern)
                    result.append(f"  - {pattern_name}: {percentage:.1f}%")
            
            # Comportements appris
            learned = prefs.get("learned_behaviors", {})
            if learned:
                result.append("\n🧠 Comportements appris:")
                for key, behavior in list(learned.items())[:5]:
                    if isinstance(behavior, dict):
                        desc = behavior.get("description", key)
                        conf = behavior.get("confidence", 0)
                        result.append(f"  - {desc} (confiance: {conf*100:.0f}%)")
            
            # Statistiques générales
            total_interactions = len(learning.interactions)
            if total_interactions > 0:
                result.append(f"\n📈 Total d'interactions enregistrées: {total_interactions}")
            
            if len(result) == 1:
                return "Aucune préférence apprise pour le moment. Continuez à utiliser Cypher pour qu'il apprenne vos habitudes."
            
            return "\n".join(result)
        
        elif action == "reset":
            # Réinitialiser les préférences (garder l'historique)
            learning.preferences = {
                "preferred_tools": {},
                "communication_style": "neutre",
                "frequent_commands": {},
                "time_patterns": {},
                "contextual_hints": {},
                "learned_behaviors": {},
                "custom_shortcuts": {},
                "suggestions_enabled": True,
                "last_updated": datetime.now().isoformat()
            }
            learning._save_preferences()
            learning._analyze_interactions()  # Réanalyser
            return "Préférences réinitialisées. Le système va réapprendre à partir de l'historique existant."
        
        return "Action inconnue. Utilisez 'view' ou 'reset'."
    
    @staticmethod
    def _error_history(source: str | None = None) -> str:
        import os, json
        error_file = str(get_memory_dir() / "cypher_memory_cortex.json")

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
    def _expert_coder_write_file(target_path: str) -> str:
        """
        Écrit dans un fichier le DERNIER code généré par l'outil expert_coder,
        en utilisant le même moteur que file_manager (gestion OneDrive, etc.).
        Cela évite à Gemini de devoir gérer les guillemets et les retours à la ligne du code.
        """
        try:
            expert = get_expert()
        except Exception as e:
            return f"Erreur : impossible d'accéder à l'expert_coder ({e})"

        code = getattr(expert, "last_code", None)
        if not code:
            return "Erreur : aucun code expert en mémoire. Tu dois d'abord appeler l'outil 'expert_coder'."

        # On délègue toute la logique de chemin à file_manager
        return file_manager(action="create_file", source_path=target_path, content=code)

    async def timer_watcher(self):
        """
        Surveille en tâche de fond le compte à rebours.
        Quand il atteint zéro, annonce automatiquement la fin.
        """
        while True:
            try:
                await asyncio.sleep(0.5)
                timer_end = get_timer_end()
                if timer_end is None:
                    continue

                now = datetime.now()
                remaining = (timer_end - now).total_seconds()
                if remaining <= 0 and not get_timer_alert_triggered():
                    logger.debug("Timer finished, sending auto alert.")
                    set_timer_alert_triggered(True)
                    set_timer_end(None)  # Réinitialiser le timer après l'alerte

                    message = "Le compte à rebours est terminé, Monsieur."
                    # On envoie dans la file TTS comme une réponse normale
                    self.is_speaking = True
                    await self.response_queue_tts.put(message)
                    await self.response_queue_tts.put(None)
            except Exception as e:
                logger.error(f"Erreur dans timer_watcher : {e}")
                await asyncio.sleep(1)
    
    # Note: _sb_cosine déplacé dans wake_word_detector.py - gardé pour compatibilité temporaire
    def _sb_cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        a = a.astype(np.float32)
        b = b.astype(np.float32)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    async def _handle_goodbye(self):
        """Gère la mise en veille quand l'utilisateur dit au revoir"""
        logger.info("Au revoir détecté - Mise en veille")
        
        # 1. Arrêter toute réponse en cours
        self.conversation_active = False
        self.is_busy = False
        
        # 2. Notifier le tool executor si interruption
        if self.tool_executor:
            self.tool_executor.set_interrupted(True)
        
        # 3. Arrêter la parole de Cypher
        if self.is_speaking:
            # Vider la file d'attente du TTS
            if self.response_queue_tts:
                while not self.response_queue_tts.empty():
                    try: self.response_queue_tts.get_nowait()
                    except asyncio.QueueEmpty: break
            
            # Vider la file d'attente du Player
            if self.audio_in_queue_player:
                while not self.audio_in_queue_player.empty():
                    try: self.audio_in_queue_player.get_nowait()
                    except asyncio.QueueEmpty: break
            
            # Arrêter le son pygame
            try: pygame.mixer.music.stop()
            except Exception as e:
                logger.debug(f"Erreur lors de l'arrêt pygame: {e}")
            
            self.is_speaking = False
        
        # 4. Jouer le son end_listening
        self.sound_manager.play("end_listening", volume=0.35)
        
        # 5. Mettre à jour le statut GUI
        self.gui_queue.put(("STATUS", "idle"))
        
        logger.info("Cypher est maintenant en veille")

    def _interrupt_playback(self):
        """KILL SWITCH : Coupe la parole instantanément et FORCE l'écoute."""
        logger.info("Interruption demandée (barge-in)")
        # --- FIX CRITIQUE : On débloque le cerveau immédiatement ---
        self.is_busy = False
        
        # Notifier le tool executor
        if self.tool_executor:
            self.tool_executor.set_interrupted(True)
        
        if self.is_speaking:
            logger.info("Wake word détecté - Cypher se tait !")
            
            # 1. On vide la file d'attente du TTS
            if self.response_queue_tts:
                while not self.response_queue_tts.empty():
                    try: self.response_queue_tts.get_nowait()
                    except asyncio.QueueEmpty: break
            
            # 2. On vide la file d'attente du Player
            if self.audio_in_queue_player:
                while not self.audio_in_queue_player.empty():
                    try: self.audio_in_queue_player.get_nowait()
                    except asyncio.QueueEmpty: break
            
            # 3. On arrête le son pygame
            try: pygame.mixer.music.stop()
            except Exception as e:
                logger.debug(f"Erreur lors de l'arrêt pygame: {e}")
            
            # 4. On force l'état silencieux
            self.is_speaking = False
            self.gui_queue.put(("STATUS", "listening"))

    async def send_realtime(self):
        import base64
        import json
        
        try:
            while True:
                msg = await self.out_queue_gemini.get()
                try:
                    if not self.session: continue
                    
                    # Extraction du contenu
                    if isinstance(msg, dict):
                        content = msg.get("data")
                        mime_type = msg.get("mime_type", "text/plain")
                    else:
                        content = msg
                        mime_type = "text/plain"

                    if not content: continue 

                    # 1. ENVOI TEXTE (Simple)
                    if isinstance(content, str):
                        await self.session.send(input=content, end_of_turn=True)
                    
                    # 2. ENVOI AUDIO (Encodage Base64 pour compatibilité MAXIMALE)
                    elif isinstance(content, bytes):
                        # On encode les octets en Base64 (texte)
                        b64_data = base64.b64encode(content).decode("utf-8")
                        
                        # On construit le payload standard de l'API Gemini
                        payload = {
                            "mime_type": "audio/pcm",
                            "data": b64_data
                        }
                        
                        # On envoie via la méthode générique send() qui gère les dicts
                        # end_of_turn=False car c'est du streaming continu
                        await self.session.send(input=payload, end_of_turn=False)
                            
                except Exception as e:
                    # On ignore les erreurs silencieuses pour la fluidité
                    pass
                finally:
                    self.out_queue_gemini.task_done()
        except asyncio.CancelledError:
            pass
    

    async def listen_audio(self):
        """Écoute le microphone et détecte le wake word 'Sayfeure' avec SpeechBrain"""
        import numpy as np
        from collections import deque
        import winsound
        import pyaudio
        
        target_device_index = 1  # Index du micro (ajuste si nécessaire)
        sample_rate = 16000
        chunk_size = 4000  # ~250ms à 16kHz
        
        logger.info("Initialisation du micro pour la détection du wake word...")
        
        try:
            self.audio_stream = await asyncio.to_thread(
                pya.open, 
                format=pyaudio.paInt16, 
                channels=1, 
                rate=sample_rate, 
                input=True, 
                input_device_index=target_device_index, 
                frames_per_buffer=chunk_size
            )
        except Exception as e:
            logger.error(f"Impossible d'ouvrir le micro : {e}")
            return
        
        # Buffer audio pour accumuler ~1 seconde d'audio
        audio_deque = deque(maxlen=4)  # ~1 seconde à 16kHz
        last_detection_time = 0
        cooldown_sec = 1.0  # Temps minimum entre deux détections (réduit pour plus de réactivité)
        barge_in_skip_counter = 0  # Compteur pour traiter moins souvent pendant que Cypher parle
        
        logger.info("Écoute active - dis 'Sayfeure' pour activer (barge-in activé)")
        
        while True:
            try:
                # Lecture du micro
                data = await asyncio.to_thread(
                    self.audio_stream.read, 
                    chunk_size, 
                    exception_on_overflow=False
                )
                
                # Convertir en float32 normalisé [-1, 1]
                np_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                audio_deque.append(np_data)
                
                # Si Cypher parle, on traite moins souvent pour économiser CPU
                # mais on continue d'écouter pour permettre le barge-in
                if self.is_speaking:
                    barge_in_skip_counter += 1
                    # Traiter seulement 1 fois sur 3 pour économiser CPU
                    if barge_in_skip_counter < 3:
                        continue
                    barge_in_skip_counter = 0
                else:
                    barge_in_skip_counter = 0
                
                # Il faut au moins 3 chunks pour analyser (~750ms)
                if len(audio_deque) < 3:
                    continue
                
                # Concaténer les chunks pour avoir une fenêtre d'analyse
                live_audio = np.concatenate(list(audio_deque))
                
                # Calculer le RMS (volume moyen)
                rms = float(np.sqrt(np.mean(np_data ** 2) + 1e-12))
                
                # Envoyer le niveau audio au GUI pour l'animation de l'orb (seulement en listening)
                if self.conversation_active and not self.is_speaking:
                    # Normaliser le RMS (typiquement 0.0-0.1, mais on peut aller plus haut)
                    # On utilise une fonction logarithmique pour une meilleure visualisation
                    normalized_level = min(1.0, rms * 10.0)  # Scale pour avoir 0.0-1.0
                    # Appliquer une courbe pour rendre les variations plus visibles
                    normalized_level = normalized_level ** 0.5  # Racine carrée pour étaler les faibles volumes
                    try:
                        self.gui_queue.put_nowait(("AUDIO_LEVEL", str(normalized_level)))
                    except queue.Full:
                        pass  # Si la queue est pleine, on ignore (pas critique)
                
                # Si Cypher parle, on utilise un seuil RMS plus élevé pour éviter les faux positifs
                # (sa propre voix ne doit pas déclencher le wake word)
                min_rms_threshold = self.WAKE_MIN_RMS * 2.0 if self.is_speaking else self.WAKE_MIN_RMS
                
                # Ignorer le silence/bruit faible
                if rms < min_rms_threshold:
                    score = 0.0
                    is_detected = False
                elif self.sb_classifier is None or self.sb_target is None:
                    # SpeechBrain non disponible - désactiver la détection
                    score = 0.0
                    is_detected = False
                else:
                    # Convertir en tensor pour SpeechBrain
                    audio_tensor = torch.tensor(live_audio, dtype=torch.float32).unsqueeze(0)  # [1, T]
                    
                    try:
                        # Générer l'embedding avec SpeechBrain
                        with torch.no_grad():
                            emb = self.sb_classifier.encode_batch(audio_tensor).squeeze().cpu().numpy()
                        
                        # AMÉLIORATION 1: Utiliser l'embedding pré-normalisé pour accélérer
                        if hasattr(self, 'sb_target_normalized') and self.sb_target_normalized is not None:
                            # Version optimisée avec embedding pré-normalisé (plus rapide)
                            emb_norm = np.linalg.norm(emb)
                            if emb_norm > 0:
                                emb_normalized = emb / emb_norm
                                score = float(np.dot(emb_normalized, self.sb_target_normalized))
                            else:
                                score = 0.0
                        else:
                            # Fallback vers l'ancienne méthode si pas de cache
                            score = self._sb_cosine(emb, self.sb_target)
                        
                        # Détection plus réactive : 1 seul hit suffit (au lieu de 2)
                        # Cela rend la détection plus immédiate et fiable
                        if score >= self.WAKE_THRESHOLD:
                            self._wake_hit_count = 1  # On met directement à 1 pour déclencher
                            is_detected = True
                        else:
                            self._wake_hit_count = 0
                            is_detected = False
                        
                        # Debug : afficher les scores élevés pour calibration
                        if score > 0.35:  # Afficher seulement les scores intéressants
                            logger.debug(f"Wake word debug - Score: {score:.3f}, RMS: {rms:.3f}, Threshold: {self.WAKE_THRESHOLD}")
                    except Exception as e:
                        logger.warning(f"Erreur lors de la détection du wake word: {e}")
                        score = 0.0
                        is_detected = False
                
                current_time = time.time()
                
                # Détection du wake word
                if is_detected and (current_time - last_detection_time > cooldown_sec):
                    # BARGE-IN : Si Cypher parle ou travaille, on l'interrompt immédiatement
                    if self.is_speaking or self.is_busy:
                        logger.info(f"BARGE-IN: Sayfeure détecté pendant la parole/travail - Interruption ! (Score: {score:.3f})")
                        self._interrupt_playback()
                        # Activer la conversation immédiatement
                        self.conversation_active = True
                        self.last_interaction_time = time.time()
                        last_detection_time = current_time
                        # Son de confirmation (barge-in)
                        self.sound_manager.play("wake", volume=0.4)
                        # NE PAS envoyer l'audio du wake word - vider le buffer
                        audio_deque.clear()
                        # Pas besoin d'envoyer de réponse texte pour le barge-in, 
                        # l'utilisateur va continuer à parler
                        continue
                    
                    # Activation normale (quand Cypher ne parle pas)
                    if not self.conversation_active:
                        logger.info(f"WAKE: Sayfeure détecté ! (Score: {score:.3f}, RMS: {rms:.3f})")
                        
                        # Son de confirmation (wake word)
                        self.sound_manager.play("wake", volume=0.4)
                        
                        # Activer la conversation
                        self.gui_queue.put(("STATUS", "listening"))
                        self.conversation_active = True
                        self.last_interaction_time = time.time()
                        last_detection_time = current_time
                        
                        # NE PAS envoyer l'audio du wake word à Gemini
                        # Vider le buffer pour repartir proprement
                        audio_deque.clear()
                        
                        # Envoyer une réponse simple de confirmation (texte)
                        if not self.is_busy and self.out_queue_gemini:
                            # Réponse simple et naturelle
                            wake_responses = [
                                "Oui, je suis là. Comment puis-je t'aider ?",
                                "Je t'écoute.",
                                "Oui, je suis prêt. Que veux-tu ?",
                                "Je suis là, que puis-je faire pour toi ?"
                            ]
                            import random
                            response = random.choice(wake_responses)
                            await self.out_queue_gemini.put(response)
                
                # Gestion de la conversation active
                if self.conversation_active:
                    # Détecter si l'utilisateur parle encore
                    vol = np.abs(np_data).mean()
                    if vol > 0.01:
                        self.last_interaction_time = time.time()
                    
                    # Timeout après silence (mais PAS si Cypher est en train de parler ou de travailler)
                    if (time.time() - self.last_interaction_time > self.CONVERSATION_TIMEOUT) and not self.is_busy and not self.is_speaking:
                        logger.info("SLEEP: Silence détecté, retour en veille.")
                        self.sound_manager.play("end_listening", volume=0.35)
                        self.gui_queue.put(("STATUS", "idle"))
                        self.conversation_active = False
                        audio_deque.clear()
                        continue
                    
                    # Envoyer l'audio à Gemini pendant la conversation
                    if not self.is_busy:
                        await self.out_queue_gemini.put({
                            "data": data, 
                            "mime_type": "audio/pcm"
                        })
            
            except Exception as e:
                # En cas d'erreur, on continue pour éviter de planter
                logger.error(f"Erreur dans listen_audio : {e}")
                await asyncio.sleep(0.1)
                continue


    def _get_additional_state(self) -> Dict[str, Any]:
        """Retourne l'état additionnel à sauvegarder"""
        try:
            return {
                "conversation_active": self.conversation_active,
                "is_speaking": self.is_speaking,
                "is_busy": self.is_busy,
                "last_interaction_time": self.last_interaction_time
            }
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération de l'état additionnel: {e}")
            return {}

    async def receive_text(self):
        """
        Version optimisée : Nettoie le texte pour l'audio mais garde le formatage pour le GUI.
        """
        text_buffer = "" 

        while True:
            try:
                # Réinitialiser les variables d'interaction pour ce tour
                self._current_tools_used = []
                self._current_response = ""

                turn = self.session.receive()

                tool_responses = []
                web_search_urls = set()
                goodbye_detected = False  # Flag pour détecter les au revoir
                
                # Capturer l'input utilisateur depuis le turn si disponible
                if hasattr(turn, 'model_request') or hasattr(turn, 'user_input'):
                    try:
                        # Essayer de récupérer l'input utilisateur (selon l'API Gemini)
                        # Note: L'API Gemini Live ne retourne pas toujours la transcription utilisateur directement
                        # On essaie de capturer depuis les chunks si disponibles
                        pass
                    except:
                        pass

                async for chunk in turn:
                    # [BLOC TOOLS ET SERVER CONTENT INCHANGÉ - GARDER LE TIEN ICI SI BESOIN]
                    # Pour faire court, je remets la logique complète ci-dessous :
                    
                    if hasattr(chunk, "tool_call") and chunk.tool_call:
                        # 🔒 ON VERROUILLE : Cypher commence à travailler
                        self.is_busy = True
                        self._interrupted_flag = False  # Réinitialiser le flag d'interruption
                        
                        function_calls = chunk.tool_call.function_calls
                        if function_calls:
                            tool_responses = []
                            for fc in function_calls:
                                fname = fc.name
                                args = dict(fc.args or {})
                                
                                # Enregistrer l'utilisation de l'outil pour l'apprentissage
                                if fname not in self._current_tools_used:
                                    self._current_tools_used.append(fname)
                                
                                # Vérifier si on a été interrompu avant même de commencer
                                if self._interrupted_flag:
                                    logger.info(f"INTERRUPTION: Tool {fname} annulé avant exécution (interruption en cours)")
                                    tool_responses.append({"id": fc.id, "name": fname, "response": {"error": "Operation cancelled by user interruption"}})
                                    continue
                                
                                # 1. FEEDBACK VISUEL
                                if fname in ["execute_python", "document_manager", "google_search", "file_manager"]:
                                    self.gui_queue.put(("STATUS", "processing"))

                                # 1.5. FEEDBACK SONORE (processing)
                                self.sound_manager.play("processing", volume=0.25)

                                # 2. FEEDBACK AUDIO (NOUVEAU !!)
                                # On vérifie si on a des phrases pour cet outil
                                if fname in LOADING_PHRASES:
                                    # On choisit une phrase au hasard
                                    phrase = random.choice(LOADING_PHRASES[fname])
                                    
                                    # On l'ajoute à la file TTS immédiatement
                                    self.is_speaking = True # Active l'animation de l'orbe
                                    await self.response_queue_tts.put(phrase)
                                
                                # 3. EXECUTION DE L'OUTIL
                                if fname not in FUNCTION_MAP:
                                    tool_responses.append({"id": fc.id, "name": fname, "response": {"error": f"Function {fname} not implemented"}})
                                    continue
                                
                                try:
                                    # Exécution de l'outil
                                    # Gérer les fonctions d'instance (qui nécessitent self)
                                    if fname == "manage_tasks":
                                        result = await asyncio.to_thread(self._manage_tasks, **args)
                                    else:
                                        result = await asyncio.to_thread(FUNCTION_MAP[fname], **args)
                                    
                                    # Si on a été interrompu pendant l'exécution, on annule l'envoi
                                    if self._interrupted_flag:
                                        logger.info(f"INTERRUPTION: Tool {fname} annulé suite à l'interruption pendant l'exécution")
                                        tool_responses.append({"id": fc.id, "name": fname, "response": {"error": "Operation cancelled by user interruption"}})
                                    else:
                                        tool_responses.append({"id": fc.id, "name": fname, "response": {"result": result}})
                                        # Son de succès pour tool exécuté avec succès
                                        self.sound_manager.play("success", volume=0.2)
                                except Exception as e:
                                    # Son d'erreur si erreur non interrompue
                                    if not self._interrupted_flag:
                                        self.sound_manager.play("error", volume=0.25)
                                    # Même si une exception se produit, on ajoute l'erreur (sauf si interrompu)
                                    if not self._interrupted_flag:
                                        tool_responses.append({"id": fc.id, "name": fname, "response": {"error": str(e)}})
                                    else:
                                        tool_responses.append({"id": fc.id, "name": fname, "response": {"error": "Operation cancelled by user interruption"}})
                            
                            # Construire les réponses finales : si interrompu, on envoie uniquement des annulations
                            was_interrupted = self._interrupted_flag
                            if self._interrupted_flag:
                                # Si interrompu, on remplace toutes les réponses par des annulations
                                final_responses = [{"id": fc.id, "name": fc.name, "response": {"error": "Operation cancelled by user interruption"}} for fc in function_calls]
                                logger.info(f"INTERRUPTION: Envoi de {len(final_responses)} réponse(s) d'annulation à Gemini pour débloquer la session")
                            else:
                                final_responses = tool_responses
                            
                            # Toujours envoyer une réponse à Gemini pour débloquer la session
                            if final_responses:
                                try:
                                    await self.session.send_tool_response(function_responses=final_responses)
                                    logger.info(f"TOOL: Réponse(s) envoyée(s) à Gemini ({len(final_responses)} tool(s)) - Session débloquée")
                                except Exception as e:
                                    logger.error(f"Impossible d'envoyer la réponse tool à Gemini: {e}")
                            
                            # 🔓 ON DEVERROUILLE : Cypher a fini ce tool (ou a été interrompu)
                            self.is_busy = False
                            self.last_interaction_time = time.time() # On remet le chrono à zéro
                            
                            # Si on a été interrompu, on reset le flag pour la prochaine fois
                            # IMPORTANT: On reset le flag APRÈS avoir envoyé la réponse pour éviter les race conditions
                            if was_interrupted:
                                logger.info("INTERRUPTION: Reset du flag d'interruption - prêt pour nouvelle interaction")
                                self._interrupted_flag = False
                                
                                # Forcer un petit délai pour s'assurer que Gemini a bien reçu la réponse
                                await asyncio.sleep(0.1)
                        continue

                    if hasattr(chunk, "server_content") and chunk.server_content:
                        if (hasattr(chunk.server_content, 'grounding_metadata') and chunk.server_content.grounding_metadata and chunk.server_content.grounding_metadata.grounding_chunks):
                            for grounding_chunk in chunk.server_content.grounding_metadata.grounding_chunks:
                                if grounding_chunk.web and grounding_chunk.web.uri:
                                    web_search_urls.add(grounding_chunk.web.uri)

                    # --- GESTION DU TEXTE (MODIFIÉ) ---
                    if getattr(chunk, "text", None):
                        current_text = chunk.text
                        print(current_text, end="", flush=True)
                        
                        text_buffer += current_text
                        
                        # 🔍 DÉTECTION DES AU REVOIR PENDANT LE STREAMING (AMÉLIORÉE)
                        import re
                        text_lower_check = text_buffer.lower()
                        
                        # Liste étendue des mots-clés d'au revoir - patterns simplifiés pour détecter même au milieu d'une phrase
                        goodbye_patterns = [
                            r"\bau\s+revoir\b",
                            r"\bà\s+plus\b",
                            r"\ba\s+plus\b",
                            r"\bbye\b",
                            r"\bà\s+bientôt\b",
                            r"\ba\s+bientot\b",
                            r"\bbonne\s+nuit\b",
                            r"\bsalut\s*[.,;:!?]*\s*$",  # "salut" à la fin
                            r"\bciao\b",
                            r"\bsee\s+you\b",
                            r"\bgoodbye\b",
                            r"\bfarewell\b",
                            r"\bà\s+la\s+prochaine\b",
                            r"\bprochainement\b",
                        ]
                        
                        # Vérifier si un pattern d'au revoir est détecté dans le buffer
                        for pattern in goodbye_patterns:
                            if re.search(pattern, text_lower_check, re.IGNORECASE):
                                logger.info(f"Au revoir détecté dans la réponse: '{pattern}'")
                                await self._handle_goodbye()
                                text_buffer = ""  # Vider le buffer
                                goodbye_detected = True
                                break
                        
                        # Si on a détecté un au revoir, on ignore le reste du texte
                        if goodbye_detected:
                            continue
                        
                        # Traitement normal du texte (split par phrases)
                        split_pattern = r'([.?!;])\s+'
                        parts = re.split(split_pattern, text_buffer)
                        
                        if len(parts) > 1:
                            for i in range(0, len(parts) - 1, 2):
                                if i + 1 >= len(parts):
                                    text_buffer = parts[i]
                                    break
                                
                                raw_sentence = parts[i] + parts[i+1]
                                
                                # Vérifier aussi chaque phrase individuellement
                                sentence_lower = raw_sentence.lower()
                                for pattern in goodbye_patterns:
                                    if re.search(pattern, sentence_lower, re.IGNORECASE):
                                        logger.info(f"Au revoir détecté dans une phrase: '{pattern}'")
                                        await self._handle_goodbye()
                                        text_buffer = ""
                                        goodbye_detected = True
                                        break
                                
                                if goodbye_detected:  # Si on a détecté un au revoir, on arrête
                                    break
                                
                                # === LE FIX EST ICI ===
                                # On nettoie AVANT d'envoyer à la voix
                                clean_sentence = clean_text_for_tts(raw_sentence)
                                
                                if clean_sentence:
                                    self.is_speaking = True
                                    await self.response_queue_tts.put(clean_sentence)
                            
                            if not goodbye_detected:
                                text_buffer = parts[-1]
                            else:
                                text_buffer = ""

                # --- FIN DU TOUR ---
                if text_buffer.strip() and not goodbye_detected:
                    text_lower = text_buffer.lower()
                    
                    # DERNIÈRE VÉRIFICATION À LA FIN DU TOUR
                    import re
                    # Patterns simplifiés pour détecter même au milieu d'une phrase
                    goodbye_patterns_final = [
                        r"\bau\s+revoir\b",
                        r"\bà\s+plus\b",
                        r"\ba\s+plus\b",
                        r"\bbye\b",
                        r"\bà\s+bientôt\b",
                        r"\ba\s+bientot\b",
                        r"\bbonne\s+nuit\b",
                        r"\bciao\b",
                        r"\bsee\s+you\b",
                        r"\bgoodbye\b",
                        r"\bà\s+la\s+prochaine\b",
                    ]
                    
                    for pattern in goodbye_patterns_final:
                        if re.search(pattern, text_lower, re.IGNORECASE):
                            logger.info(f"Au revoir détecté à la fin du tour: '{pattern}'")
                            await self._handle_goodbye()
                            text_buffer = ""
                            goodbye_detected = True  # CRITIQUE: Mettre à jour le flag
                            break
                    
                    # Si on a détecté un au revoir, on ne continue pas avec le TTS
                    if goodbye_detected or not text_buffer:
                        continue

                    self.is_speaking = True
                    
                    # Sauvegarder la réponse pour l'apprentissage
                    self._current_response = text_buffer.strip()
                    
                    # 1. On envoie le texte BRUT (avec *) au GUI pour qu'il soit joli
                    self.gui_queue.put(("ASSISTANT_TEXT", text_buffer.strip()))
                    
                    # 2. On envoie le texte NETTOYÉ (sans *) à Azure pour qu'il le lise bien
                    clean_buffer = clean_text_for_tts(text_buffer)
                    await self.response_queue_tts.put(clean_buffer)
                    
                    text_buffer = "" 
                
                # Si un au revoir a été détecté, on arrête complètement le traitement
                if goodbye_detected:
                    # On ne continue pas avec l'enregistrement ni le reste du traitement
                    await self.response_queue_tts.put(None)  # Signal de fin pour le TTS
                    continue  # Retourner au début de la boucle principale
                
                # Enregistrer l'interaction pour l'apprentissage (à la fin du tour)
                if hasattr(self, 'learning_system') and self._current_response:
                    # Essayer de récupérer l'input utilisateur depuis le contexte
                    # (Pour l'instant on utilise un placeholder, idéalement on devrait capturer le texte transcrit)
                    user_input = self._current_user_input if hasattr(self, '_current_user_input') and self._current_user_input else "conversation_audio"
                    
                    # Enregistrer l'interaction dans le learning system
                    try:
                        self.learning_system.record_interaction(
                            user_input=user_input,
                            cypher_response=self._current_response,
                            tools_used=self._current_tools_used,
                            context={"timestamp": datetime.now().isoformat()}
                        )
                    except Exception as e:
                        logger.debug(f"Erreur lors de l'enregistrement de l'interaction: {e}")
                    
                    # AMÉLIORATION 2 & 4: Enregistrer le tour dans le StateManager pour résumé et sauvegarde
                    try:
                        self.state_manager.add_conversation_turn(
                            user_input=user_input,
                            assistant_response=self._current_response,
                            tools_used=self._current_tools_used
                        )
                    except Exception as e:
                        logger.debug(f"Erreur lors de l'ajout du tour au StateManager: {e}")
                    
                    # Réinitialiser pour la prochaine interaction
                    self._current_user_input = ""
                    self._current_tools_used = []
                    self._current_response = ""
                
                await self.response_queue_tts.put(None)
                self.last_interaction_time = time.time()

            except Exception as e:
                error_str = str(e).lower()
                if "1011" in error_str or "unavailable" in error_str or "connection" in error_str or "deadline" in error_str:
                    logger.warning(f"Session expirée: {e}")
                    self.needs_reconnect = True
                    return  # Sortir proprement au lieu de raise
                
                logger.error(f"Erreur dans receive_text: {e}")
                traceback.print_exc()
                self.needs_reconnect = True
                return  # Sortir proprement

    async def tts(self):
        """
        Génère le TTS via Azure AI Speech avec SSML (Style & Vitesse).
        """
        # --- CONFIG AZURE ---
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        # Note: Avec SSML, la voix est définie dans le XML, mais on garde la config de base propre
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
        )
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    
        logger.info(f"Azure TTS (SSML) prêt ({AZURE_VOICE_NAME} | Vitesse: {TTS_RATE})")
    
        while True:
            full_text = await self.response_queue_tts.get()
            
            # --- SIGNAL DE FIN ---
            if full_text is None:
                await self.audio_in_queue_player.put(None)
                self.response_queue_tts.task_done()
                continue
    
            try:
                # 1. On transforme le texte brut en SSML (XML avec réglages)
                ssml_text = generate_ssml(full_text, AZURE_VOICE_NAME, TTS_RATE, TTS_PITCH)

                # 2. On génère l'audio via SSML
                def _generate_audio_blocking():
                    return synthesizer.speak_ssml_async(ssml_text).get()
    
                result = await asyncio.to_thread(_generate_audio_blocking)
    
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    audio_data = result.audio_data
                    if audio_data:
                        await self.audio_in_queue_player.put(audio_data)
                
                elif result.reason == speechsdk.ResultReason.Canceled:
                    cancellation_details = result.cancellation_details
                    logger.error(f"Erreur Azure TTS : {cancellation_details.reason}")
                    if cancellation_details.reason == speechsdk.CancellationReason.Error:
                        logger.error(f"Code erreur: {cancellation_details.error_code}")
                        logger.error(f"Détails: {cancellation_details.error_details}")
    
            except Exception as e:
                logger.error(f"Exception TTS : {e}")
            
            finally:
                self.response_queue_tts.task_done()


    async def play_audio(self):
        """
        Joue l'audio avec gestion du timeout correcte.
        ✅ VERSION CORRIGÉE : Reset du timer quand Cypher finit de parler
        """
        stream = None
        
        try:
            stream = await asyncio.to_thread(
                pya.open, 
                format=FORMAT, 
                channels=CHANNELS,
                rate=RECEIVE_SAMPLE_RATE, 
                output=True,
                frames_per_buffer=CHUNK_SIZE
            )
            logger.info("Audio output stream is open.")
        except Exception as e:
            logger.error(f"FATAL: Could not open PyAudio stream: {e}")
            return

        while True:
            try:
                # Récupère le paquet audio (ou signal de fin)
                bytestream = await self.audio_in_queue_player.get()
                
                # --- SIGNAL DE FIN REÇU ---
                if bytestream is None:
                    # ✅ LIBÉRATION DU MICRO
                    self.is_speaking = False
                    
                    # 🔥 FIX CRITIQUE : RESET DU TIMER ICI
                    self.last_interaction_time = time.time()
                    
                    if self.conversation_active:
                        self.gui_queue.put(("STATUS", "listening"))
                    else:
                        self.gui_queue.put(("STATUS", "idle"))
                        
                    logger.info(f"Micro libéré (active={self.conversation_active})")
                    self.audio_in_queue_player.task_done()
                    continue

                # --- LECTURE AUDIO AVEC PROTECTION ---
                if bytestream:
                    try:
                        # Vérifier que le stream est toujours ouvert
                        if stream and stream.is_active():
                            self.gui_queue.put(("STATUS", "speaking"))
                            await asyncio.to_thread(stream.write, bytestream)
                        else:
                            # Stream fermé, on le réouvre
                            logger.warning("Stream audio fermé, réouverture...")
                            if stream:
                                try:
                                    stream.close()
                                except:
                                    pass
                            
                            stream = await asyncio.to_thread(
                                pya.open, 
                                format=FORMAT, 
                                channels=CHANNELS,
                                rate=RECEIVE_SAMPLE_RATE, 
                                output=True,
                                frames_per_buffer=CHUNK_SIZE
                            )
                            
                            # Réessayer la lecture
                            await asyncio.to_thread(stream.write, bytestream)
                    
                    except OSError as e:
                        # Gestion spécifique des erreurs PyAudio
                        if e.errno in [-9999, -9988, -9981]:
                            logger.error(f"Erreur PyAudio {e.errno}, tentative de récupération...")
                            
                            # Fermer et rouvrir le stream
                            if stream:
                                try:
                                    stream.stop_stream()
                                    stream.close()
                                except:
                                    pass
                            
                            # Attendre un peu
                            await asyncio.sleep(0.5)
                            
                            # Réouvrir
                            try:
                                stream = await asyncio.to_thread(
                                    pya.open, 
                                    format=FORMAT, 
                                    channels=CHANNELS,
                                    rate=RECEIVE_SAMPLE_RATE, 
                                    output=True,
                                    frames_per_buffer=CHUNK_SIZE
                                )
                                logger.info("Stream audio récupéré.")
                            except Exception as e2:
                                logger.error(f"FATAL: Impossible de récupérer le stream : {e2}")
                                self.is_speaking = False
                                break
                        else:
                            raise  # Autre erreur, on propage
                
                self.audio_in_queue_player.task_done()
                
            except asyncio.CancelledError:
                logger.info("play_audio task cancelled")
                break
            except Exception as e:
                logger.error(f"Erreur dans la boucle de lecture audio: {e}")
                self.is_speaking = False
                await asyncio.sleep(0.5)
        
        # NETTOYAGE PROPRE
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
                logger.info("Audio stream closed cleanly.")
            except:
                pass

    def _cleanup_queues(self):
        """Vide toutes les queues pour repartir sur une base propre après reconnexion"""
        logger.info("CLEANUP: Nettoyage des queues audio...")
        
        # Vider la queue TTS
        if self.response_queue_tts:
            while not self.response_queue_tts.empty():
                try:
                    self.response_queue_tts.get_nowait()
                    self.response_queue_tts.task_done()
                except:
                    break
        
        # Vider la queue Player
        if self.audio_in_queue_player:
            while not self.audio_in_queue_player.empty():
                try:
                    self.audio_in_queue_player.get_nowait()
                    self.audio_in_queue_player.task_done()
                except:
                    break
        
        # Vider la queue Gemini
        if self.out_queue_gemini:
            while not self.out_queue_gemini.empty():
                try:
                    self.out_queue_gemini.get_nowait()
                    self.out_queue_gemini.task_done()
                except:
                    break
        
        # Reset des états
        self.is_speaking = False
        self.is_busy = False
        
        logger.info("CLEANUP: Queues vidées, prêt pour reconnexion")

    async def run(self):
        import websockets
        reconnect_delay = 2
        max_delay = 30
        
        while True:
            self.needs_reconnect = False
            
            try:
                logger.info("Tentative de connexion à Gemini...")
                self.session = None
                
                async with self.client.aio.live.connect(model=MODEL, config=self.config) as session:
                    self.session = session
                    # Son de connexion réussie
                    self.sound_manager.play("connect", volume=0.25)
                    self.out_queue_gemini = asyncio.Queue(maxsize=20)
                    
                    if self.response_queue_tts is None:
                        self.response_queue_tts = asyncio.Queue()
                    if self.audio_in_queue_player is None:
                        self.audio_in_queue_player = asyncio.Queue()

                    logger.info("Connecté !")
                    self.gui_queue.put(("STATUS", "idle"))
                    
                    reconnect_delay = 2

                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(self.listen_audio())
                            tg.create_task(self.send_realtime())
                            tg.create_task(self.receive_text())
                            tg.create_task(self.tts())
                            tg.create_task(self.play_audio())
                            tg.create_task(self.timer_watcher())
                            tg.create_task(self.agenda_watcher())
                            # AMÉLIORATION 4: Auto-sauvegarde périodique
                            tg.create_task(self.state_manager.auto_save_loop(
                                learning_system=self.learning_system,
                                additional_state_callback=self._get_additional_state
                            ))
                    except* (websockets.exceptions.ConnectionClosed,
                            websockets.exceptions.ConnectionClosedError,
                            ConnectionResetError) as eg:
                        logger.warning(f"RECONNECT: Connexion perdue (group): {eg}")
                        self.needs_reconnect = True
                    except* Exception as eg:
                        logger.error(f"RECONNECT: Erreur TaskGroup: {eg}")
                        self.needs_reconnect = True

            except asyncio.CancelledError:
                logger.info("Arrêt manuel.")
                break
            
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.ConnectionClosedError,
                    ConnectionResetError) as e:
                logger.warning(f"RECONNECT: Connexion perdue: {e}")
                self.sound_manager.play("disconnect", volume=0.25)
                self.needs_reconnect = True
            
            except Exception as e:
                logger.error(f"Erreur inattendue: {e}")
                traceback.print_exc()
                self.needs_reconnect = True
            
            finally:
                self.session = None
                if self.audio_stream:
                    try:
                        if self.audio_stream.is_active():
                            self.audio_stream.stop_stream()
                        self.audio_stream.close()
                    except:
                        pass
            
            # Reconnexion si nécessaire
            if self.needs_reconnect:
                logger.info(f"RECONNECT: Reconnexion dans {reconnect_delay}s...")
                self._cleanup_queues()
                self.gui_queue.put(("STATUS", "reconnecting"))
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_delay)
                continue
            else:
                break



FUNCTION_MAP = {
    "get_time": get_time,
    "get_date": get_date,
    "get_weather": get_weather,
    "manage_stopwatch": manage_stopwatch,
    "manage_timer": manage_timer,
    "open_app": open_app,
    "open_website": open_website,
    "execute_python": execute_python,
    "get_python_execution_history": get_python_execution_history,
    "file_manager": file_manager,
    "window_manager": window_manager,
    "system_control": system_control,
    "process_manager": process_manager,
    "power_control": power_control,
    "system_optimize": system_optimize,
    "network_manager": network_manager,
    "memory_manager": memory_manager,
    "error_history_tool": AudioLoop._error_history,
    "manage_agenda": manage_agenda,
    "email_manager": email_manager,
    "document_manager": document_manager,
    "manage_tasks": AudioLoop._manage_tasks,
    "expert_coder": expert_coder_tool,
    "expert_coder_write_file": AudioLoop._expert_coder_write_file,
    "expert_stats": expert_stats,
    "spotify_control": spotify_tool,
    "analyze_screen": analyze_screen_tool,
    "web_navigator": web_navigator_tool,
    "user_preferences": AudioLoop._user_preferences,
}

def run_backend(gui_queue):
    """
    Cette fonction crée une boucle asyncio isolée pour Cypher
    afin qu'il puisse tourner en même temps que le GUI.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # On initialise Cypher avec la queue de communication
    # (On force le mode vidéo à "none" ou DEFAULT_MODE si défini plus haut)
    mode = "none" 
    if 'DEFAULT_MODE' in globals():
        mode = DEFAULT_MODE
        
    main_loop = AudioLoop(gui_queue=gui_queue, video_mode=mode)
    
    try:
        loop.run_until_complete(main_loop.run())
    except KeyboardInterrupt:
        pass
    finally:
        # Nettoyage propre quand le thread s'arrête
        loop.close()
        # Si pyaudio est global, on peut le fermer ici si besoin, 
        # mais le daemon thread s'arrêtera brutalement à la fermeture du GUI, ce qui est OK.

# --- LANCEMENT PRINCIPAL ---
if __name__ == "__main__":
    import queue
    import threading
    from modules.gui import CypherGUI 

    logger.info("Lancement de l'interface graphique...")

    # 1. Création du canal de communication (Le Tuyau)
    gui_queue = queue.Queue()
    
    # 2. Lancement de Cypher (Backend) dans un thread parallèle
    # daemon=True signifie que si tu fermes la fenêtre, Cypher s'éteint aussi.
    backend_thread = threading.Thread(target=run_backend, args=(gui_queue,), daemon=True)
    backend_thread.start()
    
    # 3. Lancement du GUI (C'est lui qui prend le contrôle du thread principal)
    try:
        app = CypherGUI(data_queue=gui_queue)
        app.mainloop()
    except Exception as e:
        logger.error(f"CRASH GUI: {e}")
    finally:
        # Nettoyage final
        try:
            pya.terminate()
        except:
            pass
        logger.info("Application fermée.")