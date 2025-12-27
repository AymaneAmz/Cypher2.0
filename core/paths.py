"""
Gestion centralisée des chemins pour Cypher 2.0
Fournit des fonctions utilitaires pour obtenir les chemins vers les différents dossiers
"""

import os
from pathlib import Path

def get_project_root() -> Path:
    """Retourne le chemin de la racine du projet Cypher"""
    # Cette fonction se trouve dans core/paths.py
    # Donc on remonte de 2 niveaux pour atteindre la racine
    return Path(__file__).parent.parent.resolve()

def get_assets_dir() -> Path:
    """Retourne le chemin du dossier assets"""
    return get_project_root() / "assets"

def get_sounds_dir() -> Path:
    """Retourne le chemin du dossier sounds"""
    return get_assets_dir() / "sounds"

def get_vocab_dir() -> Path:
    """Retourne le chemin du dossier vocab"""
    return get_assets_dir() / "vocab"

def get_data_dir() -> Path:
    """Retourne le chemin du dossier data"""
    return get_project_root() / "data"

def get_config_dir() -> Path:
    """Retourne le chemin du dossier config"""
    return get_data_dir() / "config"

def get_cache_dir() -> Path:
    """Retourne le chemin du dossier cache"""
    return get_data_dir() / "cache"

def get_models_dir() -> Path:
    """Retourne le chemin du dossier models"""
    return get_data_dir() / "models"

def get_memory_dir() -> Path:
    """Retourne le chemin du dossier memory"""
    return get_data_dir() / "memory"

def get_logs_dir() -> Path:
    """Retourne le chemin du dossier logs"""
    return get_data_dir() / "logs"

def get_rag_db_dir() -> Path:
    """Retourne le chemin du dossier rag_db"""
    return get_data_dir() / "rag_db"
