"""
Module d'exécution des tools avec gestion d'interruption
"""

import asyncio
import random
from typing import Dict, Any, Callable, List, Optional

from .logger import get_logger

logger = get_logger("tool")


class ToolExecutor:
    """Exécute les tools avec gestion d'interruption et logging"""
    
    def __init__(self, function_map: Dict[str, Callable], loading_phrases: Dict[str, List[str]]):
        """
        Initialise l'exécuteur de tools
        
        Args:
            function_map: Dictionnaire des fonctions disponibles
            loading_phrases: Phrases à dire pendant le chargement par tool
        """
        self.function_map = function_map
        self.loading_phrases = loading_phrases
        self._interrupted_flag = False
        self.is_busy = False
    
    def set_interrupted(self, value: bool):
        """Définit le flag d'interruption"""
        self._interrupted_flag = value
        if value:
            logger.warning("Flag d'interruption activé")
    
    def reset_interrupted(self):
        """Réinitialise le flag d'interruption"""
        self._interrupted_flag = False
        logger.debug("Flag d'interruption réinitialisé")
    
    async def execute_tools(
        self,
        function_calls: List[Any],
        on_status_update: Optional[Callable] = None,
        on_tts_phrase: Optional[Callable] = None,
        send_response: Callable = None
    ) -> List[Dict[str, Any]]:
        """
        Exécute une liste de tool calls
        
        Args:
            function_calls: Liste des appels de fonction à exécuter
            on_status_update: Callback pour mettre à jour le statut GUI
            on_tts_phrase: Callback pour envoyer une phrase TTS
            send_response: Fonction pour envoyer la réponse à Gemini
        
        Returns:
            Liste des réponses des tools
        """
        self.is_busy = True
        self._interrupted_flag = False
        
        tool_responses = []
        
        for fc in function_calls:
            fname = fc.name
            args = dict(fc.args or {})
            
            # Vérifier si on a été interrompu avant même de commencer
            if self._interrupted_flag:
                logger.warning(f"Tool {fname} annulé avant exécution (interruption en cours)")
                tool_responses.append({
                    "id": fc.id,
                    "name": fname,
                    "response": {"error": "Operation cancelled by user interruption"}
                })
                continue
            
            # Feedback visuel
            if fname in ["execute_python", "document_manager", "google_search", "file_manager"]:
                if on_status_update:
                    on_status_update("processing")
            
            # Feedback audio
            if fname in self.loading_phrases and on_tts_phrase:
                phrase = random.choice(self.loading_phrases[fname])
                if on_tts_phrase:
                    await on_tts_phrase(phrase)
            
            # Exécution de l'outil
            if fname not in self.function_map:
                logger.warning(f"Function {fname} not found in function map")
                tool_responses.append({
                    "id": fc.id,
                    "name": fname,
                    "response": {"error": f"Function {fname} not implemented"}
                })
                continue
            
            try:
                # Exécution de l'outil
                result = await asyncio.to_thread(self.function_map[fname], **args)
                
                # Si on a été interrompu pendant l'exécution
                if self._interrupted_flag:
                    logger.warning(f"Tool {fname} annulé suite à l'interruption pendant l'exécution")
                    tool_responses.append({
                        "id": fc.id,
                        "name": fname,
                        "response": {"error": "Operation cancelled by user interruption"}
                    })
                else:
                    tool_responses.append({
                        "id": fc.id,
                        "name": fname,
                        "response": {"result": result}
                    })
                    logger.info(f"Tool {fname} exécuté avec succès")
                    
            except Exception as e:
                logger.exception(f"Erreur lors de l'exécution de {fname}: {e}")
                if not self._interrupted_flag:
                    tool_responses.append({
                        "id": fc.id,
                        "name": fname,
                        "response": {"error": str(e)}
                    })
                else:
                    tool_responses.append({
                        "id": fc.id,
                        "name": fname,
                        "response": {"error": "Operation cancelled by user interruption"}
                    })
        
        # Construire les réponses finales
        was_interrupted = self._interrupted_flag
        if self._interrupted_flag:
            # Si interrompu, remplacer toutes les réponses par des annulations
            final_responses = [
                {
                    "id": fc.id,
                    "name": fc.name,
                    "response": {"error": "Operation cancelled by user interruption"}
                }
                for fc in function_calls
            ]
            logger.info(f"Envoi de {len(final_responses)} réponse(s) d'annulation à Gemini")
        else:
            final_responses = tool_responses
        
        # Envoyer les réponses à Gemini
        if final_responses and send_response:
            try:
                await send_response(function_responses=final_responses)
                logger.info(f"Réponse(s) envoyée(s) à Gemini ({len(final_responses)} tool(s))")
            except Exception as e:
                logger.error(f"Impossible d'envoyer la réponse tool à Gemini: {e}")
        
        # Déverrouiller
        self.is_busy = False
        
        # Si on a été interrompu, reset le flag
        if was_interrupted:
            logger.info("Reset du flag d'interruption - prêt pour nouvelle interaction")
            self._interrupted_flag = False
            await asyncio.sleep(0.1)  # Petit délai pour s'assurer que Gemini a bien reçu
        
        return final_responses
