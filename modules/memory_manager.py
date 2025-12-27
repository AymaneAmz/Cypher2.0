# -*- coding: utf-8 -*-
"""
Module de gestion de mémoire pour Cypher
Gère la mémoire longue durée (mémoire persistante)
"""

import json
import os
from datetime import datetime
from core.paths import get_memory_dir
from core.logger import get_logger

logger = get_logger("memory_manager")

MEMORY_FILE = str(get_memory_dir() / "cypher_memory_cortex.json")


def memory_manager(
    action: str, 
    category: str, 
    key: str | None = None, 
    value: str | None = None
) -> str:
    """
    Gère la MÉMOIRE LONGUE DURÉE.
    """
    # 1. Chargement de la mémoire
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                memory = json.load(f)
        except json.JSONDecodeError:
            memory = {}
    else:
        memory = {}

    action = action.lower()
    
    # Liste des catégories valides pour guider (mais on accepte les nouvelles)
    VALID_CATEGORIES = [
        "profil_utilisateur", "gouts_et_preferences", "projets_actifs", 
        "environnement_systeme", "entourage", "base_de_connaissances", "journal_evenements"
    ]

    # --- ACTION : MÉMORISER (Remember) ---
    if action == "remember":
        if not key or not value:
            return "Erreur : Pour mémoriser, il me faut un sujet (key) et une information (value)."
        
        # Normalisation
        category_slug = category.lower().replace(" ", "_")
        
        if category_slug not in memory:
            memory[category_slug] = {}
        
        # Ajout d'un timestamp pour savoir quand on a appris ça
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        memory_entry = {
            "value": value,
            "updated_at": timestamp
        }
        
        memory[category_slug][key.lower()] = memory_entry
        
        # Sauvegarde atomique
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
        
        return f"🧠 Mémoire enregistrée dans [{category_slug}] : J'ai noté que '{key}' est '{value}'."

    # --- ACTION : SE RAPPELER (Recall) ---
    if action == "recall":
        category_slug = category.lower().replace(" ", "_")
        
        # Si on veut tout savoir sur une catégorie
        if not key:
            if category_slug not in memory:
                return f"Je n'ai aucune information dans la catégorie '{category}'."
            
            content = []
            for k, v in memory[category_slug].items():
                # On gère le format ancien (juste str) et nouveau (dict avec timestamp)
                val = v["value"] if isinstance(v, dict) and "value" in v else v
                content.append(f"- **{k.title()}** : {val}")
            
            return f"📂 **Contenu de la mémoire '{category}'** :\n" + "\n".join(content)

        # Si on cherche une clé précise
        key_lower = key.lower()
        if category_slug in memory and key_lower in memory[category_slug]:
            data = memory[category_slug][key_lower]
            val = data["value"] if isinstance(data, dict) and "value" in data else data
            return f"💡 **Souvenir retrouvé** ({category}) : {val}"
        else:
            return f"Je n'ai pas de mémoire précise pour '{key}' dans '{category}'."

    # --- ACTION : OUBLIER (Forget) ---
    if action == "forget":
        category_slug = category.lower().replace(" ", "_")
        if category_slug in memory:
            if key:
                if key.lower() in memory[category_slug]:
                    del memory[category_slug][key.lower()]
                    save = True
                else:
                    return f"Je ne connaissais pas '{key}' dans cette catégorie."
            else:
                # Oublier toute la catégorie
                del memory[category_slug]
                save = True
            
            if save:
                with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                    json.dump(memory, f, indent=4, ensure_ascii=False)
                return f"🗑️ Mémoire effacée avec succès."
        return "Rien à effacer."

    # --- ACTION : LISTER LES CATÉGORIES (Map) ---
    if action == "list_categories":
        cats = list(memory.keys())
        return f"🗂️ Catégories actuelles de mon cerveau : {', '.join(cats)}"

    return "Action mémoire inconnue."

