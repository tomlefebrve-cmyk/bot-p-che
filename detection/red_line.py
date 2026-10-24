"""
Trait / curseur — HSV rouge optimisé + fallback luminosité.
- 2 plages H (rouge traverse 0°)
- morphologie légère
- point le plus éloigné du centre = bout du trait
- lissage angulaire
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from detection.colors import cursor_mask


@dataclass
class RedLine:
    angle_deg: float
    confidence: float


class RedLineDetector:
    def __init__(self, settings):
        self.settings = settings
        self._last_angle: Optional[float] = None
        self._smooth = 0.40

    def reset(self) -> None:
        self._last_angle = None

    def _hsv_enhanced(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        v = clahe.apply(v)
        return cv2.merge([h, s, v])

    def detect(self, frame: np.ndarray, circle) -> Optional[RedLine]:
        if frame is None or circle is None:
            return None

        s = self.settings
        hsv = self._hsv_enhanced(frame)

        mask = cursor_mask(hsv, s)  # rouge par défaut, bleu si target_color = "red"

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)

        ring = np.zeros(mask.shape, dtype=np.uint8)
        cv2.circle(ring, (circle.x, circle.y), int(circle.r * 1.14), 255, -1)
        cv2.circle(ring, (circle.x, circle.y), int(circle.r * 0.28), 0, -1)
        mask = cv2.bitwise_and(mask, ring)

        # fallback : pointeur très clair (blanc / jaune clair)
        if cv2.countNonZero(mask) < 6:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            bright = cv2.inRange(gray, 195, 255)
            # exclure le centre (lettre)
            bright = cv2.bitwise_and(bright, ring)
            mask = bright

        ys, xs = np.where(mask > 0)
        n = len(xs)
        if n < 4:
            return None

        # pondérer par distance au centre → favorise le bout du trait
        dx = xs.astype(np.float64) - circle.x
        dy = ys.astype(np.float64) - circle.y
        dist = np.sqrt(dx * dx + dy * dy)
        # top 25% les plus loin
        thr = np.percentile(dist, 75)
        sel = dist >= thr
        if not np.any(sel):
            sel = dist >= dist.max() * 0.85
        dx_s, dy_s = dx[sel], dy[sel]
        # angle moyen des pixels lointains
        rad = np.arctan2(-dy_s, dx_s)
        mx, my = float(np.mean(np.cos(rad))), float(np.mean(np.sin(rad)))
        ang = math.degrees(math.atan2(my, mx)) % 360.0

        if self._last_angle is not None:
            d = ((ang - self._last_angle + 180) % 360) - 180
            ang = (self._last_angle + self._smooth * d) % 360.0
        self._last_angle = ang

        conf = float(np.clip(n / 40.0, 0.15, 1.0))
        return RedLine(float(ang), conf)
