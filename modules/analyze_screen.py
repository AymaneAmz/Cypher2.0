# -*- coding: utf-8 -*-
"""
Screen Analyzer - Module de vision complète pour Cypher
Permet l'analyse approfondie de l'écran du PC: capture, OCR, détection UI, 
reconnaissance d'applications, analyse contextuelle.
"""

import os
import sys
import json
import base64
import time
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Tuple
from io import BytesIO
from datetime import datetime

# Imports pour capture d'écran et traitement d'image
try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    print("⚠️ [SCREEN] mss non installé - pip install mss")

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ [SCREEN] Pillow non installé - pip install Pillow")

try:
    import pytesseract
    # Configuration Windows - ajuster le chemin si nécessaire
    if sys.platform == "win32":
        tesseract_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.getenv("USERNAME", "")),
        ]
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ [SCREEN] pytesseract non installé - pip install pytesseract")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("⚠️ [SCREEN] pyautogui non installé - pip install pyautogui")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import win32gui
    import win32process
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("⚠️ [SCREEN] pywin32 non installé - pip install pywin32")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ [SCREEN] opencv-python non installé - pip install opencv-python (pour détection visuelle avancée)")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    print("⚠️ [SCREEN] easyocr non installé - pip install easyocr (OCR amélioré optionnel)")

try:
    from google import genai
    from dotenv import load_dotenv
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_VISION_AVAILABLE = bool(GEMINI_API_KEY)
    if GEMINI_VISION_AVAILABLE:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except ImportError:
    GEMINI_VISION_AVAILABLE = False
    gemini_client = None
    print("⚠️ [SCREEN] google-genai non installé - pip install google-genai (pour analyse vision IA)")

# Import pour hash d'images (cache)
try:
    import hashlib
    HASH_AVAILABLE = True
except ImportError:
    HASH_AVAILABLE = False


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class WindowInfo:
    """Information sur une fenêtre"""
    handle: int
    title: str
    class_name: str
    process_name: str
    process_id: int
    rect: Dict[str, int]  # left, top, right, bottom
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    is_foreground: bool

@dataclass
class ScreenRegion:
    """Région de l'écran"""
    left: int
    top: int
    width: int
    height: int
    monitor_index: int = 0

@dataclass
class TextBlock:
    """Bloc de texte détecté par OCR"""
    text: str
    confidence: float
    bbox: Dict[str, int]  # x, y, width, height
    
@dataclass
class UIElement:
    """Élément d'interface détecté"""
    element_type: str  # button, input, link, icon, image, text
    text: Optional[str]
    bbox: Dict[str, int]
    confidence: float
    
@dataclass
class ColorInfo:
    """Information sur une couleur"""
    hex: str
    rgb: Tuple[int, int, int]
    name: str
    percentage: float

@dataclass
class ScreenAnalysis:
    """Résultat complet d'analyse d'écran"""
    timestamp: str
    monitor_info: Dict[str, Any]
    active_window: Optional[WindowInfo]
    visible_windows: List[WindowInfo]
    extracted_text: str
    text_blocks: List[TextBlock]
    ui_elements: List[UIElement]
    dominant_colors: List[ColorInfo]
    detected_apps: List[str]
    context_summary: str
    screenshot_base64: Optional[str]


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class ScreenAnalyzer:
    """
    Analyseur d'écran complet pour Cypher.
    Fournit une vision détaillée du PC comparable à la vue humaine.
    """
    
    # Couleurs nommées communes
    COLOR_NAMES = {
        (255, 255, 255): "blanc",
        (0, 0, 0): "noir",
        (255, 0, 0): "rouge",
        (0, 255, 0): "vert lime",
        (0, 0, 255): "bleu",
        (255, 255, 0): "jaune",
        (255, 0, 255): "magenta",
        (0, 255, 255): "cyan",
        (128, 128, 128): "gris",
        (192, 192, 192): "argent",
        (128, 0, 0): "marron",
        (0, 128, 0): "vert",
        (0, 0, 128): "bleu marine",
        (128, 128, 0): "olive",
        (128, 0, 128): "violet",
        (0, 128, 128): "sarcelle",
        (255, 165, 0): "orange",
        (255, 192, 203): "rose",
    }
    
    # Applications connues (nom du processus -> nom lisible)
    KNOWN_APPS = {
        "chrome.exe": "Google Chrome",
        "firefox.exe": "Mozilla Firefox",
        "msedge.exe": "Microsoft Edge",
        "brave.exe": "Brave Browser",
        "opera.exe": "Opera",
        "code.exe": "Visual Studio Code",
        "devenv.exe": "Visual Studio",
        "pycharm64.exe": "PyCharm",
        "idea64.exe": "IntelliJ IDEA",
        "sublime_text.exe": "Sublime Text",
        "notepad++.exe": "Notepad++",
        "notepad.exe": "Bloc-notes",
        "explorer.exe": "Explorateur Windows",
        "spotify.exe": "Spotify",
        "discord.exe": "Discord",
        "slack.exe": "Slack",
        "teams.exe": "Microsoft Teams",
        "zoom.exe": "Zoom",
        "WINWORD.EXE": "Microsoft Word",
        "EXCEL.EXE": "Microsoft Excel",
        "POWERPNT.EXE": "Microsoft PowerPoint",
        "OUTLOOK.EXE": "Microsoft Outlook",
        "ONENOTE.EXE": "Microsoft OneNote",
        "Acrobat.exe": "Adobe Acrobat",
        "Photoshop.exe": "Adobe Photoshop",
        "AfterFX.exe": "Adobe After Effects",
        "Premiere Pro.exe": "Adobe Premiere Pro",
        "vlc.exe": "VLC Media Player",
        "wmplayer.exe": "Windows Media Player",
        "iTunes.exe": "iTunes",
        "Steam.exe": "Steam",
        "EpicGamesLauncher.exe": "Epic Games",
        "Battle.net.exe": "Battle.net",
        "cmd.exe": "Invite de commandes",
        "powershell.exe": "PowerShell",
        "WindowsTerminal.exe": "Windows Terminal",
        "python.exe": "Python",
        "pythonw.exe": "Python",
        "node.exe": "Node.js",
        "Calculator.exe": "Calculatrice",
        "mspaint.exe": "Paint",
        "SnippingTool.exe": "Outil Capture",
        "Taskmgr.exe": "Gestionnaire des tâches",
        "SystemSettings.exe": "Paramètres Windows",
        "ApplicationFrameHost.exe": "Application UWP",
    }
    
    def __init__(self):
        """Initialise l'analyseur d'écran"""
        self.last_screenshot: Optional[Image.Image] = None
        self.last_analysis: Optional[ScreenAnalysis] = None
        self._ocr_lang = "fra+eng"  # Français + Anglais par défaut
        self.sct = mss.mss() if MSS_AVAILABLE else None
        
        # Cache intelligent
        self._screenshot_cache: Dict[str, Tuple[Image.Image, float]] = {}  # hash -> (image, timestamp)
        self._cache_timeout = 2.0  # secondes
        
        # OCR amélioré (EasyOCR)
        self._easyocr_reader = None
        if EASYOCR_AVAILABLE:
            try:
                print("🔄 [SCREEN] Initialisation EasyOCR (première fois, peut prendre du temps)...")
                self._easyocr_reader = easyocr.Reader(['fr', 'en'], gpu=False)
                print("✅ [SCREEN] EasyOCR initialisé")
            except Exception as e:
                print(f"⚠️ [SCREEN] Erreur initialisation EasyOCR: {e}")
                self._easyocr_reader = None
        
    # ========================================================================
    # CAPTURE D'ÉCRAN
    # ========================================================================
    
    def capture_screen(self, monitor: int = 0, region: Optional[ScreenRegion] = None, 
                       use_cache: bool = True) -> Optional[Image.Image]:
        """
        Capture l'écran avec cache intelligent.
        
        Args:
            monitor: Index du moniteur (0=tous, 1=principal)
            region: Région spécifique à capturer
            use_cache: Utiliser le cache si disponible (< 2 secondes)
        """
        if not MSS_AVAILABLE or not self.sct:
            print("❌ [SCREEN] mss non disponible")
            return None
            
        try:
            # Générer une clé de cache
            cache_key = f"{monitor}_{region.left if region else None}_{region.top if region else None}_{region.width if region else None}_{region.height if region else None}"
            
            # Vérifier le cache
            if use_cache and cache_key in self._screenshot_cache:
                cached_img, cached_time = self._screenshot_cache[cache_key]
                if time.time() - cached_time < self._cache_timeout:
                    print(f"📸 [SCREEN] Capture (cache): {cached_img.width}x{cached_img.height}")
                    self.last_screenshot = cached_img
                    return cached_img
            
            # Capturer
            if region:
                capture_area = {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height
                }
            else:
                monitors = self.sct.monitors
                if monitor >= len(monitors):
                    monitor = 0
                capture_area = monitors[monitor]
            
            sct_img = self.sct.grab(capture_area)
            img = Image.frombytes('RGB', (sct_img.width, sct_img.height), sct_img.rgb)
            self.last_screenshot = img
            
            # Mettre en cache (limiter à 10 entrées)
            if use_cache:
                if len(self._screenshot_cache) >= 10:
                    # Supprimer la plus ancienne
                    oldest_key = min(self._screenshot_cache.keys(), 
                                   key=lambda k: self._screenshot_cache[k][1])
                    del self._screenshot_cache[oldest_key]
                self._screenshot_cache[cache_key] = (img, time.time())
            
            print(f"📸 [SCREEN] Capture: {img.width}x{img.height}")
            return img
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur capture: {e}")
            return None
    
    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
        """
        Capture une région rectangulaire spécifique de l'écran.
        
        Args:
            x, y: Position du coin supérieur gauche
            width, height: Dimensions de la région
        """
        region = ScreenRegion(left=x, top=y, width=width, height=height)
        return self.capture_screen(region=region)
    
    def capture_window(self, hwnd: int = None, title_contains: str = None) -> Optional[Image.Image]:
        """
        Capture une fenêtre spécifique.
        
        Args:
            hwnd: Handle de la fenêtre
            title_contains: Texte contenu dans le titre de la fenêtre
            
        Returns:
            Image PIL de la fenêtre
        """
        if not WIN32_AVAILABLE:
            print("❌ [SCREEN] pywin32 requis pour capture de fenêtre")
            return None
            
        try:
            if hwnd is None and title_contains:
                # Trouver la fenêtre par titre
                def callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if title_contains.lower() in title.lower():
                            results.append(h)
                    return True
                
                results = []
                win32gui.EnumWindows(callback, results)
                if results:
                    hwnd = results[0]
                    
            if hwnd is None:
                hwnd = win32gui.GetForegroundWindow()
            
            rect = win32gui.GetWindowRect(hwnd)
            region = ScreenRegion(
                left=rect[0],
                top=rect[1],
                width=rect[2] - rect[0],
                height=rect[3] - rect[1]
            )
            return self.capture_screen(region=region)
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur capture fenêtre: {e}")
            return None
    
    def capture_active_window(self) -> Optional[Image.Image]:
        """Capture la fenêtre active"""
        return self.capture_window()
    
    def get_screenshot_base64(self, image: Image.Image = None, quality: int = 85, 
                               max_size: int = 1920) -> Optional[str]:
        """
        Convertit une image en base64.
        
        Args:
            image: Image à convertir (ou dernière capture)
            quality: Qualité JPEG (1-100)
            max_size: Taille max d'un côté
            
        Returns:
            String base64 de l'image
        """
        if image is None:
            image = self.last_screenshot
        if image is None:
            return None
            
        try:
            # Redimensionner si nécessaire
            if image.width > max_size or image.height > max_size:
                ratio = min(max_size / image.width, max_size / image.height)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur base64: {e}")
            return None
    
    # ========================================================================
    # OCR - EXTRACTION DE TEXTE
    # ========================================================================
    
    def extract_text(self, image: Image.Image = None, lang: str = None, 
                     use_easyocr: bool = False) -> str:
        """
        Extrait tout le texte visible d'une image.
        
        Args:
            image: Image source (ou dernière capture)
            lang: Langue(s) OCR (ex: "fra", "eng", "fra+eng")
            use_easyocr: Utiliser EasyOCR si disponible (plus précis mais plus lent)
            
        Returns:
            Texte extrait
        """
        if image is None:
            image = self.last_screenshot
        if image is None:
            return ""
        
        # Essayer EasyOCR en premier si demandé
        if use_easyocr and self._easyocr_reader:
            try:
                img_array = np.array(image.convert('RGB'))
                results = self._easyocr_reader.readtext(img_array)
                text = '\n'.join([detection[1] for detection in results])
                text = self._clean_ocr_text(text)
                print(f"📝 [SCREEN] OCR (EasyOCR): {len(text)} caractères extraits")
                return text
            except Exception as e:
                print(f"⚠️ [SCREEN] Erreur EasyOCR, fallback Tesseract: {e}")
                # Fallback sur Tesseract
        
        if not TESSERACT_AVAILABLE:
            print("❌ [SCREEN] Tesseract non disponible")
            return ""
            
        try:
            # Prétraitement amélioré pour l'OCR
            img_processed = self._preprocess_for_ocr(image)
            
            lang = lang or self._ocr_lang
            text = pytesseract.image_to_string(img_processed, lang=lang)
            
            # Nettoyer le texte
            text = self._clean_ocr_text(text)
            print(f"📝 [SCREEN] OCR (Tesseract): {len(text)} caractères extraits")
            return text
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur OCR: {e}")
            return ""
    
    def extract_text_blocks(self, image: Image.Image = None, 
                            min_confidence: float = 60) -> List[TextBlock]:
        """
        Extrait les blocs de texte avec leur position et confiance.
        
        Args:
            image: Image source
            min_confidence: Confiance minimale (0-100)
            
        Returns:
            Liste de TextBlock
        """
        if not TESSERACT_AVAILABLE:
            return []
            
        if image is None:
            image = self.last_screenshot
        if image is None:
            return []
            
        try:
            img_processed = self._preprocess_for_ocr(image)
            data = pytesseract.image_to_data(img_processed, lang=self._ocr_lang, 
                                             output_type=pytesseract.Output.DICT)
            
            blocks = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = float(data['conf'][i])
                
                if text and conf >= min_confidence:
                    blocks.append(TextBlock(
                        text=text,
                        confidence=conf,
                        bbox={
                            'x': data['left'][i],
                            'y': data['top'][i],
                            'width': data['width'][i],
                            'height': data['height'][i]
                        }
                    ))
            
            print(f"📝 [SCREEN] {len(blocks)} blocs de texte détectés")
            return blocks
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur extraction blocs: {e}")
            return []
    
    def find_text_on_screen(self, search_text: str, image: Image.Image = None) -> List[Dict]:
        """
        Trouve toutes les occurrences d'un texte sur l'écran.
        
        Args:
            search_text: Texte à rechercher
            image: Image source
            
        Returns:
            Liste de positions trouvées
        """
        blocks = self.extract_text_blocks(image)
        results = []
        
        search_lower = search_text.lower()
        for block in blocks:
            if search_lower in block.text.lower():
                results.append({
                    'text': block.text,
                    'position': block.bbox,
                    'confidence': block.confidence
                })
        
        return results
    
    def _preprocess_for_ocr(self, image: Image.Image) -> Image.Image:
        """Prétraite une image pour améliorer l'OCR (version améliorée)"""
        try:
            # Convertir en niveaux de gris
            img = image.convert('L')
            
            # Utiliser OpenCV si disponible pour un meilleur prétraitement
            if OPENCV_AVAILABLE and NUMPY_AVAILABLE:
                img_array = np.array(img)
                
                # Binarisation adaptative (meilleure que seuil fixe)
                img_array = cv2.adaptiveThreshold(
                    img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                    cv2.THRESH_BINARY, 11, 2
                )
                
                # Dénoyautage (enlever le bruit)
                img_array = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
                
                # Améliorer le contraste
                img_array = cv2.convertScaleAbs(img_array, alpha=1.2, beta=10)
                
                img = Image.fromarray(img_array)
            else:
                # Fallback sur PIL
                # Augmenter le contraste
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.5)
                
                # Augmenter la netteté
                img = img.filter(ImageFilter.SHARPEN)
            
            # Redimensionner si trop petit
            if img.width < 1000:
                ratio = 1500 / img.width
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), 
                                Image.Resampling.LANCZOS)
            
            return img
        except Exception as e:
            print(f"⚠️ [SCREEN] Erreur prétraitement OCR: {e}")
            return image
    
    def _clean_ocr_text(self, text: str) -> str:
        """Nettoie le texte OCR"""
        # Supprimer les lignes vides multiples
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # Supprimer les espaces multiples
        text = re.sub(r' +', ' ', text)
        # Supprimer les caractères parasites courants
        text = re.sub(r'[|—_]{3,}', '', text)
        return text.strip()
    
    # ========================================================================
    # GESTION DES FENÊTRES
    # ========================================================================
    
    def get_all_windows(self, visible_only: bool = True) -> List[WindowInfo]:
        """
        Récupère toutes les fenêtres ouvertes.
        
        Args:
            visible_only: Ne retourner que les fenêtres visibles
            
        Returns:
            Liste de WindowInfo
        """
        if not WIN32_AVAILABLE:
            return []
            
        windows = []
        foreground_hwnd = win32gui.GetForegroundWindow()
        
        def enum_callback(hwnd, results):
            try:
                if visible_only and not win32gui.IsWindowVisible(hwnd):
                    return True
                    
                title = win32gui.GetWindowText(hwnd)
                if not title:  # Ignorer les fenêtres sans titre
                    return True
                
                class_name = win32gui.GetClassName(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                
                # Obtenir le processus
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process_name = ""
                if PSUTIL_AVAILABLE:
                    try:
                        process = psutil.Process(pid)
                        process_name = process.name()
                    except:
                        pass
                
                # État de la fenêtre
                placement = win32gui.GetWindowPlacement(hwnd)
                is_minimized = placement[1] == win32con.SW_SHOWMINIMIZED
                is_maximized = placement[1] == win32con.SW_SHOWMAXIMIZED
                
                window_info = WindowInfo(
                    handle=hwnd,
                    title=title,
                    class_name=class_name,
                    process_name=process_name,
                    process_id=pid,
                    rect={
                        'left': rect[0],
                        'top': rect[1],
                        'right': rect[2],
                        'bottom': rect[3]
                    },
                    is_visible=win32gui.IsWindowVisible(hwnd),
                    is_minimized=is_minimized,
                    is_maximized=is_maximized,
                    is_foreground=(hwnd == foreground_hwnd)
                )
                results.append(window_info)
                
            except Exception as e:
                pass
            return True
        
        try:
            win32gui.EnumWindows(enum_callback, windows)
            
            # Filtrer les fenêtres système/cachées
            windows = [w for w in windows if self._is_real_window(w)]
            
            print(f"🪟 [SCREEN] {len(windows)} fenêtres détectées")
            return windows
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur énumération fenêtres: {e}")
            return []
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """Récupère la fenêtre active"""
        windows = self.get_all_windows()
        for w in windows:
            if w.is_foreground:
                return w
        return None
    
    def get_window_by_title(self, title_contains: str) -> Optional[WindowInfo]:
        """Trouve une fenêtre par son titre"""
        windows = self.get_all_windows()
        for w in windows:
            if title_contains.lower() in w.title.lower():
                return w
        return None
    
    def focus_window(self, hwnd: int = None, title_contains: str = None) -> bool:
        """
        Met une fenêtre au premier plan.
        
        Args:
            hwnd: Handle de la fenêtre
            title_contains: Texte dans le titre
            
        Returns:
            True si réussi
        """
        if not WIN32_AVAILABLE:
            return False
            
        try:
            if hwnd is None and title_contains:
                window = self.get_window_by_title(title_contains)
                if window:
                    hwnd = window.handle
                    
            if hwnd:
                # Restaurer si minimisée
                placement = win32gui.GetWindowPlacement(hwnd)
                if placement[1] == win32con.SW_SHOWMINIMIZED:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                
                win32gui.SetForegroundWindow(hwnd)
                print(f"🎯 [SCREEN] Fenêtre {hwnd} au premier plan")
                return True
                
        except Exception as e:
            print(f"❌ [SCREEN] Erreur focus: {e}")
        return False
    
    def minimize_window(self, hwnd: int = None) -> bool:
        """Minimise une fenêtre"""
        if not WIN32_AVAILABLE:
            return False
        try:
            hwnd = hwnd or win32gui.GetForegroundWindow()
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return True
        except:
            return False
    
    def maximize_window(self, hwnd: int = None) -> bool:
        """Maximise une fenêtre"""
        if not WIN32_AVAILABLE:
            return False
        try:
            hwnd = hwnd or win32gui.GetForegroundWindow()
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return True
        except:
            return False
    
    def close_window(self, hwnd: int = None, title_contains: str = None) -> bool:
        """Ferme une fenêtre"""
        if not WIN32_AVAILABLE:
            return False
        try:
            if hwnd is None and title_contains:
                window = self.get_window_by_title(title_contains)
                if window:
                    hwnd = window.handle
            if hwnd:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                return True
        except:
            pass
        return False
    
    def _is_real_window(self, window: WindowInfo) -> bool:
        """Filtre les fenêtres système/cachées"""
        # Ignorer certaines classes de fenêtres système
        ignored_classes = [
            'Progman', 'WorkerW', 'Shell_TrayWnd', 'NotifyIconOverflowWindow',
            'Windows.UI.Core.CoreWindow', 'Shell_SecondaryTrayWnd'
        ]
        if window.class_name in ignored_classes:
            return False
            
        # Ignorer les fenêtres trop petites
        width = window.rect['right'] - window.rect['left']
        height = window.rect['bottom'] - window.rect['top']
        if width < 50 or height < 50:
            return False
            
        return True
    
    # ========================================================================
    # ANALYSE DES COULEURS
    # ========================================================================
    
    def analyze_colors(self, image: Image.Image = None, num_colors: int = 5) -> List[ColorInfo]:
        """
        Analyse les couleurs dominantes d'une image.
        
        Args:
            image: Image source
            num_colors: Nombre de couleurs à retourner
            
        Returns:
            Liste de ColorInfo
        """
        if image is None:
            image = self.last_screenshot
        if image is None:
            return []
            
        try:
            # Réduire l'image pour accélérer l'analyse
            img_small = image.copy()
            img_small.thumbnail((200, 200))
            
            # Quantifier les couleurs
            img_quantized = img_small.quantize(colors=num_colors * 2)
            palette = img_quantized.getpalette()[:num_colors * 2 * 3]
            
            # Compter les pixels
            pixels = list(img_quantized.getdata())
            color_counts = {}
            for pixel in pixels:
                color_counts[pixel] = color_counts.get(pixel, 0) + 1
            
            total_pixels = len(pixels)
            
            # Créer les ColorInfo
            colors = []
            sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
            
            for idx, count in sorted_colors[:num_colors]:
                r = palette[idx * 3]
                g = palette[idx * 3 + 1]
                b = palette[idx * 3 + 2]
                
                colors.append(ColorInfo(
                    hex=f"#{r:02x}{g:02x}{b:02x}",
                    rgb=(r, g, b),
                    name=self._get_color_name((r, g, b)),
                    percentage=round(count / total_pixels * 100, 1)
                ))
            
            return colors
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur analyse couleurs: {e}")
            return []
    
    def _get_color_name(self, rgb: Tuple[int, int, int]) -> str:
        """Trouve le nom de couleur le plus proche"""
        min_distance = float('inf')
        closest_name = "inconnu"
        
        for color_rgb, name in self.COLOR_NAMES.items():
            distance = sum((a - b) ** 2 for a, b in zip(rgb, color_rgb))
            if distance < min_distance:
                min_distance = distance
                closest_name = name
        
        return closest_name
    
    def get_pixel_color(self, x: int, y: int) -> Optional[ColorInfo]:
        """Obtient la couleur d'un pixel spécifique"""
        if self.last_screenshot is None:
            self.capture_screen()
        if self.last_screenshot is None:
            return None
            
        try:
            if 0 <= x < self.last_screenshot.width and 0 <= y < self.last_screenshot.height:
                r, g, b = self.last_screenshot.getpixel((x, y))[:3]
                return ColorInfo(
                    hex=f"#{r:02x}{g:02x}{b:02x}",
                    rgb=(r, g, b),
                    name=self._get_color_name((r, g, b)),
                    percentage=100
                )
        except:
            pass
        return None
    
    # ========================================================================
    # DÉTECTION D'APPLICATIONS
    # ========================================================================
    
    def detect_running_apps(self) -> List[str]:
        """
        Détecte les applications en cours d'exécution.
        
        Returns:
            Liste des noms d'applications
        """
        if not PSUTIL_AVAILABLE:
            return []
            
        apps = set()
        try:
            for proc in psutil.process_iter(['name']):
                try:
                    name = proc.info['name']
                    if name in self.KNOWN_APPS:
                        apps.add(self.KNOWN_APPS[name])
                except:
                    pass
            return sorted(list(apps))
        except:
            return []
    
    def detect_visible_apps(self) -> List[str]:
        """Détecte les applications avec fenêtres visibles"""
        windows = self.get_all_windows()
        apps = set()
        
        for w in windows:
            if w.process_name in self.KNOWN_APPS:
                apps.add(self.KNOWN_APPS[w.process_name])
            elif w.title:
                # Essayer de deviner l'app par le titre
                title_lower = w.title.lower()
                if 'chrome' in title_lower:
                    apps.add('Google Chrome')
                elif 'firefox' in title_lower:
                    apps.add('Mozilla Firefox')
                elif 'edge' in title_lower:
                    apps.add('Microsoft Edge')
                elif 'code' in title_lower or 'visual studio code' in title_lower:
                    apps.add('Visual Studio Code')
                elif 'discord' in title_lower:
                    apps.add('Discord')
                elif 'spotify' in title_lower:
                    apps.add('Spotify')
        
        return sorted(list(apps))
    
    def is_app_running(self, app_name: str) -> bool:
        """Vérifie si une application est en cours d'exécution"""
        running = self.detect_running_apps()
        return any(app_name.lower() in app.lower() for app in running)
    
    def is_app_visible(self, app_name: str) -> bool:
        """Vérifie si une application a une fenêtre visible"""
        visible = self.detect_visible_apps()
        return any(app_name.lower() in app.lower() for app in visible)
    
    # ========================================================================
    # DÉTECTION D'ÉLÉMENTS UI
    # ========================================================================
    
    def detect_ui_elements(self, image: Image.Image = None) -> List[UIElement]:
        """
        Détecte les éléments d'interface (boutons, champs, liens...).
        Utilise une combinaison d'OCR et d'analyse visuelle.
        
        Args:
            image: Image source
            
        Returns:
            Liste d'UIElement
        """
        if image is None:
            image = self.last_screenshot
        if image is None:
            return []
            
        elements = []
        
        # 1. Détecter les blocs de texte
        text_blocks = self.extract_text_blocks(image, min_confidence=70)
        
        for block in text_blocks:
            # Classifier le type d'élément basé sur le texte et la taille
            element_type = self._classify_ui_element(block)
            elements.append(UIElement(
                element_type=element_type,
                text=block.text,
                bbox=block.bbox,
                confidence=block.confidence
            ))
        
        # 2. Détecter les boutons/éléments visuels (analyse basique)
        if NUMPY_AVAILABLE and PIL_AVAILABLE:
            visual_elements = self._detect_visual_elements(image)
            elements.extend(visual_elements)
        
        print(f"🔍 [SCREEN] {len(elements)} éléments UI détectés")
        return elements
    
    def _classify_ui_element(self, block: TextBlock) -> str:
        """Classifie un bloc de texte comme type d'élément UI"""
        text = block.text.lower()
        
        # Boutons typiques
        button_keywords = ['ok', 'cancel', 'annuler', 'valider', 'submit', 'envoyer',
                          'save', 'enregistrer', 'delete', 'supprimer', 'close', 'fermer',
                          'next', 'suivant', 'previous', 'précédent', 'back', 'retour',
                          'login', 'connexion', 'logout', 'déconnexion', 'sign in', 'sign up']
        
        if any(kw in text for kw in button_keywords):
            return "button"
        
        # Liens
        if text.startswith('http') or text.startswith('www.'):
            return "link"
        
        # Champs de saisie (souvent vides ou avec placeholder)
        if len(text) < 3 or text in ['...', '___', '   ']:
            return "input"
        
        # Par défaut: texte
        return "text"
    
    def _detect_visual_elements(self, image: Image.Image) -> List[UIElement]:
        """Détecte les éléments visuels (rectangles, boutons...) avec OpenCV"""
        elements = []
        try:
            if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE:
                return elements
            
            # Convertir en numpy array
            img_array = np.array(image.convert('RGB'))
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # Détecter les contours
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filtrer les contours intéressants (rectangles approximatifs)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 500:  # Ignorer les petits éléments
                    continue
                
                # Approximation polygonale
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # Si c'est un rectangle (4 points)
                if len(approx) == 4:
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Vérifier si c'est un bouton (zone colorée avec bordure)
                    roi = img_array[y:y+h, x:x+w]
                    if roi.size > 0:
                        # Calculer la variance des couleurs (boutons ont souvent couleurs uniformes)
                        mean_color = np.mean(roi, axis=(0, 1))
                        std_color = np.std(roi, axis=(0, 1))
                        
                        # Si variance faible = zone uniforme = probablement bouton
                        if np.mean(std_color) < 30:
                            elements.append(UIElement(
                                element_type="button",
                                text=None,
                                bbox={'x': x, 'y': y, 'width': w, 'height': h},
                                confidence=0.7
                            ))
                
                # Détecter les zones de texte (zones rectangulaires horizontales)
                elif len(approx) >= 4:
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 0
                    
                    # Zones de texte sont généralement larges et basses
                    if 2.0 < aspect_ratio < 10.0 and h > 20:
                        elements.append(UIElement(
                            element_type="text_area",
                            text=None,
                            bbox={'x': x, 'y': y, 'width': w, 'height': h},
                            confidence=0.5
                        ))
            
            # Détecter les zones cliquables (cercle/icône approximatif)
            circles = cv2.HoughCircles(
                gray, cv2.HOUGH_GRADIENT, dp=1, minDist=50,
                param1=50, param2=30, minRadius=10, maxRadius=100
            )
            
            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")
                for (x, y, r) in circles:
                    elements.append(UIElement(
                        element_type="icon",
                        text=None,
                        bbox={'x': x-r, 'y': y-r, 'width': 2*r, 'height': 2*r},
                        confidence=0.6
                    ))
            
        except Exception as e:
            print(f"⚠️ [SCREEN] Erreur détection visuelle: {e}")
        
        return elements
    
    def find_element_by_text(self, text: str, image: Image.Image = None) -> Optional[UIElement]:
        """Trouve un élément UI par son texte"""
        elements = self.detect_ui_elements(image)
        text_lower = text.lower()
        
        for elem in elements:
            if elem.text and text_lower in elem.text.lower():
                return elem
        return None
    
    def click_element(self, element: UIElement) -> bool:
        """Clique sur un élément UI"""
        if not PYAUTOGUI_AVAILABLE:
            return False
            
        try:
            x = element.bbox['x'] + element.bbox['width'] // 2
            y = element.bbox['y'] + element.bbox['height'] // 2
            pyautogui.click(x, y)
            print(f"🖱️ [SCREEN] Clic sur ({x}, {y})")
            return True
        except:
            return False
    
    def scroll(self, x: int = None, y: int = None, clicks: int = 3) -> bool:
        """Fait défiler la page/fenêtre"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            if x is None or y is None:
                x, y = pyautogui.position()
            pyautogui.scroll(clicks, x=x, y=y)
            print(f"🖱️ [SCREEN] Scroll {clicks} clics à ({x}, {y})")
            return True
        except Exception as e:
            print(f"❌ [SCREEN] Erreur scroll: {e}")
            return False
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
             duration: float = 1.0) -> bool:
        """Effectue un drag & drop"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.drag(start_x, start_y, end_x - start_x, end_y - start_y, 
                          duration=duration, button='left')
            print(f"🖱️ [SCREEN] Drag de ({start_x}, {start_y}) à ({end_x}, {end_y})")
            return True
        except Exception as e:
            print(f"❌ [SCREEN] Erreur drag: {e}")
            return False
    
    def type_text(self, text: str, x: int = None, y: int = None, 
                  interval: float = 0.05) -> bool:
        """Tape du texte à la position actuelle ou à une position spécifique"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y)
                time.sleep(0.2)  # Petit délai pour s'assurer que le champ est focus
            
            pyautogui.write(text, interval=interval)
            print(f"⌨️ [SCREEN] Texte tapé: '{text[:50]}...'")
            return True
        except Exception as e:
            print(f"❌ [SCREEN] Erreur type_text: {e}")
            return False
    
    def press_key(self, *keys) -> bool:
        """Appuie sur une ou plusieurs touches (raccourcis clavier)"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.hotkey(*keys)
            print(f"⌨️ [SCREEN] Touches pressées: {'+'.join(keys)}")
            return True
        except Exception as e:
            print(f"❌ [SCREEN] Erreur press_key: {e}")
            return False
    
    def compare_screenshots(self, img1: Image.Image = None, 
                           img2: Image.Image = None) -> Dict[str, Any]:
        """
        Compare deux screenshots et détecte les différences.
        
        Returns:
            Dict avec les zones de différences
        """
        if img1 is None:
            img1 = self.last_screenshot
        if img2 is None:
            img2 = self.capture_screen()
        
        if img1 is None or img2 is None:
            return {"error": "Images manquantes"}
        
        try:
            if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE:
                return {"error": "OpenCV requis pour comparaison"}
            
            # Redimensionner si nécessaire
            if img1.size != img2.size:
                img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)
            
            # Convertir en numpy arrays
            arr1 = np.array(img1.convert('RGB'))
            arr2 = np.array(img2.convert('RGB'))
            
            # Calculer la différence
            diff = cv2.absdiff(arr1, arr2)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
            
            # Seuiller pour trouver les zones de changement
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
            
            # Trouver les contours des zones de changement
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filtrer les petites zones
            changed_regions = []
            total_changed_pixels = np.sum(thresh > 0)
            change_percentage = (total_changed_pixels / (img1.width * img1.height)) * 100
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Ignorer les petits changements
                    x, y, w, h = cv2.boundingRect(contour)
                    changed_regions.append({
                        'x': int(x),
                        'y': int(y),
                        'width': int(w),
                        'height': int(h),
                        'area': int(area)
                    })
            
            return {
                "changed": len(changed_regions) > 0,
                "change_percentage": round(change_percentage, 2),
                "changed_regions": changed_regions,
                "total_changed_pixels": int(total_changed_pixels)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    # ========================================================================
    # INFORMATIONS SYSTÈME
    # ========================================================================
    
    def get_monitor_info(self) -> Dict[str, Any]:
        """Récupère les informations sur les moniteurs"""
        if not MSS_AVAILABLE or not self.sct:
            return {}
            
        try:
            # 👇 MODIFICATION 3 : IDEM ICI
            with mss.mss() as sct:
                monitors = sct.monitors
                return {
                    'count': len(monitors) - 1,
                    'monitors': [
                        {
                            'index': i,
                            'left': m['left'],
                            'top': m['top'],
                            'width': m['width'],
                            'height': m['height'],
                            'is_primary': i == 1
                        }
                        for i, m in enumerate(monitors) if i > 0
                    ],
                    'total_resolution': {
                        'width': monitors[0]['width'],
                        'height': monitors[0]['height']
                    }
                }
        except Exception as e:
            print(f"❌ [SCREEN] Erreur monitor info: {e}")
            return {}
    
    def get_cursor_position(self) -> Tuple[int, int]:
        """Récupère la position du curseur"""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.position()
        return (0, 0)
    
    def get_clipboard_text(self) -> str:
        """Récupère le contenu du presse-papiers"""
        try:
            if WIN32_AVAILABLE:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return data
                finally:
                    win32clipboard.CloseClipboard()
        except:
            pass
        return ""
    
    def set_clipboard_text(self, text: str) -> bool:
        """Définit le contenu du presse-papiers"""
        try:
            if WIN32_AVAILABLE:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                    return True
                finally:
                    win32clipboard.CloseClipboard()
        except:
            pass
        return False
    
    def analyze_with_gemini_vision(self, image: Image.Image = None, 
                                   prompt: str = "Décris ce que tu vois à l'écran en détail. Identifie les applications, le contenu visible, et tout élément important.") -> Dict[str, Any]:
        """
        Analyse un screenshot avec Gemini Vision API pour une compréhension contextuelle.
        
        Args:
            image: Image à analyser (ou dernière capture)
            prompt: Prompt pour guider l'analyse
            
        Returns:
            Dict avec l'analyse Gemini
        """
        if not GEMINI_VISION_AVAILABLE or gemini_client is None:
            return {"error": "Gemini Vision API non disponible"}
        
        if image is None:
            image = self.last_screenshot
        if image is None:
            return {"error": "Aucune image à analyser"}
        
        try:
            # Convertir l'image en base64
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Préparer le contenu pour Gemini (méthode compatible avec l'API)
            try:
                from google.genai import types as genai_types
                # Méthode 1: Avec types.Part (nouvelle API)
                contents = [
                    prompt,
                    genai_types.Part(
                        inline_data=genai_types.Part.InlineData(
                            mime_type='image/png',
                            data=img_base64
                        )
                    )
                ]
                response = gemini_client.models.generate_content(
                    model="gemini-2.0-flash-exp",
                    contents=contents
                )
            except (AttributeError, TypeError, ImportError) as e1:
                # Méthode 2: Fallback avec dict (ancienne API)
                try:
                    response = gemini_client.models.generate_content(
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
                except Exception as e2:
                    raise Exception(f"Erreur Gemini API (méthode 1: {e1}, méthode 2: {e2})")
            
            # Extraire le texte de la réponse
            if hasattr(response, 'text'):
                analysis_text = response.text
            else:
                analysis_text = str(response)
            
            return {
                "success": True,
                "analysis": analysis_text,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ [SCREEN] Erreur Gemini Vision: {e}")
            return {"error": str(e)}
    
    def extract_code_from_screen(self, image: Image.Image = None) -> Dict[str, Any]:
        """
        Extrait et analyse le code visible à l'écran.
        Détecte automatiquement la syntaxe et formate le code.
        """
        if image is None:
            image = self.last_screenshot
        if image is None:
            return {"error": "Aucune image à analyser"}
        
        try:
            # Utiliser Gemini Vision pour identifier le code
            prompt = """Identifie et extrait tout le code visible à l'écran. 
            Indique le langage de programmation, formate le code proprement, 
            et signale s'il y a des erreurs visibles (soulignements rouges, messages d'erreur, etc.).
            Retourne le code dans un bloc formaté."""
            
            gemini_result = self.analyze_with_gemini_vision(image, prompt)
            
            if gemini_result.get("success"):
                # Extraire aussi avec OCR pour avoir les deux
                ocr_text = self.extract_text(image, use_easyocr=False)
                
                # Détecter le langage depuis le texte OCR
                detected_language = self._detect_code_language(ocr_text)
                
                return {
                    "success": True,
                    "gemini_analysis": gemini_result.get("analysis", ""),
                    "ocr_code": ocr_text,
                    "detected_language": detected_language,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return gemini_result
                
        except Exception as e:
            print(f"❌ [SCREEN] Erreur extraction code: {e}")
            return {"error": str(e)}
    
    def _detect_code_language(self, text: str) -> str:
        """Détecte le langage de programmation depuis le texte"""
        text_lower = text.lower()
        
        # Patterns simples pour détecter les langages
        patterns = {
            "python": [r'\bdef\s+\w+', r'\bimport\s+\w+', r'\bfrom\s+\w+\s+import', r'\bclass\s+\w+', r'\bprint\('],
            "javascript": [r'\bfunction\s+\w+', r'\bconst\s+\w+\s*=', r'\blet\s+\w+\s*=', r'\bvar\s+\w+\s*=', r'=>'],
            "java": [r'public\s+class', r'@Override', r'System\.out\.print', r'import\s+java\.'],
            "cpp": [r'#include\s*<', r'std::', r'cout\s*<<', r'\bint\s+main\('],
            "html": [r'<!DOCTYPE', r'<html', r'<div', r'<span'],
            "css": [r'\w+\s*\{', r'\w+:\s*[^;]+;'],
            "sql": [r'\bSELECT\s+', r'\bFROM\s+', r'\bWHERE\s+', r'\bINSERT\s+INTO'],
        }
        
        scores = {}
        for lang, lang_patterns in patterns.items():
            score = sum(1 for pattern in lang_patterns if re.search(pattern, text_lower))
            if score > 0:
                scores[lang] = score
        
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return "unknown"
    
    # ========================================================================
    # ANALYSE COMPLÈTE
    # ========================================================================
    
    def analyze_screen(self, include_screenshot: bool = True, 
                       screenshot_quality: int = 70,
                       detailed_ocr: bool = True) -> ScreenAnalysis:
        """
        Effectue une analyse complète de l'écran.
        
        Args:
            include_screenshot: Inclure le screenshot en base64
            screenshot_quality: Qualité du screenshot (1-100)
            detailed_ocr: Extraire les blocs de texte détaillés
            
        Returns:
            ScreenAnalysis complète
        """
        print("🔬 [SCREEN] Analyse complète en cours...")
        
        # 1. Capture d'écran
        screenshot = self.capture_screen(monitor=1)  # Moniteur principal
        
        # 2. Informations moniteur
        monitor_info = self.get_monitor_info()
        
        # 3. Fenêtres
        all_windows = self.get_all_windows()
        active_window = None
        for w in all_windows:
            if w.is_foreground:
                active_window = w
                break
        
        # 4. OCR
        extracted_text = ""
        text_blocks = []
        if screenshot:
            extracted_text = self.extract_text(screenshot)
            if detailed_ocr:
                text_blocks = self.extract_text_blocks(screenshot)
        
        # 5. Éléments UI (optionnel, peut être lent)
        ui_elements = []  # self.detect_ui_elements(screenshot) si besoin
        
        # 6. Couleurs
        colors = self.analyze_colors(screenshot) if screenshot else []
        
        # 7. Applications
        detected_apps = self.detect_visible_apps()
        
        # 8. Résumé contextuel
        context_summary = self._generate_context_summary(
            active_window, extracted_text, detected_apps
        )
        
        # 9. Screenshot base64
        screenshot_b64 = None
        if include_screenshot and screenshot:
            screenshot_b64 = self.get_screenshot_base64(screenshot, screenshot_quality)
        
        analysis = ScreenAnalysis(
            timestamp=datetime.now().isoformat(),
            monitor_info=monitor_info,
            active_window=active_window,
            visible_windows=all_windows[:10],  # Top 10 fenêtres
            extracted_text=extracted_text[:5000],  # Limiter la taille
            text_blocks=[asdict(b) for b in text_blocks[:50]],  # Top 50 blocs
            ui_elements=[asdict(e) for e in ui_elements[:30]],
            dominant_colors=[asdict(c) for c in colors],
            detected_apps=detected_apps,
            context_summary=context_summary,
            screenshot_base64=screenshot_b64
        )
        
        self.last_analysis = analysis
        print("✅ [SCREEN] Analyse complète terminée")
        return analysis
    
    def _generate_context_summary(self, active_window: Optional[WindowInfo],
                                   text: str, apps: List[str]) -> str:
        """Génère un résumé contextuel de l'écran"""
        parts = []
        
        if active_window:
            app_name = self.KNOWN_APPS.get(active_window.process_name, active_window.process_name)
            parts.append(f"Fenêtre active: {active_window.title} ({app_name})")
        
        if apps:
            parts.append(f"Applications visibles: {', '.join(apps[:5])}")
        
        # Détecter le contexte par le texte
        text_lower = text.lower()
        if 'google' in text_lower or 'search' in text_lower:
            parts.append("Contexte: Navigation web / Recherche")
        elif 'code' in text_lower or 'function' in text_lower or 'def ' in text_lower:
            parts.append("Contexte: Programmation / Code")
        elif '@' in text_lower and ('inbox' in text_lower or 'message' in text_lower):
            parts.append("Contexte: Messagerie / Email")
        elif 'document' in text_lower or 'page' in text_lower:
            parts.append("Contexte: Traitement de texte")
        
        return " | ".join(parts) if parts else "Écran standard"
    
    def quick_look(self) -> Dict[str, Any]:
        """
        Analyse rapide de l'écran (plus rapide que analyze_screen).
        Retourne un aperçu sans screenshot ni OCR détaillé.
        """
        active = self.get_active_window()
        apps = self.detect_visible_apps()
        
        return {
            'active_window': asdict(active) if active else None,
            'visible_apps': apps,
            'cursor_position': self.get_cursor_position(),
            'timestamp': datetime.now().isoformat()
        }
    
    def describe_screen(self) -> str:
        """
        Retourne une description textuelle de l'écran actuel.
        Idéal pour donner du contexte à Cypher.
        """
        analysis = self.analyze_screen(include_screenshot=False, detailed_ocr=False)
        
        lines = [
            "=== Description de l'écran ===",
            f"Timestamp: {analysis.timestamp}",
            f"Moniteurs: {analysis.monitor_info.get('count', '?')}",
            ""
        ]
        
        if analysis.active_window:
            w = analysis.active_window
            lines.append(f"📍 Fenêtre active: {w.title}")
            lines.append(f"   Application: {self.KNOWN_APPS.get(w.process_name, w.process_name)}")
            lines.append(f"   État: {'Maximisée' if w.is_maximized else 'Normale'}")
            lines.append("")
        
        if analysis.detected_apps:
            lines.append(f"🖥️ Applications visibles: {', '.join(analysis.detected_apps)}")
            lines.append("")
        
        if analysis.dominant_colors:
            colors_str = ', '.join([f"{c['name']} ({c['percentage']}%)" 
                                   for c in analysis.dominant_colors[:3]])
            lines.append(f"🎨 Couleurs dominantes: {colors_str}")
            lines.append("")
        
        if analysis.extracted_text:
            preview = analysis.extracted_text[:500].replace('\n', ' ')
            lines.append(f"📝 Texte visible (aperçu): {preview}...")
        
        lines.append("")
        lines.append(f"📊 Résumé: {analysis.context_summary}")
        
        return '\n'.join(lines)


# ============================================================================
# INSTANCE SINGLETON
# ============================================================================

_screen_analyzer: Optional[ScreenAnalyzer] = None

def get_screen_analyzer() -> ScreenAnalyzer:
    """Retourne l'instance singleton du ScreenAnalyzer"""
    global _screen_analyzer
    if _screen_analyzer is None:
        _screen_analyzer = ScreenAnalyzer()
    return _screen_analyzer


# ============================================================================
# OUTIL POUR CYPHER
# ============================================================================

def analyze_screen_tool(action: str, **kwargs) -> str:
    """
    Outil principal pour l'analyse d'écran de Cypher.
    
    Args:
        action: L'action à effectuer
        **kwargs: Arguments supplémentaires selon l'action
        
    Returns:
        Résultat JSON de l'action
    """
    analyzer = get_screen_analyzer()
    result = {"success": False, "action": action}
    
    try:
        # === CAPTURE ===
        if action == "capture_screen":
            monitor = kwargs.get("monitor", 1)
            img = analyzer.capture_screen(monitor=monitor)
            if img:
                result["success"] = True
                result["size"] = {"width": img.width, "height": img.height}
                if kwargs.get("include_base64", False):
                    result["screenshot_base64"] = analyzer.get_screenshot_base64(
                        img, kwargs.get("quality", 70)
                    )
        
        elif action == "capture_window":
            title = kwargs.get("title")
            img = analyzer.capture_window(title_contains=title)
            if img:
                result["success"] = True
                result["size"] = {"width": img.width, "height": img.height}
                if kwargs.get("include_base64", False):
                    result["screenshot_base64"] = analyzer.get_screenshot_base64(img)
        
        elif action == "capture_active_window":
            img = analyzer.capture_active_window()
            if img:
                result["success"] = True
                result["size"] = {"width": img.width, "height": img.height}
        
        # === OCR ===
        elif action == "extract_text":
            use_easyocr = kwargs.get("use_easyocr", False)
            text = analyzer.extract_text(use_easyocr=use_easyocr)
            result["success"] = True
            result["text"] = text
            result["length"] = len(text)
        
        elif action == "capture_region":
            x = kwargs.get("x", 0)
            y = kwargs.get("y", 0)
            width = kwargs.get("width", 100)
            height = kwargs.get("height", 100)
            img = analyzer.capture_region(x, y, width, height)
            if img:
                result["success"] = True
                result["size"] = {"width": img.width, "height": img.height}
                if kwargs.get("include_base64", False):
                    result["screenshot_base64"] = analyzer.get_screenshot_base64(
                        img, kwargs.get("quality", 70)
                    )
        
        elif action == "extract_text_blocks":
            blocks = analyzer.extract_text_blocks(min_confidence=kwargs.get("min_confidence", 60))
            result["success"] = True
            result["blocks"] = [asdict(b) for b in blocks]
            result["count"] = len(blocks)
        
        elif action == "find_text":
            search = kwargs.get("search_text", "")
            if search:
                found = analyzer.find_text_on_screen(search)
                result["success"] = True
                result["results"] = found
                result["count"] = len(found)
            else:
                result["error"] = "search_text requis"
        
        # === FENÊTRES ===
        elif action == "get_windows":
            windows = analyzer.get_all_windows()
            result["success"] = True
            result["windows"] = [asdict(w) for w in windows]
            result["count"] = len(windows)
        
        elif action == "get_active_window":
            window = analyzer.get_active_window()
            result["success"] = True
            result["window"] = asdict(window) if window else None
        
        elif action == "focus_window":
            title = kwargs.get("title")
            if title:
                success = analyzer.focus_window(title_contains=title)
                result["success"] = success
            else:
                result["error"] = "title requis"
        
        elif action == "minimize_window":
            result["success"] = analyzer.minimize_window()
        
        elif action == "maximize_window":
            result["success"] = analyzer.maximize_window()
        
        elif action == "close_window":
            title = kwargs.get("title")
            result["success"] = analyzer.close_window(title_contains=title)
        
        # === APPLICATIONS ===
        elif action == "get_running_apps":
            apps = analyzer.detect_running_apps()
            result["success"] = True
            result["apps"] = apps
            result["count"] = len(apps)
        
        elif action == "get_visible_apps":
            apps = analyzer.detect_visible_apps()
            result["success"] = True
            result["apps"] = apps
            result["count"] = len(apps)
        
        elif action == "is_app_running":
            app = kwargs.get("app_name", "")
            result["success"] = True
            result["is_running"] = analyzer.is_app_running(app)
            result["app"] = app
        
        # === COULEURS ===
        elif action == "analyze_colors":
            num = kwargs.get("num_colors", 5)
            colors = analyzer.analyze_colors(num_colors=num)
            result["success"] = True
            result["colors"] = [asdict(c) for c in colors]
        
        elif action == "get_pixel_color":
            x, y = kwargs.get("x", 0), kwargs.get("y", 0)
            color = analyzer.get_pixel_color(x, y)
            result["success"] = color is not None
            result["color"] = asdict(color) if color else None
        
        # === ÉLÉMENTS UI ===
        elif action == "detect_ui_elements":
            elements = analyzer.detect_ui_elements()
            result["success"] = True
            result["elements"] = [asdict(e) for e in elements]
            result["count"] = len(elements)
        
        elif action == "find_element":
            text = kwargs.get("text", "")
            if text:
                element = analyzer.find_element_by_text(text)
                result["success"] = element is not None
                result["element"] = asdict(element) if element else None
            else:
                result["error"] = "text requis"
        
        elif action == "click_element":
            text = kwargs.get("text", "")
            if text:
                element = analyzer.find_element_by_text(text)
                if element:
                    result["success"] = analyzer.click_element(element)
                else:
                    result["error"] = f"Élément '{text}' non trouvé"
            else:
                result["error"] = "text requis"
        
        # === ACTIONS INTERACTIVES AVANCÉES ===
        elif action == "scroll":
            x = kwargs.get("x")
            y = kwargs.get("y")
            clicks = kwargs.get("clicks", 3)
            result["success"] = analyzer.scroll(x, y, clicks)
        
        elif action == "drag":
            start_x = kwargs.get("start_x", 0)
            start_y = kwargs.get("start_y", 0)
            end_x = kwargs.get("end_x", 0)
            end_y = kwargs.get("end_y", 0)
            duration = kwargs.get("duration", 1.0)
            result["success"] = analyzer.drag(start_x, start_y, end_x, end_y, duration)
        
        elif action == "type_text":
            text = kwargs.get("text", "")
            x = kwargs.get("x")
            y = kwargs.get("y")
            interval = kwargs.get("interval", 0.05)
            if text:
                result["success"] = analyzer.type_text(text, x, y, interval)
            else:
                result["error"] = "text requis"
        
        elif action == "press_key":
            keys = kwargs.get("keys", [])
            if keys:
                if isinstance(keys, str):
                    keys = keys.split("+")
                result["success"] = analyzer.press_key(*keys)
            else:
                result["error"] = "keys requis (ex: ['ctrl', 'c'])"
        
        # === COMPARAISON SCREENSHOTS ===
        elif action == "compare_screenshots":
            comparison = analyzer.compare_screenshots()
            result["success"] = True
            result["comparison"] = comparison
        
        # === GEMINI VISION ===
        elif action == "analyze_with_gemini":
            prompt = kwargs.get("prompt", "Décris ce que tu vois à l'écran en détail.")
            gemini_result = analyzer.analyze_with_gemini_vision(prompt=prompt)
            result.update(gemini_result)
        
        # === ANALYSE DE CODE ===
        elif action == "extract_code":
            code_result = analyzer.extract_code_from_screen()
            result.update(code_result)
        
        # === SYSTÈME ===
        elif action == "get_monitor_info":
            result["success"] = True
            result["monitors"] = analyzer.get_monitor_info()
        
        elif action == "get_cursor_position":
            pos = analyzer.get_cursor_position()
            result["success"] = True
            result["position"] = {"x": pos[0], "y": pos[1]}
        
        elif action == "get_clipboard":
            text = analyzer.get_clipboard_text()
            result["success"] = True
            result["clipboard"] = text
        
        elif action == "set_clipboard":
            text = kwargs.get("text", "")
            result["success"] = analyzer.set_clipboard_text(text)
        
        # === ANALYSE COMPLÈTE ===
        elif action == "full_analysis":
            analysis = analyzer.analyze_screen(
                include_screenshot=kwargs.get("include_screenshot", False),
                screenshot_quality=kwargs.get("quality", 70),
                detailed_ocr=kwargs.get("detailed_ocr", True)
            )
            result["success"] = True
            result["analysis"] = {
                "timestamp": analysis.timestamp,
                "monitor_info": analysis.monitor_info,
                "active_window": asdict(analysis.active_window) if analysis.active_window else None,
                "visible_windows": [asdict(w) for w in analysis.visible_windows] if analysis.visible_windows else [],
                "extracted_text": analysis.extracted_text,
                "text_blocks": analysis.text_blocks,
                "dominant_colors": analysis.dominant_colors,
                "detected_apps": analysis.detected_apps,
                "context_summary": analysis.context_summary,
                "screenshot_base64": analysis.screenshot_base64
            }
        
        elif action == "quick_look":
            result["success"] = True
            result["data"] = analyzer.quick_look()
        
        elif action == "describe":
            result["success"] = True
            result["description"] = analyzer.describe_screen()
        
        else:
            result["error"] = f"Action inconnue: {action}"
            result["available_actions"] = [
                "capture_screen", "capture_window", "capture_active_window", "capture_region",
                "extract_text", "extract_text_blocks", "find_text",
                "get_windows", "get_active_window", "focus_window", 
                "minimize_window", "maximize_window", "close_window",
                "get_running_apps", "get_visible_apps", "is_app_running",
                "analyze_colors", "get_pixel_color",
                "detect_ui_elements", "find_element", "click_element",
                "get_monitor_info", "get_cursor_position", 
                "get_clipboard", "set_clipboard",
                "full_analysis", "quick_look", "describe",
                "scroll", "drag", "type_text", "press_key",
                "compare_screenshots", "analyze_with_gemini", "extract_code"
            ]
    
    except Exception as e:
        result["error"] = str(e)
        print(f"❌ [SCREEN TOOL] Erreur: {e}")
    
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================================
# DÉCLARATION DU TOOL POUR GEMINI
# ============================================================================

SCREEN_ANALYZER_TOOL_DECLARATION = {
    "name": "analyze_screen",
    "description": """Outil de vision complète pour analyser l'écran du PC.
    
Capacités:
- CAPTURE: Screenshots de l'écran entier, fenêtres spécifiques ou zones
- OCR: Extraction de tout le texte visible à l'écran
- FENÊTRES: Liste, focus, minimiser, maximiser, fermer les fenêtres
- APPLICATIONS: Détecter les apps en cours d'exécution
- COULEURS: Analyser les couleurs dominantes
- UI: Détecter boutons, champs, liens et interagir avec
- SYSTÈME: Position curseur, presse-papiers, infos moniteurs

Utilisez cet outil pour "voir" ce que l'utilisateur voit sur son écran.""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": """Action à effectuer:
                
CAPTURE:
- capture_screen: Capture l'écran (params: monitor, include_base64, quality)
- capture_window: Capture une fenêtre (params: title, include_base64)
- capture_active_window: Capture la fenêtre active

OCR:
- extract_text: Extrait tout le texte visible
- extract_text_blocks: Extrait les blocs avec positions (params: min_confidence)
- find_text: Cherche un texte spécifique (params: search_text)

FENÊTRES:
- get_windows: Liste toutes les fenêtres
- get_active_window: Info sur la fenêtre active
- focus_window: Met une fenêtre au premier plan (params: title)
- minimize_window: Minimise la fenêtre active
- maximize_window: Maximise la fenêtre active
- close_window: Ferme une fenêtre (params: title)

APPLICATIONS:
- get_running_apps: Liste les applications en cours
- get_visible_apps: Liste les apps avec fenêtres visibles
- is_app_running: Vérifie si une app tourne (params: app_name)

COULEURS:
- analyze_colors: Couleurs dominantes (params: num_colors)
- get_pixel_color: Couleur d'un pixel (params: x, y)

UI:
- detect_ui_elements: Détecte boutons, champs, etc.
- find_element: Trouve un élément par texte (params: text)
- click_element: Clique sur un élément (params: text)

SYSTÈME:
- get_monitor_info: Infos sur les moniteurs
- get_cursor_position: Position du curseur
- get_clipboard: Contenu du presse-papiers
- set_clipboard: Définit le presse-papiers (params: text)

ANALYSE:
- full_analysis: Analyse complète de l'écran
- quick_look: Aperçu rapide (sans OCR)
- describe: Description textuelle de l'écran
- analyze_with_gemini: Analyse avec Gemini Vision API (params: prompt)
- extract_code: Extrait et analyse le code visible (détection langage, formatage)

INTERACTIONS AVANCÉES:
- scroll: Fait défiler (params: x, y, clicks)
- drag: Drag & drop (params: start_x, start_y, end_x, end_y, duration)
- type_text: Tape du texte (params: text, x, y, interval)
- press_key: Raccourcis clavier (params: keys=['ctrl', 'c'])

AUTRES:
- capture_region: Capture une zone rectangulaire (params: x, y, width, height)
- compare_screenshots: Compare deux screenshots pour détecter changements""",
                "enum": [
                    "capture_screen", "capture_window", "capture_active_window", "capture_region",
                    "extract_text", "extract_text_blocks", "find_text",
                    "get_windows", "get_active_window", "focus_window",
                    "minimize_window", "maximize_window", "close_window",
                    "get_running_apps", "get_visible_apps", "is_app_running",
                    "analyze_colors", "get_pixel_color",
                    "detect_ui_elements", "find_element", "click_element",
                    "get_monitor_info", "get_cursor_position",
                    "get_clipboard", "set_clipboard",
                    "full_analysis", "quick_look", "describe",
                    "scroll", "drag", "type_text", "press_key",
                    "compare_screenshots", "analyze_with_gemini", "extract_code"
                ]
            },
            "monitor": {
                "type": "integer",
                "description": "Index du moniteur (0=tous, 1=principal, 2+=secondaires)"
            },
            "title": {
                "type": "string",
                "description": "Titre (partiel) de la fenêtre"
            },
            "include_base64": {
                "type": "boolean",
                "description": "Inclure l'image en base64 dans la réponse"
            },
            "quality": {
                "type": "integer",
                "description": "Qualité JPEG pour les screenshots (1-100)"
            },
            "search_text": {
                "type": "string",
                "description": "Texte à rechercher sur l'écran"
            },
            "text": {
                "type": "string",
                "description": "Texte de l'élément UI à trouver/cliquer"
            },
            "app_name": {
                "type": "string",
                "description": "Nom de l'application à vérifier"
            },
            "min_confidence": {
                "type": "number",
                "description": "Confiance minimale OCR (0-100)"
            },
            "num_colors": {
                "type": "integer",
                "description": "Nombre de couleurs dominantes à retourner"
            },
            "x": {
                "type": "integer",
                "description": "Position X du pixel"
            },
            "y": {
                "type": "integer",
                "description": "Position Y du pixel"
            },
            "detailed_ocr": {
                "type": "boolean",
                "description": "Extraction OCR détaillée (blocs avec positions)"
            },
            "use_easyocr": {
                "type": "boolean",
                "description": "Utiliser EasyOCR au lieu de Tesseract (plus précis mais plus lent)"
            },
            "prompt": {
                "type": "string",
                "description": "Prompt pour l'analyse Gemini Vision"
            },
            "x": {
                "type": "integer",
                "description": "Position X (pour capture_region, scroll, type_text)"
            },
            "y": {
                "type": "integer",
                "description": "Position Y (pour capture_region, scroll, type_text)"
            },
            "width": {
                "type": "integer",
                "description": "Largeur (pour capture_region)"
            },
            "height": {
                "type": "integer",
                "description": "Hauteur (pour capture_region)"
            },
            "start_x": {
                "type": "integer",
                "description": "Position X de départ (pour drag)"
            },
            "start_y": {
                "type": "integer",
                "description": "Position Y de départ (pour drag)"
            },
            "end_x": {
                "type": "integer",
                "description": "Position X de fin (pour drag)"
            },
            "end_y": {
                "type": "integer",
                "description": "Position Y de fin (pour drag)"
            },
            "duration": {
                "type": "number",
                "description": "Durée en secondes (pour drag)"
            },
            "clicks": {
                "type": "integer",
                "description": "Nombre de clics de scroll (pour scroll)"
            },
            "interval": {
                "type": "number",
                "description": "Intervalle entre chaque caractère en secondes (pour type_text)"
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste des touches à presser (pour press_key, ex: ['ctrl', 'c'])"
            }
        },
        "required": ["action"]
    }
}


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("=== Test Screen Analyzer ===\n")
    
    analyzer = get_screen_analyzer()
    
    # Test quick look
    print("1. Quick Look:")
    quick = analyzer.quick_look()
    print(json.dumps(quick, indent=2, ensure_ascii=False, default=str))
    
    # Test capture
    print("\n2. Capture écran:")
    img = analyzer.capture_screen()
    if img:
        print(f"   Taille: {img.width}x{img.height}")
    
    # Test OCR
    print("\n3. OCR:")
    text = analyzer.extract_text()
    print(f"   {len(text)} caractères extraits")
    if text:
        print(f"   Aperçu: {text[:200]}...")
    
    # Test fenêtres
    print("\n4. Fenêtres:")
    windows = analyzer.get_all_windows()
    for w in windows[:5]:
        print(f"   - {w.title[:50]}... ({w.process_name})")
    
    # Test apps
    print("\n5. Applications visibles:")
    apps = analyzer.detect_visible_apps()
    print(f"   {', '.join(apps)}")
    
    # Test description
    print("\n6. Description de l'écran:")
    print(analyzer.describe_screen())