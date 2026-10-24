"""
Vérifie l'auto-clic avec un faux clavier/souris (sans cliquer pour de vrai) :
intervalle, nombre de clics, position fixe, compte à rebours et ARRÊT IMMÉDIAT.

    python tools/clicker_check.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.autoclicker import AutoClicker, HotkeyPoller


class Fake:
    def __init__(self):
        self.clicks, self.moves, self.down = [], [], set()
        self.lock = threading.Lock()
    def cursor_pos(self): return (10, 10)
    def set_cursor_pos(self, x, y): self.moves.append((x, y))
    def click(self, b):
        with self.lock: self.clicks.append((time.perf_counter(), b))
    def is_down(self, vk): return vk in self.down
    def timer_begin(self): pass
    def timer_end(self): pass


ok_all = True
def check(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("OK  " if cond else "KO  ") + name + (f"  {extra}" if extra else ""))

# 1) intervalle + nombre de clics
b = Fake(); c = AutoClicker(b); c.configure(50, "left", repeat=10); c.start()
while c.running: time.sleep(0.01)
ts = [t for t, _ in b.clicks]
gaps = [(ts[i+1] - ts[i]) * 1000 for i in range(len(ts) - 1)]
check("10 clics puis arrêt tout seul", len(b.clicks) == 10 and c.count == 10)
check("intervalle ≈ 50 ms", all(35 < g < 80 for g in gaps), f"min {min(gaps):.0f} max {max(gaps):.0f} ms")

# 2) bouton droit + position fixe
b = Fake(); c = AutoClicker(b); c.configure(20, "right", repeat=3, pos=(481, 427)); c.start()
while c.running: time.sleep(0.01)
check("bouton droit", all(x[1] == "right" for x in b.clicks))
check("position fixe X/Y avant chaque clic", b.moves == [(481, 427)] * 3)

# 3) position actuelle : le curseur n'est pas déplacé
b = Fake(); c = AutoClicker(b); c.configure(20, "left", repeat=2); c.start()
while c.running: time.sleep(0.01)
check("position actuelle : curseur non déplacé", b.moves == [])

# 4) ARRÊT IMMÉDIAT : aucun clic après stop(), même avec un intervalle de 1 ms
worst = 0
for trial in range(40):
    b = Fake(); c = AutoClicker(b); c.configure(1 if trial % 2 else 5, "left"); c.start()
    time.sleep(0.03 + (trial % 5) * 0.003)
    c.stop(); n = len(b.clicks)
    time.sleep(0.05)
    worst = max(worst, len(b.clicks) - n)
check("aucun clic en trop après Arrêter (40 essais)", worst == 0, f"clics en trop max = {worst}")

# 5) arrêt pendant un long intervalle : réaction immédiate
b = Fake(); c = AutoClicker(b); c.configure(5000, "left"); c.start(); time.sleep(0.05)
t0 = time.perf_counter(); c.stop(); dt = (time.perf_counter() - t0) * 1000
check("arrêt immédiat pendant un intervalle de 5 s", dt < 100 and not c.running and len(b.clicks) == 1, f"{dt:.0f} ms")

# 6) compte à rebours : annulable, aucun clic
b = Fake(); c = AutoClicker(b); c.configure(10, "left"); c.start(delay=1.0); time.sleep(0.2)
st = c.state; c.stop(); time.sleep(0.1)
check("compte à rebours annulable sans clic", st == "countdown" and len(b.clicks) == 0)

# 7) raccourcis (touches simulées)
b = Fake(); seen = []
hp = HotkeyPoller(b, {"start": lambda: seen.append("start"), "stop": lambda: seen.append("stop"),
                      "toggle": lambda: seen.append("toggle")}, {"start": 109, "stop": 106, "toggle": 111})
hp.start()
for vk in (109, 111, 106):
    b.down.add(vk); time.sleep(0.06); b.down.discard(vk); time.sleep(0.04)
hp.paused = True; b.down.add(109); time.sleep(0.06); b.down.discard(109); hp.paused = False
hp.close()
check("raccourcis détectés (1 appui = 1 action, pause respectée)", seen == ["start", "toggle", "stop"], str(seen))

# 8) pause automatique : marche 0,4 s / pause 0,4 s — aucun clic pendant les pauses
b = Fake(); c = AutoClicker(b); c.configure(20, "left", cycle_run=0.4, cycle_pause=0.4)
t0 = time.perf_counter(); c.start(); time.sleep(1.7)
states = []
c.stop(); n = len(b.clicks); time.sleep(0.1)
rel = [t - t0 for t, _ in b.clicks]
in_pause = [x for x in rel if 0.43 < x < 0.77 or 1.23 < x < 1.57]
in_run = [x for x in rel if x < 0.4 or 0.8 <= x < 1.2 or 1.6 <= x]
check("cycle : des clics pendant la marche", len(in_run) >= 20, f"{len(in_run)} clics")
check("cycle : AUCUN clic pendant les pauses", len(in_pause) == 0, f"{len(in_pause)} clics en pause")
check("cycle : arrêt pendant une pause = plus aucun clic", len(b.clicks) == n)
b = Fake(); c = AutoClicker(b); c.configure(20, "left", cycle_run=0.2, cycle_pause=5)
c.start(); time.sleep(0.5); st = c.state; t = time.perf_counter(); c.stop(); dt = (time.perf_counter() - t) * 1000
check("cycle : état « paused » puis arrêt immédiat", st == "paused" and dt < 100 and not c.running, f"{dt:.0f} ms")

print("\nTOUT OK" if ok_all else "\nECHEC")
sys.exit(0 if ok_all else 1)
