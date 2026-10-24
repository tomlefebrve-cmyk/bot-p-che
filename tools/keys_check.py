"""
Vérifie que les touches Z/Q/S/D partent sur la BONNE touche physique, en AZERTY comme en QWERTY
(Windows simulé : aucune vraie touche n'est envoyée).

    python tools/keys_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.input_keys import Keyboard

# scancodes : position PHYSIQUE des touches. Z/Q/S/D n'ont pas les mêmes positions en AZERTY.
QWERTY = {"z": (0x5A, 0x2C), "q": (0x51, 0x10), "s": (0x53, 0x1F), "d": (0x44, 0x20),
          "w": (0x57, 0x11), "a": (0x41, 0x1E)}
AZERTY = {"z": (0x5A, 0x11), "q": (0x51, 0x1E), "s": (0x53, 0x1F), "d": (0x44, 0x20),
          "w": (0x57, 0x2C), "a": (0x41, 0x10)}
OLD_PYDIRECTINPUT = {"z": 0x2C, "q": 0x10, "s": 0x1F, "d": 0x20}      # toujours QWERTY


class FakeApi:
    available = True
    def __init__(self, table): self.table, self.sent = table, []
    def layout(self): return 1
    def vk_scan(self, ch, hkl): return self.table.get(ch)
    def send_scan(self, scan, up): self.sent.append((scan, up)); return True


ok_all = True
def check(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("OK  " if cond else "KO  ") + name + (f"  {extra}" if extra else ""))

for layout, table in (("AZERTY", AZERTY), ("QWERTY", QWERTY)):
    api = FakeApi(table); kb = Keyboard(api)
    sent = {}
    for k in "zqsd":
        api.sent.clear(); kb.press(k); sent[k] = api.sent[0][0]
        assert api.sent == [(sent[k], False), (sent[k], True)]
    want = {k: table[k][1] for k in "zqsd"}
    check(f"{layout} : Z Q S D envoyés sur la bonne touche", sent == want,
          " ".join(f"{k.upper()}=0x{v:02X}" for k, v in sent.items()))

# ce que faisait l'ancien envoi sur un AZERTY
wrong = [k.upper() for k in "zqsd" if OLD_PYDIRECTINPUT[k] != AZERTY[k][1]]
check("ancien envoi sur AZERTY : seules Z et Q étaient fausses (S et D OK)", wrong == ["Z", "Q"], f"fausses = {wrong}")

# lettre absente de la disposition → repli (pas de plantage)
api = FakeApi({}); kb = Keyboard(api)
check("lettre inconnue : pas de plantage", kb.press("z") in (True, False))
print("\nTOUT OK" if ok_all else "\nECHEC")
sys.exit(0 if ok_all else 1)
