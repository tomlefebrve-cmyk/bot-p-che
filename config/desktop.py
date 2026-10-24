"""Raccourci sur le bureau (version .exe) — créé via PowerShell, sans dépendance."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Tuple

from config.settings import FROZEN

NAME = "AUTO FISHER"


def _q(text: str) -> str:
    return text.replace("'", "''")        # guillemets simples PowerShell


def shortcut_script(target: str, name: str = NAME) -> str:
    return (
        "$d=[Environment]::GetFolderPath('Desktop');"
        f"$l=Join-Path $d '{_q(name)}.lnk';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l);"
        f"$s.TargetPath='{_q(target)}';"
        f"$s.WorkingDirectory='{_q(os.path.dirname(target))}';"
        f"$s.IconLocation='{_q(target)},0';"
        f"$s.Description='{_q(name)}';"
        "$s.Save()"
    )


def create_desktop_shortcut() -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Le raccourci se crée uniquement sous Windows."
    if not FROZEN:
        return False, "Disponible dans la version .exe (AUTO_FISHER.exe)."
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", shortcut_script(sys.executable)],
            capture_output=True, text=True, timeout=25, creationflags=0x08000000,   # sans fenêtre
        )
    except Exception as exc:                       # noqa: BLE001
        return False, f"Impossible de créer le raccourci : {exc}"
    if r.returncode != 0:
        return False, "Impossible de créer le raccourci (PowerShell a refusé)."
    return True, "Raccourci « AUTO FISHER » créé sur le bureau."
