"""
Utilitaires TTS (Text-to-Speech) pour le nettoyage et la génération SSML
"""

import re


def generate_ssml(text: str, voice_name: str = "fr-FR-HenriNeural", rate: str = "+15%", pitch: str = "default") -> str:
    """
    Génère du SSML à partir du texte pour Azure Speech SDK.
    
    Args:
        text: Texte à convertir en SSML
        voice_name: Nom de la voix Azure (défaut: "fr-FR-HenriNeural")
        rate: Vitesse de parole (défaut: "+15%")
        pitch: Hauteur de la voix (défaut: "default")
    """
    # Nettoie d'abord le texte
    clean_text = clean_text_for_tts(text)
    
    # Échappe les caractères spéciaux XML
    safe_text = clean_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Génère le SSML avec les paramètres de vitesse et de pitch
    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="fr-FR">
    <voice name="{voice_name}">
        <prosody rate="{rate}" pitch="{pitch}">
            {safe_text}
        </prosody>
    </voice>
</speak>"""
    return ssml


def clean_text_for_tts(text: str) -> str:
    """
    Nettoie le texte pour la lecture vocale (Supprime le code et le Markdown).
    """
    # 1. SUPPRIMER LES BLOCS DE CODE (Entre ``` et ```)
    # On remplace tout le bloc de code par une courte pause silencieuse
    text = re.sub(r'```[\s\S]*?```', ' [Code analysé] ', text)
    
    # 2. SUPPRIMER LES LIGNES DE CODE TYPIQUES (Sécurité supplémentaire)
    # Si une ligne commence par 'import ', 'def ', 'class ', on la zappe
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        l = line.strip()
        if not l.startswith(('import ', 'from ', 'def ', 'class ', 'return ', 'self.', '@', 'print(')):
            clean_lines.append(line)
    text = '\n'.join(clean_lines)

    # 3. Nettoyage Markdown standard (*, #, _, `)
    clean = re.sub(r'[\*#_`]', '', text)
    
    return clean.strip()


def shorten_for_tts(text: str, max_length: int = 150) -> str:
    """
    Retourne une version courte du texte pour la voix (première phrase ou troncation).
    Cherche la fin de la première phrase (point, interrogation, exclamation) ou tronque.
    """
    if not text:
        return ""
    
    txt = text.strip().replace("\n", " ")
    
    # Chercher la fin de la première phrase
    end_idx = None
    for i, ch in enumerate(txt):
        if ch in ".?!":
            if i >= 20:  # Éviter de couper sur une abréviation ultra courte
                end_idx = i + 1
                break
    
    if end_idx is None:
        end_idx = min(len(txt), max_length)  # Tronquer à max_length caractères maximum si pas de point
    
    spoken = txt[:end_idx].strip()
    return spoken

