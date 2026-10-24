"""
Calibration automatique : 6 « écrans » aux couleurs différentes (bleu/rouge, rouge/rouge,
rouge/bleu, écrans ternes ou décalés). Pour chacun : calibration → pêche complète sur un faux
mini-jeu → vérifie bonne touche à chaque fois et jamais d'appui avant l'arc.

    python tools/autocal_check.py
"""
import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cv2
import numpy as np

import sim_check as sc
from bot.engine import Engine
from config.settings import Settings
from detection.autocal import AutoCalibrator
class Game(sc.FakeGame):
    def __init__(self, keys, tdir, arc, cur, shift=(0,1.0,1.0)):
        super().__init__(keys, tdir, arc_color=arc); self.cur=cur; self.shift=shift
    def render(self):
        f=np.full((220,220,3),28,np.uint8); cv2.circle(f,(110,110),70,(105,105,105),3)
        cv2.ellipse(f,(110,110),(70,70),0,-(self.blue+12),-(self.blue-12),self.arc_color,6)
        a=math.radians(self.red())
        cv2.line(f,(int(110+60*math.cos(a)),int(110-60*math.sin(a))),(int(110+75*math.cos(a)),int(110-75*math.sin(a))),self.cur,4)
        t=self.tpl[self.key]; t=cv2.resize(t,(int(t.shape[1]*1.8),int(t.shape[0]*1.8)))
        y0,x0=110-t.shape[0]//2,110-t.shape[1]//2; f[y0:y0+t.shape[0],x0:x0+t.shape[1]]=t[:,:,None]
        f=cv2.GaussianBlur(f,(3,3),0)
        hsv=cv2.cvtColor(f,cv2.COLOR_BGR2HSV).astype(np.float32); dh,ms,mv=self.shift
        hsv[...,0]=(hsv[...,0]+dh)%180; hsv[...,1]=np.clip(hsv[...,1]*ms,0,255); hsv[...,2]=np.clip(hsv[...,2]*mv,0,255)
        f=cv2.cvtColor(hsv.astype(np.uint8),cv2.COLOR_HSV2BGR)
        return np.clip(f.astype(int)+np.random.randint(-5,6,f.shape),0,255).astype(np.uint8)
SCEN = {
 "std":    ((255,120,0),(40,40,235),(0,1.0,1.0)),
 "decale": ((255,120,0),(40,40,235),(-9,0.75,0.8)),
 "sombre": ((255,120,0),(40,40,235),(6,0.6,0.7)),
 "rr":     ((40,40,235),(40,40,235),(0,1.0,1.0)),
 "rrdec":  ((40,40,235),(40,40,235),(8,0.7,0.8)),
 "rb":     ((40,40,235),(255,120,0),(0,1.0,1.0)),
}
def run(name, seconds=16, want=6, verbose=True):
    arc,cur,shift=SCEN[name]
    random.seed(4); np.random.seed(4)
    s=Settings(); s.target_color='blue'
    g=Game(list('zqsd'),s.templates_path(),arc,cur,shift); g.new_round()
    cap=sc.FakeCapture(g); cal=AutoCalibrator(s,cap); res=cal.run(n_frames=16,interval=0.05); cal.apply(res)
    logs=[]; eng=Engine(s,on_log=logs.append); eng.capture=cap; kb=sc.FakeKeyboard(g); eng.keyboard=kb; eng.start()
    end=time.time()+seconds
    while time.time()<end and len(kb.presses)<want: eng.step(); time.sleep(0.03)
    eng.stop()
    if verbose:
        print(name, res.layout, {k:v for k,v in res.updates.items() if k.startswith(('blue','red'))})
        print([l for l in logs if 'WARN' in l or 'LOCK' in l][:12])
        print([round(p[1],1) for p in kb.presses])
    return res, logs, kb


if __name__ == "__main__":
    allok = True
    for name in SCEN:
        res, logs, kb = run(name, seconds=16, want=6, verbose=False)
        n = len(kb.presses)
        good = sum(p[0] == p[2] for p in kb.presses)
        early = sum(p[1] < -15 for p in kb.presses)
        ok = res.ok and n >= 5 and good == n and early == 0
        allok &= ok
        print(("OK  " if ok else "KO  ") + f"{name:7s} -> {res.updates.get('target_color')}  "
              f"bonne touche {good}/{n}  avant l'arc {early}")
    print("\nTOUT OK" if allok else "\nECHEC")
    sys.exit(0 if allok else 1)
