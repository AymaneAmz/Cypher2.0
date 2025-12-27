# Configuration du Web Navigator (Computer Use)

Ce document explique comment configurer le module de navigation web autonome de Cypher.

## Dépendances requises

### 1. Playwright (avec Firefox)
```bash
pip install playwright
playwright install firefox
```

**Important** : Après l'installation de `playwright`, vous devez installer les navigateurs avec la commande `playwright install chromium`.

### 2. Pillow (pour le traitement d'images)
```bash
pip install Pillow
```

### 3. google-genai (pour Gemini Vision)
```bash
pip install google-genai
```

Assurez-vous que votre variable d'environnement `GEMINI_API_KEY` est définie dans votre fichier `.env`.

## Utilisation

Une fois les dépendances installées, le module `web_navigator` est automatiquement disponible dans Cypher.

### Exemples de commandes vocales :

- "Navigue vers amazon.com"
- "Va sur Google et recherche 'Python tutorial'"
- "Clique sur le bouton 'Ajouter au panier' sur la page actuelle"
- "Remplis le formulaire avec mon nom et email"

## Interface Agent Vision

Quand le Web Navigator est actif, une fenêtre "Agent Vision" s'affiche automatiquement. Cette fenêtre montre :
- **L'image en temps réel** : Ce que l'IA voit dans le navigateur
- **Les logs d'actions** : Les actions en cours d'exécution
- **Le feedback visuel** : Un point rouge indique où l'IA va cliquer

## Sécurité

Le module détecte automatiquement les actions critiques (paiement, validation) et demande une confirmation avant de les exécuter.

## Dépannage

### Erreur "Playwright n'est pas installé"
- Vérifiez que `playwright` est installé : `pip list | grep playwright`
- Installez les navigateurs : `playwright install chromium`

### Erreur "Gemini non disponible"
- Vérifiez que `GEMINI_API_KEY` est défini dans votre `.env`
- Vérifiez que `google-genai` est installé : `pip list | grep google-genai`

### Le navigateur ne s'ouvre pas
- Vérifiez que Playwright est correctement installé
- Essayez de lancer manuellement : `python -c "from playwright.sync_api import sync_playwright; sync_playwright().start()"`

