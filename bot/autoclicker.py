"""
Auto-clic (comme GT Auto Clicker) — indépendant du mode pêche.

Windows uniquement, sans dépendance : tout passe par ctypes (user32 / winmm).
Sur un autre système le moteur existe mais ne clique pas (utile pour les tests).
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Dict, Optional, Tuple

# (appui, relâchement) pour SendInput / mouse_event
_MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}
_MOVE_ABS = 0x0001 | 0x8000 | 0x4000        # MOVE | ABSOLUTE | VIRTUALDESK
_IGNORED_VK = {0x01, 0x02, 0x04, 0x05, 0x06}          # boutons de souris


class WinBackend:
    """Clic, position du curseur et lecture des touches via l'API Windows."""

    available = sys.platform == "win32"
    hold = 0.012            # durée de l'appui (s) : certains jeux/navigateurs ignorent un clic instantané

    def __init__(self):
        if not self.available:
            return
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._pt = wintypes.POINT
        self.user32 = u = ctypes.windll.user32
        self.winmm = ctypes.windll.winmm
        self.kernel32 = ctypes.windll.kernel32
        self.advapi32 = ctypes.windll.advapi32

        ULONG_PTR = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self._MOUSEINPUT, self._U, self._INPUT = MOUSEINPUT, _U, INPUT
        u.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        u.SendInput.restype = wintypes.UINT
        u.WindowFromPoint.argtypes = [wintypes.POINT]
        u.WindowFromPoint.restype = ctypes.c_void_p
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = ctypes.c_void_p
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        self.advapi32.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                      wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

    def cursor_pos(self) -> Tuple[int, int]:
        if not self.available:
            return (0, 0)
        p = self._pt()
        self.user32.GetCursorPos(self._ct.byref(p))
        return (p.x, p.y)

    def set_cursor_pos(self, x: int, y: int) -> None:
        if self.available:
            self.user32.SetCursorPos(int(x), int(y))

    def _send(self, flags: int, dx: int = 0, dy: int = 0) -> int:
        inp = self._INPUT(type=0, u=self._U(mi=self._MOUSEINPUT(dx, dy, 0, flags, 0, 0)))
        return self.user32.SendInput(1, self._ct.byref(inp), self._ct.sizeof(inp))

    def _move_here(self) -> None:
        """Vrai évènement « la souris est ici » : certains programmes n'acceptent un clic qu'après."""
        gm = self.user32.GetSystemMetrics
        vx, vy, vw, vh = gm(76), gm(77), gm(78), gm(79)
        x, y = self.cursor_pos()
        self._send(_MOVE_ABS, int(round((x - vx) * 65535 / max(1, vw - 1))),
                   int(round((y - vy) * 65535 / max(1, vh - 1))))

    def click(self, button: str) -> None:
        """Déplacement réel → appui → petite pause → relâchement (toujours relâché)."""
        if not self.available:
            return
        down, up = _MOUSE_FLAGS.get(button, _MOUSE_FLAGS["left"])
        try:
            self._move_here()
        except Exception:
            pass
        try:
            ok = self._send(down) == 1
        except Exception:
            ok = False
        if ok:
            if self.hold > 0:
                time.sleep(self.hold)
            try:
                self._send(up)
            except Exception:
                self.user32.mouse_event(up, 0, 0, 0, 0)
        else:                                       # repli : ancienne méthode
            self.user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(self.hold)
            self.user32.mouse_event(up, 0, 0, 0, 0)

    # ---- droits d'administrateur -------------------------------------------------
    def is_admin(self) -> bool:
        try:
            return bool(self.available and self._ct.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def target_blocked(self, pos: Optional[Tuple[int, int]] = None) -> Optional[bool]:
        """True si la fenêtre visée tourne en administrateur alors que nous non : Windows bloque
        alors les clics (UIPI). None = on ne sait pas."""
        if not self.available or self.is_admin():
            return False
        try:
            x, y = pos if pos is not None else self.cursor_pos()
            hwnd = self.user32.WindowFromPoint(self._pt(int(x), int(y)))
            if not hwnd:
                return None
            from ctypes import wintypes
            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, self._ct.byref(pid))
            if pid.value == self._ct.windll.kernel32.GetCurrentProcessId():
                return False
            h = self.kernel32.OpenProcess(0x1000, False, pid.value)       # QUERY_LIMITED_INFORMATION
            if not h:
                return True                        # accès refusé : processus protégé / administrateur
            try:
                tok = self._ct.c_void_p()
                if not self.advapi32.OpenProcessToken(h, 0x0008, self._ct.byref(tok)):   # TOKEN_QUERY
                    return True
                try:
                    elev, size = wintypes.DWORD(0), wintypes.DWORD(0)
                    if not self.advapi32.GetTokenInformation(tok, 20, self._ct.byref(elev), 4,
                                                             self._ct.byref(size)):      # TokenElevation
                        return None
                    return bool(elev.value)
                finally:
                    self.kernel32.CloseHandle(tok)
            finally:
                self.kernel32.CloseHandle(h)
        except Exception:
            return None

    def is_down(self, vk: int) -> bool:
        return bool(self.available and (self.user32.GetAsyncKeyState(int(vk)) & 0x8000))

    def timer_begin(self) -> None:          # précision 1 ms pour les petits intervalles
        if self.available:
            self.winmm.timeBeginPeriod(1)

    def timer_end(self) -> None:
        if self.available:
            self.winmm.timeEndPeriod(1)


class AutoClicker:
    """États : idle → (countdown) → running → idle."""

    def __init__(self, backend=None, on_log: Optional[Callable[[str], None]] = None):
        self.b = backend or WinBackend()
        self.on_log = on_log or (lambda m: None)
        self.interval_ms = 1000
        self.button = "left"
        self.repeat = 0                       # 0 = infini
        self.pos: Optional[Tuple[int, int]] = None   # None = position actuelle
        self.cycle_run = 0.0                  # secondes de marche (0 = pas de cycle)
        self.cycle_pause = 0.0                # secondes de pause
        self.state = "idle"
        self.count = 0
        self.remaining = 0.0                  # compte à rebours avant le 1er clic
        self._stop = threading.Event()
        self._lock = threading.Lock()         # garantit : aucun clic après stop()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self.state != "idle"

    def configure(self, interval_ms: int, button: str = "left", repeat: int = 0,
                  pos: Optional[Tuple[int, int]] = None, cycle_run: float = 0.0,
                  cycle_pause: float = 0.0) -> None:
        self.interval_ms = max(1, int(interval_ms))
        self.button = button if button in _MOUSE_FLAGS else "left"
        self.repeat = max(0, int(repeat))
        self.pos = pos
        on = cycle_run > 0 and cycle_pause > 0
        self.cycle_run, self.cycle_pause = (float(cycle_run), float(cycle_pause)) if on else (0.0, 0.0)

    def start(self, delay: float = 0.0) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self.count = 0
        self.remaining = float(delay)
        self.state = "countdown" if delay > 0 else "running"
        self._thread = threading.Thread(target=self._run, args=(float(delay),), daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Arrêt immédiat : quand cette méthode rend la main, plus aucun clic ne partira."""
        with self._lock:
            self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=1.0)
        self.state = "idle"

    def toggle(self, delay: float = 0.0) -> None:
        if self.running:
            self.stop()
        else:
            self.start(delay)

    # ------------------------------------------------------------------
    def _run(self, delay: float) -> None:
        self.b.timer_begin()
        reason = "arrêté"
        try:
            if delay > 0:
                end = time.perf_counter() + delay
                while not self._stop.is_set():
                    rem = end - time.perf_counter()
                    if rem <= 0:
                        break
                    self.remaining = rem
                    self._stop.wait(min(0.05, rem))
                if self._stop.is_set():
                    return
                self.state = "running"
            interval = self.interval_ms / 1000.0
            if hasattr(self.b, "hold"):                    # appui tenu, mais jamais plus que l'intervalle
                self.b.hold = min(0.012, interval * 0.5)
            cycle = self.cycle_run > 0 and self.cycle_pause > 0
            phase = "run"
            phase_end = time.perf_counter() + self.cycle_run
            nxt = time.perf_counter()
            while True:
                now = time.perf_counter()
                if cycle and now >= phase_end:            # marche ↔ pause
                    if phase == "run":
                        phase, phase_end, self.state = "pause", now + self.cycle_pause, "paused"
                        self.on_log(f"[INFO] Auto-clic : pause ({self.cycle_pause:g} s)")
                    else:
                        phase, phase_end, self.state, nxt = "run", now + self.cycle_run, "running", now
                        self.on_log(f"[INFO] Auto-clic : reprise ({self.cycle_run:g} s)")
                if phase == "pause":
                    self.remaining = max(0.0, phase_end - now)
                    if self._stop.wait(min(0.05, self.remaining)):
                        return
                    continue
                if now < nxt:
                    wait = nxt - now
                    if cycle:
                        wait = min(wait, max(0.0, phase_end - now))
                    if self._stop.wait(wait):
                        return
                    continue
                with self._lock:                          # vérifié juste avant CHAQUE clic
                    if self._stop.is_set():
                        return
                    if self.pos is not None:
                        self.b.set_cursor_pos(*self.pos)
                    self.b.click(self.button)
                    self.count += 1
                if self.repeat and self.count >= self.repeat:
                    reason = "terminé"
                    return
                nxt += interval
                if nxt < time.perf_counter():
                    nxt = time.perf_counter()             # on ne rattrape pas le retard
        finally:
            self.b.timer_end()
            self.state = "idle"
            self.on_log(f"[INFO] Auto-clic {reason} — {self.count} clic(s)")


# ---------------------------------------------------------------------- raccourcis
VK_DEFAULTS = {"start": 109, "stop": 106, "toggle": 111}      # Numpad - , * , /


def vk_name(vk: int) -> str:
    vk = int(vk)
    if 0x60 <= vk <= 0x69:
        return f"Numpad {vk - 0x60}"
    named = {0x6A: "Numpad *", 0x6B: "Numpad +", 0x6D: "Numpad -", 0x6E: "Numpad .",
             0x6F: "Numpad /", 0x20: "Espace", 0x0D: "Entrée", 0x09: "Tab", 0x2D: "Inser",
             0x2E: "Suppr", 0x24: "Début", 0x23: "Fin", 0x21: "Page haut", 0x22: "Page bas",
             0x26: "Flèche haut", 0x28: "Flèche bas", 0x25: "Flèche gauche", 0x27: "Flèche droite"}
    if vk in named:
        return named[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"Touche {vk}"


def scan_pressed(backend) -> Optional[int]:
    """Première touche actuellement enfoncée (pour « Modifier » un raccourci), hors souris/Échap."""
    for vk in range(8, 255):
        if vk in _IGNORED_VK or vk in (0x1B, 0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            continue
        if backend.is_down(vk):
            return vk
    return None


class HotkeyPoller(threading.Thread):
    """Surveille les raccourcis même quand le jeu est au premier plan (sans hook clavier)."""

    def __init__(self, backend, callbacks: Dict[str, Callable[[], None]], keys: Dict[str, int]):
        super().__init__(daemon=True)
        self.b = backend
        self.callbacks = callbacks
        self.keys = dict(keys)
        self.paused = False                   # pendant « Modifier un raccourci »
        self._alive = True
        self._prev: Dict[str, bool] = {}

    def set_keys(self, keys: Dict[str, int]) -> None:
        self.keys = dict(keys)

    def close(self) -> None:
        self._alive = False

    def run(self) -> None:
        while self._alive:
            for name, vk in list(self.keys.items()):
                down = self.b.is_down(vk)
                if down and not self._prev.get(name, False) and not self.paused:
                    try:
                        self.callbacks[name]()
                    except Exception:
                        pass
                self._prev[name] = down
            time.sleep(0.015)


def relaunch_as_admin() -> bool:
    """Relance AUTO FISHER avec les droits d'administrateur (Windows demande confirmation)."""
    if sys.platform != "win32":
        return False
    import ctypes
    import os
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, ""
    else:
        exe = sys.executable
        params = '"%s"' % os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    try:
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1) > 32
    except Exception:
        return False
