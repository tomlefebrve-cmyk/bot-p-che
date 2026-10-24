"""
Touches Z/Q/S/D — OpenCV matchTemplate.

Les templates fournis (templates/keys/z.png, q.png, s.png, d.png) sont des
captures de la touche entière (carré sombre + lettre). Le carré sombre varie
d'une image à l'autre et noie la lettre dans le score, donc on isole la
lettre elle-même au chargement.

Lecture :
  - les 4 lettres sont comparées à la MÊME échelle (celle où la meilleure
    correspondance est la plus nette) : une lettre ne peut pas « gagner »
    parce qu'elle tombe mieux à une échelle bizarre ;
  - si deux lettres sont trop proches, on ne répond pas (le moteur réessaie
    à l'image suivante) : un appui manqué vaut mieux qu'un mauvais appui.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2
import numpy as np

from config.settings import ROOT


@dataclass
class KeyResult:
    key: str
    confidence: float
    margin: float = 1.0


def extract_glyph(gray: np.ndarray) -> np.ndarray:
    """Isole la lettre (composante claire proche du centre, sans toucher le bord)."""
    h, w = gray.shape[:2]
    if h < 8 or w < 8:
        return gray
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, _, st, cen = cv2.connectedComponentsWithStats(b, connectivity=8)
    best, best_d = None, 1e9
    for i in range(1, n):
        x, y, cw, ch, area = (int(v) for v in st[i])
        if area < 20:
            continue
        if x <= 0 or y <= 0 or x + cw >= w or y + ch >= h:
            continue  # touche le bord → pas la lettre (cadre de la touche)
        d = float(np.hypot(cen[i][0] - w / 2, cen[i][1] - h / 2))
        if d < best_d:
            best, best_d = (x, y, cw, ch), d
    if best is None:
        return gray  # rien de net : on garde l'image telle quelle
    x, y, cw, ch = best
    p = 1
    return gray[max(0, y - p): y + ch + p, max(0, x - p): x + cw + p]


def _binarize(gray: np.ndarray) -> np.ndarray:
    if gray.size == 0:
        return gray
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return b


def count_holes(binary: np.ndarray) -> int:
    """Nombre de trous dans la lettre (Q, D : 1 ; Z, S : 0). Calculé sur une version agrandie."""
    if binary is None or binary.size == 0:
        return 0
    h, w = binary.shape[:2]
    k = max(1.0, 48.0 / max(h, 1))
    big = cv2.resize(binary, (max(8, int(w * k)), max(8, int(h * k))), interpolation=cv2.INTER_CUBIC)
    _, big = cv2.threshold(big, 127, 255, cv2.THRESH_BINARY)
    big = cv2.copyMakeBorder(big, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    cnts, hier = cv2.findContours(big, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return 0
    min_area = 0.015 * big.shape[0] * big.shape[1]
    return sum(
        1 for i, c in enumerate(cnts)
        if hier[0][i][3] != -1 and cv2.contourArea(c) >= min_area
    )


def tail_ratio(binary: np.ndarray) -> float:
    """Part de pixels allumés en bas à droite : la queue du Q (le D n'en a pas)."""
    if binary is None or binary.size == 0:
        return 0.0
    g = cv2.resize(binary, (24, 32), interpolation=cv2.INTER_AREA) > 127
    return float(g[25:, 14:].mean())


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    """Recouvrement de deux formes binaires (0..1) — redimensionne b sur a."""
    if a.size == 0 or b.size == 0:
        return 0.0
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    A, B = a > 127, b > 127
    tot = A.sum() + B.sum()
    return float(2.0 * (A & B).sum() / tot) if tot else 0.0


class KeyReader:
    SCALES = tuple(np.round(np.arange(0.6, 2.61, 0.1), 2))

    def __init__(
        self,
        keys: Optional[List[str]] = None,
        templates_dir: Optional[str] = None,
        min_confidence: float = 0.75,
        min_margin: float = 0.06,
    ):
        self.keys = [k.strip().lower() for k in (keys or ["z", "q", "s", "d"]) if k.strip()]
        self.templates_dir = templates_dir or os.path.join(ROOT, "templates", "keys")
        self.min_confidence = min_confidence
        self.min_margin = min_margin
        self._templates: Dict[str, np.ndarray] = {}
        self._shapes: Dict[str, np.ndarray] = {}
        self._holes: Dict[str, int] = {}
        self._tails: Dict[str, float] = {}
        self._last_scores: Dict[str, float] = {}
        self.reload_templates()

    @property
    def loaded(self) -> List[str]:
        return sorted(self._templates)

    def reload_templates(self) -> None:
        self._templates = {}
        self._shapes = {}
        self._holes = {}
        self._tails = {}
        os.makedirs(self.templates_dir, exist_ok=True)
        for k in self.keys:
            path = os.path.join(self.templates_dir, f"{k}.png")
            if not os.path.isfile(path):
                continue
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is not None and img.size > 0:
                glyph = extract_glyph(img)
                self._templates[k] = glyph
                self._shapes[k] = _binarize(glyph)
                self._holes[k] = count_holes(self._shapes[k])
                self._tails[k] = tail_ratio(self._shapes[k])

    def save_template(self, key: str, crop_gray: np.ndarray) -> str:
        os.makedirs(self.templates_dir, exist_ok=True)
        path = os.path.join(self.templates_dir, f"{key.lower()}.png")
        cv2.imwrite(path, crop_gray)
        self.reload_templates()
        return path

    def _roi(self, gray: np.ndarray, circle) -> Optional[np.ndarray]:
        if circle is not None:
            r = max(14, int(circle.r * 0.55))
            x1 = max(0, circle.x - r)
            y1 = max(0, circle.y - r)
            x2 = min(gray.shape[1], circle.x + r)
            y2 = min(gray.shape[0], circle.y + r)
            return gray[y1:y2, x1:x2]
        h, w = gray.shape[:2]
        m = max(14, min(h, w) // 3)
        return gray[h // 2 - m: h // 2 + m, w // 2 - m: w // 2 + m]

    def detect(self, frame: np.ndarray, circle=None) -> Optional[KeyResult]:
        if not self._templates or frame is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        roi = self._roi(gray, circle)
        if roi is None or roi.size < 16:
            return None

        rh, rw = roi.shape[:2]
        best_vec: Optional[Dict[str, float]] = None
        best_loc: Dict[str, tuple] = {}
        best_top = -1.0

        for scale in self.SCALES:
            vec: Dict[str, float] = {}
            locs: Dict[str, tuple] = {}
            for k, tmpl in self._templates.items():
                th, tw = tmpl.shape[:2]
                nw, nh = max(6, int(tw * scale)), max(6, int(th * scale))
                if nh >= rh or nw >= rw:
                    vec[k] = -1.0
                    continue
                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                scaled = cv2.resize(tmpl, (nw, nh), interpolation=interp)
                res = cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(res)
                vec[k] = float(mx)
                locs[k] = (loc[0], loc[1], nw, nh)
            top = max(vec.values())
            if top > best_top:
                best_top, best_vec, best_loc = top, vec, locs

        if not best_vec or best_top <= 0:
            return None

        # --- départage par la forme (même lettre vue sous plusieurs angles) ---
        winner = max(best_vec, key=best_vec.get)
        x, y, w, h = best_loc[winner]
        patch = roi[max(0, y - 1): y + h + 1, max(0, x - 1): x + w + 1]
        pbin = _binarize(patch)
        holes_obs = count_holes(pbin) if min(patch.shape[:2]) >= 8 else None
        final: Dict[str, float] = {}
        tail_obs = tail_ratio(pbin)
        small = min(patch.shape[:2]) < 12      # lettre minuscule : la queue du Q disparaît
        for k, ncc in best_vec.items():
            if ncc < 0:
                final[k] = -1.0
                continue
            score = 0.7 * ncc + 0.3 * _dice(pbin, self._shapes[k])
            if holes_obs is not None and holes_obs != self._holes.get(k, holes_obs):
                score -= 0.12          # Q/D ont un trou, Z/S non
            if not small:
                score -= min(0.12, abs(tail_obs - self._tails.get(k, tail_obs)) * 0.8)   # queue du Q
            final[k] = score

        self._last_scores = final
        ranked = sorted(final.items(), key=lambda kv: -kv[1])
        best_k, best_score = ranked[0]
        margin = best_score - ranked[1][1] if len(ranked) > 1 else 1.0
        conf = best_vec[best_k]
        need = self.min_margin * (2.0 if small else 1.0)
        # Q et D se ressemblent beaucoup quand la lettre est minuscule : on refuse plutôt que deviner
        if small and {best_k, ranked[1][0]} == {"q", "d"}:
            return None
        if conf < self.min_confidence or margin < need:
            return None
        return KeyResult(best_k, conf, margin)
