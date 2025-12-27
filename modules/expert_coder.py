# -*- coding: utf-8 -*-
"""
Expert Codeur Claude - Cerveau Secondaire v3.0
===============================================
Améliorations majeures :
- Streaming temps réel
- Auto-repair si erreur syntaxe
- Sandbox d'exécution sécurisée
- Scoring qualité du code
- Génération multi-fichiers
- Analyse de code (sécurité, performance, complexité)
- Système de templates
- Support async/await
- Diff et patch
- Modèles Claude 4 à jour
"""

import os
import re
import json
import time
import hashlib
import base64
import asyncio
import subprocess
import tempfile
import difflib
import ast
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Dict, Any, List, Callable, Generator, Tuple, Union, Literal
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from anthropic import Anthropic, APIError, RateLimitError, APIConnectionError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ anthropic non installé: pip install anthropic")


# ========================================
# CONFIGURATION
# ========================================

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Modèles Claude 4 à jour (Juin 2025)
CLAUDE_MODELS = [
    "claude-sonnet-4-5",           # Le plus capable
    "claude-sonnet-4-20250514",    # Fallback
    "claude-3-5-sonnet-20241022",  # Legacy
]

USER_HOME = os.path.expanduser("~")
ONEDRIVE_BASE = os.path.join(USER_HOME, "OneDrive")
DESKTOP_PATH = os.path.join(ONEDRIVE_BASE, "Desktop")
DOCUMENTS_PATH = os.path.join(ONEDRIVE_BASE, "Documents")

# Fichiers de persistance
# Chemins vers les fichiers de cache (dans data/cache/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Racine du projet
CACHE_BASE = os.path.join(BASE_DIR, "data", "cache")
MEMORY_FILE = os.path.join(CACHE_BASE, "expert_coder_memory.json")
CACHE_FILE = os.path.join(CACHE_BASE, "expert_coder_cache.json")
TEMPLATES_FILE = os.path.join(CACHE_BASE, "expert_coder_templates.json")

# Config retry
MAX_RETRIES = 3
INITIAL_BACKOFF = 1
MAX_BACKOFF = 30

# Config sandbox
SANDBOX_TIMEOUT = 10  # secondes max pour exécution
SANDBOX_MAX_OUTPUT = 10000  # caractères max


# ========================================
# ENUMS & DATA CLASSES
# ========================================

class CodeQuality(Enum):
    """Niveaux de qualité du code"""
    EXCELLENT = auto()
    GOOD = auto()
    ACCEPTABLE = auto()
    POOR = auto()
    FAILED = auto()


class Language(Enum):
    """Langages supportés avec leurs configs"""
    PYTHON = ("python", ".py", "# ", ["py", "python3"])
    JAVASCRIPT = ("javascript", ".js", "// ", ["node", "js"])
    TYPESCRIPT = ("typescript", ".ts", "// ", ["ts", "tsx"])
    HTML = ("html", ".html", "<!-- ", ["html5"])
    CSS = ("css", ".css", "/* ", ["css3", "scss"])
    JAVA = ("java", ".java", "// ", ["java"])
    CPP = ("c++", ".cpp", "// ", ["cpp", "c++"])
    RUST = ("rust", ".rs", "// ", ["rs"])
    GO = ("go", ".go", "// ", ["golang"])
    BASH = ("bash", ".sh", "# ", ["shell", "sh"])
    
    @classmethod
    def from_string(cls, lang: str) -> "Language":
        lang = lang.lower().strip()
        for member in cls:
            if lang == member.value[0] or lang in member.value[3]:
                return member
        return cls.PYTHON  # Défaut


@dataclass
class CodeResult:
    """Résultat structuré de génération"""
    success: bool
    code: str = ""
    model_used: str = ""
    tokens_used: int = 0
    error: Optional[str] = None
    from_cache: bool = False
    quality_score: float = 0.0
    quality_level: CodeQuality = CodeQuality.FAILED
    stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)  # Pour multi-fichiers
    execution_result: Optional[Dict] = None
    diff: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quality_level"] = self.quality_level.name
        return d

    def to_base64_payload(self) -> dict:
        """Payload robuste (anti-problèmes de guillemets) pour transport via autres LLM/tools."""
        return {
            "version": "3.1",
            "success": self.success,
            "language": self.stats.get("language"),
            "model_used": self.model_used,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level.name,
            "warnings": self.warnings,
            "stats": self.stats,
            "encoding": "base64",
            "code_b64": base64.b64encode((self.code or "").encode("utf-8")).decode("ascii"),
            "files_b64": {
                k: base64.b64encode(v.encode("utf-8")).decode("ascii")
                for k, v in (self.files or {}).items()
            },
            "error": self.error,
        }


@dataclass
class AnalysisResult:
    """Résultat d'analyse de code"""
    complexity_score: float = 0.0
    security_issues: List[str] = field(default_factory=list)
    performance_issues: List[str] = field(default_factory=list)
    style_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ========================================
# TEMPLATES SYSTÈME
# ========================================

DEFAULT_TEMPLATES = {
    "gui_tkinter": {
        "name": "Interface Tkinter Dark Mode",
        "language": "python",
        "description": "Application GUI Tkinter avec thème sombre",
        "template": '''# -*- coding: utf-8 -*-
"""
{description}
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os

# Thème Dark Mode
COLORS = {{
    "bg": "#1E1E1E",
    "fg": "#ECF0F1",
    "accent": "#3498DB",
    "secondary": "#2C3E50",
    "success": "#27AE60",
    "warning": "#F39C12",
    "error": "#E74C3C"
}}


class {class_name}(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{title}")
        self.geometry("{geometry}")
        self.configure(bg=COLORS["bg"])
        self._center_window()
        self._setup_styles()
        self._build_ui()
    
    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{{x}}+{{y}}")
    
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=COLORS["bg"], foreground=COLORS["fg"])
        style.configure("TButton", padding=10, font=("Segoe UI", 10))
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["fg"])
        style.configure("TEntry", fieldbackground=COLORS["secondary"])
    
    def _build_ui(self):
        # TODO: Implémenter l'interface
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="{title}", font=("Segoe UI", 18, "bold")).pack(pady=20)


def main():
    app = {class_name}()
    app.mainloop()


if __name__ == "__main__":
    main()
'''
    },
    
    "api_client": {
        "name": "Client API REST",
        "language": "python",
        "description": "Client API avec retry et gestion d'erreurs",
        "template": '''# -*- coding: utf-8 -*-
"""
{description}
"""

import os
import time
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class APIResponse:
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    status_code: int = 0


class {class_name}:
    """Client API avec retry automatique"""
    
    def __init__(self, base_url: str, api_key: str = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {{api_key}}"
    
    def _request(self, method: str, endpoint: str, **kwargs) -> APIResponse:
        url = f"{{self.base_url}}/{{endpoint.lstrip('/')}}"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                return APIResponse(True, response.json(), status_code=response.status_code)
            except requests.exceptions.HTTPError as e:
                if response.status_code >= 500 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return APIResponse(False, error=str(e), status_code=response.status_code)
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return APIResponse(False, error=str(e))
        
        return APIResponse(False, error="Max retries exceeded")
    
    def get(self, endpoint: str, params: Dict = None) -> APIResponse:
        return self._request("GET", endpoint, params=params)
    
    def post(self, endpoint: str, data: Dict = None, json_data: Dict = None) -> APIResponse:
        return self._request("POST", endpoint, data=data, json=json_data)
    
    def put(self, endpoint: str, data: Dict = None, json_data: Dict = None) -> APIResponse:
        return self._request("PUT", endpoint, data=data, json=json_data)
    
    def delete(self, endpoint: str) -> APIResponse:
        return self._request("DELETE", endpoint)


# Exemple d'utilisation
if __name__ == "__main__":
    client = {class_name}("https://api.example.com", api_key="your-key")
    response = client.get("/users")
    if response.success:
        print(response.data)
    else:
        print(f"Erreur: {{response.error}}")
'''
    },
    
    "web_scraper": {
        "name": "Web Scraper",
        "language": "python",
        "description": "Scraper web avec BeautifulSoup et gestion d'erreurs",
        "template": '''# -*- coding: utf-8 -*-
"""
{description}
"""

import os
import time
import random
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


@dataclass
class ScrapedData:
    url: str
    title: str = ""
    content: str = ""
    links: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


class {class_name}:
    """Web Scraper avec anti-détection"""
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/17.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    def __init__(self, delay: float = 1.0, timeout: int = 30):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        return {{
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }}
    
    def scrape(self, url: str) -> ScrapedData:
        try:
            time.sleep(self.delay * random.uniform(0.5, 1.5))
            response = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extraction
            title = soup.title.string if soup.title else ""
            content = soup.get_text(separator=" ", strip=True)[:5000]
            links = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)]
            
            # Métadonnées
            metadata = {{}}
            for meta in soup.find_all("meta"):
                name = meta.get("name") or meta.get("property")
                content_meta = meta.get("content")
                if name and content_meta:
                    metadata[name] = content_meta
            
            return ScrapedData(url=url, title=title, content=content, links=links, metadata=metadata)
        
        except Exception as e:
            return ScrapedData(url=url, error=str(e))
    
    def scrape_multiple(self, urls: List[str]) -> List[ScrapedData]:
        return [self.scrape(url) for url in urls]


if __name__ == "__main__":
    scraper = {class_name}()
    result = scraper.scrape("https://example.com")
    print(f"Titre: {{result.title}}")
    print(f"Liens: {{len(result.links)}}")
'''
    },
    
    "cli_tool": {
        "name": "Outil CLI",
        "language": "python",
        "description": "Outil en ligne de commande avec argparse",
        "template": '''# -*- coding: utf-8 -*-
"""
{description}
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional


# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def setup_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="{description}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s --input file.txt --output result.txt
  %(prog)s -v --dry-run
        """
    )
    
    parser.add_argument("input", nargs="?", help="Fichier d'entrée")
    parser.add_argument("-o", "--output", help="Fichier de sortie")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mode verbeux")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans exécution")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    
    return parser


def process(input_path: Optional[str], output_path: Optional[str], dry_run: bool) -> int:
    """Logique principale"""
    if dry_run:
        logger.info("Mode dry-run activé")
    
    # TODO: Implémenter la logique
    logger.info(f"Traitement: {{input_path}} -> {{output_path}}")
    
    return 0


def main():
    parser = setup_argparser()
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        exit_code = process(args.input, args.output, args.dry_run)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interruption utilisateur")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Erreur: {{e}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
    }
}


# ========================================
# ANALYSEUR DE CODE
# ========================================

class CodeAnalyzer:
    """Analyse statique du code généré"""
    
    # Patterns de sécurité à détecter
    SECURITY_PATTERNS = {
        "python": [
            (r'\beval\s*\(', "Utilisation de eval() - risque d'injection"),
            (r'\bexec\s*\(', "Utilisation de exec() - risque d'injection"),
            (r'\b__import__\s*\(', "Import dynamique dangereux"),
            (r'pickle\.loads?\s*\(', "Désérialisation pickle non sécurisée"),
            (r'subprocess\..*shell\s*=\s*True', "Shell=True dans subprocess - risque d'injection"),
            (r'input\s*\([^)]*\)\s*(?:==|!=|<|>)', "Comparaison directe d'input utilisateur"),
            (r'os\.system\s*\(', "os.system() - préférer subprocess"),
        ],
        "javascript": [
            (r'\beval\s*\(', "Utilisation de eval() - risque d'injection"),
            (r'innerHTML\s*=', "innerHTML - risque XSS, utiliser textContent"),
            (r'document\.write\s*\(', "document.write() obsolète et dangereux"),
            (r'\.innerText\s*=\s*[^\'\"]+\+', "Concaténation dans innerText potentiellement dangereuse"),
        ]
    }
    
    # Patterns de performance
    PERFORMANCE_PATTERNS = {
        "python": [
            (r'\+\s*=\s*[\'\"]\w', "Concaténation de chaînes en boucle - utiliser join()"),
            (r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(', "Utiliser enumerate() plutôt que range(len())"),
            (r'\.append\s*\([^)]+\)\s*$.*\.append\s*\([^)]+\)', "Multiples append - utiliser extend()"),
            (r'import\s+\*', "Import * déconseillé - imports explicites"),
        ],
        "javascript": [
            (r'document\.querySelector\([^)]+\).*document\.querySelector\([^)]+\)', "Multiples querySelector - cacher la référence"),
            (r'\.forEach\s*\((?!.*return)', "forEach sans return - considérer map/filter"),
        ]
    }
    
    @classmethod
    def analyze(cls, code: str, language: str = "python") -> AnalysisResult:
        """Analyse complète du code"""
        result = AnalysisResult()
        lang = language.lower()
        
        # Analyse de sécurité
        if lang in cls.SECURITY_PATTERNS:
            for pattern, message in cls.SECURITY_PATTERNS[lang]:
                if re.search(pattern, code, re.MULTILINE):
                    result.security_issues.append(message)
        
        # Analyse de performance
        if lang in cls.PERFORMANCE_PATTERNS:
            for pattern, message in cls.PERFORMANCE_PATTERNS[lang]:
                if re.search(pattern, code, re.MULTILINE | re.DOTALL):
                    result.performance_issues.append(message)
        
        # Métriques
        lines = code.split('\n')
        result.metrics = {
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            "comment_lines": len([l for l in lines if l.strip().startswith('#')]),
            "blank_lines": len([l for l in lines if not l.strip()]),
            "functions": len(re.findall(r'\bdef\s+\w+\s*\(', code)),
            "classes": len(re.findall(r'\bclass\s+\w+', code)),
            "imports": len(re.findall(r'^(?:import|from)\s+', code, re.MULTILINE)),
        }
        
        # Score de complexité (simplifié)
        complexity = 0
        complexity += result.metrics["functions"] * 2
        complexity += result.metrics["classes"] * 5
        complexity += len(re.findall(r'\bif\s+', code)) * 1
        complexity += len(re.findall(r'\bfor\s+', code)) * 2
        complexity += len(re.findall(r'\bwhile\s+', code)) * 3
        complexity += len(re.findall(r'\btry\s*:', code)) * 1
        result.complexity_score = min(100, complexity)
        
        # Suggestions
        if result.metrics["comment_lines"] < result.metrics["code_lines"] * 0.1:
            result.suggestions.append("Ajouter plus de commentaires (< 10% actuellement)")
        
        if result.metrics["functions"] == 0 and result.metrics["code_lines"] > 30:
            result.suggestions.append("Considérer la décomposition en fonctions")
        
        if lang == "python":
            if not re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:', code):
                result.suggestions.append("Ajouter if __name__ == '__main__':")
            
            if not re.search(r'^"""', code):
                result.suggestions.append("Ajouter une docstring au module")
        
        return result
    
    @classmethod
    def score_quality(cls, code: str, language: str, is_valid_syntax: bool) -> Tuple[float, CodeQuality]:
        """Calcule un score de qualité 0-100"""
        if not is_valid_syntax:
            return 0.0, CodeQuality.FAILED
        
        analysis = cls.analyze(code, language)
        
        score = 100.0
        
        # Pénalités sécurité (graves)
        score -= len(analysis.security_issues) * 15
        
        # Pénalités performance
        score -= len(analysis.performance_issues) * 5
        
        # Pénalités style
        score -= len(analysis.style_issues) * 2
        
        # Bonus pour bonnes pratiques
        if analysis.metrics.get("comment_lines", 0) >= analysis.metrics.get("code_lines", 1) * 0.1:
            score += 5
        
        if analysis.metrics.get("functions", 0) > 0:
            score += 5
        
        # Clamp
        score = max(0.0, min(100.0, score))
        
        # Niveau de qualité
        if score >= 90:
            level = CodeQuality.EXCELLENT
        elif score >= 75:
            level = CodeQuality.GOOD
        elif score >= 50:
            level = CodeQuality.ACCEPTABLE
        else:
            level = CodeQuality.POOR
        
        return score, level


# ========================================
# SANDBOX D'EXÉCUTION
# ========================================

class CodeSandbox:
    """Exécution sécurisée du code généré"""
    
    @staticmethod
    def execute_python(code: str, timeout: int = SANDBOX_TIMEOUT) -> Dict[str, Any]:
        """Exécute du code Python dans un environnement isolé"""
        result = {
            "success": False,
            "output": "",
            "error": "",
            "execution_time": 0.0,
            "return_code": -1
        }
        
        # Créer fichier temporaire
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.py', 
            delete=False, 
            encoding='utf-8'
        ) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            start = time.time()
            proc = subprocess.run(
                ['python', temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir()
            )
            result["execution_time"] = time.time() - start
            result["return_code"] = proc.returncode
            result["output"] = proc.stdout[:SANDBOX_MAX_OUTPUT]
            result["error"] = proc.stderr[:SANDBOX_MAX_OUTPUT]
            result["success"] = proc.returncode == 0
            
        except subprocess.TimeoutExpired:
            result["error"] = f"Timeout après {timeout}s"
        except Exception as e:
            result["error"] = str(e)
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
        
        return result
    
    @staticmethod
    def execute_javascript(code: str, timeout: int = SANDBOX_TIMEOUT) -> Dict[str, Any]:
        """Exécute du code JavaScript via Node.js"""
        result = {
            "success": False,
            "output": "",
            "error": "",
            "execution_time": 0.0,
            "return_code": -1
        }
        
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.js', 
            delete=False, 
            encoding='utf-8'
        ) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            start = time.time()
            proc = subprocess.run(
                ['node', temp_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            result["execution_time"] = time.time() - start
            result["return_code"] = proc.returncode
            result["output"] = proc.stdout[:SANDBOX_MAX_OUTPUT]
            result["error"] = proc.stderr[:SANDBOX_MAX_OUTPUT]
            result["success"] = proc.returncode == 0
            
        except FileNotFoundError:
            result["error"] = "Node.js non installé"
        except subprocess.TimeoutExpired:
            result["error"] = f"Timeout après {timeout}s"
        except Exception as e:
            result["error"] = str(e)
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
        
        return result
    
    @classmethod
    def execute(cls, code: str, language: str, timeout: int = SANDBOX_TIMEOUT) -> Dict[str, Any]:
        """Exécute le code dans le langage approprié"""
        lang = language.lower()
        
        if lang == "python":
            return cls.execute_python(code, timeout)
        elif lang in ("javascript", "js"):
            return cls.execute_javascript(code, timeout)
        else:
            return {
                "success": False,
                "output": "",
                "error": f"Exécution {language} non supportée",
                "execution_time": 0.0,
                "return_code": -1
            }


# ========================================
# CLASSE PRINCIPALE v3.0
# ========================================

class ClaudeExpertCoder:
    """
    Expert Codeur Claude v3.0
    
    Améliorations:
    - Streaming temps réel
    - Auto-repair si erreur syntaxe  
    - Sandbox d'exécution
    - Scoring qualité
    - Multi-fichiers
    - Templates
    - Analyse de code
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        
        if not self.api_key:
            raise ValueError(
                "❌ ANTHROPIC_API_KEY manquante !\n"
                "Ajoute-la dans ton fichier .env :\n"
                "ANTHROPIC_API_KEY=sk-ant-api03-xxxxx"
            )
        
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Module anthropic non installé: pip install anthropic")
        
        self.client = Anthropic(api_key=self.api_key)
        self.memory = self._load_json(MEMORY_FILE, self._default_memory())
        self.cache = OrderedDict(self._load_json(CACHE_FILE, {}))
        self.templates = self._load_json(TEMPLATES_FILE, DEFAULT_TEMPLATES)
        
        self.cache_max_size = 100
        self.last_code = None
        self.last_specs = None
        self.conversation_context: List[Dict] = []
        
        # Callbacks pour streaming
        self._stream_callbacks: List[Callable[[str], None]] = []
    
    @staticmethod
    def _default_memory() -> dict:
        return {
            "generations": [],
            "errors": [],
            "repairs": [],
            "total_tokens": 0,
            "total_time_ms": 0,
            "model_usage": {},
            "quality_scores": []
        }
    
    @staticmethod
    def _load_json(path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(default, dict):
                        for key, val in default.items():
                            data.setdefault(key, val)
                    return data
            except Exception:
                pass
        return default
    
    def _save_json(self, path: str, data: Any):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde {path}: {e}")
    
    def _save_memory(self):
        self._save_json(MEMORY_FILE, self.memory)
    
    def _save_cache(self):
        while len(self.cache) > self.cache_max_size:
            self.cache.popitem(last=False)
        self._save_json(CACHE_FILE, dict(self.cache))
    
    def _get_cache_key(self, specs: str, language: str) -> str:
        content = f"{language}::{specs.strip().lower()}"
        return hashlib.md5(content.encode()).hexdigest()
    
    # ========================================
    # STREAMING
    # ========================================
    
    def on_stream(self, callback: Callable[[str], None]):
        """Ajoute un callback pour le streaming"""
        self._stream_callbacks.append(callback)
    
    def _emit_stream(self, text: str):
        """Émet du texte aux callbacks de streaming"""
        for cb in self._stream_callbacks:
            try:
                cb(text)
            except:
                pass
    
    # ========================================
    # VALIDATION MULTI-LANGAGES
    # ========================================
    
    def _validate_syntax(self, code: str, language: str) -> Tuple[bool, str]:
        """Valide la syntaxe du code"""
        lang = language.lower()
        
        if lang == "python":
            try:
                compile(code, '<string>', 'exec')
                return True, ""
            except SyntaxError as e:
                return False, f"Ligne {e.lineno}: {e.msg}"
        
        elif lang in ("javascript", "js"):
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.js', delete=False, encoding='utf-8'
                ) as f:
                    f.write(code)
                    temp_path = f.name
                
                result = subprocess.run(
                    ['node', '--check', temp_path],
                    capture_output=True, text=True, timeout=5
                )
                os.unlink(temp_path)
                
                if result.returncode == 0:
                    return True, ""
                return False, result.stderr[:200]
            except FileNotFoundError:
                return True, "(Node.js non disponible)"
            except Exception:
                return True, "(Validation JS échouée)"
        
        elif lang == "html":
            if code.count('<') != code.count('>'):
                return False, "Balises HTML non équilibrées"
            return True, ""
        
        return True, f"(Validation {language} non implémentée)"
    
    # ========================================
    # PROMPTS OPTIMISÉS
    # ========================================
    
    def _build_system_prompt(self, language: str) -> str:
        return f"""Tu es un Architecte Logiciel Senior Expert en {language}.

🎯 MISSION : Générer du code production-ready de la plus haute qualité.

⚠️ CHEMINS SYSTÈME (Windows OneDrive) :
- Bureau : {DESKTOP_PATH}
- Documents : {DOCUMENTS_PATH}

📋 RÈGLES STRICTES :

1. FORMAT DE RÉPONSE :
   - UNIQUEMENT du code, ZÉRO texte explicatif
   - PAS de markdown (pas de ```)
   - Premier caractère = début du code
   - Dernier caractère = fin du code

2. QUALITÉ :
   - ✅ Complet et immédiatement exécutable
   - ✅ Gestion d'erreurs robuste (try/except/finally)
   - ✅ Architecture propre (fonctions, classes)
   - ✅ Standards du langage (PEP 8 pour Python)
   - ✅ Imports organisés (stdlib → tiers → locaux)
   - ❌ Pas de TODO, pas de placeholder, pas de pass vide

3. INTERFACES GRAPHIQUES :
   - Tkinter obligatoire (pas PyQt/wx)
   - Dark mode (#1E1E1E, #2C3E50, #3498DB, #ECF0F1)
   - Fenêtre centrée au lancement
   - Responsive

4. SÉCURITÉ :
   - Pas d'eval()/exec() sur input utilisateur
   - Validation des entrées
   - Timeout sur réseau
   - with pour ressources

5. STRUCTURE :
   # Imports
   # Constantes (MAJUSCULES)
   # Classes
   # Fonctions
   # main()
   # if __name__ == "__main__": main()

❌ INTERDIT : Texte, TODO, imports inutilisés, pass vides, eval sur input.
"""

    def _build_user_prompt(self, specs: str, language: str) -> str:
        context_str = ""
        if self.conversation_context:
            context_str = "\n\nCONTEXTE PRÉCÉDENT :\n" + "\n".join([
                f"- {c['role']}: {c['content'][:80]}..." 
                for c in self.conversation_context[-3:]
            ])
        
        return f"""SPÉCIFICATIONS :

{specs}

LANGAGE : {language}
{context_str}

GÉNÈRE LE CODE MAINTENANT (pas de markdown, juste le code) :"""

    def _build_repair_prompt(self, code: str, error: str, language: str) -> str:
        return f"""Le code suivant contient une erreur de syntaxe. Corrige-la.

CODE ACTUEL :
{code}

ERREUR :
{error}

RÈGLES :
- Retourne UNIQUEMENT le code corrigé
- PAS de markdown, PAS d'explication
- Garde la même logique et structure

CODE CORRIGÉ :"""

    # ========================================
    # API AVEC RETRY ET STREAMING
    # ========================================
    
    def _call_api(
        self, 
        model: str, 
        system: str, 
        messages: list,
        max_tokens: int = 8192,
        stream: bool = False
    ) -> Optional[Any]:
        """Appel API avec retry exponential backoff"""
        
        backoff = INITIAL_BACKOFF
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if stream:
                    return self._stream_response(model, system, messages, max_tokens)
                else:
                    response = self.client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=0.2,
                        system=system,
                        messages=messages
                    )
                    return response
                
            except RateLimitError:
                print(f"   ⏳ Rate limit, attente {backoff}s (tentative {attempt}/{MAX_RETRIES})")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                
            except APIConnectionError:
                print(f"   🔌 Erreur connexion, retry dans {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                
            except APIError as e:
                if hasattr(e, 'status_code') and e.status_code >= 500:
                    print(f"   🔥 Erreur serveur, retry dans {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    raise
        
        return None
    
    def _stream_response(
        self, 
        model: str, 
        system: str, 
        messages: list,
        max_tokens: int
    ) -> Tuple[str, int, int]:
        """Stream la réponse et retourne (texte, input_tokens, output_tokens)"""
        
        full_text = ""
        input_tokens = 0
        output_tokens = 0
        
        with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=0.2,
            system=system,
            messages=messages
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                self._emit_stream(text)
            
            # Récupérer les tokens après le stream
            final_message = stream.get_final_message()
            input_tokens = final_message.usage.input_tokens
            output_tokens = final_message.usage.output_tokens
        
        return full_text, input_tokens, output_tokens
    
    # ========================================
    # EXTRACTION RÉPONSE (ROBUSTE)
    # ========================================

    def _extract_text_from_response(self, response: Any) -> Tuple[str, List[str]]:
        """Extrait tout le texte d'une réponse Anthropic, même si des blocs non-text sont présents."""
        if response is None:
            return "", []

        non_text: List[str] = []
        parts: List[str] = []

        content = getattr(response, "content", None)
        if not content:
            return "", []

        # response.content peut être une liste de blocs (text/tool_use/etc.)
        for block in content:
            btype = getattr(block, "type", None)
            text = getattr(block, "text", None)

            if isinstance(text, str) and text:
                parts.append(text)
                continue

            # Certains SDK renvoient des dicts
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                else:
                    non_text.append(str(block.get("type") or "unknown"))
                continue

            non_text.append(str(btype or block.__class__.__name__))

        return "".join(parts), non_text

    # ========================================
    # NETTOYAGE DU CODE
    # ========================================

    def _clean_code(self, raw: str) -> str:
        """Nettoie le code des artefacts markdown et texte."""
        if not raw:
            return ""

        code = raw.strip()

        # Supprimer les fences markdown (même si le modèle n'est pas censé en produire)
        if "```" in code:
            lines = code.split("\n")
            out: List[str] = []
            in_fence = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence or "```" not in line:
                    out.append(line)
            code = "\n".join(out).strip()

        # Couper les préambules bavards (robuste)
        bad_prefixes = (
            "voici", "le code", "j'ai créé", "bien sûr", "here is", "here's", "certainly", "sure,", "voilà",
            "explication", "description", "résumé",
        )
        lines = code.split("\n")
        if lines:
            first = lines[0].strip().lower()
            if any(first.startswith(p) for p in bad_prefixes):
                for i, line in enumerate(lines):
                    l = line.lstrip()
                    if l.startswith(("#", "import ", "from ", "class ", "def ", "if __name__", "const ", "function ", "<!DOCTYPE", "<html", "/*")):
                        code = "\n".join(lines[i:]).strip()
                        break

        return code.strip()
    
    # ========================================
    # AUTO-REPAIR
    # ========================================
    
    def _auto_repair(self, code: str, error: str, language: str) -> Optional[str]:
        """Tente de réparer automatiquement le code avec Claude"""
        print(f"\n🔧 AUTO-REPAIR : Tentative de correction...")
        
        repair_prompt = self._build_repair_prompt(code, error, language)
        
        response = self._call_api(
            model=CLAUDE_MODELS[0],
            system="Tu es un expert en débogage. Corrige les erreurs de syntaxe.",
            messages=[{"role": "user", "content": repair_prompt}],
            max_tokens=8192
        )

        if response:
            raw_text, non_text = self._extract_text_from_response(response)
            if non_text:
                self.memory["errors"].append({
                    "timestamp": datetime.now().isoformat(),
                    "specs": "(auto_repair non-text blocks)",
                    "error": f"Réponse contenait des blocs non-text: {non_text}"
                })
            repaired = self._clean_code(raw_text)
            is_valid, new_error = self._validate_syntax(repaired, language)

            if is_valid:
                print(f"   ✅ Code réparé avec succès!")
                self.memory["repairs"].append({
                    "timestamp": datetime.now().isoformat(),
                    "original_error": error,
                    "success": True
                })
                self._save_memory()
                return repaired
            else:
                print(f"   ❌ Réparation échouée: {new_error}")

        return None
    
    # ========================================
    # GÉNÉRATION PRINCIPALE
    # ========================================
    
    def generate(
        self, 
        specifications: str, 
        language: str = "python",
        use_cache: bool = True,
        auto_repair: bool = True,
        execute: bool = False,
        stream: bool = False,
        template: str = None
    ) -> CodeResult:
        """
        Génère du code avec toutes les options v3.0
        
        Args:
            specifications: Description du code
            language: Langage cible
            use_cache: Utiliser le cache
            auto_repair: Réparer automatiquement si erreur syntaxe
            execute: Exécuter le code dans sandbox
            stream: Activer le streaming (callbacks requis)
            template: Utiliser un template prédéfini
        
        Returns:
            CodeResult avec toutes les métadonnées
        """
        
        start_time = time.time()
        result = CodeResult(success=False)
        
        # 1. Template
        if template and template in self.templates:
            print(f"\n📦 Utilisation du template: {template}")
            tmpl = self.templates[template]
            specifications = f"{tmpl['description']}\n\nSPÉCIFICATIONS :\n{specifications}"
        
        # 2. Cache
        cache_key = self._get_cache_key(specifications, language)
        if use_cache and cache_key in self.cache:
            cached = self.cache[cache_key]
            print(f"\n💾 CACHE HIT")
            
            result.success = True
            result.code = cached["code"]
            result.model_used = cached["model"] + " (cached)"
            result.from_cache = True
            result.stats = cached.get("stats", {})
            result.quality_score = cached.get("quality_score", 0)
            
            return result
        
        # 3. Prompts
        system_prompt = self._build_system_prompt(language)
        user_prompt = self._build_user_prompt(specifications, language)
        
        print(f"\n{'='*70}")
        print(f"🧠 EXPERT CODEUR CLAUDE v3.0")
        print(f"{'='*70}")
        print(f"📋 {specifications[:80]}...")
        print(f"💻 {language}")
        
        # 4. Génération
        for model_idx, model_name in enumerate(CLAUDE_MODELS, 1):
            print(f"\n[{model_idx}/{len(CLAUDE_MODELS)}] {model_name}")
            
            try:
                if stream:
                    raw_code, input_tokens, output_tokens = self._stream_response(
                        model_name, system_prompt, 
                        [{"role": "user", "content": user_prompt}],
                        8192
                    )
                    tokens_used = input_tokens + output_tokens
                else:
                    response = self._call_api(
                        model=model_name,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}]
                    )

                    raw_text, non_text = self._extract_text_from_response(response)
                    if not raw_text.strip():
                        print(f"   ❌ Réponse vide")
                        if non_text:
                            print(f"   ⚠️ Blocs non-text: {non_text}")
                        continue

                    raw_code = raw_text
                    tokens_used = response.usage.input_tokens + response.usage.output_tokens

                    # Note: on garde une trace si le modèle renvoie des blocs non-text
                    if non_text:
                        result.warnings.append(f"Réponse contenait des blocs non-text: {non_text}")
                
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
                continue
            
            # 5. Nettoyage
            code = self._clean_code(raw_code)
            
            # 6. Validation
            is_valid, error_msg = self._validate_syntax(code, language)
            
            if not is_valid:
                print(f"   ⚠️ Erreur syntaxe: {error_msg}")
                
                if auto_repair:
                    repaired = self._auto_repair(code, error_msg, language)
                    if repaired:
                        code = repaired
                        is_valid = True
                
                if not is_valid:
                    continue
            
            print(f"   ✅ Syntaxe valide")
            
            # 7. Analyse qualité
            quality_score, quality_level = CodeAnalyzer.score_quality(code, language, is_valid)
            analysis = CodeAnalyzer.analyze(code, language)
            
            # 8. Succès
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            result.success = True
            result.code = code
            result.model_used = model_name
            result.tokens_used = tokens_used
            result.quality_score = quality_score
            result.quality_level = quality_level
            result.warnings = analysis.security_issues + analysis.performance_issues
            
            result.stats = {
                "lines": len(code.splitlines()),
                "chars": len(code),
                "tokens": tokens_used,
                "time_ms": elapsed_ms,
                "model_attempt": model_idx,
                "complexity": analysis.complexity_score,
                "functions": analysis.metrics.get("functions", 0),
                "classes": analysis.metrics.get("classes", 0),
                "language": language,
            }
            
            # 9. Exécution si demandée
            if execute and language in ("python", "javascript"):
                print(f"\n🧪 Exécution dans sandbox...")
                result.execution_result = CodeSandbox.execute(code, language)
                if result.execution_result["success"]:
                    print(f"   ✅ Exécution réussie ({result.execution_result['execution_time']:.2f}s)")
                else:
                    print(f"   ❌ Erreur: {result.execution_result['error'][:100]}")
            
            # 10. Mise à jour mémoire
            self.last_code = code
            self.last_specs = specifications
            self.memory["total_tokens"] += tokens_used
            self.memory["total_time_ms"] += elapsed_ms
            self.memory["model_usage"][model_name] = self.memory["model_usage"].get(model_name, 0) + 1
            self.memory["quality_scores"].append(quality_score)
            
            self.memory["generations"].append({
                "timestamp": datetime.now().isoformat(),
                "model": model_name,
                "specs": specifications[:200],
                "language": language,
                "quality_score": quality_score,
                **result.stats
            })
            self._save_memory()
            
            # 11. Cache
            self.cache[cache_key] = {
                "code": code,
                "model": model_name,
                "timestamp": datetime.now().isoformat(),
                "stats": result.stats,
                "quality_score": quality_score
            }
            self._save_cache()
            
            # 12. Contexte
            self.conversation_context.append({"role": "user", "content": specifications})
            self.conversation_context.append({
                "role": "assistant", 
                "content": f"[CODE {language.upper()} - {result.stats['lines']} lignes]"
            })
            if len(self.conversation_context) > 10:
                self.conversation_context = self.conversation_context[-10:]
            
            print(f"\n{'='*70}")
            print(f"✅ CODE GÉNÉRÉ AVEC SUCCÈS")
            print(f"{'='*70}")
            print(f"📊 {result.stats['lines']} lignes | {tokens_used} tokens | {elapsed_ms}ms")
            print(f"⭐ Qualité: {quality_score:.0f}/100 ({quality_level.name})")
            
            if result.warnings:
                print(f"⚠️ Avertissements: {len(result.warnings)}")
            
            return result
        
        # Échec total
        result.error = "Tous les modèles ont échoué"
        self.memory["errors"].append({
            "timestamp": datetime.now().isoformat(),
            "specs": specifications[:200],
            "error": result.error
        })
        self._save_memory()
        
        return result
    
    # Alias pour compatibilité
    def generate_code(self, specifications: str, language: str = "python", **kwargs) -> dict:
        """Alias pour compatibilité avec v2"""
        result = self.generate(specifications, language, **kwargs)
        return result.to_dict()
    
    # ========================================
    # GÉNÉRATION MULTI-FICHIERS
    # ========================================
    
    def generate_project(
        self, 
        specifications: str, 
        structure: Dict[str, str] = None
    ) -> Dict[str, CodeResult]:
        """
        Génère un projet multi-fichiers
        
        Args:
            specifications: Description du projet
            structure: Dict {filename: description}
            
        Returns:
            Dict {filename: CodeResult}
        """
        results = {}
        
        if not structure:
            # Structure par défaut
            structure = {
                "main.py": "Point d'entrée principal",
                "utils.py": "Fonctions utilitaires",
                "config.py": "Configuration et constantes"
            }
        
        print(f"\n{'='*70}")
        print(f"📁 GÉNÉRATION PROJET MULTI-FICHIERS")
        print(f"{'='*70}")
        print(f"📋 {specifications[:80]}...")
        print(f"📦 {len(structure)} fichiers à générer")
        
        for filename, file_desc in structure.items():
            print(f"\n--- {filename} ---")
            
            file_specs = f"""Projet: {specifications}

Fichier: {filename}
Description: {file_desc}

Ce fichier fait partie d'un projet plus large. 
Assure-toi qu'il s'intègre bien avec les autres fichiers."""
            
            # Détecter le langage depuis l'extension
            ext = Path(filename).suffix.lower()
            lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript", ".html": "html", ".css": "css"}
            language = lang_map.get(ext, "python")
            
            result = self.generate(file_specs, language, use_cache=False)
            results[filename] = result
            
            if not result.success:
                print(f"   ❌ Échec: {result.error}")
        
        success_count = sum(1 for r in results.values() if r.success)
        print(f"\n✅ {success_count}/{len(structure)} fichiers générés")
        
        return results
    
    # ========================================
    # AMÉLIORATION DE CODE EXISTANT
    # ========================================
    
    def improve(
        self, 
        code: str, 
        instructions: str = "Améliore ce code",
        language: str = "python"
    ) -> CodeResult:
        """
        Améliore du code existant
        
        Args:
            code: Code à améliorer
            instructions: Instructions d'amélioration
            language: Langage du code
        
        Returns:
            CodeResult avec le code amélioré et le diff
        """
        
        specs = f"""AMÉLIORATION DE CODE EXISTANT

INSTRUCTIONS : {instructions}

CODE ACTUEL :
```
{code}
```

CONTRAINTES :
- Garde la même logique et fonctionnalité
- Améliore la qualité, lisibilité, performance
- Ajoute la gestion d'erreurs si manquante
- Respecte les conventions du langage

Génère le code amélioré complet :"""
        
        result = self.generate(specs, language, use_cache=False)
        
        if result.success:
            # Générer le diff
            original_lines = code.splitlines(keepends=True)
            improved_lines = result.code.splitlines(keepends=True)
            
            diff = difflib.unified_diff(
                original_lines, improved_lines,
                fromfile='original', tofile='improved',
                lineterm=''
            )
            result.diff = ''.join(diff)
        
        return result
    
    # ========================================
    # UTILITAIRES
    # ========================================
    
    def analyze(self, code: str, language: str = "python") -> AnalysisResult:
        """Analyse un code existant"""
        return CodeAnalyzer.analyze(code, language)
    
    def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Exécute du code dans la sandbox"""
        return CodeSandbox.execute(code, language)

    def write_files(self, files: Dict[str, str], base_dir: str, overwrite: bool = False) -> Dict[str, str]:
        """Écrit des fichiers de manière atomique et sûre (évite les bugs de guillemets via file_manager)."""
        base = Path(base_dir).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)

        results: Dict[str, str] = {}
        for rel_path, content in (files or {}).items():
            try:
                p = Path(rel_path)
                if p.is_absolute() or ".." in p.parts:
                    results[rel_path] = "SKIP: chemin interdit"
                    continue

                out_path = (base / p).resolve()
                if base not in out_path.parents and out_path != base:
                    results[rel_path] = "SKIP: path traversal"
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)
                if out_path.exists() and not overwrite:
                    results[rel_path] = "SKIP: existe déjà"
                    continue

                # écriture atomique
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=str(out_path.parent),
                    suffix=out_path.suffix or ".tmp",
                ) as tf:
                    tf.write(content or "")
                    tmp_name = tf.name

                os.replace(tmp_name, str(out_path))
                results[rel_path] = f"OK: {out_path}"
            except Exception as e:
                results[rel_path] = f"ERR: {e}"

        return results

    def clear_context(self):
        """Réinitialise le contexte de conversation"""
        self.conversation_context = []
        print("🔄 Contexte réinitialisé")

    def clear_cache(self):
        """Vide le cache"""
        self.cache = OrderedDict()
        self._save_cache()
        print("🗑️ Cache vidé")

    def add_template(self, name: str, template: Dict):
        """Ajoute un template personnalisé"""
        self.templates[name] = template
        self._save_json(TEMPLATES_FILE, self.templates)
        print(f"📦 Template '{name}' ajouté")
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques détaillées"""
        gens = self.memory.get("generations", [])
        errs = self.memory.get("errors", [])
        repairs = self.memory.get("repairs", [])
        quality_scores = self.memory.get("quality_scores", [])
        total = len(gens) + len(errs)
        
        model_usage = self.memory.get("model_usage", {})
        top_model = max(model_usage, key=model_usage.get) if model_usage else "N/A"
        
        avg_quality = sum(quality_scores) / max(1, len(quality_scores))
        avg_lines = sum(g.get("lines", 0) for g in gens) / max(1, len(gens))
        avg_tokens = sum(g.get("tokens", 0) for g in gens) / max(1, len(gens))
        avg_time = self.memory.get("total_time_ms", 0) / max(1, len(gens))
        
        # Estimation coût (Claude Sonnet 4)
        # Input: $3/1M tokens, Output: $15/1M tokens (estimation)
        total_tokens = self.memory.get("total_tokens", 0)
        cost = (total_tokens / 1_000_000) * 9  # Moyenne
        
        return {
            "total_generations": len(gens),
            "total_errors": len(errs),
            "total_repairs": len(repairs),
            "success_rate": (len(gens) / max(1, total)) * 100,
            "repair_success_rate": sum(1 for r in repairs if r.get("success", False)) / max(1, len(repairs)) * 100,
            "total_tokens": total_tokens,
            "total_time_ms": self.memory.get("total_time_ms", 0),
            "estimated_cost_usd": cost,
            "avg_quality": avg_quality,
            "avg_lines": avg_lines,
            "avg_tokens": avg_tokens,
            "avg_time_ms": avg_time,
            "top_model": top_model,
            "model_usage": model_usage,
            "cache_size": len(self.cache),
            "templates_count": len(self.templates)
        }


# ========================================
# SINGLETON
# ========================================

_EXPERT_INSTANCE = None

def get_expert() -> ClaudeExpertCoder:
    """Retourne l'instance unique de l'expert"""
    global _EXPERT_INSTANCE
    if _EXPERT_INSTANCE is None:
        _EXPERT_INSTANCE = ClaudeExpertCoder()
    return _EXPERT_INSTANCE


# ========================================
# FONCTIONS TOOLS (pour Gemini/Cypher)
# ========================================

def expert_coder_tool(specifications: str, language: str = "python") -> str:
    """Fonction tool pour intégration Gemini (retourne uniquement le code)."""
    try:
        result = get_expert().generate(specifications, language)
        if result.success:
            return result.code
        return f"ERREUR_EXPERT: {result.error}"
    except Exception as e:
        return f"ERREUR_EXPERT: {e}"


def expert_coder_payload_tool(specifications: str, language: str = "python") -> str:
    """Retourne un JSON base64 (anti-guillemets) pour éviter les échecs de création de fichier via d'autres outils."""
    try:
        result = get_expert().generate(specifications, language)
        payload = result.to_base64_payload()
        payload["language"] = language
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "version": "3.1"}, ensure_ascii=False)


def expert_generate_file_tool(
    specifications: str,
    language: str = "python",
    output_path: str = "",
    overwrite: bool = False,
) -> str:
    """Génère et écrit directement un fichier sur disque (bypass total de file_manager)."""
    try:
        expert = get_expert()
        result = expert.generate(specifications, language)
        if not result.success:
            return f"ERREUR_EXPERT: {result.error}"

        lang = Language.from_string(language)
        ext = lang.value[1]

        if not output_path:
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", specifications.strip().lower())[:40].strip("_")
            if not safe_name:
                safe_name = "generated"
            output_path = str(Path(DOCUMENTS_PATH) / f"{safe_name}{ext}")

        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not overwrite:
            return f"ERREUR_EXPERT: Le fichier existe déjà: {out}"

        # écriture atomique
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(out.parent),
            suffix=out.suffix or ".tmp",
        ) as tf:
            tf.write(result.code)
            tmp_name = tf.name
        os.replace(tmp_name, str(out))

        return f"OK_EXPERT: Fichier créé -> {out}"
    except Exception as e:
        return f"ERREUR_EXPERT: {e}"


def expert_improve_tool(code: str, instructions: str, language: str = "python") -> str:
    """Améliore du code existant"""
    try:
        result = get_expert().improve(code, instructions, language)
        if result.success:
            return result.code
        return f"ERREUR_EXPERT: {result.error}"
    except Exception as e:
        return f"ERREUR_EXPERT: {e}"


def expert_analyze_tool(code: str, language: str = "python") -> str:
    """Analyse du code"""
    try:
        analysis = get_expert().analyze(code, language)

        output = ["📊 ANALYSE DE CODE", ""]
        output.append(f"Complexité: {analysis.complexity_score:.0f}")
        output.append(f"Lignes: {analysis.metrics.get('code_lines', 0)}")
        output.append(f"Fonctions: {analysis.metrics.get('functions', 0)}")
        output.append(f"Classes: {analysis.metrics.get('classes', 0)}")

        if analysis.security_issues:
            output.append("\n🔒 SÉCURITÉ:")
            for issue in analysis.security_issues:
                output.append(f"  ⚠️ {issue}")

        if analysis.performance_issues:
            output.append("\n⚡ PERFORMANCE:")
            for issue in analysis.performance_issues:
                output.append(f"  ⚠️ {issue}")

        if analysis.suggestions:
            output.append("\n💡 SUGGESTIONS:")
            for sug in analysis.suggestions:
                output.append(f"  • {sug}")

        return "\n".join(output)
    except Exception as e:
        return f"ERREUR_ANALYSE: {e}"


def expert_stats() -> str:
    """Retourne les stats formatées"""
    try:
        stats = get_expert().get_stats()

        return f"""📊 STATISTIQUES EXPERT CODEUR v3.0

✅ Générations : {stats['total_generations']}
❌ Erreurs : {stats['total_errors']}
🔧 Réparations : {stats['total_repairs']}
📈 Taux succès : {stats['success_rate']:.1f}%

⭐ Qualité moyenne : {stats['avg_quality']:.0f}/100
🪙 Tokens : {stats['total_tokens']:,}
💰 Coût estimé : ${stats['estimated_cost_usd']:.4f}
⏱️ Temps total : {stats['total_time_ms']/1000:.1f}s

📊 Moyennes :
  • Lignes/code : {stats['avg_lines']:.0f}
  • Tokens/génération : {stats['avg_tokens']:.0f}
  • Temps/génération : {stats['avg_time_ms']:.0f}ms

🤖 Modèle favori : {stats['top_model']}
💾 Cache : {stats['cache_size']} entrées
📦 Templates : {stats['templates_count']}
"""
    except Exception as e:
        return f"Erreur stats : {e}"



# ========================================
# TOOL DECLARATIONS
# ========================================

EXPERT_CODER_TOOL_DECLARATION = {
    "name": "expert_coder",
    "description": """🧠 CERVEAU SECONDAIRE : Expert Codeur Claude v3.0

⚡ CAPACITÉS :
- Génération de code production-ready
- Auto-réparation des erreurs syntaxe
- Analyse qualité et sécurité
- Exécution sandbox
- Templates prédéfinis

🎯 QUAND UTILISER :
- Applications/programmes complexes
- Interfaces graphiques (Tkinter)
- Scripts > 20 lignes
- Web scraping, automatisation

⚠️ NE JAMAIS modifier le code reçu""",
    "parameters": {
        "type": "object",
        "properties": {
            "specifications": {
                "type": "string",
                "description": "Description ULTRA-DÉTAILLÉE du code"
            },
            "language": {
                "type": "string",
                "description": "Langage cible",
                "default": "python",
                "enum": ["python", "javascript", "typescript", "java", "c++", "html", "css", "rust", "go", "bash"]
            }
        },
        "required": ["specifications"]
    }
}

EXPERT_CODER_PAYLOAD_TOOL_DECLARATION = {
    "name": "expert_coder_payload",
    "description": """📦 Retourne un payload JSON base64

Utile quand un autre agent/outillage (ex: file_manager) casse sur les guillemets.
Le champ code_b64 doit être décodé en UTF-8.""",
    "parameters": {
        "type": "object",
        "properties": {
            "specifications": {"type": "string"},
            "language": {"type": "string", "default": "python"}
        },
        "required": ["specifications"]
    }
}

EXPERT_GENERATE_FILE_TOOL_DECLARATION = {
    "name": "expert_generate_file",
    "description": """📝 Génère puis écrit un fichier directement sur disque.

Bypass total de file_manager (et donc des bugs de guillemets).""",
    "parameters": {
        "type": "object",
        "properties": {
            "specifications": {"type": "string"},
            "language": {"type": "string", "default": "python"},
            "output_path": {"type": "string", "description": "Chemin complet du fichier à créer", "default": ""},
            "overwrite": {"type": "boolean", "default": False}
        },
        "required": ["specifications"]
    }
}

EXPERT_IMPROVE_TOOL_DECLARATION = {
    "name": "expert_improve",
    "description": """🔧 Améliore du code existant

Optimise, corrige, ajoute gestion d'erreurs.
Retourne le code amélioré + diff.""",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code à améliorer"},
            "instructions": {"type": "string", "description": "Instructions d'amélioration"},
            "language": {"type": "string", "default": "python"}
        },
        "required": ["code"]
    }
}

EXPERT_ANALYZE_TOOL_DECLARATION = {
    "name": "expert_analyze",
    "description": """📊 Analyse du code

Détecte problèmes de sécurité, performance, style.
Retourne un rapport détaillé.""",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code à analyser"},
            "language": {"type": "string", "default": "python"}
        },
        "required": ["code"]
    }
}


# ========================================
# TEST
# ========================================

if __name__ == "__main__":
    print("🧪 TEST EXPERT CODEUR CLAUDE v3.0\n")
    
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY manquante")
        exit(1)
    
    expert = ClaudeExpertCoder()
    
    # Test génération simple
    result = expert.generate(
        "Script Python qui affiche les nombres de 1 à 10 avec leur carré",
        "python",
        execute=True
    )
    
    if result.success:
        print("\n" + "="*50)
        print(result.code)
        print("="*50)
        
        if result.execution_result:
            print(f"\n📤 Output:\n{result.execution_result['output']}")
        
        print(f"\n⭐ Qualité: {result.quality_score:.0f}/100")
        print("\n" + expert_stats())
    else:
        print(f"❌ {result.error}")