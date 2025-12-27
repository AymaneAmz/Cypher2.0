"""
Configuration centralisée pour Cypher
Gère les paramètres, la détection automatique des périphériques, etc.
"""

import os
import json
import pyaudio
from pathlib import Path
from typing import Optional, Dict, Any
from .paths import get_config_dir, get_sounds_dir, get_vocab_dir, get_models_dir

class CypherConfig:
    """Configuration centralisée pour Cypher"""
    
    def __init__(self, config_file: str = "cypher_config.json"):
        self.config_file = config_file
        self.config_dir = get_config_dir()
        
        # Charger ou créer la config
        self.config = self._load_config()
        
        # Détection automatique du micro
        self.input_device_index = self._detect_input_device()
        
        # Sauvegarder si nouvelle config créée
        config_path = self.config_dir / config_file
        if not config_path.exists():
            self._save_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier JSON"""
        config_path = self.config_dir / self.config_file
        
        # Chemins par défaut (calculés dynamiquement)
        models_dir = get_models_dir()
        sounds_dir = get_sounds_dir()
        vocab_dir = get_vocab_dir()
        
        default_config = {
            "wake_word": {
                "threshold": 0.5,
                "min_rms": 0.020,
                "cooldown_sec": 1.0,
                "enable_debug": False,
                "debug_score_min": 0.35
            },
            "audio": {
                "sample_rate": 16000,
                "chunk_size": 4000,
                "buffer_size": 4,
                "auto_detect_mic": True,
                "input_device_index": None  # None = auto-detect
            },
            "paths": {
                "wakeword_embedding": str(models_dir / "wakeword_embedding.npy"),
                "wake_sound": str(sounds_dir / "wake.mp3"),
                "end_sound": str(sounds_dir / "end_listening.mp3"),
                "vocab_dir": str(vocab_dir)
            },
            "conversation": {
                "timeout_sec": 15.0,
                "barge_in_enabled": True,
                "barge_in_skip_factor": 3
            }
        }
        
        if config_path.exists():
            try:
                with open(str(config_path), 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # Fusionner avec les valeurs par défaut
                    return self._merge_config(default_config, user_config)
            except Exception as e:
                print(f">>> [CONFIG] Erreur lors du chargement, utilisation des valeurs par défaut: {e}")
                return default_config
        
        return default_config
    
    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """Fusionne la config utilisateur avec les valeurs par défaut"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def _save_config(self):
        """Sauvegarde la configuration actuelle"""
        config_path = self.config_dir / self.config_file
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(str(config_path), 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print(f">>> [CONFIG] Configuration sauvegardée dans {config_path}")
        except Exception as e:
            print(f">>> [CONFIG] Erreur lors de la sauvegarde: {e}")
    
    def _detect_input_device(self) -> Optional[int]:
        """Détecte automatiquement le meilleur périphérique d'entrée audio"""
        auto_detect = self.config["audio"].get("auto_detect_mic", True)
        
        if not auto_detect:
            # Utiliser l'index spécifié dans la config
            return self.config["audio"].get("input_device_index")
        
        try:
            pya = pyaudio.PyAudio()
            
            # Lister tous les périphériques d'entrée
            input_devices = []
            for i in range(pya.get_device_count()):
                info = pya.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    input_devices.append({
                        'index': i,
                        'name': info['name'],
                        'channels': info['maxInputChannels'],
                        'default': info['defaultSampleRate']
                    })
            
            pya.terminate()
            
            if not input_devices:
                print(">>> [CONFIG] Aucun périphérique d'entrée trouvé, utilisation du défaut")
                return None
            
            # Préférer le périphérique par défaut ou le premier disponible
            default_device = None
            for device in input_devices:
                # Chercher un périphérique qui semble être un micro (contient "micro" ou "mic" dans le nom)
                name_lower = device['name'].lower()
                if 'micro' in name_lower or 'mic' in name_lower or 'microphone' in name_lower:
                    default_device = device['index']
                    break
            
            if default_device is None:
                # Sinon prendre le premier périphérique d'entrée
                default_device = input_devices[0]['index']
            
            print(f">>> [CONFIG] Micro détecté automatiquement: {input_devices[default_device]['name']} (index {default_device})")
            
            # Sauvegarder dans la config
            self.config["audio"]["input_device_index"] = default_device
            return default_device
            
        except Exception as e:
            print(f">>> [CONFIG] Erreur lors de la détection du micro: {e}")
            print(">>> [CONFIG] Utilisation du périphérique par défaut")
            return None
    
    def get(self, *keys, default=None):
        """Récupère une valeur de configuration avec chemin"""
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default
    
    def set(self, *keys, value):
        """Définit une valeur de configuration avec chemin"""
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self._save_config()
    
    @property
    def wake_threshold(self) -> float:
        return self.config["wake_word"]["threshold"]
    
    @property
    def wake_min_rms(self) -> float:
        return self.config["wake_word"]["min_rms"]
    
    @property
    def wake_cooldown(self) -> float:
        return self.config["wake_word"]["cooldown_sec"]
    
    @property
    def audio_sample_rate(self) -> int:
        return self.config["audio"]["sample_rate"]
    
    @property
    def audio_chunk_size(self) -> int:
        return self.config["audio"]["chunk_size"]
    
    @property
    def audio_buffer_size(self) -> int:
        return self.config["audio"]["buffer_size"]
    
    @property
    def conversation_timeout(self) -> float:
        return self.config["conversation"]["timeout_sec"]


# Instance globale de configuration
_config_instance: Optional[CypherConfig] = None

def get_config() -> CypherConfig:
    """Retourne l'instance globale de configuration"""
    global _config_instance
    if _config_instance is None:
        _config_instance = CypherConfig()
    return _config_instance
