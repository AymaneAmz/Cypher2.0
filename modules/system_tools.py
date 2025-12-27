"""
Module pour les outils système : réseau, processus, alimentation, fenêtres, contrôle système
Centralise toutes les fonctions système qui utilisent subprocess/PowerShell
"""

import subprocess
import os
from typing import Optional
from core.logger import get_logger

logger = get_logger("system_tools")


def _run_powershell_command(cmd: str, shell: bool = True) -> str:
    """
    Fonction helper pour exécuter des commandes PowerShell ou système.
    
    Args:
        cmd: Commande à exécuter
        shell: Si True, utilise shell=True pour subprocess.run
    
    Returns:
        str: Sortie de la commande ou message d'erreur
    """
    try:
        encoding = 'cp850' if shell else 'utf-8'  # cp850 pour console Windows FR
        result = subprocess.run(
            cmd if isinstance(cmd, str) else cmd,
            capture_output=True,
            text=True,
            encoding=encoding,
            shell=shell
        )
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de la commande: {e}")
        return str(e)


def network_manager(action: str, target: Optional[str] = None) -> str:
    """
    Gère le Wi-Fi, le Bluetooth et le Mode Avion.
    Utilise netsh pour le Wi-Fi et Powershell/Commandes pour le reste.
    """
    action = action.lower()
    
    # --- WI-FI ---
    if action == "list_networks":
        output = _run_powershell_command("netsh wlan show networks mode=bssid")
        networks = []
        for line in output.split('\n'):
            if "SSID" in line and ":" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    networks.append(parts[1].strip())
        unique_networks = list(set(networks))
        return "Réseaux Wi-Fi visibles :\n" + "\n".join(unique_networks[:10])

    if action == "wifi_status":
        return f"État de l'interface Wi-Fi :\n{_run_powershell_command('netsh wlan show interfaces')}"

    if action == "disconnect_wifi":
        _run_powershell_command("netsh wlan disconnect")
        return "Déconnexion du réseau Wi-Fi effectuée."

    if action == "connect_wifi":
        if not target:
            return "Quel réseau Wi-Fi dois-je rejoindre ?"
        output = _run_powershell_command(f'netsh wlan connect name="{target}"')
        if "réussie" in output or "successfully" in output:
            return f"Tentative de connexion au réseau '{target}'..."
        else:
            return f"Erreur : {output}. (Le profil doit exister dans Windows)."

    # --- MODE AVION ---
    if action == "airplane_mode":
        # Windows 10/11 ne permet pas de toggle le mode avion facilement par ligne de commande
        # sans scripts PowerShell complexes ou droits admin. On ouvre la page dédiée.
        subprocess.Popen("start ms-settings:network-airplanemode", shell=True)
        return "J'ouvre les paramètres du Mode Avion (Windows restreint l'accès direct)."

    # --- BLUETOOTH ---
    if action == "bluetooth_status":
        # Utilise PowerShell pour lister les périphériques Bluetooth connectés/appairés
        ps_script = "Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -eq 'OK'} | Select-Object -ExpandProperty FriendlyName"
        output = _run_powershell_command(f'powershell -Command "{ps_script}"')
        if output:
            return f"Périphériques Bluetooth actifs/détectés :\n{output}"
        return "Aucun périphérique Bluetooth actif détecté ou erreur de lecture."

    if action == "bluetooth_settings" or action == "connect_bluetooth":
        # La connexion Bluetooth spécifique en ligne de commande est très instable sur Windows.
        # Le mieux est d'ouvrir la page d'appairage.
        subprocess.Popen("start ms-settings:bluetooth", shell=True)
        return "J'ouvre les paramètres Bluetooth pour gérer les connexions."

    return f"Action réseau non reconnue : {action}"


def window_manager(action: str, target_window: Optional[str] = None) -> str:
    """
    Gère les fenêtres Windows : minimiser, maximiser, fermer, lister, focus.
    Utilise pygetwindow.
    """
    import pygetwindow as gw
    
    action = action.lower()

    # Lister les fenêtres visibles
    if action == "list":
        titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
        return f"Fenêtres ouvertes :\n" + "\n".join(titles[:15])

    # Récupérer la fenêtre active
    if action == "active":
        try:
            win = gw.getActiveWindow()
            if win:
                return f"La fenêtre active est : {win.title}"
            return "Aucune fenêtre active détectée."
        except:
            return "Impossible de détecter la fenêtre active."

    # Pour les actions suivantes, il faut une cible
    if not target_window:
        return "Quelle fenêtre dois-je cibler ?"

    # Recherche floue de la fenêtre (ex: "Chrome" trouve "Google Chrome...")
    target_window_lower = target_window.lower()
    windows = [w for w in gw.getAllWindows() if target_window_lower in w.title.lower()]

    if not windows:
        return f"Je ne trouve aucune fenêtre contenant '{target_window}'."
    
    win = windows[0]  # On prend la première correspondance

    try:
        if action == "minimize":
            win.minimize()
            return f"Fenêtre '{win.title}' réduite."
        elif action == "maximize":
            win.maximize()
            return f"Fenêtre '{win.title}' maximisée."
        elif action == "restore":
            win.restore()
            return f"Fenêtre '{win.title}' restaurée."
        elif action == "close":
            win.close()
            return f"Fenêtre '{win.title}' fermée."
        elif action == "focus" or action == "activate":
            try:
                win.activate()
                return f"Je bascule sur '{win.title}'."
            except:
                # Parfois Windows bloque le focus forcé, on tente de minimiser/restaurer
                win.minimize()
                win.restore()
                return f"Tentative de focus sur '{win.title}'."
    except Exception as e:
        return f"Erreur lors de l'action sur la fenêtre : {e}"
    
    return "Action de fenêtre inconnue."


def system_control(feature: str, value: Optional[str | int] = None) -> str:
    """
    Contrôle le volume, la luminosité, et le presse-papier.
    Feature: volume, brightness, mute, clipboard_get, clipboard_set.
    """
    import screen_brightness_control as sbc
    import pyperclip
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    feature = feature.lower()

    # --- PRESSE-PAPIER (Bonus) ---
    if feature == "clipboard_get":
        content = pyperclip.paste()
        return f"Contenu du presse-papier : {content}" if content else "Le presse-papier est vide."
    
    if feature == "clipboard_set":
        if not value:
            return "Aucun texte fourni pour le presse-papier."
        pyperclip.copy(str(value))
        return "Texte copié dans le presse-papier."

    # --- LUMINOSITÉ ---
    if feature == "brightness":
        if value is None:
            current = sbc.get_brightness()
            return f"Luminosité actuelle : {current[0]}%." if current else "Impossible de lire la luminosité."
        
        try:
            # Gérer "+10", "-10" ou "50"
            val_str = str(value).strip()
            if val_str.startswith("+") or val_str.startswith("-"):
                current = sbc.get_brightness()[0]
                new_val = current + int(val_str)
            else:
                new_val = int(val_str)
            
            # Borner entre 0 et 100
            new_val = max(0, min(100, new_val))
            sbc.set_brightness(new_val)
            return f"Luminosité réglée à {new_val}%."
        except Exception as e:
            return f"Erreur de luminosité : {e}"

    # --- VOLUME (PyCaw) ---
    if feature in ["volume", "mute"]:
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            
            if feature == "mute":
                # Basculer le mute
                current_mute = volume.GetMute()
                volume.SetMute(not current_mute, None)
                return "Son coupé." if not current_mute else "Son réactivé."

            if feature == "volume":
                # Convertir pourcentage en dB (échelle logarithmique approximative pour Windows)
                # Note: Pycaw utilise SetMasterVolumeLevelScalar pour le % (0.0 à 1.0)
                if value is None:
                    current = round(volume.GetMasterVolumeLevelScalar() * 100)
                    return f"Volume actuel : {current}%."

                val_str = str(value).strip()
                current_vol = volume.GetMasterVolumeLevelScalar() * 100
                
                if val_str.startswith("+") or val_str.startswith("-"):
                    target = current_vol + int(val_str)
                else:
                    target = int(val_str)
                
                target = max(0.0, min(100.0, target))
                volume.SetMasterVolumeLevelScalar(target / 100.0, None)
                return f"Volume réglé à {int(target)}%."

        except Exception as e:
            return f"Erreur de volume : {e}"

    return "Fonctionnalité système inconnue."


def process_manager(action: str, target: Optional[str] = None) -> str:
    """
    Gère les processus : lister (top CPU/RAM), tuer un processus, infos système.
    Utilise psutil.
    """
    import psutil
    import platform

    action = action.lower()

    # Infos Globales
    if action == "system_info":
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        batt = psutil.sensors_battery()
        batt_status = f"{batt.percent}%" if batt else "Secteur/Inconnu"
        return (f"📊 État du Système :\n"
                f"- OS : {platform.system()} {platform.release()}\n"
                f"- CPU : {cpu}%\n"
                f"- RAM : {ram}%\n"
                f"- Batterie : {batt_status}")

    # Lister les processus gourmands
    if action == "list":
        # Top 5 par utilisation mémoire
        procs = []
        for p in psutil.process_iter(['name', 'memory_percent']):
            try:
                procs.append(p.info)
            except:
                pass
        # Trier et prendre le top 5
        top_5 = sorted(procs, key=lambda x: x['memory_percent'] or 0, reverse=True)[:5]
        
        report = "🚀 Top 5 Processus (RAM) :\n"
        for p in top_5:
            report += f"- {p['name']} : {p['memory_percent']:.1f}%\n"
        return report

    # Tuer un processus
    if action == "kill":
        if not target:
            return "Quel processus dois-je fermer ?"
        
        killed_count = 0
        target_lower = target.lower()
        if not target_lower.endswith(".exe"): 
            target_exe = target_lower + ".exe"
        else:
            target_exe = target_lower

        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Correspondance nom exact ou partiel
                if proc.info['name'].lower() == target_exe or target_lower in proc.info['name'].lower():
                    proc.kill()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if killed_count > 0:
            return f"J'ai arrêté {killed_count} processus correspondant à '{target}'."
        else:
            return f"Je n'ai pas trouvé de processus nommé '{target}'."

    return "Action de processus inconnue."


def power_control(action: str, force: bool = False) -> str:
    """
    Contrôle l'alimentation du PC : veille, redémarrage, arrêt, verrouillage.
    """
    action = action.lower()
    
    # Commande de base pour shutdown
    # /s = shutdown, /r = restart, /l = logoff, /h = hibernate
    # /t 0 = temps 0s, /f = force (si force=True)
    
    force_flag = "/f" if force else ""
    
    try:
        if action == "sleep":
            # La mise en veille se fait via rundll32
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "Mise en veille du système..."
        
        elif action == "lock":
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return "Session verrouillée."
        
        elif action == "shutdown":
            os.system(f"shutdown /s /t 5 {force_flag}")
            return "Arrêt du système dans 5 secondes."
        
        elif action == "restart":
            os.system(f"shutdown /r /t 5 {force_flag}")
            return "Redémarrage du système dans 5 secondes."
            
        elif action == "abort":
            os.system("shutdown /a")
            return "Annulation de l'arrêt/redémarrage planifié."
            
    except Exception as e:
        return f"Erreur lors de l'action d'alimentation : {e}"
        
    return "Action d'alimentation inconnue."


def system_optimize(action: str) -> str:
    """
    Outils d'optimisation : vider la RAM (via EmptyStandbyList si dispo, sinon garbage collector), vider les temp.
    """
    import gc
    import shutil
    import tempfile
    
    action = action.lower()
    
    if action == "clean_ram":
        # 1. Force le Garbage Collector de Python
        gc.collect()
        
        # 2. Sous Windows, on ne peut pas vraiment "vider la RAM" sans droits admin et outils tiers.
        # On peut suggérer de fermer les apps gourmandes via process_manager.
        return "Garbage Collector Python exécuté. Pour libérer plus de RAM système, utilisez `process_manager` pour fermer les applications gourmandes."

    if action == "clean_temp":
        temp_dir = tempfile.gettempdir()
        deleted_count = 0
        total_size = 0
        
        try:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        size = os.path.getsize(file_path)
                        os.remove(file_path)
                        deleted_count += 1
                        total_size += size
                    except:
                        pass  # Fichier utilisé, on ignore
        except Exception as e:
            return f"Erreur lors du nettoyage : {e}"
        
        size_mb = total_size / (1024 * 1024)
        return f"Nettoyage terminé. {deleted_count} fichiers temporaires supprimés (~{size_mb:.2f} MB libérés)."
        
    return "Action d'optimisation inconnue."

