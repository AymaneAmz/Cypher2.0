# Cypher 2.0 - Assistant IA Vocal

Assistant IA vocal moderne avec interface graphique, reconnaissance vocale, et intégration de multiples outils.

## Structure du projet

```
Cypher 2.0/
├── core/                    # Modules core du système
│   ├── paths.py            # Gestion centralisée des chemins
│   ├── config.py           # Configuration centralisée
│   ├── logger.py           # Système de logging structuré
│   ├── sound_manager.py    # Gestion des sons discrets
│   ├── tool_executor.py    # Exécution des tools avec interruption
│   └── wake_word_detector.py  # Détection du wake word "Sayfeure"
│
├── modules/                 # Modules fonctionnels
│   ├── expert_coder.py     # Module de génération de code avec Claude
│   ├── spotify_controller.py  # Contrôle Spotify
│   ├── analyze_screen.py   # Analyse d'écran
│   └── gui.py              # Interface graphique
│
├── assets/                  # Ressources
│   ├── sounds/             # Fichiers audio (.mp3)
│   └── vocab/              # Fichiers d'entraînement wake word (.wav)
│
├── data/                    # Données et fichiers de persistance
│   ├── config/             # Configuration (cypher_config.json)
│   ├── cache/              # Cache (expert_coder_*.json)
│   ├── models/             # Modèles ML (wakeword_embedding.npy)
│   ├── memory/             # Mémoire persistante (cypher_*.json)
│   ├── rag_db/             # Base de données vectorielle RAG
│   └── logs/               # Fichiers de logs
│
├── scripts/                 # Scripts utilitaires
│   └── generate_sounds.py  # Génération des sons discrets
│
└── main.py                  # Point d'entrée principal
```

## Installation

1. Installer les dépendances :
```bash
pip install -r requirements.txt
```

2. Configurer les variables d'environnement dans `.env` :
```
GEMINI_API_KEY=your_key
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=your_region
ANTHROPIC_API_KEY=your_key  # Optionnel (pour expert_coder)
```

## Utilisation

```bash
python main.py
```

## Organisation des fichiers

Tous les chemins sont gérés via `core.paths` qui fournit des fonctions pour obtenir les chemins corrects vers chaque dossier. Aucun chemin hardcodé n'est nécessaire.

## Génération des sons

Pour régénérer les sons discrets :
```bash
python scripts/generate_sounds.py
```

Les sons seront sauvegardés dans `assets/sounds/`.
