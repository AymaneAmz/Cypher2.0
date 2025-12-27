# Organisation du projet Cypher 2.0

## Structure des dossiers

```
Cypher 2.0/
├── core/                    # Modules core du système
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── logger.py
│   ├── sound_manager.py
│   ├── tool_executor.py
│   └── wake_word_detector.py
│
├── modules/                 # Modules fonctionnels
│   ├── __init__.py
│   ├── expert_coder.py
│   ├── spotify_controller.py
│   ├── analyze_screen.py
│   └── gui.py
│
├── assets/                  # Ressources (sons, vocab, etc.)
│   ├── sounds/              # Fichiers audio (.mp3)
│   │   ├── wake.mp3
│   │   ├── end_listening.mp3
│   │   ├── success.mp3
│   │   ├── error.mp3
│   │   ├── processing.mp3
│   │   ├── notification.mp3
│   │   ├── warning.mp3
│   │   ├── connect.mp3
│   │   └── disconnect.mp3
│   └── vocab/               # Fichiers d'entraînement wake word (.wav)
│       ├── seq1.wav
│       ├── seq2.wav
│       └── ...
│
├── data/                    # Données et fichiers de persistance
│   ├── config/              # Fichiers de configuration
│   │   └── cypher_config.json
│   ├── cache/               # Cache et fichiers temporaires
│   │   ├── expert_coder_cache.json
│   │   └── expert_coder_memory.json
│   ├── models/              # Modèles ML (embeddings, etc.)
│   │   └── wakeword_embedding.npy
│   ├── memory/              # Mémoire et données persistantes
│   │   ├── cypher_agenda.json
│   │   └── cypher_memory_cortex.json
│   ├── rag_db/              # Base de données vectorielle RAG
│   │   └── (fichiers ChromaDB)
│   └── logs/                # Fichiers de logs
│       ├── cypher.log
│       ├── cypher_wakeword.log
│       └── cypher_tools.log
│
├── scripts/                 # Scripts utilitaires
│   └── generate_sounds.py
│
├── .env                     # Variables d'environnement (ne pas déplacer)
├── README.md
└── requirements.txt
```

## Migration des fichiers

Tous les chemins dans le code ont été adaptés pour utiliser des chemins relatifs basés sur la racine du projet.
