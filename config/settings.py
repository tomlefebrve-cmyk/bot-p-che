"""Configuration centrale AUTO FISHER."""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict

# Version .exe (PyInstaller) : les fichiers modifiables (réglages, templates)
# vivent dans %APPDATA%\\AUTO_FISHER ; les fichiers d'origine sont dans le .exe.
FROZEN = bool(getattr(sys, "frozen", False))
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _data_dir() -> str:
    """Dossier des réglages / templates du .exe : %APPDATA%\\AUTO_FISHER (jamais à côté du .exe)."""
    base = os.environ.get("APPDATA")
    candidates = []
    if base:
        candidates.append(os.path.join(base, "AUTO_FISHER"))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "AUTO_FISHER_data"))
    candidates.append(os.path.join(os.path.expanduser("~"), "AUTO_FISHER_data"))
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except OSError:
            continue
    return os.path.dirname(sys.executable)


ROOT = _data_dir() if FROZEN else _SRC
RES_DIR = getattr(sys, "_MEIPASS", _SRC)
CFG_PATH = os.path.join(ROOT, "user_config.json")


def ensure_default_templates() -> None:
    """Première exécution du .exe : copie les templates Z/Q/S/D dans le dossier utilisateur."""
    if not FROZEN:
        return
    src = os.path.join(RES_DIR, "templates")
    dst = os.path.join(ROOT, "templates")
    if not os.path.isdir(src):
        return
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            target = os.path.join(dst, rel, f)
            if not os.path.isfile(target):
                shutil.copy2(os.path.join(dirpath, f), target)


@dataclass
class Settings:
    capture_left: int = 860
    capture_top: int = 480
    capture_size: int = 220

    poll_interval_ms: int = 30
    tolerance_deg: float = 8.0
    reaction_delay_ms: int = 15
    align_confirm_frames: int = 1
    press_only_when_aligned: bool = False
    min_key_interval_ms: int = 120
    post_catch_cooldown_ms: int = 400
    max_wait_ms: int = 12000

    debug_mode: bool = True
    sounds_enabled: bool = True
    hotkey_toggle: str = "f8"

    # Touches du mini-jeu (lettres possibles)
    keys_enabled: str = "z,q,s,d"
    key_templates_dir: str = "templates/keys"
    key_min_confidence: float = 0.75   # score minimum pour accepter une lettre
    key_min_margin: float = 0.06       # écart minimum avec la 2e lettre

    key_send_mode: str = "layout"      # "layout" = selon le clavier (AZERTY ok) · "classic" = ancien envoi QWERTY
    cycle_enabled: bool = False        # pêche : marche X s puis pause Y s, en boucle
    cycle_run_s: int = 10
    cycle_pause_s: int = 10
    # --- Anti-spam : n'appuie que si un vrai mini-jeu est là, et limite le nombre d'appuis ---
    anti_spam: bool = True
    anti_spam_max: int = 8             # appuis maximum ...
    anti_spam_window_s: int = 10       # ... par fenêtre de X secondes
    anti_spam_pause_s: int = 10        # pause quand la limite est atteinte / rien de valide
    anti_spam_fail_limit: int = 8      # échecs d'affilée avant une pause
    key_votes_needed: int = 2          # lectures concordantes avant de valider la lettre

    # Disposition des couleurs du mini-jeu :
    #   "blue"     arc bleu  + curseur rouge
    #   "red"      arc rouge + curseur rouge (séparés par le mouvement)
    #   "red_blue" arc rouge + curseur bleu
    target_color: str = "red"

    # Cercle : si la détection automatique échoue, on utilise ce cercle fixe
    # (fractions de la zone de capture). Réglé par la calibration automatique.
    circle_fallback: bool = True
    circle_cx: float = 0.5
    circle_cy: float = 0.5
    circle_r: float = 0.36

    desktop_shortcut_done: bool = False
    auto_check_updates: bool = True      # cherche une mise à jour au lancement (jamais d'installation sans ton accord)
    update_repo: str = ""                # remplace UPDATE_REPO de config/version.py si renseigné

    # --- Auto Clicker ---
    ac_hours: int = 0
    ac_minutes: int = 0
    ac_seconds: int = 1
    ac_ms: int = 0
    ac_infinite: bool = True
    ac_count: int = 10
    ac_button: str = "left"          # left | right
    ac_cycle: bool = False           # auto-clic : marche X s puis pause Y s, en boucle
    ac_cycle_run: int = 10
    ac_cycle_pause: int = 10
    ac_fixed: bool = False           # False = position actuelle du curseur
    ac_x: int = 0
    ac_y: int = 0
    ac_hk_start: int = 109           # Numpad -
    ac_hk_stop: int = 106            # Numpad *
    ac_hk_toggle: int = 111          # Numpad /

    blue_h_min: int = 85
    blue_h_max: int = 135
    blue_s_min: int = 60
    blue_v_min: int = 60
    red_h_min1: int = 0
    red_h_max1: int = 12
    red_h_min2: int = 168
    red_h_max2: int = 179
    red_s_min: int = 70
    red_v_min: int = 70

    def templates_path(self) -> str:
        """Dossier des templates de touches (relatif → depuis la racine du projet)."""
        d = self.key_templates_dir or "templates/keys"
        return d if os.path.isabs(d) else os.path.join(ROOT, d)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        if os.path.isfile(CFG_PATH):
            try:
                with open(CFG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            except Exception:
                pass
        return s

    def save(self) -> None:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
