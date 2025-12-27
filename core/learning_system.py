"""
Système d'apprentissage et de préférences utilisateur pour Cypher
Apprend des interactions passées et fournit des suggestions contextuelles
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
import re

from .logger import get_logger
from .paths import get_memory_dir

logger = get_logger("learning")


class LearningSystem:
    """Système d'apprentissage des préférences utilisateur"""
    
    def __init__(self):
        self.memory_dir = get_memory_dir()
        self.preferences_file = self.memory_dir / "user_preferences.json"
        self.interactions_file = self.memory_dir / "interactions_history.json"
        
        # Charger les données
        self.preferences = self._load_preferences()
        self.interactions = self._load_interactions()
        
        # Compteurs pour analyse
        self.command_patterns = defaultdict(int)
        self.tool_usage = defaultdict(int)
        self.time_preferences = defaultdict(int)
        self.context_preferences = defaultdict(list)
        
        # Analyser les interactions existantes
        self._analyze_interactions()
    
    def _load_preferences(self) -> Dict[str, Any]:
        """Charge les préférences depuis le fichier"""
        if not self.preferences_file.exists():
            return {
                "preferred_tools": {},
                "communication_style": "neutre",
                "frequent_commands": {},
                "time_patterns": {},
                "contextual_hints": {},
                "learned_behaviors": {},
                "custom_shortcuts": {},
                "suggestions_enabled": True,
                "last_updated": datetime.now().isoformat()
            }
        
        try:
            with open(self.preferences_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"Erreur lors du chargement des préférences: {e}")
            return self._load_preferences()  # Retourne les valeurs par défaut
    
    def _save_preferences(self):
        """Sauvegarde les préférences"""
        try:
            self.preferences["last_updated"] = datetime.now().isoformat()
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self.preferences, f, ensure_ascii=False, indent=2)
            logger.debug("Préférences sauvegardées")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des préférences: {e}")
    
    def _load_interactions(self) -> List[Dict[str, Any]]:
        """Charge l'historique des interactions"""
        if not self.interactions_file.exists():
            return []
        
        try:
            with open(self.interactions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("interactions", [])
        except Exception as e:
            logger.error(f"Erreur lors du chargement des interactions: {e}")
            return []
    
    def _save_interactions(self):
        """Sauvegarde l'historique des interactions"""
        try:
            # Limiter à 1000 dernières interactions
            if len(self.interactions) > 1000:
                self.interactions = self.interactions[-1000:]
            
            data = {
                "interactions": self.interactions,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.interactions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Interactions sauvegardées ({len(self.interactions)} entrées)")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des interactions: {e}")
    
    def record_interaction(self, user_input: str, cypher_response: str, tools_used: List[str] = None, context: Dict[str, Any] = None):
        """Enregistre une interaction pour l'apprentissage"""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input.lower().strip(),
            "cypher_response": cypher_response[:200] if cypher_response else "",  # Limiter la taille
            "tools_used": tools_used or [],
            "context": context or {},
            "hour": datetime.now().hour,
            "day_of_week": datetime.now().strftime("%A")
        }
        
        self.interactions.append(interaction)
        self._analyze_interaction(interaction)
        
        # Sauvegarder périodiquement (toutes les 10 interactions)
        if len(self.interactions) % 10 == 0:
            self._save_interactions()
            self._update_preferences()
    
    def _analyze_interaction(self, interaction: Dict[str, Any]):
        """Analyse une interaction pour extraire des patterns"""
        user_input = interaction["user_input"]
        tools = interaction.get("tools_used", [])
        hour = interaction.get("hour", 12)
        
        # Analyser les outils utilisés
        for tool in tools:
            self.tool_usage[tool] += 1
        
        # Analyser les patterns de commandes
        if any(word in user_input for word in ["spotify", "musique", "chanson", "playlist"]):
            self.command_patterns["music"] += 1
        if any(word in user_input for word in ["fichier", "dossier", "créer", "supprimer"]):
            self.command_patterns["file_management"] += 1
        if any(word in user_input for word in ["code", "script", "programme", "python"]):
            self.command_patterns["coding"] += 1
        if any(word in user_input for word in ["heure", "date", "temps"]):
            self.command_patterns["time_queries"] += 1
        if any(word in user_input for word in ["météo", "température", "pluie"]):
            self.command_patterns["weather"] += 1
        
        # Analyser les préférences temporelles
        self.time_preferences[hour] += 1
    
    def _analyze_interactions(self):
        """Analyse toutes les interactions pour extraire des préférences"""
        if not self.interactions:
            return
        
        # Réinitialiser les compteurs
        self.command_patterns.clear()
        self.tool_usage.clear()
        self.time_preferences.clear()
        
        # Analyser chaque interaction
        for interaction in self.interactions[-500:]:  # Dernières 500 interactions
            self._analyze_interaction(interaction)
        
        logger.info(f"Analyse de {len(self.interactions)} interactions terminée")
    
    def _update_preferences(self):
        """Met à jour les préférences basées sur l'analyse"""
        # Outils préférés
        if self.tool_usage:
            total_tool_usage = sum(self.tool_usage.values())
            self.preferences["preferred_tools"] = {
                tool: count / total_tool_usage 
                for tool, count in sorted(self.tool_usage.items(), key=lambda x: x[1], reverse=True)[:10]
            }
        
        # Commandes fréquentes
        if self.command_patterns:
            total_patterns = sum(self.command_patterns.values())
            self.preferences["frequent_commands"] = {
                pattern: count / total_patterns
                for pattern, count in sorted(self.command_patterns.items(), key=lambda x: x[1], reverse=True)[:10]
            }
        
        # Patterns temporels
        if self.time_preferences:
            # Heures les plus actives
            active_hours = sorted(self.time_preferences.items(), key=lambda x: x[1], reverse=True)[:5]
            self.preferences["time_patterns"]["most_active_hours"] = [h for h, _ in active_hours]
        
        # Sauvegarder
        self._save_preferences()
    
    def get_preferences_summary(self) -> str:
        """Retourne un résumé des préférences pour le prompt système"""
        if not self.preferences.get("suggestions_enabled", True):
            return ""
        
        summary_parts = []
        
        # Outils préférés
        preferred_tools = self.preferences.get("preferred_tools", {})
        if preferred_tools:
            top_tools = sorted(preferred_tools.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_tools:
                tools_list = ", ".join([tool for tool, _ in top_tools])
                summary_parts.append(f"Outils fréquemment utilisés par l'utilisateur: {tools_list}")
        
        # Commandes fréquentes
        frequent = self.preferences.get("frequent_commands", {})
        if frequent:
            top_patterns = sorted(frequent.items(), key=lambda x: x[1], reverse=True)[:3]
            if top_patterns:
                patterns_desc = []
                for pattern, freq in top_patterns:
                    if pattern == "music":
                        patterns_desc.append("musique/Spotify")
                    elif pattern == "file_management":
                        patterns_desc.append("gestion de fichiers")
                    elif pattern == "coding":
                        patterns_desc.append("développement de code")
                    elif pattern == "time_queries":
                        patterns_desc.append("questions sur l'heure/date")
                    elif pattern == "weather":
                        patterns_desc.append("météo")
                if patterns_desc:
                    summary_parts.append(f"Domaines d'utilisation fréquents: {', '.join(patterns_desc)}")
        
        # Comportements appris
        learned = self.preferences.get("learned_behaviors", {})
        if learned:
            behaviors = []
            for key, value in learned.items():
                if isinstance(value, dict) and value.get("confidence", 0) > 0.7:
                    behaviors.append(value.get("description", key))
            if behaviors:
                summary_parts.append(f"Comportements appris: {', '.join(behaviors[:3])}")
        
        if summary_parts:
            return "\n\n[PRÉFÉRENCES UTILISATEUR - APPRENTISSAGE] :\n" + "\n".join(f"- {part}" for part in summary_parts) + "\nUtilise ces informations pour personnaliser tes réponses et anticiper les besoins."
        
        return ""
    
    def get_contextual_suggestions(self, current_input: str, current_time: datetime = None) -> List[str]:
        """Génère des suggestions contextuelles basées sur l'historique"""
        if not current_time:
            current_time = datetime.now()
        
        suggestions = []
        current_hour = current_time.hour
        current_input_lower = current_input.lower()
        
        # Suggestions basées sur les outils préférés
        preferred_tools = self.preferences.get("preferred_tools", {})
        if "spotify_control" in preferred_tools and preferred_tools["spotify_control"] > 0.3:
            if any(word in current_input_lower for word in ["pause", "stop", "suivant"]):
                if "spotify" not in current_input_lower:
                    suggestions.append("Souhaites-tu contrôler Spotify ?")
        
        # Suggestions basées sur les patterns temporels
        active_hours = self.preferences.get("time_patterns", {}).get("most_active_hours", [])
        if current_hour in active_hours:
            # C'est une heure où l'utilisateur est souvent actif, suggérer des actions fréquentes
            frequent = self.preferences.get("frequent_commands", {})
            if "coding" in frequent and frequent["coding"] > 0.2:
                if not any(word in current_input_lower for word in ["code", "script", "programme"]):
                    suggestions.append("Besoin d'aide pour du code ?")
        
        # Suggestions basées sur l'historique récent
        if len(self.interactions) > 0:
            recent_tools = [i.get("tools_used", []) for i in self.interactions[-5:]]
            recent_tools_flat = [tool for tools in recent_tools for tool in tools]
            if recent_tools_flat:
                tool_counts = Counter(recent_tools_flat)
                most_recent_tool = tool_counts.most_common(1)[0][0]
                if most_recent_tool not in current_input_lower:
                    # Suggérer une continuation logique
                    if most_recent_tool == "spotify_control":
                        suggestions.append("Veux-tu continuer avec la musique ?")
                    elif most_recent_tool == "file_manager":
                        suggestions.append("Besoin d'aide pour d'autres fichiers ?")
        
        return suggestions[:2]  # Maximum 2 suggestions
    
    def learn_behavior(self, behavior_key: str, description: str, confidence: float = 0.5):
        """Enregistre un comportement appris"""
        if "learned_behaviors" not in self.preferences:
            self.preferences["learned_behaviors"] = {}
        
        self.preferences["learned_behaviors"][behavior_key] = {
            "description": description,
            "confidence": confidence,
            "learned_at": datetime.now().isoformat()
        }
        
        self._save_preferences()
        logger.info(f"Comportement appris: {behavior_key} (confiance: {confidence:.2f})")
    
    def get_communication_style(self) -> str:
        """Retourne le style de communication préféré"""
        return self.preferences.get("communication_style", "neutre")
    
    def update_communication_style(self, style: str):
        """Met à jour le style de communication"""
        self.preferences["communication_style"] = style
        self._save_preferences()
    
    def add_custom_shortcut(self, shortcut: str, expansion: str):
        """Ajoute un raccourci personnalisé"""
        if "custom_shortcuts" not in self.preferences:
            self.preferences["custom_shortcuts"] = {}
        
        self.preferences["custom_shortcuts"][shortcut.lower()] = expansion
        self._save_preferences()
        logger.info(f"Raccourci ajouté: '{shortcut}' -> '{expansion}'")
    
    def expand_shortcut(self, user_input: str) -> str:
        """Expand les raccourcis personnalisés dans l'input utilisateur"""
        shortcuts = self.preferences.get("custom_shortcuts", {})
        expanded = user_input
        
        for shortcut, expansion in shortcuts.items():
            # Remplacement simple (peut être amélioré avec regex)
            if shortcut in expanded.lower():
                expanded = expanded.replace(shortcut, expansion)
        
        return expanded
    
    def force_save(self):
        """Force la sauvegarde des données"""
        self._save_interactions()
        self._update_preferences()
        self._save_preferences()


# Instance globale
_learning_system_instance: Optional[LearningSystem] = None

def get_learning_system() -> LearningSystem:
    """Retourne l'instance globale du système d'apprentissage"""
    global _learning_system_instance
    if _learning_system_instance is None:
        _learning_system_instance = LearningSystem()
    return _learning_system_instance
