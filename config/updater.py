"""
Mises à jour via GitHub Releases (https, sans dépendance).

Principe : au lancement (ou sur demande) on regarde la dernière « release » du dépôt.
Si elle est plus récente on propose de l'installer ; rien n'est installé sans clic de l'utilisateur.
Sécurité : https uniquement, hôtes GitHub uniquement, empreinte SHA-256 obligatoire
(fichier AUTO_FISHER.exe.sha256 publié avec la release), fichier Windows vérifié (MZ).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

ASSET_EXE = "AUTO_FISHER.exe"
ASSET_SHA = "AUTO_FISHER.exe.sha256"
MANDATORY_TAG = "[OBLIGATOIRE]"          # à écrire dans les notes de la release
MAX_BYTES = 600 * 1024 * 1024
DEFAULT_API = "https://api.github.com"
ALLOWED_HOST_SUFFIXES = ("github.com", "githubusercontent.com")


class UpdateError(Exception):
    """Erreur lisible par l'utilisateur."""


@dataclass
class UpdateInfo:
    version: str
    notes: str
    mandatory: bool
    exe_url: str
    sha_url: str
    size: int = 0


def api_base() -> str:
    return os.environ.get("AUTO_FISHER_API", DEFAULT_API).rstrip("/")     # remplaçable pour les tests


def parse_version(v: str) -> Tuple[int, ...]:
    nums = [int(n) for n in re.findall(r"\d+", str(v))[:4]] or [0]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()                                  # 2.1 == 2.1.0
    return tuple(nums)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def _allowed(url: str) -> bool:
    u = urlparse(url)
    base = api_base()
    if base != DEFAULT_API:                         # tests : serveur local explicite
        return url.startswith(base)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES)


def _open(url: str, timeout: float):
    if not _allowed(url):
        raise UpdateError("Adresse de téléchargement refusée (hôte non autorisé).")
    req = urllib.request.Request(url, headers={"User-Agent": "AUTO-FISHER-updater",
                                               "Accept": "application/vnd.github+json, application/octet-stream"})
    return urllib.request.urlopen(req, timeout=timeout)


def check(repo: str, current: str, timeout: float = 8.0) -> Tuple[str, object]:
    """('available', UpdateInfo) | ('uptodate', None) | ('disabled'|'error', message)."""
    repo = (repo or "").strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return "disabled", "Les mises à jour ne sont pas configurées."
    try:
        with _open(f"{api_base()}/repos/{repo}/releases/latest", timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "error", "Aucune version n'est encore publiée."
        if e.code in (403, 429):
            return "error", "GitHub limite les requêtes pour l'instant. Réessaie dans quelques minutes."
        return "error", f"Le serveur de mises à jour a répondu une erreur ({e.code})."
    except (urllib.error.URLError, TimeoutError, OSError):
        return "error", "Impossible de joindre le serveur de mises à jour (pas de connexion ?)."
    except (ValueError, UpdateError) as e:
        return "error", str(e) or "Réponse du serveur illisible."

    tag = str(data.get("tag_name", "")).strip()
    if not tag or not is_newer(tag, current):
        return "uptodate", None
    assets = {str(a.get("name", "")).lower(): a for a in data.get("assets", [])}
    exe, sha = assets.get(ASSET_EXE.lower()), assets.get(ASSET_SHA.lower())
    if not exe or not sha:
        return "error", (f"La version {tag.lstrip('v')} est annoncée mais son fichier n'est pas encore prêt "
                         "(la fabrication prend environ 5 minutes). Réessaie plus tard.")
    notes = str(data.get("body") or "").strip()
    return "available", UpdateInfo(
        version=tag.lstrip("vV"), notes=notes, mandatory=MANDATORY_TAG in notes.upper(),
        exe_url=str(exe.get("browser_download_url", "")), sha_url=str(sha.get("browser_download_url", "")),
        size=int(exe.get("size") or 0))


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False))


def download(info: UpdateInfo, dest: str, progress: Optional[Callable[[float], None]] = None,
             timeout: float = 20.0, require_pe: Optional[bool] = None) -> str:
    """Télécharge le nouvel exe vers `dest`, vérifie l'empreinte. Supprime le fichier si ça ne colle pas."""
    require_pe = (sys.platform == "win32") if require_pe is None else require_pe
    try:
        with _open(info.sha_url, timeout) as r:
            m = re.search(r"\b[0-9a-fA-F]{64}\b", r.read(4096).decode("utf-8", "ignore"))
    except (urllib.error.URLError, OSError, TimeoutError):
        raise UpdateError("Impossible de télécharger l'empreinte de vérification.")
    if not m:
        raise UpdateError("Empreinte de vérification absente ou illisible : mise à jour refusée.")
    expected = m.group(0).lower()

    h, got, first = hashlib.sha256(), 0, b""
    try:
        with _open(info.exe_url, timeout) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.size or 0)
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                if not first:
                    first = chunk[:2]
                got += len(chunk)
                if got > MAX_BYTES:
                    raise UpdateError("Fichier anormalement gros : mise à jour refusée.")
                h.update(chunk)
                f.write(chunk)
                if progress and total:
                    progress(min(1.0, got / total))
        if h.hexdigest() != expected:
            raise UpdateError("Le fichier téléchargé est corrompu ou a été modifié : mise à jour refusée.")
        if require_pe and first != b"MZ":
            raise UpdateError("Le fichier téléchargé n'est pas un programme Windows valide.")
    except UpdateError:
        _silent_remove(dest)
        raise
    except (urllib.error.URLError, OSError, TimeoutError):
        _silent_remove(dest)
        raise UpdateError("Le téléchargement a été interrompu. Réessaie.")
    return dest


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def install(new_path: str, current_exe: str) -> str:
    """Remplace l'exe : l'ancien est renommé en .old (Windows autorise de renommer un exe en cours),
    le nouveau prend sa place. Retour en arrière automatique si ça échoue."""
    folder = os.path.dirname(os.path.abspath(current_exe))
    if not os.access(folder, os.W_OK):
        raise UpdateError("Le dossier du programme n'est pas modifiable. Déplace AUTO_FISHER.exe "
                          "sur le Bureau ou dans Documents, puis relance la mise à jour.")
    old = current_exe + ".old"
    _silent_remove(old)
    try:
        os.replace(current_exe, old)
    except OSError:
        raise UpdateError("Impossible de remplacer le programme (fichier verrouillé ?).")
    try:
        os.replace(new_path, current_exe)
    except OSError:
        try:
            os.replace(old, current_exe)               # retour en arrière
        except OSError:
            pass
        raise UpdateError("Le remplacement a échoué : l'ancienne version a été conservée.")
    return old


def relaunch(exe: str) -> None:
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"         # le nouvel exe repart de zéro (PyInstaller)
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], env=env, close_fds=True, cwd=os.path.dirname(exe), **kw)


def cleanup_old() -> None:
    """Au démarrage : supprime l'ancienne version laissée par la dernière mise à jour."""
    if getattr(sys, "frozen", False):
        _silent_remove(sys.executable + ".old")
