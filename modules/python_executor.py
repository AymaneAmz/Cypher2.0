# -*- coding: utf-8 -*-
"""
Module d'exécution Python sécurisée pour Cypher
Gère l'exécution de code Python avec confirmation et sécurité maximale
"""

import os
import re
import subprocess
import tempfile
import json
import hashlib
from datetime import datetime
from typing import Optional
from core.paths import get_memory_dir
from core.logger import get_logger

logger = get_logger("python_executor")

# Variables globales pour gérer le code en attente et l'historique
_pending_python_code: Optional[str] = None
_python_execution_log: list = []

# Chemins OneDrive (calculés une fois au chargement du module)
USER_HOME = os.path.expanduser("~")
ONEDRIVE_BASE = os.path.join(USER_HOME, "OneDrive")

DESKTOP_REAL = os.path.join(ONEDRIVE_BASE, "Desktop")
DOCUMENTS_REAL = os.path.join(ONEDRIVE_BASE, "Documents")
IMAGES_REAL = os.path.join(ONEDRIVE_BASE, "Images")

# Si l'utilisateur a renommé son dossier OneDrive (cas rare)
if not os.path.exists(DESKTOP_REAL):
    DESKTOP_REAL = os.path.join(USER_HOME, "Desktop")

if not os.path.exists(DOCUMENTS_REAL):
    DOCUMENTS_REAL = os.path.join(USER_HOME, "Documents")

if not os.path.exists(IMAGES_REAL):
    IMAGES_REAL = os.path.join(USER_HOME, "Images")


def _record_error(source: str, message: str, code_snippet: Optional[str] = None):
    """Enregistre une erreur dans la mémoire d'erreurs"""
    try:
        error_file = str(get_memory_dir() / "cypher_memory_cortex.json")

        # Charger l'existant
        if os.path.exists(error_file):
            try:
                with open(error_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        # Normalisation
        source = source.lower()
        if source not in data:
            data[source] = []

        # On compresse un peu l'info
        msg = (message or "").strip()
        if len(msg) > 400:
            msg = msg[:400] + "… (tronqué)"

        # petit hash pour reconnaître les erreurs récurrentes
        base = (source + "|" + msg).encode("utf-8", errors="ignore")
        err_hash = hashlib.sha1(base).hexdigest()[:12]

        entry = {
            "hash": err_hash,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "message": msg,
            "code_excerpt": (code_snippet[:400] + "…") if code_snippet else None,
        }

        # On évite de stocker 200 fois la même erreur : si même hash déjà présent on ne rajoute pas
        if not any(e.get("hash") == err_hash for e in data[source]):
            data[source].append(entry)

        with open(error_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception:
        # Surtout ne jamais faire planter Cypher à cause de la mémoire d'erreurs
        pass


def execute_python(code: str, confirmed: bool = False) -> str:
    """
    Exécute du code Python avec confirmation obligatoire et sécurité maximale.
    """
    global _pending_python_code, _python_execution_log
    
    # ==========================================
    # CORRECTION AUTOMATIQUE DES CHEMINS UTILISATEUR (OneDrive)
    # ==========================================
    # On force les dossiers vers OneDrive pour ton user
    
    # Helper : os.path.join(os.path.expanduser("~"), "Dossier")
    def _replace_join_home_folder(code_str, folder_names, target_path):
        pattern = (
            r'os\.path\.join\(\s*os\.path\.expanduser\(["\']~["\']\)\s*,\s*["\']('
            + "|".join(folder_names) +
            r')["\']\s*\)'
        )
        # IMPORTANT : utiliser une fonction pour que re.sub ne réinterprète pas les backslashes
        return re.sub(pattern, lambda m: repr(target_path), code_str)

    code = _replace_join_home_folder(code, ["Desktop", "Bureau"], DESKTOP_REAL)
    code = _replace_join_home_folder(code, ["Documents"], DOCUMENTS_REAL)
    code = _replace_join_home_folder(code, ["Images", "Pictures"], IMAGES_REAL)
    # Note: Downloads/Téléchargements n'est PAS redirigé vers OneDrive

    # Helper : os.path.expanduser("~") + "\\Dossier" ou "/Dossier"
    def _replace_concat_home_folder(code_str, folder_names, target_path):
        pattern = (
            r'os\.path\.expanduser\(["\']~["\']\)\s*\+\s*["\'][\\/]+('
            + "|".join(folder_names) +
            r')["\']'
        )
        return re.sub(pattern, lambda m: repr(target_path), code_str)

    code = _replace_concat_home_folder(code, ["Desktop", "Bureau"], DESKTOP_REAL)
    code = _replace_concat_home_folder(code, ["Documents"], DOCUMENTS_REAL)
    code = _replace_concat_home_folder(code, ["Images", "Pictures"], IMAGES_REAL)
    # Note: Downloads/Téléchargements n'est PAS redirigé vers OneDrive
    
    # ==========================================
    # ÉTAPE 1 : MODE PREVIEW (confirmed=False)
    # ==========================================
    if not confirmed:
        # Stocker le code CORRIGÉ pour le prochain appel
        _pending_python_code = code.strip()
        
        # Analyser le code pour donner un résumé intelligent
        summary_parts = []
        
        # Détection des imports
        imports = re.findall(r'^import\s+(\w+)', code, re.MULTILINE)
        imports += re.findall(r'^from\s+(\w+)', code, re.MULTILINE)
        if imports:
            summary_parts.append(f"• Utilise les bibliothèques : {', '.join(set(imports))}")
        
        # Détection des opérations fichiers
        if 'open(' in code or 'Path(' in code:
            summary_parts.append("• Manipule des fichiers")
        if 'os.mkdir' in code or 'os.makedirs' in code:
            summary_parts.append("• Crée des dossiers")
        if 'os.remove' in code or 'os.unlink' in code or 'shutil.rmtree' in code:
            summary_parts.append("• Supprime des fichiers/dossiers")
        if 'shutil.copy' in code or 'shutil.move' in code:
            summary_parts.append("• Copie ou déplace des fichiers")
        
        # Détection des boucles
        if 'for ' in code or 'while ' in code:
            summary_parts.append("• Contient des boucles")
        
        # Détection des opérations réseau
        if 'requests.' in code or 'urllib' in code or 'http' in code:
            summary_parts.append("• Effectue des requêtes réseau")
        
        summary = "\n".join(summary_parts) if summary_parts else "• Script Python personnalisé"
        
        return (
            f"CODE_EN_ATTENTE_DE_CONFIRMATION\n\n"
            f"Résumé de ce que le code va faire :\n{summary}\n\n"
            f"Lignes de code : {len(code.splitlines())}\n"
            f"Taille : {len(code)} caractères"
        )
    
    # ==========================================
    # ÉTAPE 2 : MODE EXÉCUTION (confirmed=True)
    # ==========================================
    
    # Utiliser le code stocké si disponible, sinon le code fourni
    if _pending_python_code:
        code_to_execute = _pending_python_code
        _pending_python_code = None  # Nettoyer après utilisation
    else:
        code_to_execute = code.strip()
    
    if not code_to_execute:
        return "Erreur : Aucun code à exécuter, Monsieur."
    
    # --- SÉCURITÉ : Blacklist de chemins interdits ---
    FORBIDDEN_PATHS = [
        r"C:\System32",
        "/etc",
        "/sys",
        "/root",
        "/bin",
        "/sbin",
    ]
    
    code_lower = code_to_execute.lower()
    for forbidden in FORBIDDEN_PATHS:
        if forbidden.lower() in code_lower:
            return f"🚫 SÉCURITÉ : Je ne peux pas exécuter du code qui accède à {forbidden}, Monsieur."
    
    # --- SÉCURITÉ : Détection de commandes système dangereuses ---
    DANGEROUS_PATTERNS = [
        r'os\.system\s*\(',
        r'subprocess\.call\s*\(.+shell\s*=\s*True',
        r'eval\s*\(',
        r'exec\s*\(',
    ]
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, code_to_execute):
            return f"🚫 SÉCURITÉ : Le code contient une opération potentiellement dangereuse ({pattern}), Monsieur."
    
    # --- CRÉATION DU FICHIER TEMPORAIRE ---
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.py', 
            delete=False, 
            encoding='utf-8'
        ) as f:
            f.write(code_to_execute)
            temp_file = f.name
        
        logger.debug(f"Code Python écrit dans : {temp_file}")
        
        # --- EXÉCUTION AVEC TIMEOUT ---
        start_time = datetime.now()
        
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=90,  # Timeout de 90 secondes
            encoding='utf-8',
            errors='replace'
        )
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # --- NETTOYAGE ---
        try:
            os.unlink(temp_file)
        except:
            pass
        
        # --- LOG DE L'EXÉCUTION ---
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "code_lines": len(code_to_execute.splitlines()),
            "execution_time": execution_time,
            "success": result.returncode == 0,
            "stdout_length": len(result.stdout),
            "stderr_length": len(result.stderr),
        }
        _python_execution_log.append(log_entry)
        
        # --- FORMATAGE DE LA RÉPONSE ---
        if result.returncode == 0:
            # Succès
            output = result.stdout.strip()
            
            if output:
                # Limiter la sortie à 500 caractères pour éviter les réponses trop longues
                if len(output) > 500:
                    output = output[:500] + "\n... (sortie tronquée)"
                
                return (
                    f"EXECUTION_FINALE_OK\n"  # <-- MARQUEUR
                    f"✅ CODE EXÉCUTÉ AVEC SUCCÈS (en {execution_time:.2f}s)\n\n"
                    f"Sortie :\n{output}"
                )
            else:
                return f"✅ CODE EXÉCUTÉ AVEC SUCCÈS (en {execution_time:.2f}s), Monsieur."
        else:
            # Erreur
            error = result.stderr.strip()
            if len(error) > 300:
                error = error[:300] + "\n... (erreur tronquée)"

            # 🔴 Enregistrer dans la mémoire d'erreurs
            try:
                _record_error(
                    source="execute_python",
                    message=error,
                    code_snippet=code_to_execute
                )
            except Exception:
                pass

            return (
                "EXECUTION_FINALE_ERREUR\n"
                f"❌ ERREUR LORS DE L'EXÉCUTION (après {execution_time:.2f}s)\n\n"
                f"{error}"
            )
    
    except subprocess.TimeoutExpired:
        try:
            os.unlink(temp_file)
        except:
            pass

        # 🔴 Log timeout
        try:
            _record_error(
                source="execute_python",
                message="Timeout (90s) lors de l'exécution du script.",
                code_snippet=code_to_execute
            )
        except Exception:
            pass

        return "⏱️ TIMEOUT : Le code a dépassé la limite de 90 secondes, Monsieur."
    
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution Python : {e}")
        return f"❌ ERREUR INATTENDUE : {e}"


def get_python_execution_history() -> str:
    """Retourne l'historique des dernières exécutions Python."""
    global _python_execution_log
    
    if not _python_execution_log:
        return "Aucune exécution Python n'a encore été effectuée, Monsieur."
    
    # Prendre les 5 dernières exécutions
    recent = _python_execution_log[-5:]
    
    lines = ["📊 HISTORIQUE DES EXÉCUTIONS PYTHON\n"]
    for i, entry in enumerate(reversed(recent), 1):
        status = "✅" if entry["success"] else "❌"
        lines.append(
            f"{i}. {status} {entry['timestamp'][:19]} - "
            f"{entry['code_lines']} lignes - "
            f"{entry['execution_time']:.2f}s"
        )
    
    return "\n".join(lines)

