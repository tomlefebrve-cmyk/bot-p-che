"""
Calibration automatique : cercle + couleurs de l'arc (fixe) et du curseur (mobile).

On observe ~1 s de jeu :
  - l'arc est ce qui reste immobile, le curseur ce qui bouge ;
  - la couleur de chacun (bleu ou rouge) est lue sur les vrais pixels de TON écran,
    donc ça marche même si les couleurs du jeu changent d'un écran à l'autre ;
  - la disposition est choisie toute seule : arc bleu + curseur rouge,
    arc rouge + curseur rouge, ou arc rouge + curseur bleu.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np

from detection.circle import CircleDetector

LAYOUT_FR = {
    "blue_red": "arc bleu · curseur rouge",
    "red_red": "arc rouge · curseur rouge",
    "red_blue": "arc rouge · curseur bleu",
}


@dataclass
class CalResult:
    ok: bool
    message: str
    layout: Optional[str] = None
    circle_found: bool = False
    updates: Dict[str, object] = field(default_factory=dict)


def _hsv(frame: np.ndarray) -> np.ndarray:
    """HSV + CLAHE sur V : exactement comme les détecteurs, pour que les seuils collent."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    v = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(v)
    return cv2.merge([h, s, v])


def _family_masks(hsv: np.ndarray, ring: np.ndarray) -> Dict[str, np.ndarray]:
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    colorful = (s >= 70) & (v >= 70) & (ring > 0)
    blue = colorful & (h >= 80) & (h <= 140)
    red = colorful & ((h <= 18) | (h >= 160))
    return {"blue": blue.astype(np.uint8) * 255, "red": red.astype(np.uint8) * 255}


def _clean(m: np.ndarray) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, k)


class AutoCalibrator:
    def __init__(self, settings, capture):
        self.settings = settings
        self.capture = capture

    # ------------------------------------------------------------------
    def run(self, n_frames: int = 20, interval: float = 0.05,
            progress: Optional[Callable[[float], None]] = None) -> CalResult:
        frames: List[np.ndarray] = []
        for i in range(n_frames):
            f = self.capture.grab()
            if f is None:
                return CalResult(False, "Capture d'écran indisponible.")
            frames.append(f)
            if progress:
                progress((i + 1) / n_frames)
            time.sleep(interval)
        return self.analyse(frames)

    def analyse(self, frames: List[np.ndarray]) -> CalResult:
        h, w = frames[0].shape[:2]
        # ---- cercle
        det = CircleDetector(None)
        found = []
        for f in frames[::2]:
            det.reset()
            c = det.detect(f)
            if c is not None:
                found.append((c.x, c.y, c.r))
        circle_found = len(found) >= max(2, len(frames) // 8)
        if circle_found:
            cx, cy, r = (int(np.median([c[i] for c in found])) for i in range(3))
        else:
            cx, cy, r = w // 2, h // 2, int(0.36 * min(w, h))

        # ---- anneau d'analyse
        ring = np.zeros((h, w), np.uint8)
        cv2.circle(ring, (cx, cy), int(r * 1.14), 255, -1)
        cv2.circle(ring, (cx, cy), int(r * 0.80), 0, -1)

        hsvs = [_hsv(f) for f in frames]
        per_frame = [{k: _clean(m) for k, m in _family_masks(x, ring).items()} for x in hsvs]

        # ---- fixe (arc) / mobile (curseur) pour chaque couleur
        d3 = np.ones((3, 3), np.uint8)
        static, moving_cnt, moving_px = {}, {}, {}
        for fam in ("blue", "red"):
            masks = [pf[fam] for pf in per_frame]
            st = cv2.dilate(masks[0], d3)
            for m in masks[1:]:
                st = cv2.bitwise_and(st, cv2.dilate(m, d3))
            st = cv2.erode(st, d3)
            static[fam] = st
            st_wide = cv2.dilate(st, np.ones((7, 7), np.uint8))
            mov = [cv2.bitwise_and(m, cv2.bitwise_not(st_wide)) for m in masks]
            moving_px[fam] = mov
            moving_cnt[fam] = float(np.mean([(m > 0).sum() for m in mov]))

        n_static = {k: int((v > 0).sum()) for k, v in static.items()}

        def score(arc: str, cur: str) -> float:
            return min(1.0, n_static[arc] / 60.0) * min(1.0, moving_cnt[cur] / 10.0)

        cands = {
            "blue_red": score("blue", "red"),
            "red_blue": score("red", "blue"),
            "red_red": score("red", "red"),
        }
        layout = max(cands, key=cands.get)
        if cands[layout] < 0.35:
            return CalResult(
                False,
                "Je ne vois pas l'arc et le curseur. Ouvre le mini-jeu de pêche (cercle bien "
                "visible dans la zone) et réessaie.",
                circle_found=circle_found,
            )

        arc_fam, cur_fam = layout.split("_")
        # pixels de référence : arc = fixe, curseur = mobile
        arc_px = [hs[static[arc_fam] > 0] for hs in hsvs]
        cur_px = [hs[m > 0] for hs, m in zip(hsvs, moving_px[cur_fam])]
        arc_hsv = np.concatenate([a for a in arc_px if len(a)]) if any(len(a) for a in arc_px) else np.empty((0, 3))
        cur_hsv = np.concatenate([a for a in cur_px if len(a)]) if any(len(a) for a in cur_px) else np.empty((0, 3))

        # valeur écrite dans les réglages (même vocabulaire que le menu de l'interface)
        updates: Dict[str, object] = {"target_color": {"blue_red": "blue", "red_red": "red", "red_blue": "red_blue"}[layout]}
        by_family: Dict[str, List[np.ndarray]] = {"blue": [], "red": []}
        by_family[arc_fam].append(arc_hsv)
        by_family[cur_fam].append(cur_hsv)
        for fam, parts in by_family.items():
            px = np.concatenate([p for p in parts if len(p)]) if any(len(p) for p in parts) else None
            if px is None or len(px) < 8:
                continue
            H, S, V = px[:, 0].astype(int), px[:, 1].astype(int), px[:, 2].astype(int)
            # percentile 10 (les bords flous de l'arc sont plus ternes) et planchers :
            # sous ~55/65 le bruit de l'image sur fond sombre ressemble à du rouge/bleu
            s_min = int(np.clip(np.percentile(S, 10) - 25, 75, 170))
            v_min = int(np.clip(np.percentile(V, 10) - 30, 90, 170))
            if fam == "blue":
                updates.update(
                    blue_h_min=int(np.clip(np.percentile(H, 2) - 8, 70, 120)),
                    blue_h_max=int(np.clip(np.percentile(H, 98) + 8, 100, 150)),
                    blue_s_min=s_min, blue_v_min=v_min,
                )
            else:
                low, high = H[H <= 40], H[H >= 140]
                if len(low) >= 8:
                    updates.update(red_h_min1=0, red_h_max1=int(np.clip(np.percentile(low, 98) + 6, 8, 40)))
                if len(high) >= 8:
                    updates.update(red_h_min2=int(np.clip(np.percentile(high, 2) - 6, 140, 175)), red_h_max2=179)
                updates.update(red_s_min=s_min, red_v_min=v_min)

        if circle_found:
            updates.update(circle_cx=round(cx / w, 4), circle_cy=round(cy / h, 4),
                           circle_r=round(r / float(min(w, h)), 4), circle_fallback=True)
        else:
            updates["circle_fallback"] = True

        msg = f"Calibration réussie : {LAYOUT_FR[layout]}."
        msg += " Cercle trouvé." if circle_found else " Cercle non détecté : cercle fixe au centre de la zone."
        return CalResult(True, msg, layout, circle_found, updates)

    def apply(self, result: CalResult) -> None:
        for k, v in result.updates.items():
            setattr(self.settings, k, v)
