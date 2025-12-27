"""
Script pour générer les sons discrets pour Cypher
"""

import os
import numpy as np
try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False
    print("soundfile non disponible, utilisation de scipy.io.wavfile")
    try:
        from scipy.io import wavfile
        HAS_SCIPY = True
    except ImportError:
        HAS_SCIPY = False
        print("scipy non disponible non plus. Installez soundfile ou scipy.")
        exit(1)

def generate_success_sound(filename="success.mp3"):
    """Génère un son de succès (bip ascendant court)"""
    duration = 0.15
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Bip ascendant doux
    freq_start, freq_end = 600, 1000
    freq = freq_start + (freq_end - freq_start) * t / duration
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 8)
    wave = wave * 0.5  # Réduire le volume
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        # Convertir en int16 pour wavfile
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_error_sound(filename="error.mp3"):
    """Génère un son d'erreur (bip descendant)"""
    duration = 0.2
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Bip descendant
    freq_start, freq_end = 800, 400
    freq = freq_start + (freq_end - freq_start) * t / duration
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 6)
    wave = wave * 0.4
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_processing_sound(filename="processing.mp3"):
    """Génère un son de traitement (bip court et discret)"""
    duration = 0.1
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Bip court à fréquence moyenne
    wave = np.sin(2 * np.pi * 700 * t) * np.exp(-t * 12)
    wave = wave * 0.3  # Très discret
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_notification_sound(filename="notification.mp3"):
    """Génère un son de notification (double bip doux)"""
    duration = 0.25
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Double bip
    wave = np.zeros_like(t)
    # Premier bip
    idx1 = int(sr * 0.05)
    idx2 = int(sr * 0.1)
    t1 = t[:idx2-idx1]
    wave[idx1:idx2] = np.sin(2 * np.pi * 800 * t1) * np.exp(-t1 * 15)
    # Deuxième bip
    idx3 = int(sr * 0.15)
    idx4 = int(sr * 0.2)
    t2 = t[:idx4-idx3]
    wave[idx3:idx4] = np.sin(2 * np.pi * 1000 * t2) * np.exp(-t2 * 15)
    wave = wave * 0.3
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_warning_sound(filename="warning.mp3"):
    """Génère un son d'avertissement (bip répété)"""
    duration = 0.3
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    wave = np.zeros_like(t)
    # Trois bips courts
    for i, offset in enumerate([0.05, 0.12, 0.19]):
        start = int(sr * offset)
        end = int(sr * (offset + 0.06))
        t_seg = t[:end-start]
        wave[start:end] = np.sin(2 * np.pi * 600 * t_seg) * np.exp(-t_seg * 10)
    wave = wave * 0.35
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_connect_sound(filename="connect.mp3"):
    """Génère un son de connexion (bip ascendant harmonieux)"""
    duration = 0.2
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Bip ascendant harmonieux
    freq_start, freq_end = 400, 800
    freq = freq_start + (freq_end - freq_start) * t / duration
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 5)
    wave = wave * 0.4
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

def generate_disconnect_sound(filename="disconnect.mp3"):
    """Génère un son de déconnexion (bip descendant)"""
    duration = 0.15
    sr = 22050
    t = np.linspace(0, duration, int(sr * duration))
    # Bip descendant
    freq_start, freq_end = 600, 300
    freq = freq_start + (freq_end - freq_start) * t / duration
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 8)
    wave = wave * 0.35
    if HAS_SOUNDFILE:
        sf.write(filename, wave, sr)
    elif HAS_SCIPY:
        wave_int16 = (wave * 32767).astype(np.int16)
        wavfile.write(filename.replace('.mp3', '.wav'), sr, wave_int16)
    print(f"[OK] {filename} cree")

if __name__ == "__main__":
    print("Génération des sons pour Cypher...")
    print("=" * 50)
    
    try:
        generate_success_sound()
        generate_error_sound()
        generate_processing_sound()
        generate_notification_sound()
        generate_warning_sound()
        generate_connect_sound()
        generate_disconnect_sound()
        
        print("=" * 50)
        print("[OK] Tous les sons ont ete generes avec succes!")
        print("\nNote: Si certains fichiers sont en .wav au lieu de .mp3,")
        print("mettez à jour sound_manager.py pour accepter les deux formats.")
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
