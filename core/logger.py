"""
Système de logging structuré pour Cypher
Remplace les print() par un système de logging professionnel
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from .paths import get_logs_dir

class CypherLogger:
    """Logger structuré pour Cypher"""
    
    def __init__(self, name: str = "Cypher", log_file: Optional[str] = None, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Éviter les doublons de handlers
        if self.logger.handlers:
            return
        
        # Format des messages
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler pour la console (avec formatage spécial)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter('>>> [%(levelname)s] %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Handler pour le fichier (si spécifié)
        if log_file:
            log_path = get_logs_dir() / log_file
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)  # Tout logger dans le fichier
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """Log niveau DEBUG"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log niveau INFO"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log niveau WARNING"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log niveau ERROR"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log niveau CRITICAL"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, exc_info=True, **kwargs):
        """Log une exception avec traceback"""
        self.logger.error(message, *args, exc_info=exc_info, **kwargs)


# Instances de logger pour différents modules
_main_logger: Optional[CypherLogger] = None
_wake_logger: Optional[CypherLogger] = None
_audio_logger: Optional[CypherLogger] = None
_tool_logger: Optional[CypherLogger] = None

def get_logger(module: str = "main") -> CypherLogger:
    """Retourne le logger pour un module spécifique"""
    global _main_logger, _wake_logger, _audio_logger, _tool_logger
    
    if module == "main":
        if _main_logger is None:
            _main_logger = CypherLogger("Cypher", "cypher.log")
        return _main_logger
    elif module == "wake_word":
        if _wake_logger is None:
            _wake_logger = CypherLogger("WakeWord", "cypher_wakeword.log")
        return _wake_logger
    elif module == "audio":
        if _audio_logger is None:
            _audio_logger = CypherLogger("Audio", "cypher_audio.log")
        return _audio_logger
    elif module == "tool":
        if _tool_logger is None:
            _tool_logger = CypherLogger("Tool", "cypher_tools.log")
        return _tool_logger
    else:
        return CypherLogger(module)
