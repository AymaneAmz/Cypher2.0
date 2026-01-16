"""
Système de cache intelligent pour les résultats de tools
Optimise les performances en évitant les appels répétés
"""

import time
import hashlib
import json
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
from .logger import get_logger

logger = get_logger("tool_cache")


class ToolCache:
    """Cache intelligent avec TTL (Time To Live) et LRU (Least Recently Used)"""
    
    # Configuration des TTL par outil (en secondes)
    TTL_CONFIG = {
        "get_time": 30,              # 30 secondes
        "get_date": 3600,            # 1 heure (la date change rarement)
        "get_weather": 1800,         # 30 minutes
        "google_search": 600,        # 10 minutes (résultats web)
        "document_manager": 3600,    # 1 heure (documents changent peu)
        "spotify_tool": 5,           # 5 secondes (état change vite)
        "window_manager": 2,         # 2 secondes (fenêtres changent)
        "process_manager": 10,       # 10 secondes (processus)
        "system_control": 5,         # 5 secondes (volume, etc.)
        "memory_manager": 300,       # 5 minutes (mémoire)
        "file_manager": 60,          # 1 minute (lecture fichiers)
        "network_manager": 30,       # 30 secondes (réseau)
        # Par défaut : pas de cache (0 = désactivé)
    }
    
    def __init__(self, max_size: int = 1000):
        """
        Initialise le cache
        
        Args:
            max_size: Nombre maximum d'entrées dans le cache (LRU)
        """
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.max_size = max_size
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0
        }
        logger.info(f"ToolCache initialisé (max_size={max_size})")
    
    def _generate_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Génère une clé de cache unique basée sur le nom du tool et ses arguments
        
        Args:
            tool_name: Nom du tool
            args: Arguments du tool
        
        Returns:
            Clé de cache unique
        """
        # Convertir les args en JSON stable (clés triées)
        args_str = json.dumps(args, sort_keys=True, default=str)
        # Hash pour clé courte et unique
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]
        return f"{tool_name}:{args_hash}"
    
    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """
        Récupère un résultat du cache s'il existe et n'est pas expiré
        
        Args:
            tool_name: Nom du tool
            args: Arguments du tool
        
        Returns:
            Résultat du cache ou None si non trouvé/expiré
        """
        self.stats["total_requests"] += 1
        
        # Vérifier si ce tool a un TTL configuré
        ttl = self.TTL_CONFIG.get(tool_name, 0)
        if ttl <= 0:
            # Pas de cache pour ce tool
            self.stats["misses"] += 1
            return None
        
        key = self._generate_key(tool_name, args)
        
        if key in self.cache:
            result, timestamp = self.cache[key]
            age = time.time() - timestamp
            
            if age < ttl:
                # Cache valide - déplacer en fin (LRU)
                self.cache.move_to_end(key)
                self.stats["hits"] += 1
                logger.debug(f"Cache HIT: {tool_name} (age={age:.1f}s, ttl={ttl}s)")
                return result
            else:
                # Expiré - supprimer
                del self.cache[key]
                logger.debug(f"Cache EXPIRED: {tool_name} (age={age:.1f}s > ttl={ttl}s)")
        
        self.stats["misses"] += 1
        return None
    
    def set(self, tool_name: str, args: Dict[str, Any], result: Any):
        """
        Stocke un résultat dans le cache
        
        Args:
            tool_name: Nom du tool
            args: Arguments du tool
            result: Résultat à mettre en cache
        """
        # Vérifier si ce tool a un TTL configuré
        ttl = self.TTL_CONFIG.get(tool_name, 0)
        if ttl <= 0:
            return  # Pas de cache pour ce tool
        
        key = self._generate_key(tool_name, args)
        
        # Vérifier la taille du cache (LRU)
        if len(self.cache) >= self.max_size:
            # Supprimer le plus ancien (FIFO)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.stats["evictions"] += 1
            logger.debug(f"Cache EVICTION: {oldest_key} (max_size atteint)")
        
        # Ajouter au cache avec timestamp
        self.cache[key] = (result, time.time())
        logger.debug(f"Cache SET: {tool_name} (ttl={ttl}s)")
    
    def invalidate(self, tool_name: Optional[str] = None):
        """
        Invalide le cache pour un tool spécifique ou tout le cache
        
        Args:
            tool_name: Nom du tool à invalider (None = tout invalider)
        """
        if tool_name is None:
            # Invalider tout
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"Cache totalement invalidé ({count} entrées supprimées)")
        else:
            # Invalider uniquement ce tool
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(f"{tool_name}:")]
            for key in keys_to_delete:
                del self.cache[key]
            logger.info(f"Cache invalidé pour {tool_name} ({len(keys_to_delete)} entrées supprimées)")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache"""
        total = self.stats["total_requests"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
        
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "max_size": self.max_size,
            "hit_rate": f"{hit_rate:.1f}%"
        }
    
    def clear_expired(self):
        """Nettoie les entrées expirées du cache"""
        current_time = time.time()
        keys_to_delete = []
        
        for key in list(self.cache.keys()):
            # Extraire le nom du tool de la clé
            tool_name = key.split(":")[0]
            ttl = self.TTL_CONFIG.get(tool_name, 0)
            
            if ttl > 0:
                _, timestamp = self.cache[key]
                age = current_time - timestamp
                
                if age >= ttl:
                    keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self.cache[key]
        
        if keys_to_delete:
            logger.debug(f"Nettoyage cache: {len(keys_to_delete)} entrées expirées supprimées")


# Instance globale singleton
_cache_instance: Optional[ToolCache] = None


def get_tool_cache() -> ToolCache:
    """Retourne l'instance globale du cache"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ToolCache()
    return _cache_instance
