"""Masques HSV bleu / rouge, partagés par la détection de l'arc et du curseur."""
from __future__ import annotations

import cv2
import numpy as np


def mask_blue(hsv: np.ndarray, s) -> np.ndarray:
    lo = np.array([max(0, int(s.blue_h_min)), max(0, int(s.blue_s_min) - 15),
                   max(0, int(s.blue_v_min) - 20)], dtype=np.uint8)
    hi = np.array([min(179, int(s.blue_h_max)), 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lo, hi)


def mask_red(hsv: np.ndarray, s) -> np.ndarray:
    s_min = max(0, int(s.red_s_min) - 20)
    v_min = max(0, int(s.red_v_min) - 25)
    m1 = cv2.inRange(hsv, np.array([max(0, int(s.red_h_min1)), s_min, v_min], dtype=np.uint8),
                     np.array([min(179, int(s.red_h_max1)), 255, 255], dtype=np.uint8))
    m2 = cv2.inRange(hsv, np.array([max(0, int(s.red_h_min2)), s_min, v_min], dtype=np.uint8),
                     np.array([min(179, int(s.red_h_max2)), 255, 255], dtype=np.uint8))
    return cv2.bitwise_or(m1, m2)


def layout(s) -> str:
    """Disposition des couleurs : blue_red (arc bleu, curseur rouge), red_red, red_blue."""
    v = str(getattr(s, "target_color", "blue")).strip().lower()
    return {
        "blue": "blue_red", "bleu": "blue_red", "blue_red": "blue_red",
        "red": "red_red", "rouge": "red_red", "red_red": "red_red",
        "red_blue": "red_blue",
    }.get(v, "blue_red")


def target_is_red(s) -> bool:
    """Utilisé par les détecteurs « classiques » (arc d'une couleur, curseur de l'autre)."""
    return layout(s) == "red_blue"


def target_mask(hsv, s):
    """Couleur de l'arc fixe (cible)."""
    return mask_red(hsv, s) if target_is_red(s) else mask_blue(hsv, s)


def cursor_mask(hsv, s):
    """Couleur du curseur mobile : l'autre couleur."""
    return mask_blue(hsv, s) if target_is_red(s) else mask_red(hsv, s)
