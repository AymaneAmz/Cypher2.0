"""
Core modules de Cypher 2.0
"""

# Exporter paths en premier pour éviter les imports circulaires
from .paths import (
    get_project_root,
    get_assets_dir,
    get_sounds_dir,
    get_vocab_dir,
    get_data_dir,
    get_config_dir,
    get_cache_dir,
    get_models_dir,
    get_memory_dir,
    get_logs_dir,
    get_rag_db_dir,
)

from .config import get_config, CypherConfig
from .logger import get_logger, CypherLogger
from .sound_manager import get_sound_manager, SoundManager
from .tool_executor import ToolExecutor
from .learning_system import get_learning_system, LearningSystem

# WakeWordDetector nécessite speechbrain, donc on l'importe conditionnellement
try:
    from .wake_word_detector import WakeWordDetector
    _WAKE_WORD_AVAILABLE = True
except (ImportError, AttributeError, OSError, RuntimeError, Exception) as e:
    _WAKE_WORD_AVAILABLE = False
    WakeWordDetector = None
    # Ne pas afficher l'erreur car elle sera déjà affichée dans wake_word_detector.py

__all__ = [
    # Paths
    "get_project_root",
    "get_assets_dir",
    "get_sounds_dir",
    "get_vocab_dir",
    "get_data_dir",
    "get_config_dir",
    "get_cache_dir",
    "get_models_dir",
    "get_memory_dir",
    "get_logs_dir",
    "get_rag_db_dir",
    # Config
    "get_config",
    "CypherConfig",
    # Logger
    "get_logger",
    "CypherLogger",
    # Sound
    "get_sound_manager",
    "SoundManager",
    # Tools
    "ToolExecutor",
    # Learning
    "get_learning_system",
    "LearningSystem",
    # Wake word (conditionnel)
    "WakeWordDetector",
]
