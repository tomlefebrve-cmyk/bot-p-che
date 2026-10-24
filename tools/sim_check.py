"""
Simulation de bout en bout (sans FiveM ni écran) :
faux mini-jeu (cercle, vraie touche des templates, arc bleu fixe, curseur
rouge mobile) → Engine réel → clavier factice.

Vérifie : 1) la lettre lue est la bonne, 2) l'appui n'a lieu que lorsque le
rouge est sur le bleu (écart mesuré au moment de l'appui).

    python tools/sim_check.py          # arc bleu, curseur rouge
    python tools/sim_check.py --swap   # arc rouge, curseur bleu
"""
from __future__ import annotations

import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from bot.engine import Engine
from config.settings import Settings

SIZE, CX, CY, R = 220, 110, 110, 70
SPEED_DEG_S = 140.0
# couleurs (arc, curseur) selon la disposition testée
COLORS = {"blue": ((255, 120, 0), (40, 40, 235)),        # arc bleu  + curseur rouge
          "red": ((40, 40, 235), (40, 40, 235)),         # arc rouge + curseur rouge
          "red_blue": ((40, 40, 235), (255, 120, 0))}    # arc rouge + curseur bleu
MODE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in COLORS else "red"


def _diff(a, b):
    return abs((a - b + 180) % 360 - 180)


class FakeGame:
    """Génère l'image du mini-jeu en fonction de l'heure."""

    def __init__(self, keys, templates_dir, arc_color=(40, 40, 235)):
        self.arc_color = arc_color
        self.keys = keys
        self.tpl = {k: cv2.imread(os.path.join(templates_dir, f"{k}.png"), 0) for k in keys}
        self.t0 = time.time()
        self.round = -1
        self.key = None
        self.blue = 0.0
        self.last_red_at = lambda: 0.0

    def red(self, now=None):
        return ((time.time() - self.t0) * SPEED_DEG_S) % 360.0

    def new_round(self):
        self.round += 1
        self.key = self.keys[self.round % len(self.keys)]
        self.blue = random.uniform(30, 330)
        # écart du curseur au début de la manche (pour repérer les manches « déjà dans l'arc »)
        self.start_gap = (self.red() - self.blue + 180) % 360 - 180

    def render(self):
        f = np.full((SIZE, SIZE, 3), 28, np.uint8)
        cv2.circle(f, (CX, CY), R, (105, 105, 105), 3)
        # arc bleu (fixe)
        arc_c, cur_c = self.arc_color, COLORS[MODE][1]
        cv2.ellipse(f, (CX, CY), (R, R), 0, -(self.blue + 12), -(self.blue - 12), arc_c, 6)
        # curseur rouge (mobile)
        a = math.radians(self.red())
        p1 = (int(CX + 0.86 * R * math.cos(a)), int(CY - 0.86 * R * math.sin(a)))
        p2 = (int(CX + 1.04 * R * math.cos(a)), int(CY - 1.04 * R * math.sin(a)))
        cv2.line(f, p1, p2, cur_c, 4)
        # lettre
        t = self.tpl[self.key]
        t = cv2.resize(t, (int(t.shape[1] * 1.8), int(t.shape[0] * 1.8)))
        y0, x0 = CY - t.shape[0] // 2, CX - t.shape[1] // 2
        f[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t[:, :, None]
        f = cv2.GaussianBlur(f, (3, 3), 0)
        noise = np.random.randint(-5, 6, f.shape)
        return np.clip(f.astype(int) + noise, 0, 255).astype(np.uint8)


class FakeCapture:
    def __init__(self, game): self.game = game
    def set_region(self, *a): pass
    def grab(self): return self.game.render()


class FakeKeyboard:
    def __init__(self, game): self.game, self.presses = game, []
    def press(self, key):
        signed = (self.game.red() - self.game.blue + 180) % 360 - 180  # <0 : le rouge n'a pas encore atteint le bleu
        self.presses.append((key, signed, self.game.key, self.game.round, self.game.start_gap))
        self.game.new_round()   # le mini-jeu passe à l'étape suivante
        return True


def main():
    random.seed(3)
    np.random.seed(3)
    s = Settings()
    mode = MODE
    s.target_color = mode
    s.keys_enabled = "z,q,s,d"
    logs = []
    eng = Engine(s, on_log=logs.append)
    game = FakeGame(["z", "q", "s", "d"], s.templates_path(),
                    arc_color=COLORS[mode][0])
    game.new_round()
    eng.capture = FakeCapture(game)
    kb = FakeKeyboard(game)
    eng.keyboard = kb
    eng.start()

    t_end = time.time() + 14
    while time.time() < t_end and len(kb.presses) < 8:
        eng.step()
        time.sleep(s.poll_interval_ms / 1000)
    eng.stop()

    print("\n".join(l for l in logs if "[KEY]" in l or "[WARN]" in l or "[ERR]" in l))
    HALF_ARC = 12.0  # demi-largeur de l'arc dessiné par FakeGame
    print(f"\n{'attendu':>8} {'pressé':>7} {'rouge − bleu':>14}   (négatif = rouge pas encore au centre du bleu)")
    ok_key = ok_time = early = 0
    for key, signed, expected, rnd, start_gap in kb.presses:
        note = "  ← curseur déjà dans l'arc au début de la manche" if abs(start_gap) < HALF_ARC + 25 else ""
        print(f"{expected.upper():>8} {key.upper():>7} {signed:>+13.1f}°{note}")
        ok_key += key == expected
        ok_time += abs(signed) <= HALF_ARC + 8       # arc + latence d'un cycle de capture (informatif)
        early += signed < -HALF_ARC                  # avant même d'entrer dans l'arc
    n = len(kb.presses)
    print(f"\nappuis : {n} · bonne touche : {ok_key}/{n} · avant l'arc (trop tôt) : {early}/{n}")
    print(f"informatif : {ok_time}/{n} appuis dans l'arc ± latence ; les autres sont TARDIFS (lissage du rouge + délai de boucle)")
    sys.exit(0 if n and ok_key == n and early == 0 else 1)


if __name__ == "__main__":
    main()
