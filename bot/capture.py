"""Capture d'une région d'écran."""
from __future__ import annotations

import threading

import numpy as np

try:
    import mss
except ImportError:
    mss = None


class ScreenCapture:
    def __init__(self, left: int, top: int, size: int):
        self.left = left
        self.top = top
        self.size = size
        self._sct = None
        self._tid = None

    def set_region(self, left: int, top: int, size: int) -> None:
        self.left, self.top, self.size = int(left), int(top), int(size)

    def grab(self):
        if mss is None:
            return None
        tid = threading.get_ident()
        if self._sct is None or self._tid != tid:   # mss : un handle par thread
            self._sct = mss.mss()
            self._tid = tid
        mon = {
            "left": self.left,
            "top": self.top,
            "width": self.size,
            "height": self.size,
        }
        shot = self._sct.grab(mon)
        return np.array(shot)[:, :, :3]
