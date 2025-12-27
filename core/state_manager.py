"""
Gestionnaire d'état et auto-sauvegarde pour Cypher
Gère la sauvegarde périodique de l'état et la restauration au démarrage
"""

import json
import os
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from .logger import get_logger
from .paths import get_memory_dir

logger = get_logger("state_manager")


class StateManager:
    """Gestionnaire d'état avec auto-sauvegarde et restauration"""
    
    def __init__(self):
        self.memory_dir = get_memory_dir()
        self.state_file = self.memory_dir / "cypher_state_backup.json"
        self.conversation_history_file = self.memory_dir / "conversation_history.json"
        
        # État actuel
        self.conversation_turns = []  # Historique des tours de conversation
        self.last_save_time = time.time()
        self.save_interval = 300  # Sauvegarder toutes les 5 minutes
        self.turn_count = 0
        self.context_summary = ""  # Résumé du contexte ancien
        
        # Seuils pour le résumé
        self.summary_threshold = 20  # Résumer après 20 tours
        self.keep_recent_turns = 10  # Garder les 10 derniers tours en détail
        
        logger.info("StateManager initialisé")
    
    def add_conversation_turn(self, user_input: str, assistant_response: str, tools_used: List[str] = None):
        """Ajoute un tour de conversation à l'historique"""
        turn = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input[:500] if user_input else "",  # Limiter la taille
            "assistant_response": assistant_response[:500] if assistant_response else "",
            "tools_used": tools_used or []
        }
        self.conversation_turns.append(turn)
        self.turn_count += 1
        
        # Limiter la taille de l'historique
        if len(self.conversation_turns) > 100:
            self.conversation_turns = self.conversation_turns[-100:]
    
    async def should_summarize_context(self) -> bool:
        """Vérifie si le contexte doit être résumé"""
        return self.turn_count > 0 and self.turn_count % self.summary_threshold == 0
    
    async def summarize_context(self, gemini_client) -> str:
        """
        Résume l'ancien contexte en utilisant Gemini
        Retourne le résumé qui sera ajouté au contexte
        """
        if len(self.conversation_turns) <= self.keep_recent_turns:
            return ""
        
        # Prendre les tours anciens (sauf les récents)
        old_turns = self.conversation_turns[:-self.keep_recent_turns]
        recent_turns = self.conversation_turns[-self.keep_recent_turns:]
        
        # Construire le texte à résumer
        context_text = "\n".join([
            f"Tour {i+1}: User: {turn['user_input']} | Assistant: {turn['assistant_response']}"
            for i, turn in enumerate(old_turns)
        ])
        
        try:
            # Demander à Gemini de résumer
            prompt = f"""Résume brièvement cette conversation précédente en 2-3 phrases maximum. 
            Concentre-toi sur les sujets principaux et les décisions importantes.
            
            Conversation:
            {context_text}
            
            Résumé:"""
            
            # Utiliser l'API Gemini pour résumer
            response = await gemini_client.aio.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=[prompt]
            )
            
            summary = response.text if hasattr(response, 'text') else str(response)
            
            # Mettre à jour le résumé
            if self.context_summary:
                self.context_summary += f"\n{summary}"
            else:
                self.context_summary = summary
            
            # Supprimer les tours anciens (garder seulement les récents)
            self.conversation_turns = recent_turns
            
            logger.info(f"Contexte résumé: {len(old_turns)} tours → résumé de {len(summary)} caractères")
            return summary
            
        except Exception as e:
            logger.error(f"Erreur lors du résumé du contexte: {e}")
            return ""
    
    def get_context_summary(self) -> str:
        """Retourne le résumé du contexte pour l'ajouter au prompt"""
        if not self.context_summary:
            return ""
        return f"\n[CONTEXTE PRÉCÉDENT RÉSUMÉ]: {self.context_summary}\n"
    
    def save_state(self, learning_system=None, additional_state: Dict[str, Any] = None):
        """Sauvegarde l'état actuel"""
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "turn_count": self.turn_count,
                "conversation_turns": self.conversation_turns[-50:],  # Garder les 50 derniers tours
                "context_summary": self.context_summary,
                "additional_state": additional_state or {}
            }
            
            # Ajouter les préférences du learning system si disponible
            if learning_system:
                try:
                    state["learning_preferences"] = learning_system.get_preferences_summary()
                except:
                    pass
            
            # Sauvegarder dans un fichier temporaire d'abord (atomic write)
            temp_file = str(self.state_file) + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            # Remplacer l'ancien fichier
            if os.path.exists(self.state_file):
                os.replace(temp_file, str(self.state_file))
            else:
                os.rename(temp_file, str(self.state_file))
            
            self.last_save_time = time.time()
            logger.debug(f"État sauvegardé ({len(self.conversation_turns)} tours)")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'état: {e}")
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Charge l'état sauvegardé"""
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # Vérifier si la sauvegarde est récente (moins de 24h)
            if "timestamp" in state:
                save_time = datetime.fromisoformat(state["timestamp"])
                age_hours = (datetime.now() - save_time).total_seconds() / 3600
                
                if age_hours > 24:
                    logger.info(f"Sauvegarde trop ancienne ({age_hours:.1f}h), ignorée")
                    return None
            
            logger.info(f"État chargé: {state.get('turn_count', 0)} tours")
            return state
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'état: {e}")
            return None
    
    def restore_state(self, state: Dict[str, Any]):
        """Restaure l'état depuis un dictionnaire"""
        self.turn_count = state.get("turn_count", 0)
        self.conversation_turns = state.get("conversation_turns", [])
        self.context_summary = state.get("context_summary", "")
        logger.info(f"État restauré: {self.turn_count} tours")
    
    async def auto_save_loop(self, learning_system=None, additional_state_callback=None):
        """Boucle d'auto-sauvegarde périodique"""
        try:
            while True:
                try:
                    await asyncio.sleep(self.save_interval)
                    
                    # Récupérer l'état additionnel si callback fourni
                    additional_state = {}
                    if additional_state_callback:
                        try:
                            additional_state = additional_state_callback()
                        except Exception as e:
                            logger.debug(f"Erreur lors de la récupération de l'état additionnel: {e}")
                            additional_state = {}
                    
                    # Sauvegarder
                    try:
                        self.save_state(learning_system=learning_system, additional_state=additional_state)
                    except Exception as e:
                        logger.error(f"Erreur lors de la sauvegarde dans auto_save_loop: {e}")
                        # Continuer même en cas d'erreur de sauvegarde
                    
                except asyncio.CancelledError:
                    # Sauvegarder une dernière fois avant de quitter
                    try:
                        self.save_state(learning_system=learning_system)
                    except:
                        pass
                    break
                except Exception as e:
                    logger.error(f"Erreur dans la boucle d'auto-sauvegarde: {e}")
                    # Attendre avant de réessayer, mais ne pas faire planter le TaskGroup
                    await asyncio.sleep(60)
        except Exception as e:
            # Dernière ligne de défense : ne jamais faire planter le TaskGroup
            logger.error(f"Erreur critique dans auto_save_loop: {e}")
            # La tâche se termine silencieusement


# Instance globale
_state_manager = None

def get_state_manager() -> StateManager:
    """Retourne l'instance globale du StateManager"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager

