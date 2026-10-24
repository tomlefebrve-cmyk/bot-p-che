"""
Zone bleue (cible) — HSV optimisé.
- CLAHE sur V pour stabiliser la lumière
- morphologie pour enlever le bruit
- anneau autour du cercle uniquement
- lissage angulaire (moyenne circulaire)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from detection.colors import target_mask


@dataclass
class BlueZone:
    center_angle_deg: float
    span_deg: float
    confidence: float


class BlueZoneDetector:
    def __init__(self, settings):
        self.settings = settings
        self._last_angle: Optional[float] = None
        self._smooth = 0.35  # 0 = pas de lissage, 1 = très lent

    def reset(self) -> None:
        self._last_angle = None

    def _hsv_enhanced(self, frame: np.ndarray) -> np.ndarray:
        """HSV avec CLAHE sur le canal V (meilleure robustesse lumière)."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        v = clahe.apply(v)
        return cv2.merge([h, s, v])

    def detect(self, frame: np.ndarray, circle) -> Optional[BlueZone]:
        if frame is None or circle is None:
            return None

        s = self.settings
        hsv = self._hsv_enhanced(frame)

        mask = target_mask(hsv, s)  # bleu par défaut, rouge si target_color = "red"

        # petit noyau : garde l'arc fin sans le gonfler trop
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

        # anneau : uniquement sur le bord du cercle
        ring = np.zeros(mask.shape, dtype=np.uint8)
        r_out = int(circle.r * 1.12)
        r_in = int(circle.r * 0.48)
        cv2.circle(ring, (circle.x, circle.y), r_out, 255, -1)
        cv2.circle(ring, (circle.x, circle.y), r_in, 0, -1)
        mask = cv2.bitwise_and(mask, ring)

        # supprimer les tout petits blobs
        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num > 1:
            clean = np.zeros_like(mask)
            for i in range(1, num):
                if stats[i, cv2.CC_STAT_AREA] >= 8:
                    clean[labels == i] = 255
            mask = clean

        ys, xs = np.where(mask > 0)
        n = len(xs)
        if n < 10:
            return None

        angles = np.degrees(np.arctan2(-(ys - circle.y), xs - circle.x)) % 360.0

        # moyenne circulaire
        rad = np.radians(angles)
        mx = float(np.mean(np.cos(rad)))
        my = float(np.mean(np.sin(rad)))
        center = math.degrees(math.atan2(my, mx)) % 360.0

        # lissage temporel
        if self._last_angle is not None:
            # interpolation circulaire
            d = ((center - self._last_angle + 180) % 360) - 180
            center = (self._last_angle + self._smooth * d) % 360.0
        self._last_angle = center

        diffs = np.abs(((angles - center + 180) % 360) - 180)
        span = float(np.clip(np.percentile(diffs, 88) * 2.0, 6.0, 110.0))

        # confiance : densité + cohérence angulaire
        density = min(1.0, n / 90.0)
        spread = float(np.std(diffs))
        coh = max(0.0, 1.0 - spread / 50.0)
        conf = float(np.clip(0.45 * density + 0.55 * coh, 0.0, 1.0))
        return BlueZone(center, span, conf)
