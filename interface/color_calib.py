"""
Fenêtre de calibrage HSV (zone bleue + trait rouge).
Aperçu live du masque sur la zone capturée.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from interface.theme import COLORS


class ColorCalibWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings, capture, on_save: Optional[Callable] = None,
                 on_auto: Optional[Callable] = None):
        super().__init__(parent)
        self.title("Calibrage couleurs HSV")
        self.geometry("760x640")
        self.configure(fg_color=COLORS["bg"])
        self.settings = settings
        self.capture = capture
        self.on_save = on_save
        self.on_auto = on_auto
        self._photo = None
        self._running = True

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.attributes("-topmost", True)

        ctk.CTkLabel(
            self, text="Calibrage couleurs",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["text"],
        ).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            self,
            text="Ajuste les curseurs jusqu’à ce que le bleu (cible) et le rouge (curseur) soient bien isolés.",
            text_color=COLORS["muted"], font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        if on_auto:
            ctk.CTkButton(
                self, text="Calibration automatique (recommandé)", height=44, corner_radius=10,
                fg_color="#17b45a", hover_color="#139a4c", text_color="#ffffff",
                font=ctk.CTkFont(size=15, weight="bold"),
                command=lambda: on_auto(done=self.refresh_from_settings),
            ).pack(fill="x", padx=16, pady=(0, 8))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=4)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # sliders
        left = ctk.CTkScrollableFrame(body, width=280, fg_color=COLORS["card"], corner_radius=12)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

        self.sliders = {}
        groups = [
            ("Zone bleue", [
                ("blue_h_min", "H min", 0, 179),
                ("blue_h_max", "H max", 0, 179),
                ("blue_s_min", "S min", 0, 255),
                ("blue_v_min", "V min", 0, 255),
            ]),
            ("Trait rouge", [
                ("red_h_min1", "H min 1", 0, 179),
                ("red_h_max1", "H max 1", 0, 179),
                ("red_h_min2", "H min 2", 0, 179),
                ("red_h_max2", "H max 2", 0, 179),
                ("red_s_min", "S min", 0, 255),
                ("red_v_min", "V min", 0, 255),
            ]),
        ]
        for title, fields in groups:
            ctk.CTkLabel(
                left, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["accent"],
            ).pack(anchor="w", padx=10, pady=(12, 4))
            for key, label, mn, mx in fields:
                row = ctk.CTkFrame(left, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)
                ctk.CTkLabel(row, text=label, width=56, anchor="w",
                             text_color=COLORS["text2"]).pack(side="left")
                val = int(getattr(settings, key))
                var = ctk.IntVar(value=val)
                s = ctk.CTkSlider(row, from_=mn, to=mx, variable=var, width=140,
                                  progress_color=COLORS["accent"])
                s.pack(side="left", padx=4)
                lbl = ctk.CTkLabel(row, text=str(val), width=32, text_color=COLORS["text"])
                lbl.pack(side="left")

                def _upd(v, k=key, lab=lbl, vr=var):
                    lab.configure(text=str(int(float(v))))
                    setattr(self.settings, k, int(float(v)))

                s.configure(command=_upd)
                self.sliders[key] = (s, var, lbl)

        # preview
        right = ctk.CTkFrame(body, fg_color=COLORS["card"], corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew")
        self.preview = ctk.CTkLabel(right, text="Aperçu…", text_color=COLORS["muted"])
        self.preview.pack(expand=True, padx=10, pady=10)

        # mode
        modes = ctk.CTkFrame(self, fg_color="transparent")
        modes.pack(fill="x", padx=16, pady=6)
        self.mode = ctk.StringVar(value="both")
        for val, txt in (("orig", "Original"), ("blue", "Masque bleu"), ("red", "Masque rouge"), ("both", "Les deux")):
            ctk.CTkRadioButton(
                modes, text=txt, variable=self.mode, value=val,
                text_color=COLORS["text2"],
            ).pack(side="left", padx=8)

        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkButton(
            bot, text="Enregistrer", width=140, height=36, corner_radius=10,
            fg_color=COLORS["success"], text_color="#04120a", command=self._save,
        ).pack(side="right", padx=6)
        ctk.CTkButton(
            bot, text="Fermer", width=100, height=36, corner_radius=10,
            fg_color=COLORS["card2"], command=self._close,
        ).pack(side="right")

        self.after(50, self._tick)

    def refresh_from_settings(self):
        """Remet les curseurs sur les valeurs calibrées automatiquement."""
        for key, (slider, var, lbl) in self.sliders.items():
            val = int(getattr(self.settings, key))
            var.set(val)
            lbl.configure(text=str(val))

    def _mask_blue(self, hsv):
        s = self.settings
        lo = np.array([s.blue_h_min, s.blue_s_min, s.blue_v_min])
        hi = np.array([s.blue_h_max, 255, 255])
        return cv2.inRange(hsv, lo, hi)

    def _mask_red(self, hsv):
        s = self.settings
        m1 = cv2.inRange(
            hsv,
            np.array([s.red_h_min1, s.red_s_min, s.red_v_min]),
            np.array([s.red_h_max1, 255, 255]),
        )
        m2 = cv2.inRange(
            hsv,
            np.array([s.red_h_min2, s.red_s_min, s.red_v_min]),
            np.array([s.red_h_max2, 255, 255]),
        )
        return cv2.bitwise_or(m1, m2)

    def _tick(self):
        if not self._running:
            return
        frame = self.capture.grab()
        if frame is not None:
            try:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mode = self.mode.get()
                if mode == "orig":
                    vis = frame.copy()
                elif mode == "blue":
                    m = self._mask_blue(hsv)
                    vis = cv2.bitwise_and(frame, frame, mask=m)
                    vis[m > 0] = (255, 200, 0)  # cyan-ish on blue mask
                elif mode == "red":
                    m = self._mask_red(hsv)
                    vis = cv2.bitwise_and(frame, frame, mask=m)
                    vis[m > 0] = (0, 0, 255)
                else:
                    vis = frame.copy()
                    mb, mr = self._mask_blue(hsv), self._mask_red(hsv)
                    vis[mb > 0] = (255, 180, 0)
                    vis[mr > 0] = (0, 0, 255)
                rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                max_w = 380
                if w > max_w:
                    sc = max_w / w
                    rgb = cv2.resize(rgb, (int(w * sc), int(h * sc)))
                img = Image.fromarray(rgb)
                photo = ImageTk.PhotoImage(img)
                self._photo = photo
                self.preview.configure(image=photo, text="")
            except Exception:
                pass
        self.after(80, self._tick)

    def _save(self):
        self.settings.save()
        if self.on_save:
            self.on_save()
        self._close()

    def _close(self):
        self._running = False
        try:
            self.destroy()
        except Exception:
            pass
