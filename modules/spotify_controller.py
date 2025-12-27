"""
🎵 SPOTIFY CONTROLLER v1.0 - Contrôle Ultra-Complet de Spotify
==============================================================
Module de gestion complète de l'application Spotify sur PC.
Inclut: lecture, playlists, recherche, queue, appareils, favoris, etc.

Auteur: Cypher AI Assistant
"""

import os
import sys
import json
import time
import subprocess
import webbrowser
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import threading

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
    print("⚠️ [SPOTIFY] spotipy non installé. Installez avec: pip install spotipy")

try:
    from pynput.keyboard import Key, Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("⚠️ [SPOTIFY] pynput non installé. Installez avec: pip install pynput")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class SpotifyTrack:
    """Représente un morceau Spotify"""
    id: str
    name: str
    artists: List[str]
    album: str
    album_id: str
    duration_ms: int
    uri: str
    is_playing: bool = False
    progress_ms: int = 0
    image_url: Optional[str] = None
    popularity: int = 0
    explicit: bool = False
    
    @property
    def duration_str(self) -> str:
        """Durée formatée en MM:SS"""
        mins, secs = divmod(self.duration_ms // 1000, 60)
        return f"{mins}:{secs:02d}"
    
    @property
    def progress_str(self) -> str:
        """Progression formatée en MM:SS"""
        mins, secs = divmod(self.progress_ms // 1000, 60)
        return f"{mins}:{secs:02d}"
    
    @property
    def artists_str(self) -> str:
        """Artistes en string"""
        return ", ".join(self.artists)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "artists": self.artists,
            "album": self.album,
            "duration": self.duration_str,
            "uri": self.uri,
            "is_playing": self.is_playing,
            "progress": self.progress_str,
            "popularity": self.popularity
        }


@dataclass
class SpotifyPlaylist:
    """Représente une playlist Spotify"""
    id: str
    name: str
    owner: str
    tracks_count: int
    uri: str
    image_url: Optional[str] = None
    public: bool = True
    collaborative: bool = False
    description: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "owner": self.owner,
            "tracks_count": self.tracks_count,
            "uri": self.uri,
            "public": self.public
        }


@dataclass
class SpotifyDevice:
    """Représente un appareil Spotify"""
    id: str
    name: str
    type: str
    is_active: bool
    volume_percent: int
    is_restricted: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "is_active": self.is_active,
            "volume": self.volume_percent
        }


@dataclass 
class SpotifyAlbum:
    """Représente un album Spotify"""
    id: str
    name: str
    artists: List[str]
    release_date: str
    total_tracks: int
    uri: str
    image_url: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "artists": self.artists,
            "release_date": self.release_date,
            "total_tracks": self.total_tracks,
            "uri": self.uri
        }


@dataclass
class SpotifyArtist:
    """Représente un artiste Spotify"""
    id: str
    name: str
    genres: List[str]
    followers: int
    popularity: int
    uri: str
    image_url: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "genres": self.genres,
            "followers": self.followers,
            "popularity": self.popularity,
            "uri": self.uri
        }


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class SpotifyController:
    """
    Contrôleur Spotify ultra-complet pour gérer l'application desktop.
    
    Fonctionnalités:
    - Contrôle de lecture (play, pause, next, previous, seek)
    - Gestion du volume
    - Recherche (tracks, albums, artists, playlists)
    - Gestion des playlists (créer, modifier, supprimer)
    - File d'attente
    - Gestion des appareils (Spotify Connect)
    - Favoris (like/unlike)
    - Historique de lecture
    - Recommandations
    - Lyrics (paroles)
    - Et bien plus...
    """
    
    # Scopes requis pour toutes les fonctionnalités
    SCOPES = [
        "user-read-playback-state",
        "user-modify-playback-state", 
        "user-read-currently-playing",
        "user-read-recently-played",
        "user-top-read",
        "user-library-read",
        "user-library-modify",
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-public",
        "playlist-modify-private",
        "user-follow-read",
        "user-follow-modify",
        "streaming",
        "app-remote-control"
    ]
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: str = "http://localhost:8888/callback",
        cache_path: str = ".spotify_cache"
    ):
        """
        Initialise le contrôleur Spotify.
        
        Args:
            client_id: Spotify Client ID (ou depuis env SPOTIPY_CLIENT_ID)
            client_secret: Spotify Client Secret (ou depuis env SPOTIPY_CLIENT_SECRET)
            redirect_uri: URI de redirection OAuth
            cache_path: Chemin du cache token
        """
        self.client_id = client_id or os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = redirect_uri
        self.cache_path = cache_path
        
        self.sp: Optional[spotipy.Spotify] = None
        self.keyboard = KeyboardController() if PYNPUT_AVAILABLE else None
        self.is_connected = False
        self.current_device_id: Optional[str] = None
        
        # Cache interne
        self._cache = {
            "playlists": [],
            "devices": [],
            "current_track": None,
            "last_update": None
        }
        
        # Stats
        self.stats = {
            "commands_executed": 0,
            "tracks_played": 0,
            "searches": 0,
            "errors": 0
        }
        
    # ========================================================================
    # CONNEXION & AUTHENTIFICATION
    # ========================================================================
    
    def connect(self) -> bool:
        """
        Établit la connexion avec l'API Spotify.
        
        Returns:
            bool: True si connecté avec succès
        """
        if not SPOTIPY_AVAILABLE:
            print("❌ [SPOTIFY] spotipy non disponible")
            return False
            
        if not self.client_id or not self.client_secret:
            print("❌ [SPOTIFY] Client ID ou Secret manquant")
            print("   Configurez SPOTIPY_CLIENT_ID et SPOTIPY_CLIENT_SECRET")
            return False
        
        try:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=" ".join(self.SCOPES),
                cache_path=self.cache_path,
                open_browser=True
            )
            
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            
            # Test de connexion
            user = self.sp.current_user()
            self.is_connected = True
            print(f"✅ [SPOTIFY] Connecté en tant que: {user['display_name']}")
            
            # Récupère l'appareil actif
            self._update_devices()
            
            return True
            
        except Exception as e:
            print(f"❌ [SPOTIFY] Erreur de connexion: {e}")
            self.stats["errors"] += 1
            return False
    
    def disconnect(self):
        """Déconnecte de Spotify"""
        self.sp = None
        self.is_connected = False
        print("🔌 [SPOTIFY] Déconnecté")
    
    def is_authenticated(self) -> bool:
        """Vérifie si authentifié"""
        return self.is_connected and self.sp is not None
    
    def _ensure_connected(self) -> bool:
        """S'assure que la connexion est établie"""
        if not self.is_authenticated():
            return self.connect()
        return True
    
    # ========================================================================
    # CONTRÔLE DE LECTURE - BASIQUE
    # ========================================================================
    
    def play(self, device_id: Optional[str] = None) -> bool:
        """
        Lance la lecture.

        Args:
            device_id: ID de l'appareil (optionnel)
        """
        if not self._ensure_connected():
            return self._fallback_play()

        target_device_id = device_id or self.current_device_id
        if not target_device_id:
            self._ensure_active_device(allow_open=True)
            target_device_id = device_id or self.current_device_id

        try:
            self.sp.start_playback(device_id=target_device_id)
            self.stats["commands_executed"] += 1
            print("▶️ [SPOTIFY] Lecture lancée")
            return True
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "No active device" in msg:
                if self._ensure_active_device(allow_open=True):
                    try:
                        self.sp.start_playback(device_id=device_id or self.current_device_id)
                        self.stats["commands_executed"] += 1
                        print("▶️ [SPOTIFY] Lecture lancée")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [SPOTIFY] Erreur play (retry): {e2}")
                        return self._fallback_play()

            print(f"⚠️ [SPOTIFY] Erreur play: {e}")
            return self._fallback_play()
    
    def pause(self, device_id: Optional[str] = None) -> bool:
        """Met en pause"""
        if not self._ensure_connected():
            return self._fallback_pause()
        
        try:
            self.sp.pause_playback(device_id=device_id or self.current_device_id)
            self.stats["commands_executed"] += 1
            print("⏸️ [SPOTIFY] Pause")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur pause: {e}")
            return self._fallback_pause()
    
    def toggle_playback(self) -> bool:
        """Bascule play/pause"""
        current = self.get_current_track()
        if current and current.is_playing:
            return self.pause()
        return self.play()
    
    def next_track(self, device_id: Optional[str] = None) -> bool:
        """Passe au morceau suivant"""
        if not self._ensure_connected():
            return self._fallback_next()
        
        try:
            self.sp.next_track(device_id=device_id or self.current_device_id)
            self.stats["commands_executed"] += 1
            print("⏭️ [SPOTIFY] Morceau suivant")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur next: {e}")
            return self._fallback_next()
    
    def previous_track(self, device_id: Optional[str] = None) -> bool:
        """Revient au morceau précédent"""
        if not self._ensure_connected():
            return self._fallback_previous()
        
        try:
            self.sp.previous_track(device_id=device_id or self.current_device_id)
            self.stats["commands_executed"] += 1
            print("⏮️ [SPOTIFY] Morceau précédent")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur previous: {e}")
            return self._fallback_previous()
    
    def seek(self, position_ms: int, device_id: Optional[str] = None) -> bool:
        """
        Se déplace à une position dans le morceau.
        
        Args:
            position_ms: Position en millisecondes
        """
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.seek_track(position_ms, device_id=device_id or self.current_device_id)
            self.stats["commands_executed"] += 1
            mins, secs = divmod(position_ms // 1000, 60)
            print(f"⏩ [SPOTIFY] Position: {mins}:{secs:02d}")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur seek: {e}")
            return False
    
    def seek_forward(self, seconds: int = 10) -> bool:
        """Avance de X secondes"""
        current = self.get_current_track()
        if current:
            new_pos = min(current.progress_ms + (seconds * 1000), current.duration_ms)
            return self.seek(new_pos)
        return False
    
    def seek_backward(self, seconds: int = 10) -> bool:
        """Recule de X secondes"""
        current = self.get_current_track()
        if current:
            new_pos = max(current.progress_ms - (seconds * 1000), 0)
            return self.seek(new_pos)
        return False
    
    # ========================================================================
    # CONTRÔLE DU VOLUME
    # ========================================================================
    
    def set_volume(self, volume: int, device_id: Optional[str] = None) -> bool:
        """
        Définit le volume (0-100).
        
        Args:
            volume: Niveau de volume (0-100)
        """
        if not self._ensure_connected():
            return False
        
        volume = max(0, min(100, volume))
        
        try:
            self.sp.volume(volume, device_id=device_id or self.current_device_id)
            self.stats["commands_executed"] += 1
            print(f"🔊 [SPOTIFY] Volume: {volume}%")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur volume: {e}")
            return False
    
    def volume_up(self, step: int = 10) -> bool:
        """Augmente le volume"""
        devices = self.get_devices()
        active = next((d for d in devices if d.is_active), None)
        if active:
            new_vol = min(100, active.volume_percent + step)
            return self.set_volume(new_vol)
        return False
    
    def volume_down(self, step: int = 10) -> bool:
        """Diminue le volume"""
        devices = self.get_devices()
        active = next((d for d in devices if d.is_active), None)
        if active:
            new_vol = max(0, active.volume_percent - step)
            return self.set_volume(new_vol)
        return False
    
    def mute(self) -> bool:
        """Coupe le son"""
        return self.set_volume(0)
    
    def get_volume(self) -> int:
        """Récupère le volume actuel"""
        devices = self.get_devices()
        active = next((d for d in devices if d.is_active), None)
        return active.volume_percent if active else 0
    
    # ========================================================================
    # SHUFFLE & REPEAT
    # ========================================================================
    
    def set_shuffle(self, state: bool, device_id: Optional[str] = None) -> bool:
        """Active/désactive le shuffle"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.shuffle(state, device_id=device_id or self.current_device_id)
            status = "activé" if state else "désactivé"
            print(f"🔀 [SPOTIFY] Shuffle {status}")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur shuffle: {e}")
            return False
    
    def toggle_shuffle(self) -> bool:
        """Bascule le shuffle"""
        playback = self._get_playback_state()
        if playback:
            return self.set_shuffle(not playback.get("shuffle_state", False))
        return False
    
    def set_repeat(self, state: str, device_id: Optional[str] = None) -> bool:
        """
        Définit le mode repeat.
        
        Args:
            state: "track", "context", ou "off"
        """
        if not self._ensure_connected():
            return False
        
        if state not in ["track", "context", "off"]:
            print(f"⚠️ [SPOTIFY] État repeat invalide: {state}")
            return False
        
        try:
            self.sp.repeat(state, device_id=device_id or self.current_device_id)
            print(f"🔁 [SPOTIFY] Repeat: {state}")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur repeat: {e}")
            return False
    
    def cycle_repeat(self) -> bool:
        """Cycle entre les modes repeat (off -> context -> track -> off)"""
        playback = self._get_playback_state()
        if playback:
            current = playback.get("repeat_state", "off")
            next_state = {"off": "context", "context": "track", "track": "off"}
            return self.set_repeat(next_state.get(current, "off"))
        return False
    
    # ========================================================================
    # INFORMATIONS SUR LA LECTURE
    # ========================================================================
    
    def get_current_track(self) -> Optional[SpotifyTrack]:
        """Récupère le morceau en cours de lecture"""
        if not self._ensure_connected():
            return None
        
        try:
            current = self.sp.current_playback()
            if not current or not current.get("item"):
                return None
            
            item = current["item"]
            track = SpotifyTrack(
                id=item["id"],
                name=item["name"],
                artists=[a["name"] for a in item["artists"]],
                album=item["album"]["name"],
                album_id=item["album"]["id"],
                duration_ms=item["duration_ms"],
                uri=item["uri"],
                is_playing=current.get("is_playing", False),
                progress_ms=current.get("progress_ms", 0),
                image_url=item["album"]["images"][0]["url"] if item["album"]["images"] else None,
                popularity=item.get("popularity", 0),
                explicit=item.get("explicit", False)
            )
            
            self._cache["current_track"] = track
            return track
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur current track: {e}")
            return None
    
    def get_current_track_info(self) -> str:
        """Retourne une description textuelle du morceau en cours"""
        track = self.get_current_track()
        if not track:
            return "Aucun morceau en cours de lecture"
        
        status = "▶️ En lecture" if track.is_playing else "⏸️ En pause"
        return (
            f"{status}\n"
            f"🎵 {track.name}\n"
            f"👤 {track.artists_str}\n"
            f"💿 {track.album}\n"
            f"⏱️ {track.progress_str} / {track.duration_str}"
        )
    
    def _get_playback_state(self) -> Optional[Dict]:
        """Récupère l'état complet de lecture"""
        if not self._ensure_connected():
            return None
        
        try:
            return self.sp.current_playback()
        except:
            return None
    
    def get_playback_info(self) -> Dict:
        """Récupère toutes les infos de lecture"""
        state = self._get_playback_state()
        if not state:
            return {"status": "inactive"}
        
        return {
            "status": "playing" if state.get("is_playing") else "paused",
            "shuffle": state.get("shuffle_state", False),
            "repeat": state.get("repeat_state", "off"),
            "volume": state.get("device", {}).get("volume_percent", 0),
            "device": state.get("device", {}).get("name", "Unknown"),
            "track": self.get_current_track().to_dict() if self.get_current_track() else None
        }
    
    # ========================================================================
    # RECHERCHE
    # ========================================================================
    
    def search(
        self,
        query: str,
        types: List[str] = ["track"],
        limit: int = 10,
        market: str = "FR"
    ) -> Dict[str, List]:
        """
        Recherche sur Spotify.
        
        Args:
            query: Terme de recherche
            types: Types à rechercher ("track", "album", "artist", "playlist")
            limit: Nombre de résultats par type
            market: Code pays
            
        Returns:
            Dict avec les résultats par type
        """
        if not self._ensure_connected():
            return {}

        query = (query or "").strip()
        if not query:
            print("⚠️ [SPOTIFY] Recherche ignorée: query vide")
            return {}

        self.stats["searches"] += 1

        try:
            results = self.sp.search(q=query, type=",".join(types), limit=limit, market=market)
            parsed: Dict[str, List] = {}
            
            if "tracks" in results:
                parsed["tracks"] = [
                    SpotifyTrack(
                        id=t["id"],
                        name=t["name"],
                        artists=[a["name"] for a in t["artists"]],
                        album=t["album"]["name"],
                        album_id=t["album"]["id"],
                        duration_ms=t["duration_ms"],
                        uri=t["uri"],
                        image_url=t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                        popularity=t.get("popularity", 0)
                    )
                    for t in results["tracks"]["items"]
                ]
            
            if "albums" in results:
                parsed["albums"] = [
                    SpotifyAlbum(
                        id=a["id"],
                        name=a["name"],
                        artists=[ar["name"] for ar in a["artists"]],
                        release_date=a.get("release_date", ""),
                        total_tracks=a.get("total_tracks", 0),
                        uri=a["uri"],
                        image_url=a["images"][0]["url"] if a["images"] else None
                    )
                    for a in results["albums"]["items"]
                ]
            
            if "artists" in results:
                parsed["artists"] = [
                    SpotifyArtist(
                        id=ar["id"],
                        name=ar["name"],
                        genres=ar.get("genres", []),
                        followers=ar.get("followers", {}).get("total", 0),
                        popularity=ar.get("popularity", 0),
                        uri=ar["uri"],
                        image_url=ar["images"][0]["url"] if ar["images"] else None
                    )
                    for ar in results["artists"]["items"]
                ]
            
            if "playlists" in results:
                parsed["playlists"] = [
                    SpotifyPlaylist(
                        id=p["id"],
                        name=p["name"],
                        owner=p["owner"]["display_name"],
                        tracks_count=p["tracks"]["total"],
                        uri=p["uri"],
                        image_url=p["images"][0]["url"] if p["images"] else None
                    )
                    for p in results["playlists"]["items"] if p
                ]
            
            print(f"🔍 [SPOTIFY] Recherche '{query}': {sum(len(v) for v in parsed.values())} résultats")
            return parsed
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur recherche: {e}")
            return {}
    
    def search_tracks(self, query: str, limit: int = 10) -> List[SpotifyTrack]:
        """Recherche de morceaux uniquement"""
        results = self.search(query, types=["track"], limit=limit)
        return results.get("tracks", [])
    
    def search_albums(self, query: str, limit: int = 10) -> List[SpotifyAlbum]:
        """Recherche d'albums uniquement"""
        results = self.search(query, types=["album"], limit=limit)
        return results.get("albums", [])
    
    def search_artists(self, query: str, limit: int = 10) -> List[SpotifyArtist]:
        """Recherche d'artistes uniquement"""
        results = self.search(query, types=["artist"], limit=limit)
        return results.get("artists", [])
    
    def search_playlists(self, query: str, limit: int = 10) -> List[SpotifyPlaylist]:
        """Recherche de playlists uniquement"""
        results = self.search(query, types=["playlist"], limit=limit)
        return results.get("playlists", [])
    
    # ========================================================================
    # LECTURE DE CONTENU SPÉCIFIQUE
    # ========================================================================
    
    def play_track(self, track_uri: str, device_id: Optional[str] = None) -> bool:
        """Joue un morceau spécifique par URI"""
        if not self._ensure_connected():
            return False

        if not (device_id or self.current_device_id):
            self._ensure_active_device(allow_open=True)

        target_device_id = device_id or self.current_device_id

        try:
            self.sp.start_playback(
                device_id=target_device_id,
                uris=[track_uri]
            )
            self.stats["tracks_played"] += 1
            print(f"▶️ [SPOTIFY] Lecture: {track_uri}")
            return True
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "No active device" in msg:
                if self._ensure_active_device(allow_open=True):
                    try:
                        self.sp.start_playback(
                            device_id=device_id or self.current_device_id,
                            uris=[track_uri]
                        )
                        self.stats["tracks_played"] += 1
                        print(f"▶️ [SPOTIFY] Lecture: {track_uri}")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [SPOTIFY] Erreur play track (retry): {e2}")

            # Fallback local: ouvre la piste dans l'app, puis media play/pause
            opened = self.open_spotify_uri(track_uri)
            played = self._fallback_play()
            if opened or played:
                print("🎵 [SPOTIFY] Fallback local: ouverture piste + play/pause")
                return True

            print(f"⚠️ [SPOTIFY] Erreur play track: {e}")
            return False
    
    def play_album(self, album_uri: str, device_id: Optional[str] = None) -> bool:
        """Joue un album"""
        if not self._ensure_connected():
            # Fallback: ouvre l'album dans l'app
            return self.open_spotify_uri(album_uri)

        if not (device_id or self.current_device_id):
            self._ensure_active_device(allow_open=True)

        target_device_id = device_id or self.current_device_id

        try:
            self.sp.start_playback(
                device_id=target_device_id,
                context_uri=album_uri
            )
            print(f"💿 [SPOTIFY] Album lancé: {album_uri}")
            return True
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "No active device" in msg:
                if self._ensure_active_device(allow_open=True):
                    try:
                        self.sp.start_playback(
                            device_id=device_id or self.current_device_id,
                            context_uri=album_uri
                        )
                        print(f"💿 [SPOTIFY] Album lancé: {album_uri}")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [SPOTIFY] Erreur play album (retry): {e2}")
            
            # Fallback: ouvre l'album dans l'app
            if self.open_spotify_uri(album_uri):
                print("💿 [SPOTIFY] Album ouvert dans l'application")
                return True
            
            print(f"⚠️ [SPOTIFY] Erreur play album: {e}")
            return False
    
    def play_playlist(self, playlist_uri: str, device_id: Optional[str] = None, shuffle: bool = False) -> bool:
        """Joue une playlist"""
        if not self._ensure_connected():
            # Fallback: ouvre la playlist dans l'app
            return self.open_spotify_uri(playlist_uri)

        if not (device_id or self.current_device_id):
            self._ensure_active_device(allow_open=True)

        target_device_id = device_id or self.current_device_id

        try:
            if shuffle:
                self.set_shuffle(True)
            
            self.sp.start_playback(
                device_id=target_device_id,
                context_uri=playlist_uri
            )
            print(f"📋 [SPOTIFY] Playlist lancée: {playlist_uri}")
            return True
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "No active device" in msg:
                if self._ensure_active_device(allow_open=True):
                    try:
                        if shuffle:
                            self.set_shuffle(True)
                        self.sp.start_playback(
                            device_id=device_id or self.current_device_id,
                            context_uri=playlist_uri
                        )
                        print(f"📋 [SPOTIFY] Playlist lancée: {playlist_uri}")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [SPOTIFY] Erreur play playlist (retry): {e2}")
            
            # Fallback: ouvre la playlist dans l'app
            if self.open_spotify_uri(playlist_uri):
                print("📋 [SPOTIFY] Playlist ouverte dans l'application")
                return True
            
            print(f"⚠️ [SPOTIFY] Erreur play playlist: {e}")
            return False
    
    def play_artist(self, artist_uri: str, device_id: Optional[str] = None) -> bool:
        """Joue les top tracks d'un artiste"""
        if not self._ensure_connected():
            # Fallback: ouvre l'artiste dans l'app
            return self.open_spotify_uri(artist_uri)

        if not (device_id or self.current_device_id):
            self._ensure_active_device(allow_open=True)

        target_device_id = device_id or self.current_device_id

        try:
            self.sp.start_playback(
                device_id=target_device_id,
                context_uri=artist_uri
            )
            print(f"👤 [SPOTIFY] Artiste lancé: {artist_uri}")
            return True
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "No active device" in msg:
                if self._ensure_active_device(allow_open=True):
                    try:
                        self.sp.start_playback(
                            device_id=device_id or self.current_device_id,
                            context_uri=artist_uri
                        )
                        print(f"👤 [SPOTIFY] Artiste lancé: {artist_uri}")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [SPOTIFY] Erreur play artist (retry): {e2}")
            
            # Fallback: ouvre l'artiste dans l'app
            if self.open_spotify_uri(artist_uri):
                print("👤 [SPOTIFY] Artiste ouvert dans l'application")
                return True
            
            print(f"⚠️ [SPOTIFY] Erreur play artist: {e}")
            return False
    
    def play_by_name(self, name: str, type: str = "track") -> bool:
        """
        Recherche et joue par nom.
        
        Args:
            name: Nom à rechercher
            type: "track", "album", "playlist", ou "artist"
        """
        results = self.search(name, types=[type], limit=1)
        
        if type == "track" and results.get("tracks"):
            return self.play_track(results["tracks"][0].uri)
        elif type == "album" and results.get("albums"):
            return self.play_album(results["albums"][0].uri)
        elif type == "playlist" and results.get("playlists"):
            return self.play_playlist(results["playlists"][0].uri)
        elif type == "artist" and results.get("artists"):
            return self.play_artist(results["artists"][0].uri)
        
        print(f"⚠️ [SPOTIFY] Aucun résultat pour '{name}'")
        return False
    
    # ========================================================================
    # FILE D'ATTENTE
    # ========================================================================
    
    def add_to_queue(self, track_uri: str, device_id: Optional[str] = None) -> bool:
        """Ajoute un morceau à la file d'attente"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.add_to_queue(track_uri, device_id=device_id or self.current_device_id)
            print(f"➕ [SPOTIFY] Ajouté à la queue: {track_uri}")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur add to queue: {e}")
            return False
    
    def add_to_queue_by_name(self, name: str) -> bool:
        """Recherche et ajoute un morceau à la queue"""
        tracks = self.search_tracks(name, limit=1)
        if tracks:
            return self.add_to_queue(tracks[0].uri)
        return False
    
    def get_queue(self) -> List[SpotifyTrack]:
        """Récupère la file d'attente actuelle"""
        if not self._ensure_connected():
            return []
        
        try:
            queue_data = self.sp.queue()
            tracks = []
            
            # Morceau actuel
            if queue_data.get("currently_playing"):
                item = queue_data["currently_playing"]
                tracks.append(SpotifyTrack(
                    id=item["id"],
                    name=item["name"],
                    artists=[a["name"] for a in item["artists"]],
                    album=item["album"]["name"],
                    album_id=item["album"]["id"],
                    duration_ms=item["duration_ms"],
                    uri=item["uri"],
                    is_playing=True
                ))
            
            # Queue
            for item in queue_data.get("queue", []):
                tracks.append(SpotifyTrack(
                    id=item["id"],
                    name=item["name"],
                    artists=[a["name"] for a in item["artists"]],
                    album=item["album"]["name"],
                    album_id=item["album"]["id"],
                    duration_ms=item["duration_ms"],
                    uri=item["uri"]
                ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur get queue: {e}")
            return []
    
    # ========================================================================
    # GESTION DES APPAREILS
    # ========================================================================
    
    def get_devices(self) -> List[SpotifyDevice]:
        """Récupère la liste des appareils disponibles"""
        if not self._ensure_connected():
            return []
        
        try:
            devices_data = self.sp.devices()
            devices = [
                SpotifyDevice(
                    id=d["id"],
                    name=d["name"],
                    type=d["type"],
                    is_active=d["is_active"],
                    volume_percent=d.get("volume_percent", 0),
                    is_restricted=d.get("is_restricted", False)
                )
                for d in devices_data.get("devices", [])
            ]
            
            self._cache["devices"] = devices
            
            # Met à jour l'appareil actif
            active = next((d for d in devices if d.is_active), None)
            if active:
                self.current_device_id = active.id
            
            return devices
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur devices: {e}")
            return []
    
    def _update_devices(self):
        """Met à jour le cache des appareils"""
        self.get_devices()
    
    def transfer_playback(self, device_id: str, force_play: bool = False) -> bool:
        """
        Transfère la lecture vers un autre appareil.
        
        Args:
            device_id: ID de l'appareil cible
            force_play: Lancer la lecture après le transfert
        """
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.transfer_playback(device_id, force_play=force_play)
            self.current_device_id = device_id
            print(f"📲 [SPOTIFY] Lecture transférée vers: {device_id}")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur transfert: {e}")
            return False
    
    def transfer_to_device_by_name(self, name: str, force_play: bool = False) -> bool:
        """Transfère vers un appareil par nom"""
        devices = self.get_devices()
        device = next((d for d in devices if name.lower() in d.name.lower()), None)
        if device:
            return self.transfer_playback(device.id, force_play)
        print(f"⚠️ [SPOTIFY] Appareil '{name}' non trouvé")
        return False

    def _pick_preferred_device(self, devices: List[SpotifyDevice]) -> Optional[SpotifyDevice]:
        """Choisit l'appareil le plus pertinent pour le desktop."""
        active = next((d for d in devices if d.is_active and not d.is_restricted and d.id), None)
        if active:
            return active

        computers = [d for d in devices if (d.type or "").lower() == "computer" and not d.is_restricted and d.id]
        if computers:
            return computers[0]

        any_ok = next((d for d in devices if not d.is_restricted and d.id), None)
        return any_ok

    def _ensure_active_device(self, allow_open: bool = True, wait_seconds: float = 1.2) -> bool:
        """S'assure qu'il existe un appareil Spotify actif (sinon, tente d'ouvrir Spotify + transfer)."""
        if not self._ensure_connected():
            return False

        devices = self.get_devices()
        chosen = self._pick_preferred_device(devices)
        if chosen and chosen.is_active:
            self.current_device_id = chosen.id
            return True

        if allow_open:
            self.open_spotify()
            time.sleep(max(0.0, wait_seconds))
            devices = self.get_devices()
            chosen = self._pick_preferred_device(devices)

        if chosen and chosen.id:
            ok = self.transfer_playback(chosen.id, force_play=False)
            time.sleep(0.4)
            self.get_devices()
            return ok and bool(self.current_device_id)

        return False

    # ========================================================================
    # PLAYLISTS
    # ========================================================================
    
    def get_user_playlists(self, limit: int = 50) -> List[SpotifyPlaylist]:
        """Récupère les playlists de l'utilisateur"""
        if not self._ensure_connected():
            return []
        
        try:
            playlists_data = self.sp.current_user_playlists(limit=limit)
            playlists = [
                SpotifyPlaylist(
                    id=p["id"],
                    name=p["name"],
                    owner=p["owner"]["display_name"],
                    tracks_count=p["tracks"]["total"],
                    uri=p["uri"],
                    image_url=p["images"][0]["url"] if p["images"] else None,
                    public=p.get("public", True),
                    collaborative=p.get("collaborative", False),
                    description=p.get("description", "")
                )
                for p in playlists_data.get("items", [])
            ]
            
            self._cache["playlists"] = playlists
            return playlists
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur playlists: {e}")
            return []
    
    def create_playlist(
        self,
        name: str,
        public: bool = True,
        description: str = ""
    ) -> Optional[SpotifyPlaylist]:
        """
        Crée une nouvelle playlist.
        
        Args:
            name: Nom de la playlist
            public: Visible publiquement
            description: Description
        """
        if not self._ensure_connected():
            return None
        
        try:
            user_id = self.sp.current_user()["id"]
            playlist = self.sp.user_playlist_create(
                user_id,
                name,
                public=public,
                description=description
            )
            
            result = SpotifyPlaylist(
                id=playlist["id"],
                name=playlist["name"],
                owner=playlist["owner"]["display_name"],
                tracks_count=0,
                uri=playlist["uri"],
                public=public,
                description=description
            )
            
            print(f"✅ [SPOTIFY] Playlist créée: {name}")
            return result
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur création playlist: {e}")
            return None
    
    def add_tracks_to_playlist(self, playlist_id: str, track_uris: List[str]) -> bool:
        """Ajoute des morceaux à une playlist"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.playlist_add_items(playlist_id, track_uris)
            print(f"➕ [SPOTIFY] {len(track_uris)} morceau(x) ajouté(s)")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur ajout tracks: {e}")
            return False
    
    def remove_tracks_from_playlist(self, playlist_id: str, track_uris: List[str]) -> bool:
        """Retire des morceaux d'une playlist"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.playlist_remove_all_occurrences_of_items(playlist_id, track_uris)
            print(f"➖ [SPOTIFY] {len(track_uris)} morceau(x) retiré(s)")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur suppression tracks: {e}")
            return False
    
    def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> List[SpotifyTrack]:
        """Récupère les morceaux d'une playlist"""
        if not self._ensure_connected():
            return []
        
        try:
            tracks_data = self.sp.playlist_tracks(playlist_id, limit=limit)
            tracks = []
            
            for item in tracks_data.get("items", []):
                t = item.get("track")
                if t:
                    tracks.append(SpotifyTrack(
                        id=t["id"],
                        name=t["name"],
                        artists=[a["name"] for a in t["artists"]],
                        album=t["album"]["name"],
                        album_id=t["album"]["id"],
                        duration_ms=t["duration_ms"],
                        uri=t["uri"]
                    ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur playlist tracks: {e}")
            return []
    
    def delete_playlist(self, playlist_id: str) -> bool:
        """Supprime (unfollow) une playlist"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.current_user_unfollow_playlist(playlist_id)
            print(f"🗑️ [SPOTIFY] Playlist supprimée")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur suppression playlist: {e}")
            return False
    
    def update_playlist(
        self,
        playlist_id: str,
        name: Optional[str] = None,
        public: Optional[bool] = None,
        description: Optional[str] = None
    ) -> bool:
        """Met à jour les infos d'une playlist"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.playlist_change_details(
                playlist_id,
                name=name,
                public=public,
                description=description
            )
            print(f"✏️ [SPOTIFY] Playlist mise à jour")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur update playlist: {e}")
            return False
    
    # ========================================================================
    # FAVORIS / BIBLIOTHÈQUE
    # ========================================================================
    
    def like_track(self, track_id: str) -> bool:
        """Ajoute un morceau aux favoris"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.current_user_saved_tracks_add([track_id])
            print(f"❤️ [SPOTIFY] Morceau liké")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur like: {e}")
            return False
    
    def unlike_track(self, track_id: str) -> bool:
        """Retire un morceau des favoris"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.current_user_saved_tracks_delete([track_id])
            print(f"💔 [SPOTIFY] Morceau unliké")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur unlike: {e}")
            return False
    
    def like_current_track(self) -> bool:
        """Like le morceau en cours"""
        track = self.get_current_track()
        if track:
            return self.like_track(track.id)
        return False
    
    def unlike_current_track(self) -> bool:
        """Unlike le morceau en cours"""
        track = self.get_current_track()
        if track:
            return self.unlike_track(track.id)
        return False
    
    def is_track_saved(self, track_id: str) -> bool:
        """Vérifie si un morceau est dans les favoris"""
        if not self._ensure_connected():
            return False
        
        try:
            result = self.sp.current_user_saved_tracks_contains([track_id])
            return result[0] if result else False
        except:
            return False
    
    def get_saved_tracks(self, limit: int = 50) -> List[SpotifyTrack]:
        """Récupère les morceaux likés"""
        if not self._ensure_connected():
            return []
        
        try:
            saved = self.sp.current_user_saved_tracks(limit=limit)
            tracks = []
            
            for item in saved.get("items", []):
                t = item.get("track")
                if t:
                    tracks.append(SpotifyTrack(
                        id=t["id"],
                        name=t["name"],
                        artists=[a["name"] for a in t["artists"]],
                        album=t["album"]["name"],
                        album_id=t["album"]["id"],
                        duration_ms=t["duration_ms"],
                        uri=t["uri"]
                    ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur saved tracks: {e}")
            return []
    
    def follow_artist(self, artist_id: str) -> bool:
        """Suit un artiste"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.user_follow_artists([artist_id])
            print(f"➕ [SPOTIFY] Artiste suivi")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur follow: {e}")
            return False
    
    def unfollow_artist(self, artist_id: str) -> bool:
        """Ne plus suivre un artiste"""
        if not self._ensure_connected():
            return False
        
        try:
            self.sp.user_unfollow_artists([artist_id])
            print(f"➖ [SPOTIFY] Artiste unfollowed")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur unfollow: {e}")
            return False
    
    def get_followed_artists(self, limit: int = 50) -> List[SpotifyArtist]:
        """Récupère les artistes suivis"""
        if not self._ensure_connected():
            return []
        
        try:
            followed = self.sp.current_user_followed_artists(limit=limit)
            artists = []
            
            for ar in followed.get("artists", {}).get("items", []):
                artists.append(SpotifyArtist(
                    id=ar["id"],
                    name=ar["name"],
                    genres=ar.get("genres", []),
                    followers=ar.get("followers", {}).get("total", 0),
                    popularity=ar.get("popularity", 0),
                    uri=ar["uri"]
                ))
            
            return artists
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur followed artists: {e}")
            return []
    
    # ========================================================================
    # HISTORIQUE & RECOMMANDATIONS
    # ========================================================================
    
    def get_recently_played(self, limit: int = 20) -> List[SpotifyTrack]:
        """Récupère l'historique de lecture récent"""
        if not self._ensure_connected():
            return []
        
        try:
            recent = self.sp.current_user_recently_played(limit=limit)
            tracks = []
            
            for item in recent.get("items", []):
                t = item.get("track")
                if t:
                    tracks.append(SpotifyTrack(
                        id=t["id"],
                        name=t["name"],
                        artists=[a["name"] for a in t["artists"]],
                        album=t["album"]["name"],
                        album_id=t["album"]["id"],
                        duration_ms=t["duration_ms"],
                        uri=t["uri"]
                    ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur recently played: {e}")
            return []
    
    def get_top_tracks(self, time_range: str = "medium_term", limit: int = 20) -> List[SpotifyTrack]:
        """
        Récupère les top tracks de l'utilisateur.
        
        Args:
            time_range: "short_term" (4 semaines), "medium_term" (6 mois), "long_term" (plusieurs années)
        """
        if not self._ensure_connected():
            return []
        
        try:
            top = self.sp.current_user_top_tracks(time_range=time_range, limit=limit)
            tracks = []
            
            for t in top.get("items", []):
                tracks.append(SpotifyTrack(
                    id=t["id"],
                    name=t["name"],
                    artists=[a["name"] for a in t["artists"]],
                    album=t["album"]["name"],
                    album_id=t["album"]["id"],
                    duration_ms=t["duration_ms"],
                    uri=t["uri"],
                    popularity=t.get("popularity", 0)
                ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur top tracks: {e}")
            return []
    
    def get_top_artists(self, time_range: str = "medium_term", limit: int = 20) -> List[SpotifyArtist]:
        """Récupère les top artistes de l'utilisateur"""
        if not self._ensure_connected():
            return []
        
        try:
            top = self.sp.current_user_top_artists(time_range=time_range, limit=limit)
            artists = []
            
            for ar in top.get("items", []):
                artists.append(SpotifyArtist(
                    id=ar["id"],
                    name=ar["name"],
                    genres=ar.get("genres", []),
                    followers=ar.get("followers", {}).get("total", 0),
                    popularity=ar.get("popularity", 0),
                    uri=ar["uri"]
                ))
            
            return artists
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur top artists: {e}")
            return []
    
    def get_recommendations(
        self,
        seed_tracks: List[str] = None,
        seed_artists: List[str] = None,
        seed_genres: List[str] = None,
        limit: int = 20,
        **kwargs
    ) -> List[SpotifyTrack]:
        """
        Obtient des recommandations personnalisées.
        
        Args:
            seed_tracks: Liste d'IDs de morceaux (max 5 au total avec artists et genres)
            seed_artists: Liste d'IDs d'artistes
            seed_genres: Liste de genres
            limit: Nombre de recommandations
            **kwargs: Paramètres supplémentaires (target_energy, min_tempo, etc.)
        """
        if not self._ensure_connected():
            return []
        
        try:
            recs = self.sp.recommendations(
                seed_tracks=seed_tracks,
                seed_artists=seed_artists,
                seed_genres=seed_genres,
                limit=limit,
                **kwargs
            )
            
            tracks = []
            for t in recs.get("tracks", []):
                tracks.append(SpotifyTrack(
                    id=t["id"],
                    name=t["name"],
                    artists=[a["name"] for a in t["artists"]],
                    album=t["album"]["name"],
                    album_id=t["album"]["id"],
                    duration_ms=t["duration_ms"],
                    uri=t["uri"],
                    popularity=t.get("popularity", 0)
                ))
            
            return tracks
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur recommendations: {e}")
            return []
    
    def get_recommendations_from_current(self, limit: int = 20) -> List[SpotifyTrack]:
        """Recommandations basées sur le morceau actuel"""
        current = self.get_current_track()
        if current:
            return self.get_recommendations(seed_tracks=[current.id], limit=limit)
        return []
    
    def get_available_genres(self) -> List[str]:
        """Récupère les genres disponibles pour les recommandations"""
        if not self._ensure_connected():
            return []
        
        try:
            genres = self.sp.recommendation_genre_seeds()
            return genres.get("genres", [])
        except:
            return []
    
    # ========================================================================
    # INFORMATIONS DÉTAILLÉES
    # ========================================================================
    
    def get_track_details(self, track_id: str) -> Optional[Dict]:
        """Récupère les détails complets d'un morceau"""
        if not self._ensure_connected():
            return None
        
        try:
            track = self.sp.track(track_id)
            features = self.sp.audio_features([track_id])[0]
            
            return {
                "track": SpotifyTrack(
                    id=track["id"],
                    name=track["name"],
                    artists=[a["name"] for a in track["artists"]],
                    album=track["album"]["name"],
                    album_id=track["album"]["id"],
                    duration_ms=track["duration_ms"],
                    uri=track["uri"],
                    popularity=track.get("popularity", 0),
                    explicit=track.get("explicit", False)
                ).to_dict(),
                "audio_features": {
                    "danceability": features.get("danceability"),
                    "energy": features.get("energy"),
                    "key": features.get("key"),
                    "loudness": features.get("loudness"),
                    "mode": features.get("mode"),
                    "speechiness": features.get("speechiness"),
                    "acousticness": features.get("acousticness"),
                    "instrumentalness": features.get("instrumentalness"),
                    "liveness": features.get("liveness"),
                    "valence": features.get("valence"),
                    "tempo": features.get("tempo"),
                    "time_signature": features.get("time_signature")
                }
            }
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur track details: {e}")
            return None
    
    def get_artist_details(self, artist_id: str) -> Optional[Dict]:
        """Récupère les détails d'un artiste"""
        if not self._ensure_connected():
            return None
        
        try:
            artist = self.sp.artist(artist_id)
            top_tracks = self.sp.artist_top_tracks(artist_id, country="FR")
            albums = self.sp.artist_albums(artist_id, limit=10)
            related = self.sp.artist_related_artists(artist_id)
            
            return {
                "artist": SpotifyArtist(
                    id=artist["id"],
                    name=artist["name"],
                    genres=artist.get("genres", []),
                    followers=artist.get("followers", {}).get("total", 0),
                    popularity=artist.get("popularity", 0),
                    uri=artist["uri"],
                    image_url=artist["images"][0]["url"] if artist["images"] else None
                ).to_dict(),
                "top_tracks": [t["name"] for t in top_tracks.get("tracks", [])[:5]],
                "albums": [a["name"] for a in albums.get("items", [])[:5]],
                "related_artists": [r["name"] for r in related.get("artists", [])[:5]]
            }
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur artist details: {e}")
            return None
    
    def get_album_details(self, album_id: str) -> Optional[Dict]:
        """Récupère les détails d'un album"""
        if not self._ensure_connected():
            return None
        
        try:
            album = self.sp.album(album_id)
            
            return {
                "album": SpotifyAlbum(
                    id=album["id"],
                    name=album["name"],
                    artists=[a["name"] for a in album["artists"]],
                    release_date=album.get("release_date", ""),
                    total_tracks=album.get("total_tracks", 0),
                    uri=album["uri"],
                    image_url=album["images"][0]["url"] if album["images"] else None
                ).to_dict(),
                "tracks": [
                    {"name": t["name"], "duration": t["duration_ms"] // 1000}
                    for t in album.get("tracks", {}).get("items", [])
                ],
                "label": album.get("label", ""),
                "copyrights": [c["text"] for c in album.get("copyrights", [])]
            }
            
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur album details: {e}")
            return None
    
    # ========================================================================
    # CONTRÔLE DE L'APPLICATION (FALLBACK LOCAL)
    # ========================================================================
    
    def _fallback_play(self) -> bool:
        """Fallback: touche média Play"""
        if self.keyboard:
            self.keyboard.press(Key.media_play_pause)
            self.keyboard.release(Key.media_play_pause)
            return True
        return False
    
    def _fallback_pause(self) -> bool:
        """Fallback: touche média Pause"""
        return self._fallback_play()
    
    def _fallback_next(self) -> bool:
        """Fallback: touche média Next"""
        if self.keyboard:
            self.keyboard.press(Key.media_next)
            self.keyboard.release(Key.media_next)
            return True
        return False
    
    def _fallback_previous(self) -> bool:
        """Fallback: touche média Previous"""
        if self.keyboard:
            self.keyboard.press(Key.media_previous)
            self.keyboard.release(Key.media_previous)
            return True
        return False
    
    def open_spotify(self) -> bool:
        """Ouvre l'application Spotify"""
        try:
            if sys.platform == "win32":
                # Essaie d'abord le chemin Windows Store
                appx_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe")
                standard_path = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")

                if os.path.exists(appx_path):
                    subprocess.Popen([appx_path])
                elif os.path.exists(standard_path):
                    subprocess.Popen([standard_path])
                else:
                    # Fallback: URI scheme
                    webbrowser.open("spotify:")
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Spotify"])
            else:
                subprocess.Popen(["spotify"])

            print("🚀 [SPOTIFY] Application ouverte")
            return True

        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur ouverture: {e}")
            return False

    def open_spotify_uri(self, uri: str) -> bool:
        """Ouvre un URI Spotify (ex: spotify:track:...) dans l'app desktop."""
        try:
            if not uri:
                return False
            webbrowser.open(uri)
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur open uri: {e}")
            return False
    
    def open_artist_page(self, artist_name: str) -> bool:
        """
        Ouvre la page d'un artiste dans l'application Spotify (pas le navigateur web).
        
        Args:
            artist_name: Nom de l'artiste à rechercher
        
        Returns:
            bool: True si ouvert avec succès
        """
        if not self._ensure_connected():
            print("⚠️ [SPOTIFY] Non connecté, impossible d'ouvrir la page de l'artiste")
            return False
        
        try:
            # Recherche l'artiste
            results = self.search(artist_name, types=["artist"], limit=1)
            artists = results.get("artists", [])
            
            if not artists:
                print(f"⚠️ [SPOTIFY] Artiste '{artist_name}' introuvable")
                return False
            
            artist = artists[0]
            # Ouvre l'URI Spotify dans l'application (pas le navigateur web)
            spotify_uri = f"spotify:artist:{artist.id}"
            webbrowser.open(spotify_uri)
            print(f"👤 [SPOTIFY] Page de l'artiste '{artist.name}' ouverte dans l'application Spotify")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur ouverture page artiste: {e}")
            return False
    
    def close_spotify(self) -> bool:
        """Ferme l'application Spotify"""
        if not PSUTIL_AVAILABLE:
            print("⚠️ [SPOTIFY] psutil requis pour fermer Spotify")
            return False
        
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'spotify' in proc.info['name'].lower():
                    proc.terminate()
            print("🛑 [SPOTIFY] Application fermée")
            return True
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur fermeture: {e}")
            return False
    
    def is_spotify_running(self) -> bool:
        """Vérifie si Spotify est en cours d'exécution"""
        if not PSUTIL_AVAILABLE:
            return False
        
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and 'spotify' in proc.info['name'].lower():
                return True
        return False
    
    # ========================================================================
    # FONCTIONS UTILITAIRES
    # ========================================================================
    
    def get_stats(self) -> Dict:
        """Retourne les statistiques d'utilisation"""
        return {
            **self.stats,
            "is_connected": self.is_connected,
            "current_device": self.current_device_id,
            "cached_playlists": len(self._cache.get("playlists", [])),
            "cached_devices": len(self._cache.get("devices", []))
        }
    
    def get_user_info(self) -> Optional[Dict]:
        """Récupère les infos de l'utilisateur connecté"""
        if not self._ensure_connected():
            return None
        
        try:
            user = self.sp.current_user()
            return {
                "id": user["id"],
                "name": user.get("display_name", ""),
                "email": user.get("email", ""),
                "country": user.get("country", ""),
                "product": user.get("product", "free"),
                "followers": user.get("followers", {}).get("total", 0),
                "image": user["images"][0]["url"] if user.get("images") else None
            }
        except Exception as e:
            print(f"⚠️ [SPOTIFY] Erreur user info: {e}")
            return None


# ============================================================================
# INSTANCE GLOBALE & TOOL DECLARATIONS
# ============================================================================

# Instance globale
_spotify_controller: Optional[SpotifyController] = None

def get_spotify_controller() -> SpotifyController:
    """Récupère ou crée l'instance du contrôleur Spotify"""
    global _spotify_controller
    if _spotify_controller is None:
        _spotify_controller = SpotifyController()
    return _spotify_controller


# ============================================================================
# TOOL FUNCTION POUR CYPHER
# ============================================================================

def spotify_tool(action: str, **kwargs) -> str:
    """
    Tool principal pour contrôler Spotify.
    
    Actions disponibles:
    - connect: Se connecter à Spotify
    - play: Lancer la lecture
    - pause: Mettre en pause
    - toggle: Basculer play/pause
    - next: Morceau suivant
    - previous: Morceau précédent
    - volume: Changer le volume (level: 0-100)
    - volume_up: Augmenter le volume
    - volume_down: Diminuer le volume
    - mute: Couper le son
    - shuffle: Activer/désactiver shuffle (state: bool)
    - repeat: Changer le mode repeat (mode: "off"/"track"/"context")
    - seek: Se déplacer dans le morceau (position_ms: int)
    - current: Obtenir le morceau actuel
    - search: Rechercher (query: str, type: "track"/"album"/"artist"/"playlist")
    - play_track: Jouer un morceau (name: str)
    - play_album: Jouer un album (name: str)
    - play_playlist: Jouer une playlist (name: str)
    - play_artist: Jouer un artiste (name: str)
    - open_artist: Ouvrir la page web d'un artiste (name: str)
    - queue_add: Ajouter à la queue (name: str)
    - queue_show: Afficher la queue
    - like: Liker le morceau actuel
    - unlike: Unliker le morceau actuel
    - playlists: Lister mes playlists
    - create_playlist: Créer une playlist (name: str, public: bool)
    - devices: Lister les appareils
    - transfer: Transférer vers un appareil (device_name: str)
    - history: Historique récent
    - top_tracks: Mes top morceaux
    - top_artists: Mes top artistes
    - recommendations: Recommandations basées sur le morceau actuel
    - info: Infos détaillées (type: "track"/"artist"/"album", id: str)
    - open: Ouvrir Spotify
    - close: Fermer Spotify
    - status: État complet de la lecture
    
    Returns:
        str: Résultat de l'action en JSON
    """
    sp = get_spotify_controller()
    result = {"success": False, "action": action, "data": None, "message": ""}
    
    try:
        # === CONNEXION ===
        if action == "connect":
            success = sp.connect()
            result["success"] = success
            result["message"] = "Connecté à Spotify" if success else "Échec de connexion"
        
        # === CONTRÔLE DE LECTURE ===
        elif action == "play":
            result["success"] = sp.play()
            result["message"] = "Lecture lancée"
        
        elif action == "pause":
            result["success"] = sp.pause()
            result["message"] = "Lecture en pause"
        
        elif action == "toggle":
            result["success"] = sp.toggle_playback()
            result["message"] = "Lecture basculée"
        
        elif action == "next":
            result["success"] = sp.next_track()
            result["message"] = "Morceau suivant"
        
        elif action == "previous":
            result["success"] = sp.previous_track()
            result["message"] = "Morceau précédent"
        
        # === VOLUME ===
        elif action == "volume":
            level = kwargs.get("level", 50)
            result["success"] = sp.set_volume(int(level))
            result["message"] = f"Volume: {level}%"
        
        elif action == "volume_up":
            result["success"] = sp.volume_up()
            result["message"] = "Volume augmenté"
        
        elif action == "volume_down":
            result["success"] = sp.volume_down()
            result["message"] = "Volume diminué"
        
        elif action == "mute":
            result["success"] = sp.mute()
            result["message"] = "Son coupé"
        
        # === SHUFFLE & REPEAT ===
        elif action == "shuffle":
            state = kwargs.get("state", True)
            result["success"] = sp.set_shuffle(state)
            result["message"] = f"Shuffle {'activé' if state else 'désactivé'}"
        
        elif action == "repeat":
            mode = kwargs.get("mode", "off")
            result["success"] = sp.set_repeat(mode)
            result["message"] = f"Repeat: {mode}"
        
        # === SEEK ===
        elif action == "seek":
            position = kwargs.get("position_ms", 0)
            result["success"] = sp.seek(int(position))
            result["message"] = f"Position changée"
        
        # === INFOS MORCEAU ACTUEL ===
        elif action == "current":
            track = sp.get_current_track()
            if track:
                result["success"] = True
                result["data"] = track.to_dict()
                result["message"] = sp.get_current_track_info()
            else:
                result["message"] = "Aucun morceau en cours"
        
        # === RECHERCHE ===
        elif action == "search":
            query = (kwargs.get("query") or "").strip()
            search_type = kwargs.get("type", "track")
            limit = kwargs.get("limit", 5)

            if not query:
                result["success"] = False
                result["data"] = []
                result["message"] = "Paramètre 'query' requis pour search"
            else:
                results = sp.search(query, types=[search_type], limit=limit)
                items = results.get(f"{search_type}s", [])

                result["success"] = len(items) > 0
                result["data"] = [item.to_dict() for item in items]
                result["message"] = f"{len(items)} résultat(s) trouvé(s)"

        # === LECTURE SPÉCIFIQUE ===
        elif action == "play_track":
            name = (kwargs.get("name") or "").strip()
            if not name:
                result["success"] = False
                result["message"] = "Paramètre 'name' requis pour play_track"
            else:
                ok = sp.play_by_name(name, "track")
                result["success"] = ok
                result["message"] = f"Lecture lancée: {name}" if ok else f"Impossible de lancer: {name}"

        elif action == "play_album":
            name = (kwargs.get("name") or "").strip()
            if not name:
                result["success"] = False
                result["message"] = "Paramètre 'name' requis pour play_album"
            else:
                ok = sp.play_by_name(name, "album")
                result["success"] = ok
                result["message"] = f"Album lancé: {name}" if ok else f"Impossible de lancer l'album: {name}"

        elif action == "play_playlist":
            name = (kwargs.get("name") or "").strip()
            if not name:
                result["success"] = False
                result["message"] = "Paramètre 'name' requis pour play_playlist"
            else:
                ok = sp.play_by_name(name, "playlist")
                result["success"] = ok
                result["message"] = f"Playlist lancée: {name}" if ok else f"Impossible de lancer la playlist: {name}"

        elif action == "play_artist":
            name = (kwargs.get("name") or "").strip()
            if not name:
                result["success"] = False
                result["message"] = "Paramètre 'name' requis pour play_artist"
            else:
                ok = sp.play_by_name(name, "artist")
                result["success"] = ok
                result["message"] = f"Artiste lancé: {name}" if ok else f"Impossible de lancer l'artiste: {name}"
        
        # === QUEUE ===
        elif action == "queue_add":
            name = kwargs.get("name", "")
            result["success"] = sp.add_to_queue_by_name(name)
            result["message"] = f"Ajouté à la queue: {name}"
        
        elif action == "queue_show":
            queue = sp.get_queue()
            result["success"] = True
            result["data"] = [t.to_dict() for t in queue[:10]]
            result["message"] = f"{len(queue)} morceau(s) dans la queue"
        
        # === FAVORIS ===
        elif action == "like":
            result["success"] = sp.like_current_track()
            result["message"] = "Morceau liké"
        
        elif action == "unlike":
            result["success"] = sp.unlike_current_track()
            result["message"] = "Morceau unliké"
        
        # === PLAYLISTS ===
        elif action == "playlists":
            playlists = sp.get_user_playlists()
            result["success"] = True
            result["data"] = [p.to_dict() for p in playlists]
            result["message"] = f"{len(playlists)} playlist(s)"
        
        elif action == "create_playlist":
            name = kwargs.get("name", "Nouvelle Playlist")
            public = kwargs.get("public", True)
            playlist = sp.create_playlist(name, public=public)
            result["success"] = playlist is not None
            result["data"] = playlist.to_dict() if playlist else None
            result["message"] = f"Playlist créée: {name}"
        
        # === APPAREILS ===
        elif action == "devices":
            devices = sp.get_devices()
            result["success"] = True
            result["data"] = [d.to_dict() for d in devices]
            result["message"] = f"{len(devices)} appareil(s) disponible(s)"
        
        elif action == "transfer":
            device_name = kwargs.get("device_name", "")
            result["success"] = sp.transfer_to_device_by_name(device_name)
            result["message"] = f"Transféré vers: {device_name}"
        
        # === HISTORIQUE & TOPS ===
        elif action == "history":
            history = sp.get_recently_played()
            result["success"] = True
            result["data"] = [t.to_dict() for t in history]
            result["message"] = f"{len(history)} morceau(s) récent(s)"
        
        elif action == "top_tracks":
            period = kwargs.get("period", "medium_term")
            tracks = sp.get_top_tracks(time_range=period)
            result["success"] = True
            result["data"] = [t.to_dict() for t in tracks]
            result["message"] = f"Top {len(tracks)} morceaux"
        
        elif action == "top_artists":
            period = kwargs.get("period", "medium_term")
            artists = sp.get_top_artists(time_range=period)
            result["success"] = True
            result["data"] = [a.to_dict() for a in artists]
            result["message"] = f"Top {len(artists)} artistes"
        
        # === RECOMMANDATIONS ===
        elif action == "recommendations":
            recs = sp.get_recommendations_from_current()
            result["success"] = len(recs) > 0
            result["data"] = [t.to_dict() for t in recs]
            result["message"] = f"{len(recs)} recommandation(s)"
        
        # === INFOS DÉTAILLÉES ===
        elif action == "info":
            info_type = kwargs.get("type", "track")
            item_id = kwargs.get("id", "")
            
            if info_type == "track":
                data = sp.get_track_details(item_id)
            elif info_type == "artist":
                data = sp.get_artist_details(item_id)
            elif info_type == "album":
                data = sp.get_album_details(item_id)
            else:
                data = None
            
            result["success"] = data is not None
            result["data"] = data
            result["message"] = f"Infos {info_type}"
        
        # === OUVERTURE DE PAGES ===
        elif action == "open_artist":
            name = (kwargs.get("name") or "").strip()
            if not name:
                result["success"] = False
                result["message"] = "Paramètre 'name' requis pour open_artist"
            else:
                ok = sp.open_artist_page(name)
                result["success"] = ok
                result["message"] = f"Page de l'artiste '{name}' ouverte dans l'application" if ok else f"Impossible d'ouvrir la page de l'artiste '{name}'"
        
        # === APPLICATION ===
        elif action == "open":
            result["success"] = sp.open_spotify()
            result["message"] = "Spotify ouvert"
        
        elif action == "close":
            result["success"] = sp.close_spotify()
            result["message"] = "Spotify fermé"
        
        # === STATUS COMPLET ===
        elif action == "status":
            result["success"] = True
            result["data"] = sp.get_playback_info()
            result["message"] = "État de lecture"
        
        else:
            result["message"] = f"Action inconnue: {action}"
        
    except Exception as e:
        result["message"] = f"Erreur: {str(e)}"
        print(f"⚠️ [SPOTIFY TOOL] Erreur: {e}")
    
    return json.dumps(result, ensure_ascii=False)


# ============================================================================
# TOOL DECLARATION POUR GEMINI
# ============================================================================

SPOTIFY_TOOL_DECLARATION = {
    "name": "spotify_control",
    "description": """Contrôle complet de l'application Spotify sur PC.

Ce module permet de contrôler TOUTES les fonctionnalités de Spotify comme un humain le ferait.

Actions principales:
- connect: Se connecter à Spotify (nécessaire au démarrage)
- play/pause/toggle: Contrôle de lecture (play = lancer, pause = mettre en pause, toggle = basculer)
- next/previous: Navigation entre morceaux (next = suivant, previous = précédent)
- volume/volume_up/volume_down/mute: Contrôle du volume (volume avec level 0-100, volume_up, volume_down, mute)
- shuffle/repeat: Modes de lecture (shuffle avec state true/false, repeat avec mode off/track/context)
- current: Obtenir le morceau actuellement en lecture
- search: Rechercher sur Spotify (query: terme de recherche, type: track/album/artist/playlist, limit: nombre de résultats)
- play_track: Lancer une chanson par son nom (name: nom de la chanson)
- play_album: Lancer un album par son nom (name: nom de l'album)
- play_playlist: Lancer une playlist par son nom (name: nom de la playlist)
- play_artist: Lancer les morceaux d'un artiste par son nom (name: nom de l'artiste)
- open_artist: Ouvrir la page web d'un artiste dans le navigateur (name: nom de l'artiste)
- queue_add: Ajouter une chanson à la file d'attente (name: nom de la chanson)
- queue_show: Afficher la file d'attente actuelle
- like/unlike: Ajouter/retirer le morceau actuel des favoris
- playlists: Lister toutes les playlists de l'utilisateur
- create_playlist: Créer une nouvelle playlist (name: nom, public: true/false)
- devices: Lister tous les appareils disponibles (haut-parleurs, téléphone, etc.)
- transfer: Transférer la lecture vers un autre appareil (device_name: nom de l'appareil)
- history: Afficher l'historique récent de lecture
- top_tracks: Mes morceaux les plus écoutés (period: short_term/medium_term/long_term)
- top_artists: Mes artistes les plus écoutés (period: short_term/medium_term/long_term)
- recommendations: Obtenir des recommandations basées sur le morceau actuel
- info: Infos détaillées sur un morceau/album/artiste (type: track/album/artist, id: ID Spotify)
- open: Ouvrir l'application Spotify sur l'ordinateur
- close: Fermer l'application Spotify
- status: Obtenir l'état complet de la lecture actuelle (morceau, volume, shuffle, repeat, etc.)

Exemples d'utilisation:
- "Lance moi Bohemian Rhapsody" → action: play_track, name: "Bohemian Rhapsody"
- "Ouvre moi la page de Queen" → action: open_artist, name: "Queen"
- "Lance la playlist Mes Favoris" → action: play_playlist, name: "Mes Favoris"
- "Lance l'album Abbey Road" → action: play_album, name: "Abbey Road"
- "Joue les morceaux de The Beatles" → action: play_artist, name: "The Beatles"
- "Passe au morceau suivant" → action: next
- "Met en pause" → action: pause
- "Augmente le volume" → action: volume_up""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action à effectuer",
                "enum": [
                    "connect", "play", "pause", "toggle", "next", "previous",
                    "volume", "volume_up", "volume_down", "mute",
                    "shuffle", "repeat", "seek", "current",
                    "search", "play_track", "play_album", "play_playlist", "play_artist",
                    "open_artist", "queue_add", "queue_show", "like", "unlike",
                    "playlists", "create_playlist", "devices", "transfer",
                    "history", "top_tracks", "top_artists", "recommendations",
                    "info", "open", "close", "status"
                ]
            },
            "query": {
                "type": "string",
                "description": "Terme de recherche (pour search)"
            },
            "name": {
                "type": "string",
                "description": "Nom du morceau/album/playlist/artiste"
            },
            "type": {
                "type": "string",
                "description": "Type de recherche ou d'info",
                "enum": ["track", "album", "artist", "playlist"]
            },
            "level": {
                "type": "integer",
                "description": "Niveau de volume (0-100)"
            },
            "state": {
                "type": "boolean",
                "description": "État on/off (pour shuffle)"
            },
            "mode": {
                "type": "string",
                "description": "Mode repeat",
                "enum": ["off", "track", "context"]
            },
            "position_ms": {
                "type": "integer",
                "description": "Position en millisecondes (pour seek)"
            },
            "device_name": {
                "type": "string",
                "description": "Nom de l'appareil (pour transfer)"
            },
            "period": {
                "type": "string",
                "description": "Période pour top tracks/artists",
                "enum": ["short_term", "medium_term", "long_term"]
            },
            "id": {
                "type": "string",
                "description": "ID Spotify (pour info détaillées)"
            },
            "public": {
                "type": "boolean",
                "description": "Playlist publique (pour create_playlist)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre de résultats"
            }
        },
        "required": ["action"]
    }
}


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("🎵 Test du Spotify Controller")
    print("=" * 50)
    
    sp = get_spotify_controller()
    
    # Test connexion
    if sp.connect():
        print("\n📊 Infos utilisateur:")
        user = sp.get_user_info()
        if user:
            print(f"   Nom: {user['name']}")
            print(f"   Abonnement: {user['product']}")
        
        print("\n🎵 Morceau actuel:")
        print(sp.get_current_track_info())
        
        print("\n📱 Appareils:")
        for d in sp.get_devices():
            status = "🟢" if d.is_active else "⚪"
            print(f"   {status} {d.name} ({d.type}) - {d.volume_percent}%")
    else:
        print("❌ Connexion échouée")
