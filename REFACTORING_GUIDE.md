# Guide de Refactorisation - main.py

## 📋 Résumé

Ce document décrit comment intégrer tous les nouveaux modules créés dans `main.py` pour réduire sa taille de ~4600 lignes à ~1500-2000 lignes.

## ✅ Modules créés

1. ✅ `core/tool_declarations.py` - Toutes les déclarations de tools
2. ✅ `modules/system_tools.py` - Fonctions système (network, process, power, windows, system_control, system_optimize)
3. ✅ `modules/time_management.py` - Gestion du temps (stopwatch, timer, agenda, get_time, get_date, format_duration)
4. ✅ `core/tts_utils.py` - Utilitaires TTS (generate_ssml, clean_text_for_tts, shorten_for_tts)
5. ✅ `core/utils.py` - Fonctions utilitaires (get_weather, get_folder_size, format_bytes)
6. ✅ `modules/app_launcher.py` - Lancement d'applications et sites web (open_app, open_website)

## 📝 Instructions d'intégration dans main.py

### 1. Imports à ajouter au début de main.py

```python
# Imports des nouveaux modules
from core.tool_declarations import get_all_tool_declarations
from modules.system_tools import (
    network_manager,
    window_manager,
    system_control,
    process_manager,
    power_control,
    system_optimize
)
from modules.time_management import (
    get_time,
    get_date,
    format_duration,
    manage_stopwatch,
    manage_timer,
    manage_agenda,
    get_timer_end,
    get_timer_alert_triggered,
    set_timer_alert_triggered
)
from core.tts_utils import generate_ssml, clean_text_for_tts, shorten_for_tts
from core.utils import get_weather, get_folder_size, format_bytes
from modules.app_launcher import open_app, open_website
```

### 2. Dans `AudioLoop.__init__`, remplacer la création des tools

**AVANT** (lignes ~319-967):
```python
# Tools de Cypher
get_time = { ... }
# ... toutes les déclarations ...
tools = [ ... ]
```

**APRÈS**:
```python
from core.tool_declarations import get_all_tool_declarations
tools = get_all_tool_declarations()
```

### 3. Remplacer les méthodes dans la classe AudioLoop

#### 3.1 Méthodes système (supprimer et utiliser les imports)

**SUPPRIMER** ces méthodes de `AudioLoop` :
- `_network_manager` → utiliser `modules.system_tools.network_manager`
- `_window_manager` → utiliser `modules.system_tools.window_manager`
- `_system_control` → utiliser `modules.system_tools.system_control`
- `_process_manager` → utiliser `modules.system_tools.process_manager`
- `_power_control` → utiliser `modules.system_tools.power_control`
- `_system_optimize` → utiliser `modules.system_tools.system_optimize`

#### 3.2 Méthodes temps (supprimer et utiliser les imports)

**SUPPRIMER** :
- `_get_time` → utiliser `modules.time_management.get_time`
- `_get_date` → utiliser `modules.time_management.get_date`
- `_format_duration` → utiliser `modules.time_management.format_duration`
- `_manage_stopwatch` → utiliser `modules.time_management.manage_stopwatch`
- `_manage_timer` → utiliser `modules.time_management.manage_timer`
- `_manage_agenda` → utiliser `modules.time_management.manage_agenda`

#### 3.3 Méthodes TTS (remplacer)

**REMPLACER** :
- `_generate_ssml(self, text)` → utiliser `core.tts_utils.generate_ssml(text, voice_name, rate, pitch)`
  - Dans le code, remplacer `self._generate_ssml(text)` par `generate_ssml(text, AZURE_VOICE_NAME, TTS_RATE, TTS_PITCH)`
- `_clean_text_for_tts` → utiliser `core.tts_utils.clean_text_for_tts(text)`
- `_shorten_for_tts` → utiliser `core.tts_utils.shorten_for_tts(text)`

#### 3.4 Méthodes utilitaires

**REMPLACER** :
- `_get_weather` → utiliser `core.utils.get_weather(location, day)`
- `_get_folder_size` → utiliser `core.utils.get_folder_size(path)`
- `_format_bytes` → utiliser `core.utils.format_bytes(bytes_size)`

#### 3.5 Méthodes app launcher

**REMPLACER** :
- `_open_app` → utiliser `modules.app_launcher.open_app(application)`
- `_open_website` → utiliser `modules.app_launcher.open_website(url_or_name)`

### 4. Mettre à jour FUNCTION_MAP

**AVANT** (ligne ~4524):
```python
FUNCTION_MAP = {
    "get_time": AudioLoop._get_time,
    "get_date": AudioLoop._get_date,
    # ...
}
```

**APRÈS**:
```python
FUNCTION_MAP = {
    "get_time": get_time,
    "get_date": get_date,
    "get_weather": get_weather,
    "manage_stopwatch": manage_stopwatch,
    "manage_timer": manage_timer,
    "open_app": open_app,
    "open_website": open_website,
    "window_manager": window_manager,
    "system_control": system_control,
    "process_manager": process_manager,
    "power_control": power_control,
    "system_optimize": system_optimize,
    "network_manager": network_manager,
    "manage_agenda": manage_agenda,
    # ... autres fonctions existantes ...
}
```

### 5. Variables globales à supprimer

**SUPPRIMER** (lignes ~130-135):
```python
STOPWATCH_START = None
STOPWATCH_ACCUM = 0.0
STOPWATCH_RUNNING = False
TIMER_ALERT_TRIGGERED = False
TIMER_END = None
```
*(Ces variables sont maintenant dans `modules/time_management.py`)*

**RECHERCHER et REMPLACER** les utilisations de ces variables :
- Dans le code qui vérifie le timer (ligne ~3508), remplacer :
  ```python
  global TIMER_END, TIMER_ALERT_TRIGGERED
  if TIMER_END and ...:
  ```
  Par :
  ```python
  from modules.time_management import get_timer_end, get_timer_alert_triggered, set_timer_alert_triggered
  timer_end = get_timer_end()
  if timer_end and ...:
  ```

### 6. Fonctions `_file_manager` et autres

Pour `_file_manager`, `_document_manager`, `_email_manager`, `_memory_manager`, `_execute_python`, `_manage_tasks` :
- Ces fonctions sont encore dans `main.py` mais peuvent être extraites plus tard dans des modules séparés si nécessaire.
- Pour l'instant, on peut les garder dans `main.py` car elles sont spécifiques ou plus complexes.

**NOTE**: `_file_manager` utilise `_get_folder_size` et `_format_bytes` qui doivent être remplacés :
```python
# Dans _file_manager, remplacer :
AudioLoop._get_folder_size(source_path)  → get_folder_size(source_path)
AudioLoop._format_bytes(size_bytes)      → format_bytes(size_bytes)
```

### 7. Références dans le code

**RECHERCHER et REMPLACER** toutes les références aux anciennes méthodes :

1. `self._generate_ssml(text)` → `generate_ssml(text, AZURE_VOICE_NAME, TTS_RATE, TTS_PITCH)`
2. `AudioLoop._format_duration(...)` → `format_duration(...)`
3. `AudioLoop._get_time(...)` → `get_time(...)`
4. `AudioLoop._get_date(...)` → `get_date(...)`
5. `AudioLoop._get_weather(...)` → `get_weather(...)`

### 8. Checklist de vérification

- [ ] Tous les imports sont ajoutés
- [ ] `get_all_tool_declarations()` est utilisé au lieu des déclarations locales
- [ ] `FUNCTION_MAP` est mis à jour avec les nouvelles fonctions
- [ ] Les variables globales STOPWATCH/TIMER sont supprimées et remplacées par les fonctions du module
- [ ] Toutes les références aux anciennes méthodes sont remplacées
- [ ] Les méthodes supprimées sont bien supprimées du code
- [ ] Tester que l'application démarre correctement
- [ ] Tester quelques fonctionnalités pour vérifier que tout fonctionne

## 📊 Résultat attendu

- **Avant** : ~4610 lignes
- **Après** : ~1500-2000 lignes (réduction de ~60-65%)
- **Modules créés** : 8 nouveaux modules
- **Maintenabilité** : ⬆️ Améliorée (séparation des responsabilités)
- **Testabilité** : ⬆️ Améliorée (modules isolés)

## 🔄 Prochaines étapes (optionnel)

Les modules suivants peuvent être créés plus tard pour réduire encore plus `main.py` :
- `modules/python_executor.py` - Exécution Python (nécessite DESKTOP_REAL, DOCUMENTS_REAL, IMAGES_REAL)
- `modules/document_manager.py` - Gestion RAG/ChromaDB
- `modules/email_manager.py` - Gestion Outlook
- `modules/memory_manager.py` - Gestion mémoire JSON
- `modules/file_manager.py` - Gestion fichiers (partiellement fait)

