"""
Fonctions utilitaires communes pour Cypher
"""

import os
from typing import Optional
from core.logger import get_logger

logger = get_logger("utils")


def get_folder_size(start_path: str = '.') -> int:
    """
    Calcule récursivement la taille d'un dossier en octets.
    
    Returns:
        int: Taille en octets, ou -1 en cas d'erreur
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
    except Exception as e:
        logger.error(f"Erreur lors du calcul de la taille du dossier: {e}")
        return -1
    return total_size


def format_bytes(bytes_size: int) -> str:
    """
    Formate une taille en octets en texte lisible (KB, MB, GB, etc.).
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def get_weather(location: Optional[str] = None, day: Optional[str] = None) -> str:
    """
    Météo réelle via l'API Open-Meteo.
    Par défaut : Petit-Couronne, aujourd'hui.
    """
    import requests
    from datetime import datetime, timedelta

    # 1) Valeurs par défaut
    if not location or not location.strip():
        location = "Petit-Couronne"

    if not day or not day.strip():
        day_label = "aujourd'hui"
        target_date = datetime.now().date()
    else:
        d = day.lower()
        if "après" in d:
            day_label = "après-demain"
            target_date = datetime.now().date() + timedelta(days=2)
        elif "demain" in d:
            day_label = "demain"
            target_date = datetime.now().date() + timedelta(days=1)
        else:
            day_label = "aujourd'hui"
            target_date = datetime.now().date()

    # 2) Géocodage pour obtenir latitude / longitude
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
    try:
        geo_resp = requests.get(geo_url, timeout=5).json()
    except Exception as e:
        logger.error(f"Erreur lors de la requête géocodage: {e}")
        return f"Erreur lors de la récupération de la météo pour '{location}', Monsieur."

    if "results" not in geo_resp or len(geo_resp["results"]) == 0:
        return f"Je n'ai pas trouvé la ville '{location}', Monsieur."

    lat = geo_resp["results"][0]["latitude"]
    lon = geo_resp["results"][0]["longitude"]
    resolved_name = geo_resp["results"][0]["name"]

    # 3) Appel météo
    meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
        f"&timezone=Europe/Paris"
    )

    try:
        meteo = requests.get(meteo_url, timeout=5).json()
    except Exception as e:
        logger.error(f"Erreur lors de la requête météo: {e}")
        return f"Erreur lors de la récupération de la météo, Monsieur."

    # 4) Si on parle d'aujourd'hui -> current weather
    if target_date == datetime.now().date():
        temp = meteo["current"]["temperature_2m"]
        code = meteo["current"]["weather_code"]
    else:
        # Index dans daily
        index = (target_date - datetime.now().date()).days
        if index >= len(meteo["daily"]["weather_code"]):
            return "Prévision météo trop lointaine, Monsieur."

        temp = (
            f"{meteo['daily']['temperature_2m_min'][index]}°C à "
            f"{meteo['daily']['temperature_2m_max'][index]}°C"
        )
        code = meteo["daily"]["weather_code"][index]

    # 5) Traduction météo du weather_code
    weather_translate = {
        0: "ciel dégagé",
        1: "principalement dégagé",
        2: "partiellement nuageux",
        3: "ciel couvert",
        45: "brouillard",
        48: "brouillard givrant",
        51: "bruine légère",
        53: "bruine",
        55: "bruine intense",
        61: "pluie faible",
        63: "pluie modérée",
        65: "pluie forte",
        71: "neige faible",
        73: "neige modérée",
        75: "forte neige",
        95: "orage",
    }

    description = weather_translate.get(code, "temps variable")

    # 6) Phrase finale
    return f"À {resolved_name}, {day_label} : {temp} et {description}."

