"""Détection du cercle — OpenCV HoughCircles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class Circle:
    x: int
    y: int
    r: int
    confidence: float


class CircleDetector:
    def __init__(self, settings=None):
        self.settings = settings
        self._last: Optional[Circle] = None
        self.used_fallback = False

    def _fallback(self, w: int, h: int) -> Optional[Circle]:
        """Cercle fixe (réglé par la calibration) quand la détection automatique échoue."""
        s = self.settings
        if s is None or not getattr(s, "circle_fallback", False):
            return None
        m = min(w, h)
        return Circle(int(s.circle_cx * w), int(s.circle_cy * h), max(14, int(s.circle_r * m)), 0.45)

    def reset(self) -> None:
        self._last = None

    def detect(self, frame: np.ndarray) -> Optional[Circle]:
        if frame is None or frame.size == 0:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        h, w = gray.shape[:2]
        min_r = max(14, min(h, w) // 7)
        max_r = max(min_r + 8, min(h, w) // 2)

        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(25, min(h, w) // 3),
            param1=100,
            param2=30,
            minRadius=min_r,
            maxRadius=max_r,
        )

        if circles is None:
            edges = cv2.Canny(gray, 50, 130)
            circles = cv2.HoughCircles(
                edges,
                cv2.HOUGH_GRADIENT,
                dp=1.1,
                minDist=max(20, min(h, w) // 4),
                param1=80,
                param2=22,
                minRadius=min_r,
                maxRadius=max_r,
            )

        if circles is None:
            if self._last is not None:
                return self._last
            fb = self._fallback(w, h)
            self.used_fallback = fb is not None
            return fb

        self.used_fallback = False
        circles = np.round(circles[0]).astype(int)
        cx, cy = w // 2, h // 2
        best: Optional[Circle] = None
        best_score = -1e9
        for x, y, r in circles:
            dist = float(np.hypot(x - cx, y - cy))
            score = float(r) - dist * 0.2
            if score > best_score:
                best_score = score
                conf = min(1.0, 0.4 + r / float(max_r) * 0.6)
                best = Circle(int(x), int(y), int(r), conf)

        if best is not None:
            self._last = best
        return best
