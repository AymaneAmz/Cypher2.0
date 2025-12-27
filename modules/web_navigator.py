# -*- coding: utf-8 -*-
"""
Web Navigator - Module de navigation web autonome pour Cypher
Utilise l'API Gemini Computer Use pour le contrôle natif du navigateur.
"""

import os
import json
import base64
import asyncio
import queue
from typing import Optional, Dict, Any, Callable, Awaitable
from io import BytesIO
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ [WEB_NAV] Playwright non installé - pip install playwright && playwright install firefox")

try:
    from google import genai
    from google.genai import types
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_AVAILABLE = bool(GEMINI_API_KEY)
    if GEMINI_AVAILABLE:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        gemini_client = None
except ImportError:
    GEMINI_AVAILABLE = False
    gemini_client = None
    print("⚠️ [WEB_NAV] google-genai non installé - pip install google-genai")

from core.logger import get_logger

logger = get_logger("web_navigator")

# Configuration
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
# Modèle Computer Use de Gemini
MODEL_ID = "gemini-2.5-computer-use-preview-10-2025"  # Ou le modèle actuel disponible


class WebNavigator:
    """
    Navigateur web autonome utilisant Gemini Computer Use API.
    Le navigateur est headless (invisible) et les screenshots sont streamés vers le GUI.
    """
    
    def __init__(self, gui_queue: Optional[queue.Queue] = None):
        """
        Initialise le navigateur web.
        
        Args:
            gui_queue: Queue pour envoyer les images au GUI (optionnel)
        """
        self.gui_queue = gui_queue
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_running = False
        self.current_url = None
        self.action_history = []
        self.cookie_popup_clicked = False  # Pour éviter de cliquer plusieurs fois sur le popup
        self.last_screenshot_hash = None  # Pour détecter les changements de page
        self.search_bar_clicked = False  # Pour éviter de cliquer plusieurs fois sur la barre de recherche
        self.search_performed = False  # Pour savoir si la recherche a été effectuée
        self.search_text = ""  # Texte de recherche utilisé
        self.search_query = ""  # Texte de recherche extrait du prompt
        self.gemini_vision_calls = 0  # Compteur pour limiter les appels
        self.action_attempts = {}  # Compteur de tentatives par action
        
        if not GEMINI_AVAILABLE or not gemini_client:
            raise RuntimeError("Gemini API non disponible - vérifiez GEMINI_API_KEY")
        
        # Utiliser le client global (qui supporte aio)
        self.client = gemini_client
        # Vérifier que le client a l'attribut aio
        if not hasattr(self.client, 'aio'):
            logger.warning("Le client Gemini n'a pas d'attribut 'aio' - utilisation du client synchrone")
        logger.info("WebNavigator initialisé avec Gemini Computer Use")
    
    def denormalize_x(self, x: int, width: int = SCREEN_WIDTH) -> int:
        """Convertit les coordonnées normalisées (0-1000) en pixels"""
        return int((x / 1000) * width)
    
    def denormalize_y(self, y: int, height: int = SCREEN_HEIGHT) -> int:
        """Convertit les coordonnées normalisées (0-1000) en pixels"""
        return int((y / 1000) * height)
    
    async def start(self, headless: bool = True):
        """
        Démarre le navigateur en mode headless (invisible) avec le profil Firefox de l'utilisateur.
        
        Args:
            headless: True par défaut - le navigateur est invisible
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright n'est pas installé")
        
        try:
            self.playwright = await async_playwright().start()
            
            # Trouver le profil Firefox de l'utilisateur
            import os
            user_profile = os.path.expanduser("~")
            firefox_profiles_path = None
            
            # Chemins possibles pour le profil Firefox sur Windows
            possible_paths = [
                os.path.join(user_profile, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles"),
                os.path.join(user_profile, "AppData", "Local", "Mozilla", "Firefox", "Profiles"),
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    # Trouver le profil par défaut (généralement celui avec "default" dans le nom)
                    profiles = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)) and d.endswith(".default")]
                    if profiles:
                        firefox_profiles_path = os.path.join(path, profiles[0])
                        logger.info(f"Profil Firefox trouvé: {firefox_profiles_path}")
                        break
            
            if firefox_profiles_path and os.path.exists(firefox_profiles_path):
                # Utiliser le profil Firefox existant avec launch_persistent_context
                # Cela permet d'avoir les cookies, sessions, etc. de l'utilisateur
                try:
                    self.context = await self.playwright.firefox.launch_persistent_context(
                        user_data_dir=firefox_profiles_path,
                        headless=headless,
                        viewport={'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                        args=['--disable-blink-features=AutomationControlled']  # Moins de détection d'automatisation
                    )
                    # Avec launch_persistent_context, on obtient directement les pages
                    pages = self.context.pages
                    if pages:
                        self.page = pages[0]
                    else:
                        self.page = await self.context.new_page()
                    self.browser = None  # Pas de browser séparé avec launch_persistent_context
                    logger.info("Navigateur Firefox démarré avec profil utilisateur (sessions/cookies conservés)")
                    
                    # Vérifier si on est connecté en allant sur Amazon
                    await self.page.goto("https://www.amazon.fr", wait_until='domcontentloaded', timeout=10000)
                    await asyncio.sleep(1)
                    # Chercher un élément qui indique qu'on est connecté
                    try:
                        account_link = await self.page.query_selector('#nav-link-accountList, [data-nav-role="signin"]')
                        if account_link:
                            account_text = await account_link.inner_text()
                            if "Bonjour" in account_text or "Hello" in account_text:
                                logger.info("✅ Compte Amazon détecté comme connecté")
                            else:
                                logger.warning("⚠️ Compte Amazon peut-être non connecté")
                    except:
                        pass
                except Exception as e:
                    logger.error(f"Erreur avec profil Firefox: {e} - utilisation d'un profil vierge")
                    self.browser = await self.playwright.firefox.launch(headless=headless)
                    self.context = await self.browser.new_context(
                        viewport={'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
                    )
                    self.page = await self.context.new_page()
                    logger.info("Navigateur Firefox démarré en mode headless (profil vierge)")
            else:
                # Fallback: utiliser un nouveau contexte si le profil n'est pas trouvé
                logger.warning("Profil Firefox non trouvé - utilisation d'un profil vierge")
                self.browser = await self.playwright.firefox.launch(headless=headless)
                self.context = await self.browser.new_context(
                    viewport={'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
                )
                self.page = await self.context.new_page()
                logger.info("Navigateur Firefox démarré en mode headless (profil vierge)")
            
            self.is_running = True
        except Exception as e:
            logger.error(f"Erreur au démarrage du navigateur Firefox: {e}")
            raise
    
    async def stop(self):
        """Arrête le navigateur."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.is_running = False
            logger.info("Navigateur arrêté")
        except Exception as e:
            logger.error(f"Erreur à l'arrêt du navigateur: {e}")
    
    def _send_to_gui(self, screenshot_bytes: bytes, log_message: str, action_coords: tuple = None):
        """
        Envoie une image au GUI pour affichage (streaming optimisé).
        
        Args:
            screenshot_bytes: Bytes de l'image PNG
            log_message: Message de log à afficher
            action_coords: Tuple (x, y) des coordonnées de l'action pour afficher un point rouge
        """
        if not self.gui_queue:
            return
        
        try:
            # Convertir en base64 pour transmission
            img_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # Envoyer le message au GUI
            data = {
                "image": img_base64,
                "log": log_message,
                "log_type": "info",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            
            # Ajouter les coordonnées de l'action si présentes
            if action_coords:
                data["action_coords"] = action_coords
            
            self.gui_queue.put(("AGENT_VIEW_UPDATE", data))
        except Exception as e:
            logger.error(f"Erreur envoi au GUI: {e}")
    
    async def analyze_with_gemini_vision(self, screenshot_bytes: bytes, objective: str, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Analyse un screenshot avec Gemini Vision pour déterminer l'action à effectuer.
        Utilisé en fallback quand Computer Use n'est pas disponible.
        
        Args:
            screenshot_bytes: Bytes de l'image
            objective: Objectif à atteindre (ex: "Clique sur le bouton 'Ajouter au panier'")
            
        Returns:
            Dict avec l'action à effectuer (type, x, y, text, etc.)
        """
        if not GEMINI_AVAILABLE or not self.client:
            logger.error("Gemini non disponible")
            return None
        
        # Limiter les appels à Gemini Vision pour éviter le quota
        self.gemini_vision_calls += 1
        if self.gemini_vision_calls > 15 and not force:
            logger.warning(f"Trop d'appels à Gemini Vision ({self.gemini_vision_calls}) - utilisation des sélecteurs CSS")
            # Essayer d'utiliser les sélecteurs CSS directement
            try:
                # Si on cherche la barre de recherche
                if "search" in objective.lower() or "recherche" in objective.lower():
                    search_selectors = [
                        'input[type="text"][name*="search"]',
                        'input[type="text"][id*="search"]',
                        '#twotabsearchtextbox',
                        'input[name="field-keywords"]'
                    ]
                    for selector in search_selectors:
                        try:
                            search_bar = await self.page.query_selector(selector)
                            if search_bar:
                                box = await search_bar.bounding_box()
                                if box:
                                    return {
                                        "action": "type",
                                        "x": int(box['x'] + box['width'] / 2),
                                        "y": int(box['y'] + box['height'] / 2),
                                        "text": self.search_query,
                                        "confidence": 0.9,
                                        "reasoning": "Barre de recherche trouvée via sélecteur CSS"
                                    }
                        except:
                            continue
            except Exception as e:
                logger.error(f"Erreur sélecteurs CSS: {e}")
            
            return None
        
        try:
            # Convertir l'image en base64
            img_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # Prompt pour Gemini Vision - amélioré pour gérer le popup de cookies
            cookie_instruction = ""
            if not self.cookie_popup_clicked:
                cookie_instruction = "\n1. Si tu vois un popup de cookies en bas de la page, clique sur le bouton 'Accept' ou 'Accepter' (coordonnées précises du CENTRE du bouton)"
            else:
                cookie_instruction = "\n1. ⚠️ IGNORE le popup de cookies s'il est encore visible - on a déjà essayé de le fermer plusieurs fois. Passe directement à la barre de recherche."
            
            prompt = f"""Tu es un agent web autonome avec un navigateur Playwright. Analyse cette capture d'écran d'Amazon.

OBJECTIF: {objective}
{cookie_instruction}
2. Trouve la barre de recherche Amazon (en haut, avec "Search Amazon.fr" ou une loupe)
3. Clique sur la barre de recherche (coordonnées précises du CENTRE)
4. Tape le texte: {self.search_query}
5. Appuie sur Entrée ou clique sur la loupe
6. Dans les résultats, trouve le produit correspondant à "{self.search_query}"
7. Clique sur le produit
8. Trouve le bouton "Ajouter au panier"
9. Clique sur "Ajouter au panier"

IMPORTANT: 
- Réponds UNIQUEMENT avec la PROCHAINE action à faire
- Les coordonnées sont absolues (0-1440 pour X, 0-900 pour Y)
- Sois TRÈS PRÉCIS - trouve le CENTRE exact de l'élément
- Si le popup de cookies est visible mais qu'on a déjà essayé, IGNORE-LE et cherche la barre de recherche

Réponds UNIQUEMENT au format JSON valide:
{{
    "action": "click" | "type" | "scroll" | "wait" | "navigate" | "none",
    "x": <coordonnée X en pixels (0-1440) - CENTRE EXACT>,
    "y": <coordonnée Y en pixels (0-900) - CENTRE EXACT>,
    "text": "<texte à taper si action=type, sinon null>",
    "url": "<URL si action=navigate, sinon null>",
    "scroll_amount": <nombre de pixels si action=scroll, sinon null>,
    "confidence": <0.0 à 1.0>,
    "reasoning": "<explication brève>"
}}"""
            
            # Appel à Gemini Vision avec gestion des erreurs 429 (quota)
            max_retries = 3
            retry_delay = 2  # secondes
            response = None
            
            for attempt in range(max_retries):
                try:
                    from google.genai import types as genai_types
                    # Utiliser from_bytes pour créer la Part avec l'image (méthode correcte)
                    img_bytes = base64.b64decode(img_base64)
                    contents = [
                        genai_types.Part(text=prompt),
                        genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                    ]
                    response = await self.client.aio.models.generate_content(
                        model="gemini-2.0-flash-exp",
                        contents=contents
                    )
                    break  # Succès, sortir de la boucle
                except Exception as api_error:
                    error_str = str(api_error)
                    # Vérifier si c'est une erreur 429 (quota dépassé)
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                        if attempt < max_retries - 1:
                            # Calculer le délai de retry (augmente avec chaque tentative)
                            delay = retry_delay * (2 ** attempt)
                            logger.warning(f"Quota Gemini dépassé (429) - attente de {delay}s avant retry {attempt + 1}/{max_retries}")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # Dernière tentative échouée - essayer avec un modèle alternatif
                            logger.warning("Quota dépassé - tentative avec gemini-1.5-flash")
                            try:
                                # Réessayer avec gemini-1.5-flash
                                img_bytes = base64.b64decode(img_base64)
                                contents_retry = [
                                    genai_types.Part(text=prompt),
                                    genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                                ]
                                response = await self.client.aio.models.generate_content(
                                    model="gemini-1.5-flash",
                                    contents=contents_retry
                                )
                                break
                            except:
                                logger.error(f"Erreur API Gemini après {max_retries} tentatives: {api_error}")
                                return None
                    else:
                        # Autre erreur - réessayer
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            logger.error(f"Erreur API Gemini: {api_error}")
                            return None
            
            # Fallback si response n'est toujours pas défini
            if response is None:
                try:
                    # Essayer avec le format dict simple
                    img_bytes = base64.b64decode(img_base64)
                    response = await self.client.aio.models.generate_content(
                        model="gemini-2.0-flash-exp",
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {
                                    "inline_data": {
                                        "mime_type": "image/png",
                                        "data": img_base64
                                    }
                                }
                            ]
                        }]
                    )
                except Exception as e:
                    logger.error(f"Erreur fallback Gemini: {e}")
                    return None
            
            # Extraire le texte de la réponse
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                response_text = response.candidates[0].content.parts[0].text if hasattr(response.candidates[0].content.parts[0], 'text') else str(response)
            else:
                response_text = str(response)
            
            # Parser le JSON (peut être dans un bloc de code)
            response_text = response_text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parser le JSON
            try:
                result = json.loads(response_text)
                logger.info(f"Gemini Vision analyse: {result.get('action')} à ({result.get('x')}, {result.get('y')})")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Erreur parsing JSON Gemini: {e}, réponse: {response_text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Erreur analyse Gemini Vision: {e}")
            return None
    
    async def execute_function_calls(self, function_calls):
        """
        Exécute les function calls retournés par Gemini Computer Use.
        
        Args:
            function_calls: Liste des function calls à exécuter
            
        Returns:
            Liste de tuples (call_id, function_name, result_data)
        """
        results = []
        
        for call in function_calls:
            call_id = getattr(call, 'id', None)
            fn_name = call.name
            args = call.args or {}
            
            logger.info(f"[ACTION] {fn_name} {args}")
            result_data = {}
            
            try:
                # --- NAVIGATION ---
                if fn_name == "open_web_browser":
                    pass  # Déjà ouvert
                elif fn_name == "navigate":
                    await self.page.goto(args.get("url", "https://www.google.com"))
                    self.current_url = self.page.url
                elif fn_name == "go_back":
                    await self.page.go_back()
                    self.current_url = self.page.url
                elif fn_name == "go_forward":
                    await self.page.go_forward()
                    self.current_url = self.page.url
                elif fn_name == "search":
                    await self.page.goto("https://www.google.com")
                elif fn_name == "wait_5_seconds":
                    await asyncio.sleep(5)

                # --- MOUSE CLICKS & TYPING ---
                elif fn_name == "click_at":
                    x = self.denormalize_x(args.get("x", 0))
                    y = self.denormalize_y(args.get("y", 0))
                    await self.page.mouse.click(x, y)
                    self.action_history.append({"type": "click", "x": x, "y": y, "timestamp": datetime.now().isoformat()})
                    
                elif fn_name == "type_text_at":
                    x = self.denormalize_x(args.get("x", 0))
                    y = self.denormalize_y(args.get("y", 0))
                    text = args.get("text", "")
                    press_enter = args.get("press_enter", False)
                    clear_before = args.get("clear_before_typing", True)
                    
                    await self.page.mouse.click(x, y)
                    if clear_before:
                        await self.page.keyboard.press("Control+A")
                        await self.page.keyboard.press("Backspace")
                    
                    await self.page.keyboard.type(text)
                    if press_enter:
                        await self.page.keyboard.press("Enter")
                    
                    self.action_history.append({"type": "type", "x": x, "y": y, "text": text, "timestamp": datetime.now().isoformat()})

                # --- MOUSE MOVEMENT / HOVER ---
                elif fn_name == "hover_at":
                    x = self.denormalize_x(args.get("x", 0))
                    y = self.denormalize_y(args.get("y", 0))
                    await self.page.mouse.move(x, y)

                elif fn_name == "drag_and_drop":
                    start_x = self.denormalize_x(args.get("x", 0))
                    start_y = self.denormalize_y(args.get("y", 0))
                    end_x = self.denormalize_x(args.get("destination_x", 0))
                    end_y = self.denormalize_y(args.get("destination_y", 0))
                    
                    await self.page.mouse.move(start_x, start_y)
                    await self.page.mouse.down()
                    await self.page.mouse.move(end_x, end_y)
                    await self.page.mouse.up()

                # --- KEYBOARD ---
                elif fn_name == "key_combination":
                    key_comb = args.get("keys", "")
                    await self.page.keyboard.press(key_comb)

                # --- SCROLLING ---
                elif fn_name == "scroll_document" or fn_name == "scroll_at":
                    magnitude = args.get("magnitude", 800)
                    direction = args.get("direction", "down")
                    
                    if fn_name == "scroll_at":
                        x = self.denormalize_x(args.get("x", 0))
                        y = self.denormalize_y(args.get("y", 0))
                        await self.page.mouse.move(x, y)

                    dx, dy = 0, 0
                    if direction == "down": dy = magnitude
                    elif direction == "up": dy = -magnitude
                    elif direction == "right": dx = magnitude
                    elif direction == "left": dx = -magnitude
                    
                    await self.page.mouse.wheel(dx, dy)
                    self.action_history.append({"type": "scroll", "direction": direction, "magnitude": magnitude, "timestamp": datetime.now().isoformat()})

                else:
                    logger.warning(f"Fonction non implémentée: {fn_name}")

                # Attendre que l'UI se stabilise
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Erreur exécution {fn_name}: {e}")
                result_data = {"error": str(e)}

            results.append((call_id, fn_name, result_data))
        
        return results
    
    async def get_function_responses(self, results):
        """
        Prépare les réponses pour Gemini avec le screenshot actuel.
        
        Args:
            results: Liste des résultats d'exécution
            
        Returns:
            Tuple (function_responses, screenshot_bytes)
        """
        # Screenshot en PNG (requis par Computer Use)
        screenshot_bytes = await self.page.screenshot(type="png")
        current_url = self.page.url
        
        function_responses = []
        for call_id, name, result in results:
            response_data = {"url": current_url}
            response_data.update(result)
            
            # Construire la réponse avec le screenshot
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    id=call_id,
                    response=response_data,
                    parts=[types.FunctionResponsePart(
                        inline_data=types.FunctionResponseBlob(
                            mime_type="image/png",
                            data=screenshot_bytes
                        )
                    )]
                )
            )
        
        return function_responses, screenshot_bytes
    
    def _extract_search_query(self, prompt: str) -> str:
        """
        Extrait le texte de recherche du prompt de l'utilisateur.
        Exemples:
        - "va sur Amazon et cherche une manette PS5" -> "manette PS5"
        - "cherche une manette de ps5" -> "manette de ps5"
        - "trouve un casque bluetooth" -> "casque bluetooth"
        """
        prompt_lower = prompt.lower()
        original_prompt = prompt
        
        # Mots-clés qui indiquent une recherche
        search_keywords = ["cherche", "recherche", "trouve", "find", "search", "rechercher"]
        
        # Chercher après les mots-clés de recherche
        for keyword in search_keywords:
            if keyword in prompt_lower:
                # Trouver la position du mot-clé dans le prompt original (pas lowercase)
                idx_lower = prompt_lower.find(keyword)
                # Extraire le texte après le mot-clé (en gardant la casse originale)
                after_keyword = original_prompt[idx_lower + len(keyword):].strip()
                
                # Nettoyer (enlever "sur Amazon", "sur le site", etc. mais seulement au début)
                after_keyword_lower = after_keyword.lower()
                if after_keyword_lower.startswith("sur amazon"):
                    after_keyword = after_keyword[len("sur amazon"):].strip()
                elif after_keyword_lower.startswith("sur le site"):
                    after_keyword = after_keyword[len("sur le site"):].strip()
                elif after_keyword_lower.startswith("sur"):
                    # Vérifier que ce n'est pas "sur" dans "manette de ps5"
                    words = after_keyword.split()
                    if words and words[0].lower() == "sur":
                        after_keyword = " ".join(words[1:])
                
                # Enlever les articles en début
                articles = ["une", "un", "le", "la", "les", "des", "du", "de la"]
                words = after_keyword.split()
                if words and words[0].lower() in articles:
                    after_keyword = " ".join(words[1:])
                
                if after_keyword:
                    return after_keyword.strip()
        
        # Si pas de mot-clé de recherche, chercher "Amazon" et extraire ce qui suit
        if "amazon" in prompt_lower:
            # Chercher ce qui suit "amazon" et "et" ou "puis"
            if "et" in prompt_lower:
                # Trouver "et" après "amazon"
                amazon_idx = prompt_lower.find("amazon")
                et_idx = prompt_lower.find("et", amazon_idx)
                if et_idx > amazon_idx:
                    search_part = original_prompt[et_idx + 2:].strip()  # +2 pour "et"
                    # Nettoyer
                    search_part_lower = search_part.lower()
                    if search_part_lower.startswith("cherche"):
                        search_part = search_part[7:].strip()
                    elif search_part_lower.startswith("trouve"):
                        search_part = search_part[6:].strip()
                    elif search_part_lower.startswith("recherche"):
                        search_part = search_part[9:].strip()
                    
                    # Enlever les articles
                    articles = ["une", "un", "le", "la", "les", "des", "du", "de la"]
                    words = search_part.split()
                    if words and words[0].lower() in articles:
                        search_part = " ".join(words[1:])
                    
                    if search_part:
                        return search_part.strip()
        
        # Par défaut, retourner le prompt entier si rien n'est trouvé
        return original_prompt.strip()
    
    async def _detect_current_state(self) -> dict:
        """
        Détecte l'état actuel de la page pour éviter les actions redondantes.
        """
        state = {
            "search_text": "",
            "is_search_results": False,
            "product_selected": False,
            "in_cart": False
        }
        
        try:
            if not self.page:
                return state
            
            current_url = self.page.url
            
            # Vérifier si on est sur une page de résultats de recherche
            state["is_search_results"] = "s?k=" in current_url or "/search" in current_url.lower() or "search" in current_url.lower()
            
            # Vérifier si on est sur une page produit
            state["product_selected"] = "/dp/" in current_url or "/gp/product/" in current_url or "/product/" in current_url.lower()
            
            # Vérifier si on est dans le panier
            state["in_cart"] = "cart" in current_url.lower() or "panier" in current_url.lower()
            
            # Vérifier aussi si un produit a été ajouté au panier (via l'historique des actions)
            if not state["in_cart"]:
                for action in self.action_history:
                    if action.get("type") == "add_to_cart":
                        state["in_cart"] = True
                        break
            
            # Vérifier si un message de confirmation d'ajout au panier est présent
            if not state["in_cart"]:
                try:
                    # Chercher des messages de confirmation
                    confirmation_texts = [
                        "Added to cart",
                        "Ajouté au panier",
                        "Added to basket",
                        "Ajouté au panier",
                        "Item added to cart",
                        "Article ajouté au panier"
                    ]
                    
                    page_text = await self.page.evaluate("() => document.body.innerText")
                    page_text_lower = page_text.lower()
                    
                    for confirmation_text in confirmation_texts:
                        if confirmation_text.lower() in page_text_lower:
                            state["in_cart"] = True
                            break
                except:
                    pass
            
            # Essayer de récupérer le texte de la barre de recherche
            try:
                search_selectors = [
                    '#twotabsearchtextbox',
                    'input[name="field-keywords"]',
                    'input[type="text"][name*="search"]',
                    'input[type="text"][id*="search"]'
                ]
                
                for selector in search_selectors:
                    try:
                        search_bar = await self.page.query_selector(selector)
                        if search_bar:
                            search_value = await search_bar.get_attribute("value")
                            if search_value:
                                state["search_text"] = search_value
                                break
                    except:
                        continue
            except:
                pass
            
            # Vérifier dans l'historique des actions si un produit a été sélectionné
            if not state["product_selected"]:
                for action in self.action_history:
                    if action.get("type") == "product_click":
                        state["product_selected"] = True
                        break
            
        except Exception as e:
            logger.debug(f"Erreur détection état: {e}")
        
        return state
    
    async def _create_action_plan(self, prompt: str) -> list:
        """
        Crée un plan d'action basé sur la demande de l'utilisateur.
        Utilise Gemini pour analyser la demande et créer un plan structuré.
        """
        try:
            plan_prompt = f"""Analyse cette demande et crée un plan d'action étape par étape pour l'accomplir.

DEMANDE: {prompt}

Réponds UNIQUEMENT avec un JSON valide de cette forme:
{{
    "steps": [
        {{"step": 1, "action": "navigate", "url": "https://...", "description": "..."}},
        {{"step": 2, "action": "click", "target": "bouton de recherche", "description": "..."}},
        {{"step": 3, "action": "type", "text": "...", "description": "..."}},
        {{"step": 4, "action": "click", "target": "...", "description": "..."}}
    ]
}}

Actions possibles:
- navigate: Aller sur une URL
- click: Cliquer sur un élément (bouton, lien, etc.)
- type: Taper du texte
- scroll: Faire défiler la page
- wait: Attendre (pour chargement)
- verify: Vérifier que quelque chose est présent

Réponds UNIQUEMENT le JSON, rien d'autre."""
            
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=[{"role": "user", "parts": [{"text": plan_prompt}]}]
            )
            
            response_text = response.text if hasattr(response, 'text') else str(response)
            # Extraire le JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            plan = json.loads(response_text)
            logger.info(f"📋 Plan créé: {len(plan.get('steps', []))} étapes")
            return plan.get('steps', [])
        except Exception as e:
            logger.error(f"Erreur création plan: {e}")
            # Plan par défaut simple
            return [{"step": 1, "action": "navigate", "url": "https://www.google.com", "description": "Navigation initiale"}]
    
    async def run_task(self, prompt: str, max_turns: int = 30) -> str:
        """
        Exécute une tâche de navigation web avec un plan d'action intelligent.
        
        Args:
            prompt: La tâche à accomplir (ex: "Va sur Epic Games et installe le launcher")
            max_turns: Nombre maximum de tours de conversation
            
        Returns:
            Réponse finale de l'agent
        """
        logger.info(f"[START] WebAgent démarré. Objectif: {prompt}")
        final_response = "Tâche terminée."
        
        # Réinitialiser l'état pour une nouvelle tâche
        self.cookie_popup_clicked = False
        self.search_bar_clicked = False
        self.search_performed = False
        self.search_text = ""
        self.action_history = []
        self.last_screenshot_hash = None
        self.gemini_vision_calls = 0
        self.search_query = ""
        
        # S'assurer que le navigateur est démarré dans la MÊME boucle asyncio
        if not self.is_running or not self.page:
            logger.info("Démarrage du navigateur...")
            await self.start(headless=True)
        
        # Vérifier que le navigateur est bien initialisé
        if not self.page:
            raise RuntimeError("Le navigateur n'a pas pu être initialisé correctement")
        
        try:
            # Configuration Computer Use - Vérifier si disponible
            config = None
            computer_use_available = False
            
            try:
                # Vérifier si Computer Use est disponible - Essayer plusieurs approches
                computer_use_available = False
                
                # Approche 1: Vérifier les attributs directement
                try:
                    if hasattr(types, 'ComputerUse') and hasattr(types, 'Environment'):
                        computer_use_tool = types.Tool(
                            computer_use=types.ComputerUse(
                                environment=types.Environment.ENVIRONMENT_BROWSER
                            )
                        )
                        computer_use_available = True
                        if hasattr(types, 'GenerateContentConfig'):
                            if hasattr(types, 'ThinkingConfig'):
                                config = types.GenerateContentConfig(
                                    tools=[computer_use_tool],
                                    thinking_config=types.ThinkingConfig(include_thoughts=True)
                                )
                            else:
                                config = types.GenerateContentConfig(tools=[computer_use_tool])
                        logger.info("✅ Computer Use API disponible")
                except Exception as e1:
                    logger.debug(f"Approche 1 échouée: {e1}")
                    
                    # Approche 2: Essayer avec getattr pour les noms alternatifs
                    try:
                        ComputerUse = getattr(types, 'ComputerUse', None)
                        Environment = getattr(types, 'Environment', None)
                        
                        if ComputerUse and Environment:
                            env_browser = getattr(Environment, 'ENVIRONMENT_BROWSER', None)
                            if env_browser:
                                computer_use_tool = types.Tool(
                                    computer_use=ComputerUse(environment=env_browser)
                                )
                                computer_use_available = True
                                if hasattr(types, 'GenerateContentConfig'):
                                    config = types.GenerateContentConfig(tools=[computer_use_tool])
                                logger.info("✅ Computer Use API disponible (méthode alternative)")
                    except Exception as e2:
                        logger.debug(f"Approche 2 échouée: {e2}")
                        
                        # Approche 3: Essayer d'importer directement depuis genai.types
                        try:
                            from google.genai.types import ComputerUse, Environment
                            computer_use_tool = types.Tool(
                                computer_use=ComputerUse(
                                    environment=Environment.ENVIRONMENT_BROWSER
                                )
                            )
                            computer_use_available = True
                            if hasattr(types, 'GenerateContentConfig'):
                                config = types.GenerateContentConfig(tools=[computer_use_tool])
                            logger.info("✅ Computer Use API disponible (import direct)")
                        except (ImportError, AttributeError) as e3:
                            logger.debug(f"Approche 3 échouée: {e3}")
                
                if not computer_use_available:
                    # Vérifier la version de google-genai installée
                    try:
                        import google.genai
                        version = getattr(google.genai, '__version__', 'inconnue')
                        logger.warning(f"⚠️ Computer Use API non disponible (google-genai version: {version})")
                        logger.warning("💡 Pour activer Computer Use, mettez à jour google-genai: pip install --upgrade google-genai")
                    except:
                        logger.warning("⚠️ Computer Use API non disponible - utilisation du mode Gemini Vision standard")
                        logger.warning("💡 Pour activer Computer Use, installez/mettez à jour google-genai: pip install --upgrade google-genai")
            except Exception as e:
                logger.error(f"Erreur vérification Computer Use: {e}")
                computer_use_available = False
            
            
            # Créer un plan d'action basé sur la demande
            action_plan = await self._create_action_plan(prompt)
            logger.info(f"📋 Plan d'action créé: {len(action_plan)} étapes")
            
            # Naviguer vers la première URL du plan ou Google par défaut
            initial_url = "https://www.google.com"
            if action_plan and action_plan[0].get("action") == "navigate":
                initial_url = action_plan[0].get("url", initial_url)
            
            try:
                await self.page.goto(initial_url, wait_until='domcontentloaded', timeout=30000)
                self.current_url = self.page.url
                initial_screenshot = await self.page.screenshot(type="png")
                self._send_to_gui(initial_screenshot, f"✅ Navigation vers {initial_url}")
            except Exception as e:
                logger.error(f"Erreur navigation: {e}")
                initial_screenshot = await self.page.screenshot(type="png")
                self._send_to_gui(initial_screenshot, "[Web Agent] Initialized")
            
            # Historique de conversation avec instructions claires
            # IMPORTANT: Expliquer à Gemini qu'il a un navigateur à sa disposition
            system_prompt = f"""Tu es un agent web autonome avec un navigateur Firefox headless ACTIF et FONCTIONNEL.

⚠️ CRITIQUE : Tu as ACCÈS COMPLET à un navigateur web via Playwright. Le navigateur est OUVERT et prêt.

OBJECTIF PRÉCIS: {prompt}

⚠️⚠️⚠️ IMPORTANT - TU DOIS UTILISER LES FUNCTION CALLS ⚠️⚠️⚠️
Tu as accès à Computer Use API avec les function calls suivants:
- click_at(x, y): Cliquer à une coordonnée
- type_text_at(x, y, text): Taper du texte à une coordonnée
- scroll_document(delta_x, delta_y): Faire défiler la page
- navigate(url): Naviguer vers une URL

TU DOIS ABSOLUMENT UTILISER CES FUNCTION CALLS pour interagir avec le navigateur.
Ne réponds PAS juste avec du texte - UTILISE LES FUNCTION CALLS !

INSTRUCTIONS:
1. Analyse le screenshot que je t'envoie
2. Détermine la prochaine action à effectuer pour accomplir l'objectif
3. ⚠️ UTILISE LES FUNCTION CALLS (click_at, type_text_at, navigate, etc.) - C'EST OBLIGATOIRE
4. Continue étape par étape jusqu'à ce que l'objectif soit accompli

EXEMPLE:
- Si l'objectif est "mets dans mon panier Amazon une manette de ps5":
  1. Utilise navigate("https://www.amazon.fr")
  2. Utilise click_at(x, y) pour cliquer sur la barre de recherche
  3. Utilise type_text_at(x, y, "manette ps5") pour taper
  4. Utilise click_at(x, y) pour cliquer sur le bouton de recherche
  5. Utilise click_at(x, y) pour cliquer sur le meilleur produit
  6. Utilise click_at(x, y) pour cliquer sur "Ajouter au panier"

IMPORTANT: 
- Ne dis JAMAIS que tu ne peux pas accéder aux sites web
- Utilise TOUJOURS les function calls - ne réponds pas juste avec du texte
- Utilise le texte EXACT de l'objectif pour les recherches
- Continue jusqu'à ce que la tâche soit complètement terminée"""

            try:
                if hasattr(types, 'Content') and hasattr(types, 'Part'):
                    chat_history = [
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(text=system_prompt),
                                types.Part.from_bytes(data=initial_screenshot, mime_type="image/png")
                            ]
                        )
                    ]
                else:
                    # Format alternatif si types.Content/Part n'existent pas
                    logger.warning("Types.Content/Part non disponible, utilisation du format dict")
                    chat_history = [{
                        "role": "user",
                        "parts": [
                            {"text": system_prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": base64.b64encode(initial_screenshot).decode('utf-8')
                                }
                            }
                        ]
                    }]
            except Exception as e:
                logger.error(f"Erreur initialisation chat_history: {e}")
                # Format minimal
                chat_history = [{
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                }]
            
            # Boucle principale : Exécuter la tâche étape par étape avec Gemini (style ADA)
            for turn in range(max_turns):
                logger.info(f"\n--- Tour {turn + 1}/{max_turns} ---")
                
                # Utiliser Gemini Computer Use pour analyser et agir (style ADA)
                if computer_use_available and config:
                    try:
                        # Prendre un screenshot de l'état actuel
                        screenshot = await self.page.screenshot(type="png")
                        current_url = self.page.url
                        
                        # Ajouter le screenshot au chat_history (style ADA)
                        if hasattr(types, 'Content') and hasattr(types, 'Part'):
                            chat_history.append(
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part(text=f"Continue à accomplir cette tâche: {prompt}. URL actuelle: {current_url}"),
                                        types.Part.from_bytes(data=screenshot, mime_type="image/png")
                                    ]
                                )
                            )
                        
                        # Appel à Computer Use API (style ADA)
                        try:
                            response = await self.client.aio.models.generate_content(
                                model=MODEL_ID,
                                contents=chat_history,
                                config=config
                            )
                        except Exception as api_error:
                            logger.error(f"[COMPUTER_USE] Erreur API: {api_error}")
                            logger.exception(api_error)
                            break
                        
                        # Vérifier la réponse (style ADA)
                        if not response.candidates:
                            logger.warning("[WARN] Le modèle n'a retourné aucun contenu.")
                            break
                        
                        candidate = response.candidates[0]
                        model_content = candidate.content
                        chat_history.append(model_content)
                        
                        # Traiter les thoughts et tool calls (style ADA)
                        has_tool_use = False
                        thought_text = ""
                        agent_text = ""
                        
                        for part in model_content.parts:
                            if hasattr(part, 'thought') and part.thought:
                                thought_content = part.thought if isinstance(part.thought, str) else getattr(part.thought, 'text', str(part.thought))
                                logger.info(f"[THOUGHT] {thought_content}")
                                thought_text += f"[Thoughts] {thought_content}\n"
                            elif hasattr(part, 'text') and part.text:
                                logger.info(f"[AGENT] {part.text}")
                                thought_text += f"[Agent] {part.text}\n"
                                agent_text = part.text
                            if hasattr(part, 'function_call') and part.function_call:
                                has_tool_use = True
                        
                        if agent_text:
                            final_response = agent_text
                        
                        # Extraire les function calls (style ADA - méthode directe)
                        function_calls = [part.function_call for part in model_content.parts if hasattr(part, 'function_call') and part.function_call]
                        
                        if not function_calls:
                            if not has_tool_use:
                                logger.info("[DONE] Tâche terminée.")
                                screenshot = await self.page.screenshot(type="png")
                                self._send_to_gui(screenshot, "✅ Tâche terminée")
                                break
                            else:
                                logger.info("...Réflexion...")
                                continue
                        
                        # Exécuter les actions (style ADA)
                        results = await self.execute_function_calls(function_calls)
                        
                        # Capturer le nouvel état (style ADA)
                        logger.info("[SNAP] Capture du nouvel état...")
                        function_responses, screenshot_bytes = await self.get_function_responses(results)
                        
                        # Mettre à jour le GUI
                        actions_log = ", ".join([r[1] for r in results])
                        self._send_to_gui(screenshot_bytes, f"Exécuté: {actions_log}")
                        
                        # Envoyer les réponses à Gemini (style ADA)
                        response_parts = [types.Part(function_response=fr) for fr in function_responses]
                        chat_history.append(types.Content(role="user", parts=response_parts))
                        
                    except Exception as e:
                        logger.error(f"Erreur Computer Use: {e}")
                        logger.exception(e)
                        break
                
                # Si Computer Use n'est pas disponible, arrêter (pas de fallback - Computer Use doit fonctionner)
                if not computer_use_available:
                    logger.error("❌ Computer Use API non disponible - arrêt")
                    break
                
                # Pause entre les tours
                await asyncio.sleep(0.5)
            
            # Fin de la boucle principale
            logger.info("[CLOSE] Agent terminé.")
            return final_response
            
        except Exception as e:
            logger.exception(f"Erreur dans run_task: {e}")
            raise


# ============================================================================
# INSTANCE SINGLETON
# ============================================================================

_navigator: Optional[WebNavigator] = None

def get_navigator(gui_queue: Optional[queue.Queue] = None) -> WebNavigator:
    """Retourne l'instance singleton du WebNavigator"""
    global _navigator
    try:
        if _navigator is None:
            _navigator = WebNavigator(gui_queue=gui_queue)
        elif gui_queue and _navigator.gui_queue != gui_queue:
            _navigator.gui_queue = gui_queue
        return _navigator
    except Exception as e:
        logger.error(f"Erreur lors de la création du WebNavigator: {e}")
        raise


# ============================================================================
# OUTIL POUR CYPHER
# ============================================================================

def web_navigator_tool(action: str, **kwargs) -> str:
    """
    Outil principal pour la navigation web autonome de Cypher.
    
    Args:
        action: L'action à effectuer
        **kwargs: Arguments supplémentaires selon l'action
        
    Returns:
        Résultat JSON de l'action
    """
    result = {"success": False, "action": action}
    
    try:
        navigator = get_navigator()
        
        # Fonction helper pour exécuter du code async de manière sûre
        def run_async(coro):
            """Exécute une coroutine de manière sûre - CRITIQUE: recrée le navigateur dans le thread"""
            import threading
            import concurrent.futures
            
            # CRITIQUE: Les objets Playwright ne peuvent PAS être partagés entre boucles asyncio
            # Il faut recréer TOUT le navigateur dans la nouvelle boucle
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    # Recréer le navigateur dans cette boucle
                    temp_navigator = WebNavigator(gui_queue=navigator.gui_queue)
                    
                    # Exécuter la coroutine mais en remplaçant self par temp_navigator
                    # Pour run_task, on doit extraire les paramètres
                    if 'run_task' in str(coro):
                        # C'est run_task - extraire prompt et max_turns
                        # On va utiliser une approche différente : wrapper
                        async def wrapper():
                            await temp_navigator.start(headless=True)
                            # Extraire les args de la coroutine originale
                            # Pour l'instant, on va passer par une méthode différente
                            return await temp_navigator.run_task(
                                prompt if 'prompt' in locals() else kwargs.get('prompt', ''),
                                max_turns if 'max_turns' in locals() else kwargs.get('max_turns', 20)
                            )
                        return new_loop.run_until_complete(wrapper())
                    else:
                        # Autre coroutine - recréer le navigateur d'abord
                        async def wrapper():
                            await temp_navigator.start(headless=True)
                            # Remplacer navigator par temp_navigator dans la coroutine
                            # C'est complexe, donc on va utiliser une approche plus simple
                            return await coro
                        return new_loop.run_until_complete(wrapper())
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result(timeout=300)
        
        if action == "navigate":
            url = kwargs.get("url", "")
            if not url:
                result["error"] = "URL requise"
            else:
                # Recréer le navigateur dans un thread avec sa propre boucle
                def navigate_in_thread():
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            temp_navigator = WebNavigator(gui_queue=navigator.gui_queue)
                            
                            async def execute():
                                await temp_navigator.start(headless=True)
                                try:
                                    await temp_navigator.page.goto(url, wait_until='networkidle', timeout=30000)
                                    temp_navigator.current_url = temp_navigator.page.url
                                    return temp_navigator.current_url
                                finally:
                                    await temp_navigator.stop()
                            
                            return new_loop.run_until_complete(execute())
                        finally:
                            new_loop.close()
                    
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        return future.result(timeout=60)
                
                final_url = navigate_in_thread()
                result["success"] = True
                result["url"] = final_url
        
        elif action == "execute_task":
            prompt = kwargs.get("prompt", "")
            max_turns = kwargs.get("max_turns", 20)
            
            if not prompt:
                result["error"] = "Prompt requis"
            else:
                # CRITIQUE: Recréer le navigateur dans un thread avec sa propre boucle asyncio
                def run_task_in_thread():
                    import threading
                    import concurrent.futures
                    
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            # Créer un NOUVEAU navigateur dans cette boucle
                            temp_navigator = WebNavigator(gui_queue=navigator.gui_queue)
                            
                            async def execute():
                                await temp_navigator.start(headless=True)
                                try:
                                    return await temp_navigator.run_task(prompt, max_turns)
                                except Exception as e:
                                    logger.error(f"Erreur dans execute: {e}")
                                    raise
                                finally:
                                    try:
                                        await temp_navigator.stop()
                                    except Exception as e:
                                        logger.error(f"Erreur à l'arrêt du navigateur: {e}")
                            
                            result = new_loop.run_until_complete(execute())
                            # Attendre que toutes les tâches soient terminées avant de fermer
                            pending = asyncio.all_tasks(new_loop)
                            if pending:
                                new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                            return result
                        except Exception as e:
                            logger.error(f"Erreur dans run_in_thread: {e}")
                            raise
                        finally:
                            # S'assurer que toutes les tâches sont terminées avant de fermer
                            try:
                                pending = asyncio.all_tasks(new_loop)
                                for task in pending:
                                    task.cancel()
                                if pending:
                                    new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                            except:
                                pass
                            new_loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        return future.result(timeout=300)
                
                # Exécuter la tâche
                final_response = run_task_in_thread()
                result["success"] = True
                result["status"] = "completed"
                
                # Formater le message de succès de manière explicite
                if final_response and isinstance(final_response, str):
                    # Si le message contient déjà un succès, on le garde tel quel
                    if any(word in final_response.lower() for word in ["ajouté", "ajout", "succès", "terminé", "complété", "réussi"]):
                        result["message"] = final_response
                    else:
                        result["message"] = f"✅ Tâche terminée avec succès: {final_response}"
                else:
                    result["message"] = "✅ Tâche exécutée avec succès"
                
                result["response"] = final_response
                # Note: action_history sera dans temp_navigator, on ne peut pas le récupérer facilement
                result["action_history"] = []
        
        elif action == "stop":
            if navigator.is_running:
                run_async(navigator.stop())
                result["success"] = True
            else:
                result["message"] = "Navigateur déjà arrêté"
        
        elif action == "get_current_url":
            if navigator.is_running:
                result["success"] = True
                result["url"] = navigator.current_url
            else:
                result["error"] = "Navigateur non démarré"
        
        else:
            result["error"] = f"Action inconnue: {action}"
            result["available_actions"] = ["navigate", "execute_task", "stop", "get_current_url"]
    
    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"Erreur web_navigator_tool: {e}")
    
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================================
# DÉCLARATION DU TOOL POUR GEMINI
# ============================================================================

WEB_NAVIGATOR_TOOL_DECLARATION = {
    "name": "web_navigator",
    "description": """Outil de navigation web autonome utilisant Gemini Computer Use API.
    
Permet à Cypher de naviguer sur le web de manière autonome en utilisant l'API native Computer Use de Gemini.
L'agent peut voir, comprendre et interagir avec les pages web de manière naturelle.

⚠️ IMPORTANT: Le navigateur est invisible (headless). L'utilisateur voit ce que l'IA voit via la fenêtre WEB_AGENT_VIEW.""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": """Action à effectuer:
                
- navigate: Navigue vers une URL (params: url)
- execute_task: Exécute une tâche complexe avec Gemini Computer Use (params: prompt, max_turns)
- stop: Arrête le navigateur
- get_current_url: Récupère l'URL actuelle""",
                "enum": ["navigate", "execute_task", "stop", "get_current_url"]
            },
            "url": {
                "type": "string",
                "description": "URL à visiter (pour action=navigate)"
            },
            "prompt": {
                "type": "string",
                "description": """Tâche à accomplir (pour action=execute_task).
                
Exemples:
- "Va sur Amazon et cherche un casque gaming"
- "Recherche 'Python tutorial' sur Google et ouvre le premier résultat"
- "Va sur YouTube et cherche des vidéos sur l'IA"
                
L'agent utilisera Gemini Computer Use pour comprendre et interagir avec les pages automatiquement."""
            },
            "max_turns": {
                "type": "integer",
                "description": "Nombre maximum de tours de conversation (défaut: 20)"
            }
        },
        "required": ["action"]
    }
}
