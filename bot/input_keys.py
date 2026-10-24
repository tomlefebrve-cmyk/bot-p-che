"""
Envoi de touches clavier — compatible AZERTY, QWERTY, etc.

Problème d'origine : `pydirectinput` envoie toujours les positions d'un clavier QWERTY.
Sur un clavier AZERTY, « Z » tombait sur la touche W et « Q » sur la touche A (S et D sont
à la même place sur les deux, donc ils marchaient). Ici on demande à Windows quelle touche
physique produit la lettre voulue AVEC LA DISPOSITION ACTIVE (celle de la fenêtre du jeu),
puis on envoie cette touche.
"""
from __future__ import annotations

import sys
import time
from typing import Optional, Tuple

try:
    import pydirectinput
    pydirectinput.PAUSE = 0.02
except ImportError:
    pydirectinput = None

_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008


class Win32Api:
    """Les 3 appels Windows utilisés (remplaçable dans les tests)."""

    available = sys.platform == "win32"

    def __init__(self):
        if not self.available:
            return
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        u = self.user32 = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        u.GetKeyboardLayout.restype = ctypes.c_void_p
        u.VkKeyScanExW.argtypes = [wintypes.WCHAR, ctypes.c_void_p]
        u.VkKeyScanExW.restype = ctypes.c_short
        u.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
        u.MapVirtualKeyExW.restype = wintypes.UINT
        u.SendInput.restype = wintypes.UINT

        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self._KEYBDINPUT, self._INPUT, self._U = KEYBDINPUT, INPUT, _U

    def layout(self):
        """Disposition de clavier de la fenêtre au premier plan (le jeu), sinon celle du processus."""
        fg = self.user32.GetForegroundWindow()
        tid = self.user32.GetWindowThreadProcessId(fg, None) if fg else 0
        return self.user32.GetKeyboardLayout(tid)

    def vk_scan(self, ch: str, hkl) -> Optional[Tuple[int, int]]:
        """(touche virtuelle, scancode) qui produit `ch` avec cette disposition, ou None."""
        res = self.user32.VkKeyScanExW(ch, hkl)
        if res == -1:
            return None
        vk = res & 0xFF
        scan = self.user32.MapVirtualKeyExW(vk, 0, hkl)      # MAPVK_VK_TO_VSC
        return (vk, scan) if scan else None

    def send_scan(self, scan: int, up: bool) -> bool:
        flags = _KEYEVENTF_SCANCODE | (_KEYEVENTF_KEYUP if up else 0)
        inp = self._INPUT(type=1, u=self._U(ki=self._KEYBDINPUT(0, scan, flags, 0, 0)))
        return self.user32.SendInput(1, self._ct.byref(inp), self._ct.sizeof(inp)) == 1

    def layout_name(self) -> str:
        if not self.available:
            return "inconnue"
        buf = self._ct.create_unicode_buffer(16)
        self.user32.GetKeyboardLayoutNameW(buf)
        return buf.value or "inconnue"


class Keyboard:
    """mode « layout » (défaut) : selon le clavier réel ; « classic » : ancien envoi QWERTY."""

    HOLD = 0.025

    def __init__(self, api: Optional[Win32Api] = None, mode: str = "layout"):
        self.api = api or Win32Api()
        self.mode = mode
        self.last_scan: Optional[int] = None      # pour les tests / diagnostic

    def _press_layout(self, ch: str) -> bool:
        api = self.api
        if not getattr(api, "available", False) or len(ch) != 1:
            return False
        try:
            found = api.vk_scan(ch, api.layout())
            if not found:
                return False
            scan = found[1]
            if not api.send_scan(scan, up=False):
                return False
            time.sleep(self.HOLD)
            api.send_scan(scan, up=True)
            self.last_scan = scan
            return True
        except Exception:
            return False

    def press(self, key: str) -> bool:
        if not key:
            return False
        key = key.lower()
        if self.mode != "classic" and self._press_layout(key):
            return True
        if pydirectinput is None:
            return False
        try:
            pydirectinput.press(key)
            return True
        except Exception:
            return False
