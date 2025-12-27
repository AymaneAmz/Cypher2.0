"""
Module de détection du wake word "Sayfeure"
Utilise SpeechBrain ECAPA-VoxCeleb pour la détection
"""

import os
import time
import numpy as np
import torch
import pyaudio
from collections import deque
from typing import Optional, Callable
# Import optionnel de SpeechBrain (peut échouer avec torchaudio sur certaines versions)
try:
    from speechbrain.inference import EncoderClassifier
    SPEECHBRAIN_AVAILABLE = True
except (ImportError, OSError, AttributeError, Exception) as e:
    SPEECHBRAIN_AVAILABLE = False
    EncoderClassifier = None
    print(f"⚠️ [WARNING] SpeechBrain non disponible dans wake_word_detector: {type(e).__name__}: {e}")

from .config import get_config
from .logger import get_logger

logger = get_logger("wake_word")


class WakeWordDetector:
    """Détecteur de wake word utilisant SpeechBrain"""
    
    def __init__(self, embedding_path: str, on_wake_detected: Callable, on_barge_in: Optional[Callable] = None):
        """
        Initialise le détecteur de wake word
        
        Args:
            embedding_path: Chemin vers le fichier wakeword_embedding.npy
            on_wake_detected: Callback appelé quand le wake word est détecté
            on_barge_in: Callback appelé pour l'interruption (barge-in)
        """
        self.config = get_config()
        self.on_wake_detected = on_wake_detected
        self.on_barge_in = on_barge_in
        
        # Vérifier que l'embedding existe
        if not os.path.exists(embedding_path):
            logger.critical(f"Fichier wakeword_embedding.npy introuvable: {embedding_path}")
            raise FileNotFoundError(f"Fichier wakeword_embedding.npy introuvable: {embedding_path}")
        
        # Vérifier que SpeechBrain est disponible
        if not SPEECHBRAIN_AVAILABLE or EncoderClassifier is None:
            logger.error("SpeechBrain non disponible - le détecteur de wake word ne peut pas fonctionner")
            self.classifier = None
            self.target_embedding = None
            raise RuntimeError("SpeechBrain non disponible. Impossible d'initialiser le détecteur de wake word.")
        
        # Charger le modèle SpeechBrain
        logger.info("Chargement du modèle SpeechBrain ECAPA-VoxCeleb...")
        try:
            self.classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                run_opts={"device": "cpu"}  # TODO: détecter GPU automatiquement
            )
            logger.info("Modèle SpeechBrain chargé avec succès")
        except Exception as e:
            logger.critical(f"Impossible de charger le modèle SpeechBrain: {e}")
            self.classifier = None
            self.target_embedding = None
            raise
        
        # Charger l'embedding cible
        try:
            self.target_embedding = np.load(embedding_path).astype(np.float32)
            logger.info(f"Embedding du wake word chargé (shape: {self.target_embedding.shape})")
        except Exception as e:
            logger.critical(f"Impossible de charger l'embedding: {e}")
            raise
        
        # Variables d'état
        self._wake_hit_count = 0
        self.audio_stream: Optional[pyaudio.Stream] = None
        self.is_running = False
        
        # Variables pour le barge-in
        self.is_speaking = False
        self.is_busy = False
        self._barge_in_skip_counter = 0
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calcule la similarité cosine entre deux vecteurs"""
        a = a.astype(np.float32)
        b = b.astype(np.float32)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    
    def update_state(self, is_speaking: bool = False, is_busy: bool = False):
        """Met à jour l'état (pour le barge-in)"""
        self.is_speaking = is_speaking
        self.is_busy = is_busy
    
    async def start(self):
        """Démarre la détection du wake word"""
        if self.is_running:
            logger.warning("Détection déjà en cours")
            return
        
        self.is_running = True
        
        # Récupérer la configuration
        sample_rate = self.config.audio_sample_rate
        chunk_size = self.config.audio_chunk_size
        buffer_size = self.config.audio_buffer_size
        device_index = self.config.input_device_index
        
        logger.info(f"Initialisation du micro (device: {device_index}, rate: {sample_rate}Hz)")
        
        # Ouvrir le stream audio
        try:
            import asyncio
            pya = pyaudio.PyAudio()
            self.audio_stream = await asyncio.to_thread(
                pya.open,
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size
            )
            logger.info("Stream audio ouvert avec succès")
        except Exception as e:
            logger.error(f"Impossible d'ouvrir le stream audio: {e}")
            self.is_running = False
            raise
        
        # Variables pour la détection
        audio_deque = deque(maxlen=buffer_size)
        last_detection_time = 0
        cooldown_sec = self.config.wake_cooldown
        
        logger.info(f"Écoute active - dis 'Sayfeure' pour activer (barge-in: {self.on_barge_in is not None})")
        
        # Boucle principale de détection
        while self.is_running:
            try:
                import asyncio
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
                if self.is_speaking and self.config.get("conversation", "barge_in_enabled", True):
                    skip_factor = self.config.get("conversation", "barge_in_skip_factor", 3)
                    self._barge_in_skip_counter += 1
                    if self._barge_in_skip_counter < skip_factor:
                        continue
                    self._barge_in_skip_counter = 0
                else:
                    self._barge_in_skip_counter = 0
                
                # Il faut au moins quelques chunks pour analyser
                min_chunks = 3
                if len(audio_deque) < min_chunks:
                    continue
                
                # Concaténer les chunks pour avoir une fenêtre d'analyse
                live_audio = np.concatenate(list(audio_deque))
                
                # Calculer le RMS (volume moyen)
                rms = float(np.sqrt(np.mean(np_data ** 2) + 1e-12))
                
                # Seuil RMS adaptatif (plus élevé si Cypher parle)
                min_rms_threshold = self.config.wake_min_rms * 2.0 if self.is_speaking else self.config.wake_min_rms
                
                # Ignorer le silence/bruit faible
                if rms < min_rms_threshold or self.classifier is None:
                    score = 0.0
                    is_detected = False
                else:
                    # Convertir en tensor pour SpeechBrain
                    audio_tensor = torch.tensor(live_audio, dtype=torch.float32).unsqueeze(0)
                    
                    try:
                        # Générer l'embedding avec SpeechBrain
                        with torch.no_grad():
                            emb = self.classifier.encode_batch(audio_tensor).squeeze().cpu().numpy()
                        
                        # Calculer la similarité cosine avec l'embedding cible
                        if self.target_embedding is None:
                            score = 0.0
                            is_detected = False
                        else:
                            score = self._cosine_similarity(emb, self.target_embedding)
                    except Exception as e:
                        logger.error(f"Erreur lors de l'encodage audio: {e}")
                        score = 0.0
                        is_detected = False
                        continue
                    
                    # Détection : 1 seul hit suffit pour déclencher
                    if score >= self.config.wake_threshold:
                        self._wake_hit_count = 1
                        is_detected = True
                    else:
                        self._wake_hit_count = 0
                        is_detected = False
                    
                    # Debug si activé
                    if self.config.get("wake_word", "enable_debug", False):
                        debug_min = self.config.get("wake_word", "debug_score_min", 0.35)
                        if score > debug_min:
                            logger.debug(f"Score: {score:.3f}, RMS: {rms:.3f}, Threshold: {self.config.wake_threshold}")
                
                current_time = time.time()
                
                # Détection du wake word
                if is_detected and (current_time - last_detection_time > cooldown_sec):
                    # BARGE-IN : Si Cypher parle ou travaille
                    if (self.is_speaking or self.is_busy) and self.on_barge_in:
                        logger.info(f"BARGE-IN détecté ! (Score: {score:.3f})")
                        await self.on_barge_in(score, live_audio)
                        last_detection_time = current_time
                        audio_deque.clear()
                        continue
                    
                    # Activation normale
                    logger.info(f"Wake word détecté ! (Score: {score:.3f}, RMS: {rms:.3f})")
                    await self.on_wake_detected(score, live_audio)
                    last_detection_time = current_time
                    
            except Exception as e:
                logger.exception(f"Erreur dans la boucle de détection: {e}")
                import asyncio
                await asyncio.sleep(0.1)
                continue
    
    def stop(self):
        """Arrête la détection"""
        self.is_running = False
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                logger.info("Stream audio fermé")
            except Exception as e:
                logger.error(f"Erreur lors de la fermeture du stream: {e}")
