"""Aperçu en direct quand le bot est arrêté : mêmes détecteurs, aucune touche envoyée."""
from __future__ import annotations

from typing import Optional

from bot.capture import ScreenCapture
from detection.circle import CircleDetector
from detection.factory import build_detectors
from detection.key_read import KeyReader
from detection.overlay import draw_overlay


def settings_signature(s):
    """Tout ce qui change la détection : si ça bouge, l'aperçu se reconstruit."""
    keys = ("capture_left", "capture_top", "capture_size", "target_color", "circle_fallback",
            "circle_cx", "circle_cy", "circle_r", "keys_enabled",
            "blue_h_min", "blue_h_max", "blue_s_min", "blue_v_min",
            "red_h_min1", "red_h_max1", "red_h_min2", "red_h_max2", "red_s_min", "red_v_min")
    return tuple(getattr(s, k, None) for k in keys)


class Preview:
    RESET_EVERY = 30          # l'arc change à chaque étape : on le ré-apprend régulièrement

    def __init__(self, settings):
        self.settings = settings
        self.capture = ScreenCapture(settings.capture_left, settings.capture_top, settings.capture_size)
        self.circle_det = CircleDetector(settings)
        self.arc_det, self.cursor_det = build_detectors(settings)
        keys = [k.strip() for k in settings.keys_enabled.split(",") if k.strip()]
        self.keys = KeyReader(keys=keys, templates_dir=settings.templates_path(),
                              min_confidence=settings.key_min_confidence,
                              min_margin=settings.key_min_margin)
        self._n = 0
        self.signature = settings_signature(settings)

    def frame(self):
        """Une image annotée (BGR), ou None si la capture d'écran est indisponible."""
        s = self.settings
        self.capture.set_region(s.capture_left, s.capture_top, s.capture_size)
        raw = self.capture.grab()
        if raw is None:
            return None
        self._n += 1
        if self._n % self.RESET_EVERY == 0:
            self.arc_det.reset()
            self.cursor_det.reset()
        circle = self.circle_det.detect(raw)
        zone = self.arc_det.detect(raw, circle) if circle else None
        cursor = self.cursor_det.detect(raw, circle) if circle else None
        res = self.keys.detect(raw, circle) if circle else None
        return draw_overlay(raw, circle, zone, cursor, res.key if res else None,
                            res.confidence if res else None, "Apercu (bot arrete)",
                            fallback=self.circle_det.used_fallback)
