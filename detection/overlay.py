"""Dessin de l'aperçu debug : cercle, lettre, arc cible, curseur."""
from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np

GREEN = (80, 220, 90)
ORANGE = (0, 170, 255)
CYAN = (255, 200, 0)
RED = (60, 60, 255)
WHITE = (240, 240, 240)


def draw_overlay(frame, circle, zone=None, cursor=None, key: Optional[str] = None,
                 key_conf: Optional[float] = None, state: str = "", fallback: bool = False):
    vis = frame.copy()
    h, w = vis.shape[:2]
    if circle is None:
        cv2.putText(vis, "Cercle non trouve", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, ORANGE, 2)
        if state:
            cv2.putText(vis, state, (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
        return vis

    cx, cy, r = circle.x, circle.y, circle.r
    cv2.circle(vis, (cx, cy), r, ORANGE if fallback else GREEN, 2)
    cv2.drawMarker(vis, (cx, cy), GREEN, cv2.MARKER_CROSS, 8, 1)

    # zone de lecture de la lettre
    half = max(14, int(r * 0.55))
    cv2.rectangle(vis, (cx - half, cy - half), (cx + half, cy + half), ORANGE, 1)
    label = "?" if not key else key.upper()
    cv2.putText(vis, f"Lettre : {label}" + (f" ({key_conf:.2f})" if key and key_conf else ""),
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ORANGE, 2)

    # arc cible : épais, de centre - largeur/2 à centre + largeur/2
    if zone is not None:
        c, span = zone.center_angle_deg, max(6.0, zone.span_deg)
        cv2.ellipse(vis, (cx, cy), (r, r), 0, -(c + span / 2), -(c - span / 2), CYAN, 5)
        cv2.putText(vis, f"Arc : {c:.0f} deg", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 1)
    else:
        cv2.putText(vis, "Arc : non vu", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    # curseur mobile
    if cursor is not None:
        a = math.radians(cursor.angle_deg)
        p1 = (int(cx + 0.7 * r * math.cos(a)), int(cy - 0.7 * r * math.sin(a)))
        p2 = (int(cx + 1.08 * r * math.cos(a)), int(cy - 1.08 * r * math.sin(a)))
        cv2.line(vis, p1, p2, RED, 3)
        cv2.circle(vis, p2, 4, RED, -1)
        cv2.putText(vis, f"Curseur : {cursor.angle_deg:.0f} deg", (8, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED, 1)
    else:
        cv2.putText(vis, "Curseur : non vu", (8, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    if state:
        cv2.putText(vis, state, (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
    return vis
