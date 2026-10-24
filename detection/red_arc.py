"""
Arc cible ROUGE + curseur ROUGE (même couleur) : séparés par le mouvement.

- Arc : les pixels rouges présents sur plusieurs images d'affilée (fixe).
  Le curseur bouge, il disparaît de l'intersection. On garde le plus grand
  morceau continu d'angles → centre + largeur de l'arc.
- Curseur : les pixels rouges qui ne sont PAS dans l'arc. S'il passe sur l'arc
  et devient invisible, on prolonge sa position à vitesse constante (0,4 s max).

Mêmes sorties que BlueZoneDetector / RedLineDetector : le moteur ne change pas.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Optional

import cv2
import numpy as np

from detection.blue_zone import BlueZone
from detection.red_line import RedLine, RedLineDetector

LOCK_FRAMES = 4        # images nécessaires pour isoler l'arc fixe
EXTRAPOLATE_S = 0.4    # durée max de prolongement si le curseur est caché par l'arc


def _red_mask(det: RedLineDetector, frame: np.ndarray) -> np.ndarray:
    s = det.settings
    hsv = det._hsv_enhanced(frame)
    s_min = max(0, int(s.red_s_min) - 20)
    v_min = max(0, int(s.red_v_min) - 25)
    m1 = cv2.inRange(
        hsv,
        np.array([max(0, int(s.red_h_min1)), s_min, v_min], dtype=np.uint8),
        np.array([min(179, int(s.red_h_max1)), 255, 255], dtype=np.uint8),
    )
    m2 = cv2.inRange(
        hsv,
        np.array([max(0, int(s.red_h_min2)), s_min, v_min], dtype=np.uint8),
        np.array([min(179, int(s.red_h_max2)), 255, 255], dtype=np.uint8),
    )
    return cv2.bitwise_or(m1, m2)


def _ring(shape, circle, r_in: float, r_out: float) -> np.ndarray:
    ring = np.zeros(shape, dtype=np.uint8)
    cv2.circle(ring, (circle.x, circle.y), int(circle.r * r_out), 255, -1)
    cv2.circle(ring, (circle.x, circle.y), int(circle.r * r_in), 0, -1)
    return ring


def _largest_run(counts: np.ndarray, gap: int = 3):
    """Plus grand arc continu (circulaire) d'angles occupés → (début, longueur, pixels)."""
    occ = counts > 0
    if occ.all() or not occ.any():
        return None
    k = np.ones(2 * gap + 1, dtype=np.uint8)
    d = np.convolve(np.concatenate([occ[-gap:], occ, occ[:gap]]).astype(np.uint8), k, "same")[gap:-gap] > 0
    c = np.convolve(np.concatenate([d[-gap:], d, d[:gap]]).astype(np.uint8), k, "same")[gap:-gap] >= len(k)
    closed = c | occ
    if closed.all():
        return None
    start0 = int(np.where(~closed)[0][0])          # point de départ hors arc
    rolled = np.roll(closed, -start0)
    best, i, n = None, 0, len(rolled)
    while i < n:
        if rolled[i]:
            j = i
            while j < n and rolled[j]:
                j += 1
            px = int(np.roll(counts, -start0)[i:j].sum())
            if best is None or px > best[2]:
                best = ((i + start0) % n, j - i, px)
            i = j
        else:
            i += 1
    return best


class RedArcDetector:
    """Détecte l'arc cible rouge FIXE (remplace BlueZoneDetector)."""

    def __init__(self, settings):
        self.settings = settings
        self._helper = RedLineDetector(settings)   # réutilise HSV + CLAHE
        self._masks: deque = deque(maxlen=LOCK_FRAMES)
        self._zone: Optional[BlueZone] = None
        self.static_mask: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._masks.clear()
        self._zone = None
        self.static_mask = None

    def detect(self, frame: np.ndarray, circle) -> Optional[BlueZone]:
        if frame is None or circle is None:
            return None
        if self._zone is not None:
            return self._zone                      # arc fixe : déjà verrouillé

        m = _red_mask(self._helper, frame)
        m = cv2.bitwise_and(m, _ring(m.shape, circle, 0.48, 1.14))
        self._masks.append(cv2.dilate(m, np.ones((3, 3), np.uint8)))
        if len(self._masks) < LOCK_FRAMES:
            return None

        static = self._masks[0].copy()
        for x in list(self._masks)[1:]:
            static = cv2.bitwise_and(static, x)
        static = cv2.erode(static, np.ones((3, 3), np.uint8))
        num, labels, stats, _ = cv2.connectedComponentsWithStats(static, connectivity=8)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] < 8:
                static[labels == i] = 0

        ys, xs = np.where(static > 0)
        if len(xs) < 10:
            self._masks.popleft()                  # on réessaie avec l'image suivante
            return None
        ang = np.degrees(np.arctan2(-(ys - circle.y), xs - circle.x)) % 360.0
        counts = np.bincount(ang.astype(int) % 360, minlength=360)
        run = _largest_run(counts)
        if run is None:
            self._masks.popleft()
            return None
        start, length, px = run
        span = float(np.clip(length, 6.0, 110.0))
        center = (start + length / 2.0) % 360.0
        conf = float(np.clip(px / 90.0, 0.0, 1.0))
        self.static_mask = static
        self._zone = BlueZone(center, span, conf)
        return self._zone


class RedCursorOverArc(RedLineDetector):
    """Curseur rouge = pixels rouges hors de l'arc fixe (remplace RedLineDetector)."""

    def __init__(self, settings, arc: RedArcDetector):
        super().__init__(settings)
        self.arc = arc
        self._last_t = 0.0
        self._vel = 0.0

    def reset(self) -> None:
        super().reset()
        self._last_t = 0.0
        self._vel = 0.0

    def detect(self, frame: np.ndarray, circle) -> Optional[RedLine]:
        if frame is None or circle is None or self.arc.static_mask is None:
            return None                            # l'arc n'est pas encore connu
        now = time.time()
        mask = _red_mask(self, frame)
        mask = cv2.bitwise_and(mask, _ring(mask.shape, circle, 0.28, 1.14))
        mask[cv2.dilate(self.arc.static_mask, np.ones((5, 5), np.uint8)) > 0] = 0
        # enlève les points isolés (bruit de l'image) : le curseur, lui, est un trait épais
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

        ys, xs = np.where(mask > 0)
        if len(xs) < 4:
            return self._extrapolate(now)

        dx = xs.astype(np.float64) - circle.x
        dy = ys.astype(np.float64) - circle.y
        dist = np.sqrt(dx * dx + dy * dy)
        sel = dist >= np.percentile(dist, 75)
        if not np.any(sel):
            sel = dist >= dist.max() * 0.85
        rad = np.arctan2(-dy[sel], dx[sel])
        ang = math.degrees(math.atan2(float(np.mean(np.sin(rad))), float(np.mean(np.cos(rad))))) % 360.0

        if self._last_angle is not None and now - self._last_t < EXTRAPOLATE_S:
            d = ((ang - self._last_angle + 180) % 360) - 180
            dt = max(1e-3, now - self._last_t)
            self._vel = 0.6 * self._vel + 0.4 * (d / dt)
            ang = (self._last_angle + self._smooth * d) % 360.0
        else:
            self._vel = 0.0
        self._last_angle, self._last_t = ang, now
        return RedLine(float(ang), float(np.clip(len(xs) / 40.0, 0.15, 1.0)))

    def _extrapolate(self, now: float) -> Optional[RedLine]:
        """Curseur caché par l'arc : on prolonge à vitesse constante, pas plus de 0,4 s."""
        if self._last_angle is None or abs(self._vel) < 5.0:
            return None
        dt = now - self._last_t
        if dt > EXTRAPOLATE_S:
            return None
        return RedLine(float((self._last_angle + self._vel * dt) % 360.0), 0.3)
