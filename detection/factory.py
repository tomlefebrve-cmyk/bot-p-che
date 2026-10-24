"""Fabrique des détecteurs d'arc / curseur selon la disposition des couleurs."""
from __future__ import annotations

from detection.blue_zone import BlueZoneDetector
from detection.colors import layout
from detection.red_arc import RedArcDetector, RedCursorOverArc
from detection.red_line import RedLineDetector


def build_detectors(settings):
    """Retourne (détecteur d'arc, détecteur de curseur)."""
    if layout(settings) == "red_red":
        arc = RedArcDetector(settings)          # arc rouge fixe + curseur rouge mobile
        return arc, RedCursorOverArc(settings, arc)
    return BlueZoneDetector(settings), RedLineDetector(settings)   # couleurs différentes
