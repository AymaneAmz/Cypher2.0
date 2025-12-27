"""
Gestionnaire de sons pour Cypher
Joue des sons discrets pour différents événements (succès, erreur, processing, etc.)
"""

import os
import pygame
from pathlib import Path
from typing import Optional
from .logger import get_logger
from .paths import get_sounds_dir

logger = get_logger("sound")

class SoundManager:
    """Gestionnaire de sons pour les événements Cypher"""
    
    def __init__(self, sounds_dir: Optional[str] = None):
        """
        Initialise le gestionnaire de sons
        
        Args:
            sounds_dir: Répertoire contenant les fichiers son (par défaut: assets/sounds)
        """
        self.sounds_dir = Path(sounds_dir) if sounds_dir else get_sounds_dir()
        
        # Initialiser pygame mixer si pas déjà fait
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self.initialized = True
        except Exception as e:
            logger.error(f"Impossible d'initialiser pygame.mixer: {e}")
            self.initialized = False
        
        # Mapping des événements vers les fichiers son
        self.sound_files = {
            # Sons principaux (déjà existants)
            "wake": "wake.mp3",
            "end_listening": "end_listening.mp3",
            
            # Nouveaux sons pour événements (à créer ou générer)
            "success": "success.mp3",           # Action réussie
            "error": "error.mp3",               # Erreur
            "processing": "processing.mp3",     # Démarrage d'une action longue
            "notification": "notification.mp3", # Notification discrète
            "warning": "warning.mp3",           # Avertissement
            "connect": "connect.mp3",           # Connexion établie
            "disconnect": "disconnect.mp3",     # Déconnexion
        }
        
        # Cache pour les sons chargés (pour éviter de recharger)
        self._sound_cache = {}
        
        # Volume par défaut (0.0 à 1.0)
        self.volume = 0.3  # 30% pour être discret
    
    def _get_sound_path(self, event: str) -> Optional[Path]:
        """Retourne le chemin vers un fichier son"""
        filename = self.sound_files.get(event)
        if not filename:
            return None
        
        sound_path = self.sounds_dir / filename
        
        # Si le fichier n'existe pas, retourner None (on ne génère pas de son)
        if not sound_path.exists():
            return None
        
        return sound_path
    
    def play(self, event: str, volume: Optional[float] = None, block: bool = False):
        """
        Joue un son pour un événement
        
        Args:
            event: Nom de l'événement (wake, success, error, processing, etc.)
            volume: Volume (0.0 à 1.0), None pour utiliser le volume par défaut
            block: Si True, bloque jusqu'à la fin du son
        """
        if not self.initialized:
            return
        
        sound_path = self._get_sound_path(event)
        if not sound_path:
            # Si le son n'existe pas, on ne fait rien (pas d'erreur)
            logger.debug(f"Son '{event}' non trouvé: {sound_path}")
            return
        
        try:
            # Utiliser pygame.mixer.music pour les MP3
            if sound_path.suffix.lower() == '.mp3':
                pygame.mixer.music.load(str(sound_path))
                if volume is not None:
                    pygame.mixer.music.set_volume(volume)
                else:
                    pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play()
                logger.debug(f"Son '{event}' joué: {sound_path}")
            else:
                # Pour les autres formats (WAV, OGG), utiliser Sound
                if event not in self._sound_cache:
                    self._sound_cache[event] = pygame.mixer.Sound(str(sound_path))
                
                sound = self._sound_cache[event]
                if volume is not None:
                    sound.set_volume(volume)
                else:
                    sound.set_volume(self.volume)
                
                channel = sound.play()
                if block and channel:
                    while channel.get_busy():
                        pygame.time.wait(10)
                
                logger.debug(f"Son '{event}' joué: {sound_path}")
        
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du son '{event}': {e}")
    
    def set_volume(self, volume: float):
        """Définit le volume par défaut (0.0 à 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        logger.debug(f"Volume défini à {self.volume:.2f}")
    
    def stop_all(self):
        """Arrête tous les sons en cours"""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.stop()
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt des sons: {e}")


# Instance globale
_sound_manager_instance: Optional[SoundManager] = None

def get_sound_manager(sounds_dir: Optional[str] = None) -> SoundManager:
    """Retourne l'instance globale du gestionnaire de sons"""
    global _sound_manager_instance
    if _sound_manager_instance is None:
        _sound_manager_instance = SoundManager(sounds_dir)
    return _sound_manager_instance
