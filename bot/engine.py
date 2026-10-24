"""Moteur de pêche — détection + appui."""
from __future__ import annotations

import math
import time
from enum import Enum, auto
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from config.settings import Settings, ROOT
from bot.capture import ScreenCapture
from bot.input_keys import Keyboard
from detection.circle import CircleDetector
from detection.factory import build_detectors
from detection.key_read import KeyReader
from detection.overlay import draw_overlay


class State(Enum):
    IDLE = auto()
    SEARCHING = auto()
    LOCKING = auto()
    TRACKING = auto()
    PRESSING = auto()
    COOLDOWN = auto()
    PAUSED = auto()          # pause automatique (cycle marche / pause)


@dataclass
class Stats:
    fish_caught: int = 0
    stage_ok: int = 0
    stage_fail: int = 0


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


class Engine:
    def __init__(
        self,
        settings: Settings,
        on_log: Optional[Callable[[str], None]] = None,
        on_state: Optional[Callable[[State], None]] = None,
        on_frame: Optional[Callable] = None,
    ):
        self.settings = settings
        self.on_log = on_log or (lambda m: None)
        self.on_state = on_state or (lambda s: None)
        self.on_frame = on_frame
        self.stats = Stats()
        self.state = State.IDLE
        self.running = False
        self.capture = ScreenCapture(
            settings.capture_left, settings.capture_top, settings.capture_size
        )
        self.keyboard = Keyboard()
        self.circle_det = CircleDetector(settings)
        self._make_detectors()
        self.key_reader = self._make_key_reader()
        self.current_key: Optional[str] = None
        self._target_angle: Optional[float] = None
        self._target_span: float = 20.0
        self._lock_count = 0
        self._cooldown_until = 0.0
        self._last_press = 0.0
        self._stage_start = 0.0
        self._align_count = 0
        self._key_votes = {}
        self._cycle_phase = None
        self._cycle_t0 = 0.0
        self._press_times = []          # horodatage des derniers appuis (limite anti-spam)
        self._spam_pause_until = 0.0
        self._fail_streak = 0
        self._arc_hist = []             # derniers angles de l'arc (doit rester fixe)
        self._cursor_hist = []          # (heure, angle) du curseur : doit bouger
        self._arc_drift = 0

    def _make_detectors(self) -> None:
        """Détecteurs selon la disposition des couleurs (voir detection/factory.py)."""
        self.blue_det, self.red_det = build_detectors(self.settings)

    def _make_key_reader(self) -> KeyReader:
        s = self.settings
        keys = [k.strip() for k in getattr(s, "keys_enabled", "z,q,s,d").split(",") if k.strip()]
        return KeyReader(
            keys=keys,
            templates_dir=s.templates_path(),
            min_confidence=max(s.key_min_confidence, 0.80) if getattr(s, "anti_spam", False) else s.key_min_confidence,
            min_margin=s.key_min_margin,
        )

    def start(self) -> None:
        self.running = True
        self.capture.set_region(
            self.settings.capture_left,
            self.settings.capture_top,
            self.settings.capture_size,
        )
        self.key_reader = self._make_key_reader()
        loaded = self.key_reader.loaded
        n_tpl = len(loaded)
        self._make_detectors()   # applique target_color
        self.keyboard.mode = getattr(self.settings, "key_send_mode", "layout")
        self._cycle_phase = None
        self._press_times, self._spam_pause_until, self._fail_streak = [], 0.0, 0
        self._arc_hist, self._cursor_hist, self._arc_drift = [], [], 0
        self.circle_det.reset()
        self.current_key = None
        self._target_angle = None
        self._lock_count = 0
        self._align_count = 0
        self._key_votes = {}
        self._arc_hist, self._cursor_hist, self._arc_drift = [], [], 0
        self._set(State.SEARCHING)
        self.on_log(f"[INFO] Arc cible : {self.settings.target_color}")
        self.on_log(f"[INFO] Bot démarré — templates touches : {', '.join(k.upper() for k in loaded) or 'aucun'}")
        missing = [k for k in self.key_reader.keys if k not in loaded]
        if n_tpl == 0:
            self.on_log("[WARN] Aucun template dans templates/keys/ (z.png q.png s.png d.png)")
        elif missing:
            self.on_log(f"[WARN] Template manquant : {', '.join(k.upper() for k in missing)}")

    def stop(self) -> None:
        self.running = False
        self._set(State.IDLE)
        self.on_log("[INFO] Bot arrêté")

    def _set(self, st: State) -> None:
        self.state = st
        self.on_state(st)

    def step(self) -> None:
        if not self.running:
            return
        now = time.time()
        if self._cycle_tick(now):
            return                       # pause automatique : on ne capture rien, on n'appuie sur rien
        if now < self._spam_pause_until:                 # pause anti-spam en cours
            if self.state != State.PAUSED:
                self._set(State.PAUSED)
            return
        if self.state == State.PAUSED and self._cycle_phase != "pause":
            self._reset_stage()                          # fin de la pause anti-spam
            self.on_log("[INFO] Anti-spam : reprise")
        if self.state == State.COOLDOWN:
            if now >= self._cooldown_until:
                self._set(State.SEARCHING)
                self.circle_det.reset()
                self.current_key = None
                self._target_angle = None
                self._lock_count = 0
                self._key_votes = {}
                self._arc_hist, self._cursor_hist, self._arc_drift = [], [], 0
            return

        frame = self.capture.grab()
        if frame is None:
            return

        circle = self.circle_det.detect(frame)
        blue = self.blue_det.detect(frame, circle) if circle else None
        red = self.red_det.detect(frame, circle) if circle else None
        # La lecture de touche (~15 ms) n'est faite qu'avant le suivi : pendant
        # TRACKING elle ajouterait du retard à l'appui sans rien apporter.
        read_key = self.state in (State.SEARCHING, State.LOCKING)
        key_res = self.key_reader.detect(frame, circle) if (circle and read_key) else None

        # aperçu debug (cercle, lettre, arc, curseur)
        if self.on_frame:
            try:
                shown_key = key_res.key if key_res else self.current_key
                self.on_frame(draw_overlay(
                    frame, circle, blue, red, shown_key,
                    key_res.confidence if key_res else None,
                    self.state.name.lower(), fallback=self.circle_det.used_fallback,
                ))
            except Exception:
                pass

        # --- machine à états ---
        if self.state == State.SEARCHING:
            strict = getattr(self.settings, "anti_spam", False) and self.circle_det.used_fallback
            if circle and circle.confidence >= 0.4 and (key_res or not strict):
                self._stage_start = now
                self._set(State.LOCKING)
                self.on_log("[DETECT] Cercle trouvé")
            return

        if circle is None:
            if now - self._stage_start > self.settings.max_wait_ms / 1000:
                self.on_log("[WARN] Cercle perdu")
                self._stage_failed()
            return

        if self.state == State.LOCKING:
            if blue:
                self._target_angle = blue.center_angle_deg
                self._target_span = max(10.0, blue.span_deg)
                self._lock_count += 1
                self._arc_hist = (self._arc_hist + [blue.center_angle_deg])[-6:]
            if red:
                self._cursor_hist = (self._cursor_hist + [(now, red.angle_deg)])[-12:]
            if key_res and not self.current_key:
                # on valide la lettre quand plusieurs images d'affilée donnent la même
                v = self._key_votes
                v[key_res.key] = v.get(key_res.key, 0) + 1
                top = max(v, key=v.get)
                second = max([n for k, n in v.items() if k != top], default=0)
                need = max(1, int(getattr(self.settings, "key_votes_needed", 2)))
                if v[top] >= need and v[top] > second:
                    self.current_key = top
                    scores = getattr(self.key_reader, "_last_scores", {})
                    detail = " ".join(f"{k.upper()}={n:.2f}" for k, n in sorted(scores.items()))
                    self.on_log(f"[KEY] {top.upper()} ({key_res.confidence:.2f}) | {detail}")

            have_tpl = bool(self.key_reader.loaded)
            anti = getattr(self.settings, "anti_spam", False)
            key_ready = bool(self.current_key) or (not have_tpl and not anti)
            arc_ok = (not anti) or (
                len(self._arc_hist) >= 2 and _angle_diff(self._arc_hist[-1], self._arc_hist[-2]) <= 6.0)
            if self._target_angle is not None and self._lock_count >= 1 and key_ready and arc_ok:
                if not self.current_key:
                    # aucun template chargé : première touche configurée
                    self.current_key = self._default_key()
                    self.on_log(f"[WARN] Pas de template → touche par défaut '{self.current_key}'")
                self._set(State.TRACKING)
                self.on_log(
                    f"[LOCK] Cible {self._target_angle:.0f}° ±{self._target_span/2:.0f} · touche {self.current_key.upper()}"
                )
            elif now - self._stage_start > 2.5:
                if self._target_angle is None:
                    self.on_log("[WARN] Arc non détecté — lance la calibration des couleurs")
                elif not arc_ok:
                    self.on_log("[WARN] Anti-spam : l'arc n'est pas stable, ce n'est pas le mini-jeu")
                elif not have_tpl:
                    self.on_log("[WARN] Anti-spam : aucun template de lettre, pas d'appui à l'aveugle")
                else:
                    # templates chargés mais lettre illisible : on n'appuie pas au hasard
                    self.on_log("[WARN] Touche illisible — aucun appui (vérifie les templates)")
                self._stage_failed()
            return

        if self.state == State.TRACKING:
            if red is None or self._target_angle is None:
                return
            self._cursor_hist = (self._cursor_hist + [(now, red.angle_deg)])[-12:]
            if getattr(self.settings, "anti_spam", False) and blue is not None and \
                    _angle_diff(blue.center_angle_deg, self._target_angle) > 12.0:
                self._arc_drift += 1                      # l'arc « bouge » : ce n'est pas le mini-jeu
                if self._arc_drift >= 2:
                    self.on_log("[WARN] Anti-spam : l'arc n'est pas stable, aucun appui")
                    self._stage_failed()
                    return
            gap = _angle_diff(red.angle_deg, self._target_angle)
            tol = max(self.settings.tolerance_deg, self._target_span / 2)
            if gap <= tol:
                self._align_count += 1
            else:
                self._align_count = 0
            need = max(1, int(self.settings.align_confirm_frames))
            if self._align_count >= need and self._cursor_is_moving():
                self._set(State.PRESSING)
            elif now - self._stage_start > self.settings.max_wait_ms / 1000:
                self.on_log("[WARN] Timeout alignement")
                self._stage_failed()
            return

        if self.state == State.PRESSING:
            if now - self._last_press < self.settings.min_key_interval_ms / 1000:
                return
            st = self.settings
            if getattr(st, "anti_spam", False):
                if blue is None or red is None or \
                        _angle_diff(blue.center_angle_deg, self._target_angle) > 12.0:
                    # le mini-jeu a disparu (ou l'arc a bougé) à l'instant : pas d'appui
                    self._set(State.TRACKING)
                    self._align_count = 0
                    return
                window = max(1, int(st.anti_spam_window_s))
                self._press_times = [t for t in self._press_times if now - t < window]
                if len(self._press_times) >= max(1, int(st.anti_spam_max)):
                    self._spam_pause(
                        st.anti_spam_pause_s,
                        f"Anti-spam : {len(self._press_times)} appuis en {window} s, pause de {int(st.anti_spam_pause_s)} s")
                    return
            delay = self.settings.reaction_delay_ms / 1000
            if delay > 0:
                time.sleep(delay)
            key = self.current_key or "e"
            ok = self.keyboard.press(key)
            self._last_press = time.time()
            if ok:
                self._press_times.append(self._last_press)
                self._fail_streak = 0
                self.on_log(f"[PRESS] {key.upper()}")
                self.stats.stage_ok += 1
                # hypothèse: succès d'étape ; poisson complet géré plus tard
                if self.stats.stage_ok % 2 == 0:
                    self.stats.fish_caught += 1
            else:
                self.on_log("[ERR] Échec envoi touche")
                self._stage_failed()
                return
            self._enter_cooldown()

    def _cursor_is_moving(self) -> bool:
        """Un vrai curseur avance régulièrement : ≥ 6° de déplacement net dans la dernière seconde,
        presque toujours dans le même sens (un simple tremblement de l'image ne passe pas)."""
        if not getattr(self.settings, "anti_spam", False):
            return True
        now = time.time()
        h = [(t, a) for (t, a) in self._cursor_hist if now - t <= 1.0]
        if len(h) < 3:
            return False
        steps = [((a1 - a0 + 180.0) % 360.0) - 180.0 for (_, a0), (_, a1) in zip(h, h[1:])]
        net = sum(steps)
        big = [d for d in steps if abs(d) >= 0.5]
        if abs(net) < 6.0 or len(big) < 2:
            return False
        return sum(1 for d in big if d * net > 0) / len(big) >= 0.7

    def _spam_pause(self, seconds, message: str) -> None:
        self._spam_pause_until = time.time() + max(1, int(seconds))
        self._set(State.PAUSED)
        self.on_log("[WARN] " + message)

    def _stage_failed(self) -> None:
        """Une étape a échoué. Anti-spam : on ralentit, puis on fait une pause si ça dure."""
        self.stats.stage_fail += 1
        self._fail_streak += 1
        st = self.settings
        if getattr(st, "anti_spam", False):
            if self._fail_streak >= max(3, int(st.anti_spam_fail_limit)):
                self._fail_streak = 0
                self._spam_pause(
                    st.anti_spam_pause_s,
                    f"Anti-spam : aucun mini-jeu valide depuis un moment, pause de {int(st.anti_spam_pause_s)} s")
                self._reset_detectors()
                return
            self._enter_cooldown(extra=min(3.0, 0.4 * max(0, self._fail_streak - 1)))
        else:
            self._enter_cooldown()

    def _reset_detectors(self) -> None:
        for det in (self.circle_det, self.blue_det, self.red_det):
            if hasattr(det, "reset"):
                det.reset()

    def _cycle_tick(self, now: float) -> bool:
        """Cycle « marche X s puis pause Y s » (réglages cycle_*). True = on est en pause."""
        s = self.settings
        if not getattr(s, "cycle_enabled", False):
            if self._cycle_phase == "pause":
                self._reset_stage()
            self._cycle_phase = None
            return False
        run_s, pause_s = max(1, int(s.cycle_run_s)), max(1, int(s.cycle_pause_s))
        if self._cycle_phase is None:
            self._cycle_phase, self._cycle_t0 = "run", now
        elapsed = now - self._cycle_t0
        if self._cycle_phase == "run" and elapsed >= run_s:
            self._cycle_phase, self._cycle_t0 = "pause", now
            self._set(State.PAUSED)
            self.on_log(f"[INFO] Pause automatique ({pause_s} s)")
        elif self._cycle_phase == "pause" and elapsed >= pause_s:
            self._cycle_phase, self._cycle_t0 = "run", now
            self._reset_stage()
            self.on_log(f"[INFO] Reprise de la pêche ({run_s} s)")
        return self._cycle_phase == "pause"

    def _reset_stage(self) -> None:
        """Repart de zéro (nouvelle recherche du cercle, de l'arc et de la lettre)."""
        for det in (self.circle_det, self.blue_det, self.red_det):
            if hasattr(det, "reset"):
                det.reset()
        self.current_key = None
        self._target_angle = None
        self._lock_count = 0
        self._align_count = 0
        self._key_votes = {}
        self._arc_hist, self._cursor_hist, self._arc_drift = [], [], 0
        self._set(State.SEARCHING)

    def _default_key(self) -> str:
        keys = [k.strip() for k in self.settings.keys_enabled.split(",") if k.strip()]
        return keys[0] if keys else "e"

    def _enter_cooldown(self, extra: float = 0.0):
        self._cooldown_until = time.time() + self.settings.post_catch_cooldown_ms / 1000 + extra
        self._set(State.COOLDOWN)
        self.circle_det.reset()
        if hasattr(self.blue_det, "reset"):
            self.blue_det.reset()
        if hasattr(self.red_det, "reset"):
            self.red_det.reset()
        self._lock_count = 0
        self._align_count = 0
        self._key_votes = {}
        self._arc_hist, self._cursor_hist, self._arc_drift = [], [], 0
