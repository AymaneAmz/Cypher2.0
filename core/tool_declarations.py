"""
Déclarations de tous les tools pour Gemini
Centralisé pour faciliter la maintenance
"""

from modules.spotify_controller import SPOTIFY_TOOL_DECLARATION
from modules.analyze_screen import SCREEN_ANALYZER_TOOL_DECLARATION
from modules.web_navigator import WEB_NAVIGATOR_TOOL_DECLARATION
from modules.expert_coder import EXPERT_CODER_TOOL_DECLARATION
from modules.n8n_integration import N8N_WORKFLOW_TOOL_DECLARATION
# WEB_SEARCH_TOOL_DECLARATION retiré - on utilise uniquement google_search natif


def get_all_tool_declarations():
    """
    Retourne la liste complète de toutes les déclarations de tools pour Gemini.
    
    Returns:
        list: Liste contenant les dictionnaires de tools (function_declarations)
    """
    
    # Déclarations de tools locales (définies dans main.py)
    
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
            "Tu DOIS appeler ce tool dès que l'utilisateur dit des phrases comme "
            "« ouvre », « lance », « démarre », suivies d'un nom d'application, "
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
            "« ouvre le site de l'ESIGELEC », etc. "
            "⚠️ IMPORTANT : Si on te demande d'ouvrir une page de recherche Google "
            "(par exemple « ouvre moi sur google une recherche sur X »), "
            "tu DOIS utiliser cet outil avec le texte de recherche en paramètre. "
            "L'outil gère automatiquement la création de l'URL de recherche Google."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url_or_name": {
                    "type": "string",
                    "description": "Nom du site, URL complète, ou texte de recherche Google. Ex: 'youtube', 'tryhackme', 'outlook', 'https://www.google.com', 'comics spiderman' (pour une recherche Google)."
                }
            },
            "required": ["url_or_name"],
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

    file_manager = {
        "name": "file_manager",
        "description": (
            "Gère toutes les manipulations de fichiers et de dossiers. "
            "Utilise 'create_file' pour enregistrer du code ou du texte (C'EST LA MEILLEURE MÉTHODE POUR CRÉER DES SCRIPTS). "
            "Utilise 'read_file' pour lire le contenu d'un fichier."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "L'action à effectuer.",
                    "enum": ["create_file", "read_file", "create_dir", "delete", "copy", "move", "rename", "list_files", "calculate_size", "archive", "unarchive"],
                },
                "source_path": {
                    "type": "string",
                    "description": "Chemin complet du fichier ou dossier."
                },
                "destination_path": {
                    "type": "string",
                    "description": "Destination (pour copy/move) ou nouveau nom (pour rename)."
                },
                "content": {
                    "type": "string",
                    "description": "Le contenu TEXTUEL à écrire dans le fichier (obligatoire pour 'create_file')."
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

    user_preferences_tool = {
        "name": "user_preferences",
        "description": "Consulte les préférences et habitudes apprises par Cypher pour personnaliser l'interaction.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action à effectuer: 'view' pour voir les préférences, 'reset' pour réinitialiser",
                    "enum": ["view", "reset"]
                }
            },
            "required": ["action"]
        }
    }

    manage_tasks_tool = {
        "name": "manage_tasks",
        "description": (
            "Gestionnaire de tâches professionnel (Task Master) avec récurrence automatique. "
            "Gère les tâches avec priorités, dates d'échéance, et récurrence (daily, weekly, monthly, yearly). "
            "Si l'utilisateur mentionne une habitude ou action répétitive (ex: 'tous les jours', 'chaque mardi'), "
            "utilise le paramètre 'recurrence' approprié. "
            "Lorsqu'une tâche récurrente est complétée, une nouvelle occurrence est automatiquement créée."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "complete", "delete", "stats"],
                    "description": "Action : ajouter (add), lister (list), compléter (complete), supprimer (delete), statistiques (stats)."
                },
                "title": {
                    "type": "string",
                    "description": "Titre de la tâche (obligatoire pour 'add')."
                },
                "description": {
                    "type": "string",
                    "description": "Description détaillée de la tâche (optionnel)."
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Priorité de la tâche (défaut: 'medium')."
                },
                "due_date": {
                    "type": "string",
                    "description": "Date d'échéance au format ISO 'YYYY-MM-DD HH:MM' (ex: '2025-01-15 14:30'). Calcule-la toi-même par rapport à la date actuelle."
                },
                "recurrence": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly", "yearly"],
                    "description": "Règle de répétition (optionnel). Détecte automatiquement si l'utilisateur dit 'tous les jours', 'chaque semaine', 'chaque mardi', etc. et convertis en 'daily', 'weekly', 'monthly', 'yearly'. Si aucune récurrence n'est mentionnée, laisse ce champ vide (None)."
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags pour catégoriser la tâche (ex: ['pro', 'maison', 'urgent'])."
                },
                "task_id": {
                    "type": "string",
                    "description": "ID unique de la tâche (pour 'complete' ou 'delete')."
                },
                "fuzzy_name": {
                    "type": "string",
                    "description": "Nom partiel ou complet de la tâche pour recherche floue (pour 'complete' ou 'delete' si task_id n'est pas fourni)."
                },
                "filter_status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done"],
                    "description": "Filtrer par statut (pour 'list')."
                },
                "filter_priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Filtrer par priorité (pour 'list')."
                },
                "date_range": {
                    "type": "string",
                    "enum": ["today", "this_week", "overdue"],
                    "description": "Filtrer par plage de dates : 'today' (aujourd'hui), 'this_week' (cette semaine), 'overdue' (en retard)."
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

    document_manager = {
        "name": "document_manager",
        "description": (
            "Système RAG pour lire et interroger des documents locaux (PDF, Obsidian, Cours). "
            "Utilise 'index' pour apprendre un dossier entier, 'search' pour poser une question sur le contenu, "
            "et 'summary' pour résumer un fichier unique. "
            "C'est l'outil ULTIME pour répondre aux questions sur les cours, notes ou fichiers de l'utilisateur."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["index", "search", "reset", "summary"],
                    "description": "Action : apprendre (index), chercher (search), résumer un fichier (summary), tout oublier (reset)."
                },
                "query": {
                    "type": "string",
                    "description": "La question posée ou le sujet recherché (pour 'search')."
                },
                "source_folder": {
                    "type": "string",
                    "description": "Le chemin du dossier à scanner (pour 'index')."
                },
                "source_file": {
                    "type": "string",
                    "description": "Chemin complet du fichier à résumer (pour 'summary')."
                }
            },
            "required": ["action"]
        }
    }

    expert_coder_write_file = {
        "name": "expert_coder_write_file",
        "description": (
            "Écrit dans un fichier le DERNIER code généré par l'outil 'expert_coder'. "
            "Utilise ce tool pour sauvegarder du code sans avoir à gérer les guillemets ou le formatage du contenu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "Chemin complet du fichier où le code expert doit être écrit (ex: chemin d'un script sur le Bureau ou dans Documents).",
                },
            },
            "required": ["target_path"],
        },
    }

    # ========================================
    # 🔥 FIX CRITIQUE : STRUCTURE CORRECTE DES TOOLS
    # ========================================
    
    # IMPORTANT : On combine function_declarations + google_search natif
    # (malgré la doc, ça fonctionnait dans les anciens logs avec 2 tools)
    
    # Liste complète de tous les tools custom (function_declarations)
    function_declarations_dict = {
        "function_declarations": [
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
            email_tool,
            document_manager,
            EXPERT_CODER_TOOL_DECLARATION,
            expert_coder_write_file,
            SPOTIFY_TOOL_DECLARATION,
            SCREEN_ANALYZER_TOOL_DECLARATION,
            WEB_NAVIGATOR_TOOL_DECLARATION,
            user_preferences_tool,
            manage_tasks_tool,
            N8N_WORKFLOW_TOOL_DECLARATION,
        ]
    }
    
    # 🔥 GOOGLE_SEARCH NATIF UNIQUEMENT (outil natif Gemini via grounding_metadata)
    google_search_dict = {"google_search": {}}
    
    # 🔥 STRUCTURE FINALE : function_declarations + google_search natif UNIQUEMENT
    tools = [
        function_declarations_dict,  # Dict avec clé "function_declarations" (SANS web_search custom)
        google_search_dict,  # Google Search natif (résultats via grounding_metadata)
    ]
    
    return tools

