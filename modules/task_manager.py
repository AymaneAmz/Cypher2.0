# -*- coding: utf-8 -*-
"""
Task Master - Module de gestion de tâches professionnel pour Cypher
Gère les tâches avec récurrence automatique et persistance JSON
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from core.paths import get_memory_dir
from core.logger import get_logger

logger = get_logger("task_manager")


class TaskManager:
    """
    Gestionnaire de tâches professionnel avec récurrence automatique.
    
    Fonctionnalités:
    - Création, modification, suppression de tâches
    - Système de priorités (low, medium, high, critical)
    - Récurrence automatique (daily, weekly, monthly, yearly)
    - Persistance JSON
    - Recherche et filtrage avancé
    """
    
    def __init__(self, tasks_file: Optional[str] = None):
        """
        Initialise le TaskManager.
        
        Args:
            tasks_file: Chemin vers le fichier JSON (optionnel, utilise le chemin par défaut)
        """
        self.memory_dir = get_memory_dir()
        self.tasks_file = Path(tasks_file) if tasks_file else self.memory_dir / "cypher_tasks.json"
        
        # Créer le fichier s'il n'existe pas
        if not self.tasks_file.exists():
            self._save_tasks([])
        
        # Charger les tâches existantes
        self.tasks = self._load_tasks()
        loaded_count = len(self.tasks)
        logger.info(f"TaskManager initialisé - {loaded_count} tâche(s) chargée(s) depuis {self.tasks_file}")
        
        # Vérifier et compter les tâches récurrentes
        recurring_count = len([t for t in self.tasks if t.get('recurrence')])
        if recurring_count > 0:
            logger.info(f"  - {recurring_count} tâche(s) récurrente(s) détectée(s)")
        
        # Compter les tâches à venir (non terminées avec date future ou sans date)
        now = datetime.now()
        upcoming_count = len([
            t for t in self.tasks
            if t.get('status') != 'done' and (
                not t.get('due_date') or 
                (self._parse_due_date(t.get('due_date')) and self._parse_due_date(t.get('due_date')) >= now)
            )
        ])
        if upcoming_count > 0:
            logger.info(f"  - {upcoming_count} tâche(s) à venir")
    
    def _load_tasks(self) -> List[Dict[str, Any]]:
        """Charge les tâches depuis le fichier JSON"""
        try:
            if not self.tasks_file.exists():
                logger.info(f"Fichier de tâches n'existe pas encore: {self.tasks_file}")
                return []
            
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content or content == '[]':
                    logger.info("Fichier de tâches vide")
                    return []
                
                data = json.loads(content)
                # S'assurer que c'est une liste
                if isinstance(data, list):
                    logger.info(f"Chargement de {len(data)} tâche(s) depuis {self.tasks_file}")
                    return data
                elif isinstance(data, dict) and 'tasks' in data:
                    tasks = data['tasks']
                    logger.info(f"Chargement de {len(tasks)} tâche(s) depuis {self.tasks_file}")
                    return tasks
                else:
                    logger.warning(f"Format de fichier inattendu dans {self.tasks_file}, réinitialisation")
                    return []
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON dans {self.tasks_file}: {e}")
            return []
        except Exception as e:
            logger.error(f"Erreur lors du chargement des tâches depuis {self.tasks_file}: {e}", exc_info=True)
            return []
    
    def _save_tasks(self, tasks: Optional[List[Dict[str, Any]]] = None):
        """Sauvegarde les tâches dans le fichier JSON"""
        try:
            tasks_to_save = tasks if tasks is not None else self.tasks
            
            # S'assurer que le dossier existe
            self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarder dans un fichier temporaire d'abord (atomic write)
            temp_file = self.tasks_file.parent / (self.tasks_file.name + ".tmp")
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_to_save, f, ensure_ascii=False, indent=2)
            
            # Remplacer l'ancien fichier (atomic)
            if self.tasks_file.exists():
                self.tasks_file.replace(temp_file)
            else:
                temp_file.rename(self.tasks_file)
            
            # Vérifier que la sauvegarde a bien fonctionné
            if not self.tasks_file.exists():
                raise FileNotFoundError(f"Le fichier {self.tasks_file} n'a pas été créé après la sauvegarde")
            
            # Vérifier le contenu du fichier
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                if len(saved_data) != len(tasks_to_save):
                    logger.warning(f"Nombre de tâches sauvegardées ({len(saved_data)}) différent du nombre attendu ({len(tasks_to_save)})")
            
            logger.info(f"{len(tasks_to_save)} tâche(s) sauvegardée(s) dans {self.tasks_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des tâches dans {self.tasks_file}: {e}", exc_info=True)
            # Ne pas lever l'exception pour ne pas bloquer l'application
            # mais logger l'erreur avec le traceback complet
            # Essayer une sauvegarde de secours directe
            try:
                with open(self.tasks_file, 'w', encoding='utf-8') as f:
                    json.dump(tasks_to_save, f, ensure_ascii=False, indent=2)
                logger.info(f"Sauvegarde de secours réussie: {len(tasks_to_save)} tâche(s)")
            except Exception as e2:
                logger.error(f"Échec de la sauvegarde de secours: {e2}")
    
    def _generate_id(self) -> str:
        """Génère un UUID unique pour une tâche"""
        return str(uuid.uuid4())
    
    def _validate_task(self, task: Dict[str, Any]) -> bool:
        """Valide qu'une tâche a tous les champs requis"""
        required_fields = ['id', 'title', 'status', 'priority', 'created_at']
        for field in required_fields:
            if field not in task:
                logger.warning(f"Tâche invalide: champ '{field}' manquant")
                return False
        return True
    
    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: Optional[str] = None,
        recurrence: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "todo"
    ) -> Dict[str, Any]:
        """
        Ajoute une nouvelle tâche.
        
        Args:
            title: Titre de la tâche
            description: Description détaillée (optionnel)
            priority: Priorité ("low", "medium", "high", "critical")
            due_date: Date d'échéance au format ISO (YYYY-MM-DD HH:MM)
            recurrence: Règle de répétition ("daily", "weekly", "monthly", "yearly", None)
            tags: Liste de tags (optionnel)
            status: Statut initial ("todo", "in_progress", "done")
        
        Returns:
            La tâche créée
        """
        # Validation de la priorité
        valid_priorities = ["low", "medium", "high", "critical"]
        if priority not in valid_priorities:
            priority = "medium"
            logger.warning(f"Priorité invalide, utilisation de 'medium'")
        
        # Validation du statut
        valid_statuses = ["todo", "in_progress", "done"]
        if status not in valid_statuses:
            status = "todo"
            logger.warning(f"Statut invalide, utilisation de 'todo'")
        
        # Validation de la récurrence
        valid_recurrences = [None, "daily", "weekly", "monthly", "yearly"]
        if recurrence not in valid_recurrences:
            recurrence = None
            logger.warning(f"Récurrence invalide, utilisation de None")
        
        # Créer la tâche
        task = {
            "id": self._generate_id(),
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "due_date": due_date,
            "recurrence": recurrence,
            "tags": tags or [],
            "created_at": datetime.now().isoformat()
        }
        
        # Ajouter à la liste
        self.tasks.append(task)
        
        # Sauvegarder immédiatement
        try:
            self._save_tasks()
            logger.info(f"Tâche ajoutée et sauvegardée: {title} (ID: {task['id']}) dans {self.tasks_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde après ajout de tâche: {e}", exc_info=True)
            # Ne pas lever l'exception, mais logger l'erreur
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Récupère une tâche par son ID"""
        for task in self.tasks:
            if task.get('id') == task_id:
                return task
        return None
    
    def find_task_by_name(self, fuzzy_name: str) -> Optional[Dict[str, Any]]:
        """
        Trouve une tâche par son nom (recherche floue).
        
        Args:
            fuzzy_name: Nom partiel ou complet de la tâche
        
        Returns:
            La première tâche correspondante ou None
        """
        fuzzy_name_lower = fuzzy_name.lower().strip()
        
        # Recherche exacte d'abord
        for task in self.tasks:
            if task['title'].lower() == fuzzy_name_lower:
                return task
        
        # Recherche partielle
        for task in self.tasks:
            if fuzzy_name_lower in task['title'].lower():
                return task
        
        return None
    
    def list_tasks(
        self,
        filter_status: Optional[str] = None,
        filter_priority: Optional[str] = None,
        date_range: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Liste les tâches avec filtres optionnels.
        
        Args:
            filter_status: Filtrer par statut ("todo", "in_progress", "done")
            filter_priority: Filtrer par priorité ("low", "medium", "high", "critical")
            date_range: Filtrer par date ("today", "this_week", "overdue", ou None pour tout)
        
        Returns:
            Liste des tâches correspondantes
        """
        filtered = self.tasks.copy()
        
        # Filtrer par statut
        if filter_status:
            filtered = [t for t in filtered if t.get('status') == filter_status]
        
        # Filtrer par priorité
        if filter_priority:
            filtered = [t for t in filtered if t.get('priority') == filter_priority]
        
        # Filtrer par date
        if date_range:
            now = datetime.now()
            filtered = [t for t in filtered if self._matches_date_range(t, date_range, now)]
        
        # Trier par priorité et date d'échéance
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        filtered.sort(key=lambda t: (
            priority_order.get(t.get('priority', 'medium'), 2),
            self._parse_due_date(t.get('due_date')) or datetime.max
        ))
        
        return filtered
    
    def _matches_date_range(self, task: Dict[str, Any], date_range: str, now: datetime) -> bool:
        """Vérifie si une tâche correspond à la plage de dates"""
        due_date = self._parse_due_date(task.get('due_date'))
        if not due_date:
            return False
        
        if date_range == "today":
            return due_date.date() == now.date()
        elif date_range == "this_week":
            week_start = now - timedelta(days=now.weekday())
            return week_start.date() <= due_date.date() <= (week_start + timedelta(days=6)).date()
        elif date_range == "overdue":
            return due_date < now and task.get('status') != 'done'
        else:
            return True
    
    def _parse_due_date(self, due_date_str: Optional[str]) -> Optional[datetime]:
        """Parse une date ISO en datetime"""
        if not due_date_str:
            return None
        try:
            # Essayer différents formats
            formats = [
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d"
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(due_date_str, fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None
    
    def _calculate_next_due_date(self, current_due_date: str, recurrence: str) -> str:
        """
        Calcule la prochaine date d'échéance basée sur la récurrence.
        
        Args:
            current_due_date: Date actuelle au format ISO
            recurrence: Type de récurrence ("daily", "weekly", "monthly", "yearly")
        
        Returns:
            Nouvelle date au format ISO (YYYY-MM-DD HH:MM)
        """
        due_dt = self._parse_due_date(current_due_date)
        if not due_dt:
            # Si pas de date, utiliser maintenant
            due_dt = datetime.now()
        
        if recurrence == "daily":
            next_date = due_dt + timedelta(days=1)
        elif recurrence == "weekly":
            next_date = due_dt + timedelta(weeks=1)
        elif recurrence == "monthly":
            # Ajouter environ 30 jours (approximation)
            next_date = due_dt + timedelta(days=30)
        elif recurrence == "yearly":
            next_date = due_dt + timedelta(days=365)
        else:
            next_date = due_dt
        
        # Formater en ISO (YYYY-MM-DD HH:MM)
        return next_date.strftime("%Y-%m-%d %H:%M")
    
    def mark_as_done(self, task_id: Optional[str] = None, fuzzy_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Marque une tâche comme terminée et gère la récurrence automatique.
        
        Args:
            task_id: ID de la tâche (prioritaire)
            fuzzy_name: Nom de la tâche pour recherche floue
        
        Returns:
            Dictionnaire avec le résultat de l'opération
        """
        # Trouver la tâche
        task = None
        if task_id:
            task = self.get_task(task_id)
        elif fuzzy_name:
            task = self.find_task_by_name(fuzzy_name)
        
        if not task:
            return {
                "success": False,
                "message": f"Tâche non trouvée (ID: {task_id}, Nom: {fuzzy_name})"
            }
        
        # Marquer comme done
        task['status'] = 'done'
        task['completed_at'] = datetime.now().isoformat()
        
        result = {
            "success": True,
            "message": f"Tâche '{task['title']}' marquée comme terminée",
            "task": task.copy()
        }
        
        # Gérer la récurrence
        recurrence = task.get('recurrence')
        if recurrence:
            # Créer une nouvelle tâche identique
            new_task = {
                "id": self._generate_id(),
                "title": task['title'],
                "description": task.get('description', ''),
                "status": "todo",
                "priority": task.get('priority', 'medium'),
                "due_date": self._calculate_next_due_date(
                    task.get('due_date', datetime.now().isoformat()),
                    recurrence
                ),
                "recurrence": recurrence,
                "tags": task.get('tags', []).copy(),
                "created_at": datetime.now().isoformat()
            }
            
            self.tasks.append(new_task)
            result["recurrence_created"] = True
            result["new_task"] = new_task
            result["message"] += f". Nouvelle occurrence créée pour {new_task['due_date']}"
            logger.info(f"Tâche récurrente '{task['title']}' - nouvelle occurrence créée")
        else:
            result["recurrence_created"] = False
        
        # Sauvegarder
        self._save_tasks()
        
        return result
    
    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        due_date: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Met à jour une tâche existante.
        
        Returns:
            La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if not task:
            return None
        
        if title is not None:
            task['title'] = title
        if description is not None:
            task['description'] = description
        if status is not None:
            task['status'] = status
        if priority is not None:
            task['priority'] = priority
        if due_date is not None:
            task['due_date'] = due_date
        if tags is not None:
            task['tags'] = tags
        
        task['updated_at'] = datetime.now().isoformat()
        self._save_tasks()
        
        logger.info(f"Tâche mise à jour: {task_id}")
        return task
    
    def delete_task(self, task_id: Optional[str] = None, fuzzy_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Supprime une tâche.
        
        Args:
            task_id: ID de la tâche (prioritaire)
            fuzzy_name: Nom de la tâche pour recherche floue
        
        Returns:
            Dictionnaire avec le résultat de l'opération
        """
        # Trouver la tâche
        task = None
        if task_id:
            task = self.get_task(task_id)
        elif fuzzy_name:
            task = self.find_task_by_name(fuzzy_name)
        
        if not task:
            return {
                "success": False,
                "message": f"Tâche non trouvée (ID: {task_id}, Nom: {fuzzy_name})"
            }
        
        # Supprimer
        self.tasks = [t for t in self.tasks if t.get('id') != task['id']]
        self._save_tasks()
        
        logger.info(f"Tâche supprimée: {task['title']} (ID: {task['id']})")
        return {
            "success": True,
            "message": f"Tâche '{task['title']}' supprimée"
        }
    
    def delete_recurring_task_by_title(self, title: str) -> Dict[str, Any]:
        """
        Supprime toutes les occurrences d'une tâche récurrente par son titre.
        
        Args:
            title: Titre exact de la tâche récurrente
        
        Returns:
            Dictionnaire avec le résultat de l'opération
        """
        # Trouver toutes les tâches avec ce titre exact
        matching_tasks = [t for t in self.tasks if t.get('title') == title]
        
        if not matching_tasks:
            return {
                "success": False,
                "message": f"Aucune tâche trouvée avec le titre '{title}'"
            }
        
        # Supprimer toutes les occurrences
        count = len(matching_tasks)
        self.tasks = [t for t in self.tasks if t.get('title') != title]
        self._save_tasks()
        
        logger.info(f"Toutes les occurrences de la tâche récurrente '{title}' supprimées ({count} occurrence(s))")
        return {
            "success": True,
            "message": f"Toutes les occurrences de la tâche récurrente '{title}' supprimées ({count} occurrence(s))"
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques des tâches.
        
        Returns:
            Dictionnaire avec les statistiques
        """
        total = len(self.tasks)
        todo = len([t for t in self.tasks if t.get('status') == 'todo'])
        in_progress = len([t for t in self.tasks if t.get('status') == 'in_progress'])
        done = len([t for t in self.tasks if t.get('status') == 'done'])
        
        # Tâches en retard
        now = datetime.now()
        overdue = len([
            t for t in self.tasks
            if t.get('status') != 'done' and self._parse_due_date(t.get('due_date')) and
            self._parse_due_date(t.get('due_date')) < now
        ])
        
        # Tâches récurrentes
        recurring = len([t for t in self.tasks if t.get('recurrence')])
        
        # Par priorité
        by_priority = {
            "critical": len([t for t in self.tasks if t.get('priority') == 'critical' and t.get('status') != 'done']),
            "high": len([t for t in self.tasks if t.get('priority') == 'high' and t.get('status') != 'done']),
            "medium": len([t for t in self.tasks if t.get('priority') == 'medium' and t.get('status') != 'done']),
            "low": len([t for t in self.tasks if t.get('priority') == 'low' and t.get('status') != 'done'])
        }
        
        return {
            "total": total,
            "todo": todo,
            "in_progress": in_progress,
            "done": done,
            "overdue": overdue,
            "recurring": recurring,
            "by_priority": by_priority
        }


# Instance globale
_task_manager = None

def get_task_manager() -> TaskManager:
    """Retourne l'instance globale du TaskManager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

