"""
🔗 N8N INTEGRATION v1.0 - Intégration avec n8n
==============================================
Module d'intégration avec n8n pour orchestrer des workflows complexes
et connecter Cypher à des services externes.

Auteur: Cypher AI Assistant
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

load_dotenv()

# Configuration n8n
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", None)  # Optionnel, pour l'API n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", None)  # URL du webhook n8n
N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "30"))  # Timeout en secondes

# Logger (sera importé depuis core.logger)
try:
    from core.logger import get_logger
    logger = get_logger("n8n")
except ImportError:
    import logging
    logger = logging.getLogger("n8n")


class N8NIntegration:
    """Classe principale pour l'intégration avec n8n"""
    
    def __init__(self):
        """Initialise la connexion à n8n"""
        self.base_url = N8N_BASE_URL.rstrip('/')
        self.api_key = N8N_API_KEY
        self.webhook_url = N8N_WEBHOOK_URL
        self.timeout = N8N_TIMEOUT
        
        # Vérifier la configuration
        if not self.webhook_url and not self.api_key:
            logger.warning(
                "⚠️ [N8N] Aucune configuration trouvée. "
                "Définissez N8N_WEBHOOK_URL ou N8N_API_KEY dans votre .env"
            )
    
    def _get_headers(self) -> Dict[str, str]:
        """Retourne les headers pour les requêtes API n8n"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
        return headers
    
    def trigger_workflow_webhook(
        self,
        workflow_name: Optional[str] = None,
        webhook_path: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Déclenche un workflow n8n via webhook
        
        Args:
            workflow_name: Nom du workflow (pour logging)
            webhook_path: Chemin du webhook (ex: "cypher-workflow")
            data: Données à envoyer au workflow
            
        Returns:
            Réponse du workflow n8n
        """
        try:
            # Construire l'URL du webhook
            if webhook_path:
                # URL complète fournie ou chemin relatif
                if webhook_path.startswith("http"):
                    url = webhook_path
                else:
                    url = f"{self.base_url}/webhook/{webhook_path}"
            elif self.webhook_url:
                url = self.webhook_url
            else:
                return {
                    "success": False,
                    "error": "Aucune URL de webhook configurée. Définissez N8N_WEBHOOK_URL ou fournissez webhook_path"
                }
            
            # Préparer les données
            payload = data or {}
            
            # Ajouter des métadonnées Cypher
            payload["_cypher_metadata"] = {
                "timestamp": time.time(),
                "workflow_name": workflow_name or "unknown",
                "source": "cypher"
            }
            
            logger.info(f"📤 [N8N] Déclenchement du workflow '{workflow_name or webhook_path}' via webhook")
            logger.info(f"📤 [N8N] URL: {url}")
            logger.info(f"📤 [N8N] Données envoyées: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            logger.info(f"📤 [N8N] Action détectée: {payload.get('action', 'NON DÉTECTÉE')}")
            
            # Envoyer la requête
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            # Vérifier la réponse
            response.raise_for_status()
            
            # Parser la réponse
            try:
                # Vérifier si la réponse est vide
                if not response.text or response.text.strip() == "":
                    logger.warning(f"⚠️ [N8N] Réponse vide du workflow")
                    result = {"message": "Workflow exécuté (réponse vide)", "success": True}
                else:
                    result = response.json()
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [N8N] Réponse non-JSON reçue: {response.text[:200]}")
                # Si c'est une réponse HTML (erreur n8n), extraire le message
                if "text/html" in response.headers.get("content-type", ""):
                    result = {
                        "message": "Workflow exécuté mais réponse HTML reçue (vérifiez les logs n8n)",
                        "raw_response": response.text[:500]
                    }
                else:
                    result = {
                        "message": "Workflow exécuté",
                        "raw_response": response.text[:500]
                    }
            
            logger.info(f"✅ [N8N] Workflow exécuté avec succès")
            logger.debug(f"Réponse complète: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # Extraire les données utiles de la réponse
            # n8n peut renvoyer les données dans différentes structures
            extracted_data = result
            if isinstance(result, dict):
                # Si la réponse contient un champ "body" ou "data", l'utiliser
                if "body" in result and isinstance(result["body"], (dict, list)):
                    extracted_data = result["body"]
                elif "data" in result and isinstance(result["data"], (dict, list)):
                    extracted_data = result["data"]
                # Si la réponse contient directement "events" ou "items", les garder
                elif "events" in result or "items" in result:
                    extracted_data = result
            
            return {
                "success": True,
                "workflow": workflow_name or webhook_path,
                "data": extracted_data,
                "raw_response": result,
                "status_code": response.status_code
            }
            
        except Timeout:
            error_msg = f"Timeout lors de l'appel au workflow n8n (>{self.timeout}s)"
            logger.error(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
            
        except ConnectionError:
            error_msg = f"Impossible de se connecter à n8n à {self.base_url}. Vérifiez que n8n est démarré."
            logger.error(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
            
        except RequestException as e:
            # Gérer spécifiquement les erreurs HTTP (404, 401, etc.)
            status_code = None
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            
            if status_code == 404:
                error_msg = (
                    f"Workflow non trouvé à l'URL: {url}\n"
                    f"Vérifiez que:\n"
                    f"1. Le workflow existe dans n8n\n"
                    f"2. Le workflow est ACTIVÉ (bouton ON/OFF en haut à droite)\n"
                    f"3. Le chemin du webhook correspond ({webhook_path or 'chemin configuré'})\n"
                    f"4. L'URL complète est: {url}"
                )
            elif status_code == 401 or status_code == 403:
                error_msg = f"Accès refusé (HTTP {status_code}). Vérifiez votre configuration d'authentification n8n."
            elif status_code:
                error_msg = f"Erreur HTTP {status_code} lors de l'appel au workflow: {str(e)}"
            else:
                error_msg = f"Erreur lors de l'appel au workflow: {str(e)}"
            logger.error(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            logger.exception(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
    
    def trigger_workflow_api(
        self,
        workflow_id: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Déclenche un workflow n8n en récupérant son webhook path via l'API
        Note: n8n n'a pas d'endpoint /execute, on doit utiliser les webhooks
        
        Args:
            workflow_id: ID du workflow dans n8n
            data: Données à envoyer au workflow
            
        Returns:
            Réponse du workflow n8n
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "N8N_API_KEY non configurée. Utilisez trigger_workflow_webhook avec webhook_path à la place."
            }
        
        try:
            # Récupérer les infos du workflow pour trouver le webhook path
            url = f"{self.base_url}/api/v1/workflows/{workflow_id}"
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            response.raise_for_status()
            workflow_info = response.json()
            
            # Chercher le nœud webhook dans le workflow
            webhook_path = None
            nodes = workflow_info.get("nodes", [])
            for node in nodes:
                if node.get("type") == "n8n-nodes-base.webhook":
                    parameters = node.get("parameters", {})
                    path = parameters.get("path")
                    if path:
                        webhook_path = path
                        break
            
            if not webhook_path:
                return {
                    "success": False,
                    "error": f"Workflow {workflow_id} n'a pas de nœud Webhook configuré. Utilisez webhook_path directement."
                }
            
            # Utiliser le webhook trouvé
            logger.info(f"📤 [N8N] Workflow ID '{workflow_id}' utilise le webhook '{webhook_path}'")
            return self.trigger_workflow_webhook(
                workflow_name=workflow_info.get("name", workflow_id),
                webhook_path=webhook_path,
                data=data
            )
            
        except Exception as e:
            error_msg = f"Erreur lors de la récupération du workflow: {str(e)}"
            logger.error(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
    
    def list_workflows(self) -> Dict[str, Any]:
        """
        Liste tous les workflows disponibles dans n8n avec leurs webhook paths (nécessite API key)
        
        Returns:
            Liste des workflows avec leurs chemins webhook
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "N8N_API_KEY requise pour lister les workflows"
            }
        
        try:
            url = f"{self.base_url}/api/v1/workflows"
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            response.raise_for_status()
            workflows = response.json()
            
            # Extraire les infos utiles de chaque workflow
            workflows_list = []
            for wf in workflows.get("data", []):
                wf_id = wf.get("id")
                wf_name = wf.get("name", "Sans nom")
                wf_active = wf.get("active", False)
                
                # Chercher le webhook path dans les nœuds
                webhook_path = None
                nodes = wf.get("nodes", [])
                for node in nodes:
                    if node.get("type") == "n8n-nodes-base.webhook":
                        parameters = node.get("parameters", {})
                        path = parameters.get("path")
                        if path:
                            webhook_path = path
                            break
                
                workflows_list.append({
                    "id": wf_id,
                    "name": wf_name,
                    "active": wf_active,
                    "webhook_path": webhook_path
                })
            
            return {
                "success": True,
                "workflows": workflows_list,
                "count": len(workflows_list)
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de la récupération des workflows: {str(e)}"
            logger.error(f"❌ [N8N] {error_msg}")
            return {"success": False, "error": error_msg}
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Teste la connexion à n8n
        
        Returns:
            Statut de la connexion
        """
        try:
            # Essayer d'accéder à l'API de santé de n8n
            url = f"{self.base_url}/healthz"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": f"n8n est accessible à {self.base_url}",
                    "status": "connected"
                }
            else:
                return {
                    "success": False,
                    "message": f"n8n répond mais avec un statut inattendu: {response.status_code}",
                    "status": "unknown"
                }
                
        except ConnectionError:
            return {
                "success": False,
                "message": f"Impossible de se connecter à n8n à {self.base_url}. Vérifiez que n8n est démarré.",
                "status": "disconnected"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Erreur lors du test de connexion: {str(e)}",
                "status": "error"
            }


# Instance globale
_n8n_instance: Optional[N8NIntegration] = None

def get_n8n() -> N8NIntegration:
    """Retourne l'instance globale de N8NIntegration"""
    global _n8n_instance
    if _n8n_instance is None:
        _n8n_instance = N8NIntegration()
    return _n8n_instance


# ============================================================================
# FONCTION PRINCIPALE POUR LE TOOL
# ============================================================================

def _calculate_date_from_text(date_text: str, time_text: Optional[str] = None) -> tuple[str, str]:
    """
    Calcule une date ISO 8601 à partir d'un texte comme "demain", "lundi", "dans 2 jours", etc.
    
    Args:
        date_text: Texte descriptif de la date (ex: "demain", "lundi", "dans 3 jours")
        time_text: Texte descriptif de l'heure (ex: "15h", "14:30", "à 16h")
    
    Returns:
        Tuple (start, end) au format ISO 8601
    """
    from datetime import datetime, timedelta
    from dateutil import parser, relativedelta
    
    try:
        now = datetime.now()
        tz_offset = timedelta(hours=1)  # UTC+1 (Europe/Paris)
        now = now.replace(tzinfo=timezone(tz_offset))
        
        # Parser la date
        date_text_lower = date_text.lower().strip()
        
        # Calculer la date cible
        if "demain" in date_text_lower or "tomorrow" in date_text_lower:
            target_date = now + timedelta(days=1)
        elif "après-demain" in date_text_lower or "day after tomorrow" in date_text_lower:
            target_date = now + timedelta(days=2)
        elif "aujourd'hui" in date_text_lower or "today" in date_text_lower:
            target_date = now
        elif "lundi" in date_text_lower:
            days_ahead = (0 - now.weekday()) % 7
            if days_ahead == 0:  # Si c'est déjà lundi, prendre le prochain
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "mardi" in date_text_lower:
            days_ahead = (1 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "mercredi" in date_text_lower:
            days_ahead = (2 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "jeudi" in date_text_lower:
            days_ahead = (3 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "vendredi" in date_text_lower:
            days_ahead = (4 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "samedi" in date_text_lower:
            days_ahead = (5 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        elif "dimanche" in date_text_lower:
            days_ahead = (6 - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now + timedelta(days=days_ahead)
        else:
            # Essayer de parser avec dateutil
            try:
                target_date = parser.parse(date_text, default=now)
                if target_date.tzinfo is None:
                    target_date = target_date.replace(tzinfo=timezone(tz_offset))
            except:
                # Par défaut, demain
                target_date = now + timedelta(days=1)
        
        # Parser l'heure
        hour = 15  # Par défaut 15h
        minute = 0
        
        if time_text:
            time_text = time_text.replace("h", ":").replace("H", ":")
            if ":" in time_text:
                parts = time_text.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            else:
                try:
                    hour = int(time_text)
                except:
                    pass
        
        # Construire la datetime complète
        start_dt = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)  # Durée par défaut: 1h
        
        return start_dt.isoformat(), end_dt.isoformat()
    
    except Exception as e:
        logger.warning(f"Erreur calcul date depuis texte '{date_text} {time_text}': {e}")
        # Fallback: demain à 15h
        now = datetime.now(timezone(timedelta(hours=1)))
        tomorrow = now + timedelta(days=1)
        start = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        return start.isoformat(), end.isoformat()


def _format_date_for_google_calendar(date_str: str, default_duration_hours: int = 1) -> tuple[str, str]:
    """
    Formate une date pour Google Calendar au format ISO 8601 avec fuseau horaire
    
    Args:
        date_str: Date au format "YYYY-MM-DD HH:MM" ou ISO 8601
        default_duration_hours: Durée par défaut en heures
    
    Returns:
        Tuple (start, end) au format ISO 8601
    """
    
    try:
        # Essayer de parser différents formats
        if 'T' in date_str:
            # Format ISO déjà
            dt_str = date_str.replace('Z', '+00:00')
            if '+' in dt_str or dt_str.endswith('+00:00'):
                dt = datetime.fromisoformat(dt_str)
            else:
                # ISO sans fuseau, ajouter Europe/Paris
                dt = datetime.fromisoformat(dt_str)
                dt = dt.replace(tzinfo=timezone(timedelta(hours=1)))  # UTC+1 (Europe/Paris)
        else:
            # Format "YYYY-MM-DD HH:MM"
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            # Ajouter le fuseau horaire (Europe/Paris = UTC+1)
            dt = dt.replace(tzinfo=timezone(timedelta(hours=1)))
        
        # Formater en ISO 8601
        start = dt.isoformat()
        end = (dt + timedelta(hours=default_duration_hours)).isoformat()
        
        return start, end
    except Exception as e:
        logger.warning(f"Erreur formatage date '{date_str}': {e}")
        # Retourner des dates par défaut (maintenant + 1h)
        now = datetime.now(timezone(timedelta(hours=1)))  # UTC+1
        start = now.isoformat()
        end = (now + timedelta(hours=default_duration_hours)).isoformat()
        return start, end


def n8n_workflow_tool(
    action: str,
    workflow_name: Optional[str] = None,
    webhook_path: Optional[str] = None,
    workflow_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    """
    Tool principal pour interagir avec n8n depuis Cypher
    
    Args:
        action: Action à effectuer ("trigger", "list", "test")
        workflow_name: Nom du workflow (pour logging)
        webhook_path: Chemin du webhook n8n (ex: "cypher-workflow")
        workflow_id: ID du workflow (pour l'API)
        data: Données à envoyer (dict ou JSON string)
        **kwargs: Données supplémentaires (seront fusionnées avec data)
    
    Returns:
        Message de résultat formaté pour l'utilisateur
    """
    n8n = get_n8n()
    
    # Parser data si c'est une string JSON
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return f"❌ Erreur: 'data' doit être un dictionnaire ou une string JSON valide"
    
    # Fusionner kwargs avec data
    if data is None:
        data = {}
    if kwargs:
        data.update(kwargs)
    
    # Amélioration : Si c'est un workflow Google Calendar, valider et formater les dates
    if action == "trigger" and webhook_path and "calendar" in webhook_path.lower():
        logger.info(f"📅 [N8N] Données reçues pour Google Calendar: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # Détecter automatiquement l'action si elle n'est pas fournie
        # Le workflow n8n attend un champ "action" pour router via le Switch
        if "action" not in data:
            # Vérifier si c'est une suppression (event_id valide sans autres champs de création)
            event_id = data.get("event_id")
            has_event_id = event_id and event_id != "event_id" and event_id != ""  # Ignorer les valeurs invalides
            
            # Si on a un event_id valide ET pas de champs de création (start/end/title), c'est delete_event
            if has_event_id and not any(k in data for k in ["start", "end", "title", "description"]):
                data["action"] = "delete_event"
                logger.info(f"✅ [N8N] Action détectée automatiquement: delete_event")
            # Si on a event_id + start/end/title, c'est update_event
            elif has_event_id and (data.get("start") or data.get("end") or data.get("title")):
                data["action"] = "update_event"
                logger.info(f"✅ [N8N] Action détectée automatiquement: update_event")
            # Si on a seulement event_id valide sans autres champs, c'est get_event
            elif has_event_id:
                data["action"] = "get_event"
                logger.info(f"✅ [N8N] Action détectée automatiquement: get_event")
            # Si on a title + start + end, c'est create_event
            elif data.get("title") and data.get("start") and data.get("end"):
                data["action"] = "create_event"
                logger.info(f"✅ [N8N] Action détectée automatiquement: create_event")
            # Si on a query, c'est search_events
            elif data.get("query"):
                data["action"] = "search_events"
                logger.info(f"✅ [N8N] Action détectée automatiquement: search_events")
            # Si on a time_min/time_max (sans query), c'est list_events
            elif data.get("time_min") or data.get("time_max"):
                data["action"] = "list_events"
                logger.info(f"✅ [N8N] Action détectée automatiquement: list_events")
            # Sinon, par défaut list_events
            else:
                data["action"] = "list_events"
                logger.info(f"✅ [N8N] Action détectée automatiquement: list_events")
        else:
            logger.info(f"✅ [N8N] Action fournie explicitement: {data.get('action')}")
        
        # Vérifier et formater les dates si nécessaire (seulement pour create_event et update_event)
        if data.get("action") in ["create_event", "update_event"]:
            # Vérifier que title existe et n'est pas vide pour create_event
            title = data.get("title", "").strip() if data.get("title") else ""
            if data.get("action") == "create_event":
                if not title:
                    logger.error(f"❌ [N8N] ERREUR CRITIQUE: Titre manquant ou vide pour créer un événement Google Calendar!")
                    logger.error(f"   Clés présentes: {list(data.keys())}")
                    logger.error(f"   Valeur title: '{data.get('title')}'")
                    return (
                        f"❌ Erreur: Le titre est obligatoire et ne peut pas être vide pour créer un événement Google Calendar. "
                        f"Assurez-vous d'inclure 'title' avec une valeur non vide dans les données."
                    )
                # S'assurer que le titre est bien défini
                data["title"] = title
                # Google Calendar utilise "summary" pour le titre, ajouter les deux pour compatibilité
                data["summary"] = title
                logger.info(f"✅ [N8N] Titre configuré: '{title}' (également ajouté comme 'summary' pour Google Calendar)")
            
            # Vérifier que start et end existent pour create_event
            if data.get("action") == "create_event" and (not data.get("start") or not data.get("end")):
                logger.error(f"❌ [N8N] ERREUR CRITIQUE: Dates manquantes pour créer un événement Google Calendar!")
                logger.error(f"   Clés présentes: {list(data.keys())}")
                logger.error(f"   Valeurs: {json.dumps(data, indent=2, ensure_ascii=False)}")
                return (
                    f"❌ Erreur: Les dates 'start' et 'end' sont obligatoires pour créer un événement Google Calendar. "
                    f"Assurez-vous d'inclure 'title', 'start' et 'end' dans les données."
                )
            
            # Vérifier et formater les dates si elles existent
            if data.get("start"):
                start_str = str(data["start"])
                # Si les dates ne sont pas au format ISO 8601, les convertir
                if not ("T" in start_str and ("+" in start_str or "Z" in start_str)):
                    try:
                        start, end = _format_date_for_google_calendar(
                            start_str,
                            default_duration_hours=int(data.get("duration_hours", 1))
                        )
                        data["start"] = start
                        if not data.get("end") or not ("T" in str(data.get("end", "")) and ("+" in str(data.get("end", "")) or "Z" in str(data.get("end", "")))):
                            data["end"] = end
                        logger.info(f"✅ [N8N] Dates formatées: start={data['start']}, end={data['end']}")
                    except Exception as e:
                        logger.warning(f"⚠️ [N8N] Erreur formatage date start: {e}")
            
            # Vérification finale pour create_event
            if data.get("action") == "create_event" and (not data.get("start") or not data.get("end")):
                return (
                    f"❌ Erreur: Impossible de formater les dates. "
                    f"start={data.get('start')}, end={data.get('end')}. "
                    f"Les dates doivent être au format ISO 8601 (ex: '2025-01-20T15:00:00+01:00')."
                )
    
    # Exécuter l'action
    if action == "trigger":
        if webhook_path:
            result = n8n.trigger_workflow_webhook(
                workflow_name=workflow_name,
                webhook_path=webhook_path,
                data=data if data else None
            )
        elif workflow_id:
            result = n8n.trigger_workflow_api(
                workflow_id=workflow_id,
                data=data if data else None
            )
        else:
            # Utiliser le webhook par défaut
            result = n8n.trigger_workflow_webhook(
                workflow_name=workflow_name,
                data=data if data else None
            )
        
        if result.get("success"):
            response_data = result.get("data", {})
            
            # Réponses concises selon l'action
            action_type = data.get("action", "") if data else ""
            
            if action_type == "create_event":
                title = data.get("title", "événement") if data else "événement"
                # Extraire l'event_id de la réponse si disponible pour confirmation
                event_id = None
                if isinstance(response_data, dict):
                    event_id = response_data.get("id") or response_data.get("event_id")
                if event_id:
                    return f"Rendez-vous '{title}' ajouté (ID: {event_id[:20]}...)."
                return f"Rendez-vous '{title}' ajouté."
            elif action_type == "delete_event":
                # Vérifier si la suppression a réussi
                if isinstance(response_data, dict):
                    # Si Google Calendar renvoie une erreur, elle sera dans la réponse
                    if response_data.get("error") or "not found" in str(response_data).lower():
                        error_msg = response_data.get("error", {}).get("message", "Erreur lors de la suppression")
                        logger.error(f"❌ [N8N] Erreur suppression: {error_msg}")
                        return f"Erreur: Impossible de supprimer le rendez-vous. {error_msg}"
                # Si pas d'erreur, la suppression a probablement réussi
                return "Rendez-vous supprimé."
            elif action_type == "update_event":
                return "Rendez-vous modifié."
            elif action_type == "list_events" or action_type == "search_events":
                # Extraire les événements depuis la réponse n8n
                events = []
                
                # Chercher dans différentes structures possibles de la réponse n8n
                if isinstance(response_data, list):
                    events = response_data
                elif isinstance(response_data, dict):
                    # Structure Google Calendar API standard
                    events = response_data.get("items", [])
                    if not events:
                        events = response_data.get("events", [])
                    if not events and isinstance(response_data.get("data"), list):
                        events = response_data.get("data", [])
                    if not events and isinstance(response_data.get("body"), list):
                        events = response_data.get("body", [])
                    # Si la réponse contient directement un tableau d'événements
                    if not events and len(response_data) > 0:
                        # Vérifier si c'est un tableau d'objets événements
                        first_key = list(response_data.keys())[0] if response_data else None
                        if first_key and isinstance(response_data[first_key], list):
                            events = response_data[first_key]
                
                if events and len(events) > 0:
                    # Formater les événements pour Gemini (avec event_id pour permettre la suppression)
                    events_list = []
                    for event in events[:10]:  # Limiter à 10 pour la lisibilité
                        if isinstance(event, dict):
                            title = event.get("summary") or event.get("title") or event.get("name") or "(Sans titre)"
                            event_id = event.get("id", "")
                            start = event.get("start", {})
                            if isinstance(start, dict):
                                start_time = start.get("dateTime") or start.get("date", "")
                                # Formater la date pour la lisibilité
                                if start_time:
                                    try:
                                        from datetime import datetime
                                        if "T" in start_time:
                                            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                                            start_time = dt.strftime("%d/%m/%Y %H:%M")
                                    except:
                                        pass
                            else:
                                start_time = str(start) if start else ""
                            # Inclure l'event_id dans la réponse pour permettre la suppression
                            # Format clair pour que Gemini puisse facilement extraire l'ID
                            if event_id:
                                events_list.append(f"- {title} ({start_time}) | ID: {event_id}")
                            else:
                                events_list.append(f"- {title} ({start_time})")
                    
                    events_text = "\n".join(events_list)
                    count = len(events)
                    return f"{count} événement(s):\n{events_text}"
                else:
                    return "Aucun événement."
            elif action_type == "get_event":
                if isinstance(response_data, dict):
                    event_title = response_data.get("title", "événement")
                    return f"Événement: {event_title}"
                return "Événement récupéré."
            else:
                # Réponse générique concise
                return "Terminé."
        else:
            error = result.get("error", "Erreur inconnue")
            logger.error(f"❌ [N8N] Erreur workflow: {error}")
            logger.error(f"❌ [N8N] Résultat complet: {json.dumps(result, indent=2, ensure_ascii=False)}")
            # Message plus détaillé pour aider au débogage
            if "404" in error or "non trouvé" in error.lower():
                return (
                    f"❌ Workflow n8n non trouvé. "
                    f"Vérifiez que le workflow est ACTIVÉ dans n8n et que le chemin '{webhook_path}' est correct. "
                    f"Erreur: {error}"
                )
            elif "Timeout" in error or "timeout" in error.lower():
                return f"❌ Timeout lors de l'appel au workflow n8n. Le workflow prend trop de temps à répondre. {error}"
            elif "connexion" in error.lower() or "connection" in error.lower():
                return f"❌ Impossible de se connecter à n8n. Vérifiez que n8n est démarré sur {N8N_BASE_URL}. {error}"
            else:
                return f"❌ Erreur workflow n8n: {error}"
    
    elif action == "list":
        result = n8n.list_workflows()
        if result.get("success"):
            workflows = result.get("workflows", [])
            if not workflows:
                return "📋 Aucun workflow trouvé dans n8n"
            
            workflow_list = []
            for wf in workflows[:10]:  # Limiter à 10 pour la lisibilité
                name = wf.get("name", "Sans nom")
                wf_id = wf.get("id", "N/A")
                active = "✅" if wf.get("active") else "⏸️"
                webhook_path = wf.get("webhook_path")
                
                # Construire la ligne avec le webhook path si disponible
                line = f"  {active} {name} (ID: {wf_id})"
                if webhook_path:
                    line += f" → webhook: '{webhook_path}'"
                elif not wf.get("active"):
                    line += " [EN PAUSE - Activez-le pour voir le webhook]"
                else:
                    line += " [Pas de webhook configuré]"
                
                workflow_list.append(line)
            
            count = result.get("count", len(workflows))
            return f"📋 Workflows disponibles ({count}):\n" + "\n".join(workflow_list)
        else:
            error = result.get("error", "Erreur inconnue")
            return f"❌ Erreur lors de la récupération des workflows: {error}"
    
    elif action == "test":
        result = n8n.test_connection()
        if result.get("success"):
            return f"✅ {result.get('message')}"
        else:
            return f"❌ {result.get('message')}"
    
    else:
        return f"❌ Action inconnue: {action}. Actions disponibles: trigger, list, test"


# ============================================================================
# DÉCLARATION DU TOOL POUR GEMINI
# ============================================================================

N8N_WORKFLOW_TOOL_DECLARATION = {
    "name": "n8n_workflow",
    "description": (
        "Déclenche des workflows n8n pour orchestrer des tâches complexes et connecter Cypher "
        "à des services externes (Google Calendar, Slack, Notion, etc.). "
        "⚠️ POUR GOOGLE CALENDAR (rendez-vous, événements, calendrier, planning, agenda): "
        "Utilise TOUJOURS webhook_path='google-calendar' SANS poser de question. "
        "Calcule les dates au format ISO 8601 avec fuseau horaire (ex: '2025-01-20T15:00:00+01:00'). "
        "Pour CRÉER: data={{'title': 'Titre', 'start': '2025-01-20T15:00:00+01:00', 'end': '2025-01-20T16:00:00+01:00'}}. "
        "⚠️ POUR LISTER (OBLIGATOIRE pour toute demande de consultation): "
        "Si l'utilisateur demande 'quels rendez-vous', 'planning', 'événements de demain', 'liste mes rendez-vous', 'qu'est-ce que j'ai de prévu' → "
        "TU DOIS appeler n8n_workflow(action='trigger', webhook_path='google-calendar', data={{'time_min': '2025-01-20T00:00:00+01:00', 'time_max': '2025-01-20T23:59:59+01:00'}}). "
        "Pour SUPPRIMER: D'abord liste les événements pour obtenir l'event_id, puis data={{'event_id': 'vrai_id_obtenu'}}. "
        "Le champ 'action' est ajouté automatiquement selon les données envoyées. "
        "Pour autres services: utilise 'trigger' avec le webhook_path approprié, 'list' pour voir les workflows, 'test' pour vérifier la connexion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["trigger", "list", "test"],
                "description": "Action à effectuer: 'trigger' (exécuter un workflow), 'list' (lister les workflows), 'test' (tester la connexion)"
            },
            "workflow_name": {
                "type": "string",
                "description": "Nom du workflow (pour logging et identification). Optionnel si webhook_path est fourni."
            },
            "webhook_path": {
                "type": "string",
                "description": (
                    "Chemin du webhook n8n configuré dans le workflow (ex: 'google-calendar', 'cypher-workflow'). "
                    "IMPORTANT: Utilise TOUJOURS ce paramètre pour déclencher un workflow. "
                    "Le chemin doit correspondre EXACTEMENT au 'Path' configuré dans le nœud Webhook du workflow n8n. "
                    "Si tu ne connais pas le chemin, utilise 'list' pour voir les workflows disponibles, ou utilise le webhook par défaut configuré dans N8N_WEBHOOK_URL."
                )
            },
            "workflow_id": {
                "type": "string",
                "description": "ID du workflow dans n8n (pour l'API). Nécessite N8N_API_KEY configurée."
            },
            "data": {
                "type": "object",
                "description": (
                    "Données à envoyer au workflow (objet JSON). "
                    "⚠️ POUR CRÉER un événement Google Calendar: "
                    "OBLIGATOIRE: 'title' (non vide), 'start' et 'end' au format ISO 8601 (ex: '2025-01-20T15:00:00+01:00'). "
                    "Exemple: {\"title\": \"Réunion\", \"start\": \"2025-01-20T15:00:00+01:00\", \"end\": \"2025-01-20T16:00:00+01:00\"}. "
                    "⚠️ POUR SUPPRIMER un événement: "
                    "D'ABORD liste les événements avec list_events pour obtenir le vrai 'event_id', "
                    "PUIS envoie {\"event_id\": \"vrai_id_obtenu\"} (sans title/start/end). "
                    "⚠️ POUR LISTER les événements: "
                    "{\"time_min\": \"2025-01-20T00:00:00+01:00\", \"time_max\": \"2025-01-20T23:59:59+01:00\"}. "
                    "L'action est détectée automatiquement selon les champs envoyés."
                )
            }
        },
        "required": ["action"]
    }
}

