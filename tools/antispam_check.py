"""
Anti-spam : le bot ne doit PAS appuyer quand il n'y a pas de vrai mini-jeu, et doit limiter ses appuis.
Chaque cas est joué sans puis avec l'anti-spam, avec le vrai moteur et un faux clavier.

    python tools/antispam_check.py
"""
import math
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from bot.engine import Engine
from config.settings import Settings

TPL = {k: cv2.imread(os.path.join(ROOT, "templates", "keys", f"{k}.png"), 0) for k in "zqsd"}
BLUE, RED = (255, 120, 0), (40, 40, 235)
CX = CY = 110
R = 70


class World:
    """Image du « jeu » : anneau + lettre + arc bleu + curseur rouge, selon le scénario."""

    def __init__(self, mode):
        self.mode, self.t0, self.n = mode, time.time(), 0

    def frame(self):
        self.n += 1
        t = time.time() - self.t0
        f = np.full((220, 220, 3), 28, np.uint8)
        cv2.circle(f, (CX, CY), R, (105, 105, 105), 3)
        arc = 90.0
        cur = (t * 140) % 360
        if self.mode == "static_cursor":                 # curseur immobile posé sur l'arc
            cur = arc
        if self.mode == "flicker_arc":                   # « arc » qui saute partout
            arc = random.uniform(0, 360)
        if self.mode == "aligned_always":                # curseur toujours sur l'arc, mais qui tremble sur place
            cur = arc + 5 * math.sin(t * 30)
        if self.mode == "fast":                          # vrai mini-jeu très rapide (pour tester la limite)
            cur = (t * 420) % 360
        if self.mode != "no_arc":
            cv2.ellipse(f, (CX, CY), (R, R), 0, -(arc + 12), -(arc - 12), BLUE, 6)
        a = math.radians(cur)
        cv2.line(f, (int(CX + 60 * math.cos(a)), int(CY - 60 * math.sin(a))),
                 (int(CX + 75 * math.cos(a)), int(CY - 75 * math.sin(a))), RED, 4)
        g = TPL["z"]
        g = cv2.resize(g, (int(g.shape[1] * 1.8), int(g.shape[0] * 1.8)))
        f[CY - g.shape[0] // 2:CY - g.shape[0] // 2 + g.shape[0], CX - g.shape[1] // 2:CX - g.shape[1] // 2 + g.shape[1]] = g[:, :, None]
        f = cv2.GaussianBlur(f, (3, 3), 0)
        return np.clip(f.astype(int) + np.random.randint(-5, 6, f.shape), 0, 255).astype(np.uint8)


class Cap:
    def __init__(self, world): self.world = world
    def set_region(self, *a): pass
    def grab(self): return self.world.frame()


class Kb:
    mode = "layout"
    def __init__(self): self.n, self.times = 0, []
    def press(self, k):
        self.n += 1
        self.times.append(time.time())
        return True


def run(mode, anti, seconds, **over):
    random.seed(5); np.random.seed(5)
    s = Settings()
    s.target_color = "blue"
    s.anti_spam = anti
    s.circle_fallback = True
    for k, v in over.items():
        setattr(s, k, v)
    logs = []
    eng = Engine(s, on_log=logs.append)
    eng.capture, eng.keyboard = Cap(World(mode)), Kb()
    eng.start()
    t0 = time.time()
    while time.time() - t0 < seconds:
        eng.step()
        time.sleep(0.03)
    eng.stop()
    return eng.keyboard, logs


ok_all = True
def check(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("OK  " if cond else "KO  ") + name + (f"  {extra}" if extra else ""))


# 1) curseur immobile posé sur l'arc : faux mini-jeu -> ne doit jamais appuyer
off, _ = run("static_cursor", False, 6)
on, _ = run("static_cursor", True, 6)
check("curseur IMMOBILE : sans anti-spam il appuie (le défaut)", off.n > 0, f"{off.n} appuis")
check("curseur IMMOBILE : avec anti-spam, aucun appui", on.n == 0, f"{on.n} appuis")

# 2) arc qui saute : pas un vrai arc
off, _ = run("flicker_arc", False, 6)
on, lg = run("flicker_arc", True, 6)
check("arc INSTABLE : avec anti-spam, aucun appui", on.n == 0, f"{on.n} appuis (sans anti-spam : {off.n})")

# 3) aucun template de lettre : ne pas appuyer à l'aveugle
empty = tempfile.mkdtemp()
off, _ = run("aligned_always", False, 6, key_templates_dir=empty)
on, lg = run("aligned_always", True, 6, key_templates_dir=empty)
check("SANS template : sans anti-spam il appuie à l'aveugle", off.n > 0, f"{off.n} appuis")
check("SANS template : avec anti-spam, aucun appui", on.n == 0, f"{on.n} appuis")

# 3b) curseur qui tremble sur place sur l'arc (faux mini-jeu) : ne doit pas appuyer
on, _ = run("aligned_always", True, 6)
check("curseur qui TREMBLE sur place : avec anti-spam, aucun appui", on.n == 0, f"{on.n} appuis")

# 4) limite d'appuis : max 3 par 4 s, puis pause
kb, lg = run("fast", True, 9, anti_spam_max=3, anti_spam_window_s=4, anti_spam_pause_s=3,
             post_catch_cooldown_ms=0, reaction_delay_ms=0, min_key_interval_ms=0)
t = kb.times
first = [x for x in t if x - t[0] < 4] if t else []
check("LIMITE : jamais plus de 3 appuis par fenêtre de 4 s",
      all(sum(1 for y in t if x <= y < x + 4) <= 3 for x in t), f"{len(t)} appuis en 9 s")
check("LIMITE : une pause anti-spam est déclenchée puis le bot reprend",
      any("pause de 3 s" in l for l in lg) and any("Anti-spam : reprise" in l for l in lg))
off, _ = run("fast", False, 9, post_catch_cooldown_ms=0, reaction_delay_ms=0, min_key_interval_ms=0)
check("LIMITE : sans anti-spam, beaucoup plus d'appuis", off.n > len(t), f"{off.n} appuis sans anti-spam")

# 5) lettre visible mais jamais d'arc : échecs en série -> ralentit puis pause
kb, lg = run("no_arc", True, 14, anti_spam_fail_limit=3, anti_spam_pause_s=4)
check("ÉCHECS EN SÉRIE : aucun appui et pause automatique",
      kb.n == 0 and any("aucun mini-jeu valide" in l for l in lg), f"{sum('WARN' in l for l in lg)} avertissements")

# 6) vrai mini-jeu : l'anti-spam ne gêne pas (curseur qui tourne, arc fixe)
on, _ = run("real", True, 8)
check("VRAI mini-jeu : le bot appuie normalement avec l'anti-spam", on.n >= 3, f"{on.n} appuis en 8 s")

print("\nTOUT OK" if ok_all else "\nECHEC")
sys.exit(0 if ok_all else 1)
