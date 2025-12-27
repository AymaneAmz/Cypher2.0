# -*- coding: utf-8 -*-
"""
Module de gestion de fichiers pour Cypher
Gère toutes les manipulations de fichiers et dossiers avec support OneDrive
"""

import os
import shutil
from core.utils import get_folder_size, format_bytes
from core.logger import get_logger

logger = get_logger("file_manager")


def _resolve_path(p: str) -> str:
    """
    Résout un chemin en tenant compte de OneDrive.
    Redirige automatiquement Desktop, Documents et Images vers OneDrive.
    Downloads/Téléchargements reste dans le dossier utilisateur standard.
    """
    if not p:
        return p
    
    # 1. Gestion du tilde ~ et normalisation
    p = os.path.expanduser(p)
    p = os.path.normpath(p)
    
    # Calcul des chemins OneDrive
    user_home = os.path.expanduser("~")
    onedrive_base = os.path.join(user_home, "OneDrive")
    desktop_real = os.path.join(onedrive_base, "Desktop")
    documents_real = os.path.join(onedrive_base, "Documents")
    images_real = os.path.join(onedrive_base, "Images")
    
    # Si l'utilisateur a renommé son dossier OneDrive (cas rare)
    if not os.path.exists(desktop_real):
        desktop_real = os.path.join(user_home, "Desktop")
    if not os.path.exists(documents_real):
        documents_real = os.path.join(user_home, "Documents")
    if not os.path.exists(images_real):
        images_real = os.path.join(user_home, "Images")
    
    # 2. Détection des raccourcis simples
    p_lower = p.lower().strip(os.path.sep)
    if p_lower in ["documents", "doc", "mes documents"]:
        return documents_real
    if p_lower in ["desktop", "bureau"]:
        return desktop_real
    if p_lower in ["images", "pictures", "photos"]:
        return images_real
    
    # 3. Redirection des chemins standards Windows vers les chemins réels (OneDrive)
    # IMPORTANT: Seulement pour Desktop, Documents et Images. PAS pour Downloads/Téléchargements.
    std_docs = os.path.normpath(os.path.join(user_home, "Documents"))
    std_desk = os.path.normpath(os.path.join(user_home, "Desktop"))
    std_images = os.path.normpath(os.path.join(user_home, "Images"))
    
    # Si le chemin demandé commence par le faux chemin standard, on remplace par le vrai
    if p.startswith(std_docs) and documents_real not in p:
        return p.replace(std_docs, documents_real)
    
    if p.startswith(std_desk) and desktop_real not in p:
        return p.replace(std_desk, desktop_real)
    
    if p.startswith(std_images) and images_real not in p:
        return p.replace(std_images, images_real)
    
    # Downloads/Téléchargements reste dans user_home (pas de redirection OneDrive)
    return p


def file_manager(action: str, source_path: str, destination_path: str | None = None, content: str | None = None) -> str:
    """
    Tool Python pour la gestion de fichiers/dossiers.
    Gère intelligemment la redirection vers OneDrive.
    """
    # Application de la correction des chemins
    source_path = _resolve_path(source_path)
    if destination_path:
        destination_path = _resolve_path(destination_path)
        
    action = action.lower()

    # --- NOUVEAU : CRÉER UN FICHIER (ÉCRIRE DU CODE) ---
    if action == "create_file":
        if not content:
            return "Erreur : Le contenu du fichier est manquant."
        try:
            # Créer le dossier parent si besoin
            parent_dir = os.path.dirname(source_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(source_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Fichier créé avec succès : {source_path}"
        except Exception as e:
            return f"Erreur lors de l'écriture du fichier : {e}"

    # --- NOUVEAU : LIRE UN FICHIER ---
    if action == "read_file":
        if not os.path.exists(source_path):
            return f"Le fichier '{source_path}' n'existe pas."
        try:
            with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = f.read()
            return f"Contenu de '{source_path}' :\n\n{data[:4000]}"  # Limite 4000 chars
        except Exception as e:
            return f"Erreur de lecture : {e}"
    
    # --- 1. Créer un Dossier/Structure ---
    if action == "create_dir":
        try:
            os.makedirs(source_path, exist_ok=True)
            return f"Le dossier/structure '{source_path}' a été créé avec succès."
        except Exception as e:
            return f"Erreur lors de la création de '{source_path}': {e}"
    
    # --- 2. Lister les Fichiers/Scanner ---
    if action == "list_files":
        try:
            if not os.path.isdir(source_path):
                return f"Erreur : '{source_path}' n'est pas un dossier valide ou n'existe pas."
            
            # Lister les fichiers
            items = os.listdir(source_path)
            if not items:
                return f"Le répertoire '{source_path}' est vide."
            
            # On sépare dossiers et fichiers pour plus de clarté
            dirs = [d for d in items if os.path.isdir(os.path.join(source_path, d))]
            files = [f for f in items if os.path.isfile(os.path.join(source_path, f))]
            
            # On limite l'affichage pour ne pas saturer la réponse
            report = f"📂 Contenu de '{source_path}' :\n"
            if dirs:
                report += "📁 DOSSIERS :\n" + "\n".join([f"  - {d}" for d in dirs[:15]])
                if len(dirs) > 15:
                    report += "\n  ... (et autres dossiers)"
                report += "\n"
            if files:
                report += "\n📄 FICHIERS :\n" + "\n".join([f"  - {f}" for f in files[:15]])
                if len(files) > 15:
                    report += "\n  ... (et autres fichiers)"
            
            return report
        except Exception as e:
            return f"Erreur lors de la lecture du répertoire '{source_path}': {e}"

    # --- 3. Déplacer / Renommer ---
    if action == "move" or action == "rename":
        if action == "rename" and destination_path:
            destination_path = os.path.join(os.path.dirname(source_path), destination_path)
        
        if not destination_path:
            return "Le chemin de destination est manquant."

        try:
            shutil.move(source_path, destination_path)
            return f"'{source_path}' a été déplacé/renommé vers '{destination_path}'."
        except Exception as e:
            return f"Erreur : {e}"

    # --- 4. Copier ---
    if action == "copy":
        if not destination_path:
            return "Le chemin de destination est manquant."
        try:
            if os.path.isdir(source_path):
                shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
            else:
                shutil.copy2(source_path, destination_path)
            return f"Copié vers '{destination_path}'."
        except Exception as e:
            return f"Erreur copie : {e}"

    # --- 5. Supprimer ---
    if action == "delete":
        try:
            if os.path.isdir(source_path):
                shutil.rmtree(source_path)
                return f"Dossier '{source_path}' supprimé."
            else:
                os.remove(source_path)
                return f"Fichier '{source_path}' supprimé."
        except Exception as e:
            return f"Erreur suppression : {e}"

    # --- 6. Calculer la Taille ---
    if action == "calculate_size":
        try:
            size_bytes = get_folder_size(source_path)
            if size_bytes == -1:
                return "Erreur calcul taille."
            return f"Taille : {format_bytes(size_bytes)}."
        except Exception as e:
            return f"Erreur : {e}"

    # --- 7. Archivage ---
    if action == "archive":
        if not destination_path:
            return "Destination manquante."
        try:
            base_name = os.path.basename(destination_path)
            root_dir = os.path.dirname(source_path)
            archive_path = shutil.make_archive(
                base_name=destination_path, format='zip', root_dir=root_dir,
                base_dir=os.path.basename(source_path) if os.path.isdir(source_path) else source_path
            )
            return f"Archivé dans : {archive_path}"
        except Exception as e:
            return f"Erreur archivage : {e}"

    # --- 8. Désarchivage ---
    if action == "unarchive":
        if not destination_path:
            return "Destination manquante."
        try:
            shutil.unpack_archive(filename=source_path, extract_dir=destination_path)
            return f"Décompressé dans '{destination_path}'."
        except Exception as e:
            return f"Erreur décompression : {e}"

    return f"Action inconnue : {action}"

