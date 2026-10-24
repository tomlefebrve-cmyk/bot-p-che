"""
Interface FishBot — tableau de bord (maquette « Tableau de bord FishBot »).
Barre latérale, 4 cartes de stats, contrôle du bot, progression, journal,
paramètres rapides et dernières captures. Thème bleu nuit, accent vert.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import numpy as np

from config.settings import Settings, RES_DIR, FROZEN
from config.desktop import create_desktop_shortcut
from bot.autoclicker import AutoClicker, HotkeyPoller, WinBackend
from bot.capture import ScreenCapture
from bot.preview import Preview, settings_signature
from detection.autocal import AutoCalibrator
from interface.clicker_page import ClickerPage
from interface.key_test import KeyTestDialog
from interface.update_dialog import UpdateDialog
from config import updater
from config.version import UPDATE_REPO
from bot.engine import Engine, State
from interface.theme import COLORS, APP_NAME, APP_SUB, VERSION, FONT
from interface.icons import icon, round_button, banner

C = COLORS

NAV = [
    ("dashboard", "Tableau de bord", "home"),
    ("fishing", "Pêche", "rod"),
    ("clicker", "Auto-clic", "cursor"),
    ("settings", "Paramètres", "gear"),
    ("journal", "Journal", "doc"),
    ("about", "À propos", "info"),
]

STATE_FR = {
    "IDLE": "Arrêté", "SEARCHING": "Recherche", "LOCKING": "Verrouillage",
    "TRACKING": "Suivi", "PRESSING": "Appui", "COOLDOWN": "Pause", "PAUSED": "Pause auto",
}

TAG_COLORS = {
    "INFO": C["blue"], "DETECT": C["blue"], "LOCK": C["blue"],
    "PARAM": C["purple"], "KEY": C["purple"], "CALIB": C["purple"],
    "OK": C["success"], "PRESS": C["success"],
    "WARN": C["warning"], "ERR": C["danger"],
}
KEY_FISH_COLOR = {"z": "#3ddc84", "q": "#f2d13d", "s": "#35a7ff", "d": "#f59e0b"}
ARC_CHOICES = {"Arc bleu · curseur rouge": "blue", "Arc rouge · curseur rouge": "red",
               "Arc rouge · curseur bleu": "red_blue"}


def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self.title(f"{APP_NAME}")
        self.geometry("1280x940")
        self.minsize(1100, 760)
        self.configure(fg_color=C["bg"])

        self.settings = Settings.load()
        self.engine = Engine(
            self.settings,
            on_log=self._log,
            on_state=self._on_state,
            on_frame=self._on_frame,
        )
        self._thread: Optional[threading.Thread] = None
        self._stop = False
        self._page = "dashboard"
        self._photo = None
        self._calib_photo = None
        self._last_frame = None
        self._session_start: Optional[float] = None
        self._elapsed = 0
        self._fade_job = None
        self._entries = {}
        self._quick = {}
        self._log_boxes = []
        self._history = []
        self._press_n = 0
        self._alive = True
        self._pv_pause = False
        self._cal_busy = False
        self._debug_targets = []          # (label, boîte) où afficher l'image debug

        # auto-clic : moteur + raccourcis clavier globaux (indépendants de la pêche)
        self.backend = WinBackend()
        self.ac = AutoClicker(self.backend, on_log=self._log)
        self.hotkeys = HotkeyPoller(
            self.backend,
            {n: (lambda n=n: self._safe_after(lambda: self.clicker.on_hotkey(n))) for n in ("start", "stop", "toggle")},
            self._hotkey_map(),
        )

        self._build()
        self.clicker = self.pages["clicker"]
        if self.backend.available:
            self.hotkeys.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_window_icon()
        threading.Thread(target=self._preview_loop, daemon=True).start()
        if FROZEN and not self.settings.desktop_shortcut_done:
            self.after(2500, self._first_run_shortcut)
        self._update_info = None
        updater.cleanup_old()                       # supprime l'ancienne version laissée par la dernière mise à jour
        if self.settings.auto_check_updates and self._update_repo():
            self.after(4000, lambda: self.check_updates(manual=False))
        self._log("[INFO] %s v%s lancé" % (APP_NAME, VERSION))
        self._log("[PARAM] Paramètres chargés avec succès")
        self._log("[INFO] Système prêt. Vous pouvez démarrer la pêche.")
        self._tick_stats()

    # ------------------------------------------------------------ structure
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=232, corner_radius=0, fg_color=C["sidebar"],
                            border_width=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)

        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(24, 30))
        ctk.CTkLabel(logo, text="", image=icon("fish", C["blue"], 46)).pack(side="left")
        names = ctk.CTkFrame(logo, fg_color="transparent")
        names.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(names, text=APP_NAME, font=F(19, True), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(names, text=APP_SUB, font=F(12), text_color=C["text2"]).pack(anchor="w")

        self._nav_btns = {}
        for key, label, ic in NAV:
            btn = ctk.CTkButton(
                side, text=f"  {label}", anchor="w", height=46, corner_radius=8,
                fg_color="transparent", hover_color=C["card2"], text_color=C["text2"],
                font=F(15), image=icon(ic, C["muted"], 24), compound="left",
                command=lambda k=key: self._show(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._nav_btns[key] = btn

        dot = ctk.CTkFrame(side, fg_color="transparent")
        dot.pack(side="bottom", fill="x", padx=22, pady=22)
        self.btn_update = ctk.CTkButton(side, text="⬇  Mise à jour disponible", height=40, corner_radius=8,
                                        fg_color="#17b45a", hover_color="#139a4c", text_color="#ffffff",
                                        font=F(13, True), command=self.open_update_dialog)
        self.status_dot = ctk.CTkFrame(dot, width=12, height=12, corner_radius=6, fg_color=C["accent"])
        self.status_dot.pack(side="left")
        self.status_side = ctk.CTkLabel(dot, text="INACTIF", text_color=C["text2"], font=F(13))
        self.status_side.pack(side="left", padx=10)

        self.content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {
            "dashboard": self._page_dashboard(self.content),
            "fishing": self._page_fishing(self.content),
            "clicker": ClickerPage(self.content, self),
            "settings": self._page_settings(self.content),
            "journal": self._page_journal(self.content),
            "about": self._page_about(self.content),
        }
        self._show("dashboard")

    def _show(self, key: str):
        self._page = key
        for k, btn in self._nav_btns.items():
            ic = dict((n[0], n[2]) for n in NAV)[k]
            if k == key:
                btn.configure(fg_color=C["blue_dim"], text_color=C["blue"],
                              hover_color=C["blue_dim"], image=icon(ic, C["blue"], 24))
            else:
                btn.configure(fg_color="transparent", text_color=C["text2"],
                              hover_color=C["card2"], image=icon(ic, C["muted"], 24))
        for frame in self.pages.values():
            frame.grid_forget()

        def reveal():
            self.pages[key].grid(row=0, column=0, sticky="nsew", padx=26, pady=20)

        if self._fade_job:
            try:
                self.after_cancel(self._fade_job)
            except Exception:
                pass
        self._fade_job = self.after(30, reveal)

    # ------------------------------------------------------------ widgets
    def _card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"], **kw)

    def _card_head(self, card, ic: str, title: str, link: Optional[str] = None, on_link=None):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(14, 8))
        ctk.CTkLabel(row, text="", image=icon(ic, C["blue"], 26)).pack(side="left")
        ctk.CTkLabel(row, text=title, font=F(17, True), text_color=C["text"]).pack(side="left", padx=12)
        if link:
            b = ctk.CTkButton(row, text=link, width=70, height=24, fg_color="transparent",
                              hover_color=C["card2"], text_color=C["blue"], font=F(13),
                              command=on_link)
            b.pack(side="right")
        ctk.CTkFrame(card, height=1, fg_color=C["border"]).pack(fill="x", padx=20)

    def _tile(self, parent, ic: str, size: int = 56, glyph: int = 30):
        t = ctk.CTkFrame(parent, width=size, height=size, corner_radius=12, fg_color=C["icon_bg"])
        t.pack_propagate(False)
        ctk.CTkLabel(t, text="", image=icon(ic, C["blue"], glyph)).place(relx=0.5, rely=0.5, anchor="center")
        return t

    def _stat(self, parent, col, ic, title, value, caption):
        card = self._card(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 7, 0 if col == 3 else 7))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=11)
        self._tile(inner, ic).pack(side="left", padx=(0, 14))
        box = ctk.CTkFrame(inner, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(box, text=title, font=F(14), text_color=C["text"]).pack(anchor="w")
        v = ctk.CTkLabel(box, text=value, font=F(30, True), text_color=C["text"])
        v.pack(anchor="w")
        cap = ctk.CTkLabel(box, text=caption, font=F(12), text_color=C["text2"])
        cap.pack(anchor="w")
        return v, cap

    def _make_log_box(self, parent, height=None):
        box = ctk.CTkTextbox(parent, corner_radius=8, fg_color=C["card"], text_color=C["text"],
                             border_width=0, font=F(13), wrap="word", **({"height": height} if height else {}))
        tb = box._textbox
        tb.configure(tabs=("96", "178"))
        tb.tag_config("ts", foreground=C["text2"])
        tb.tag_config("msg", foreground=C["text"])
        for tag, color in TAG_COLORS.items():
            tb.tag_config(tag, foreground=color)
        for item in self._history:
            self._write(box, *item)
        self._log_boxes.append(box)
        return box

    @staticmethod
    def _write(box, ts: str, tag: str, text: str):
        box.insert("end", f"{ts}\t", "ts")
        box.insert("end", f"[{tag}]\t", tag if tag in TAG_COLORS else "msg")
        box.insert("end", text + "\n", "msg")
        box.see("end")
        n = int(box.index("end-1c").split(".")[0])
        if n > 500:
            box.delete("1.0", f"{n - 400}.0")

    def _spinner(self, parent, key: str, step: float, lo: float, hi: float, cast):
        wrap = ctk.CTkFrame(parent, fg_color=C["input"], corner_radius=8,
                            border_width=1, border_color=C["border"], width=230, height=34)
        wrap.pack_propagate(False)
        e = ctk.CTkEntry(wrap, border_width=0, fg_color="transparent", font=F(14), height=30)
        e.insert(0, str(getattr(self.settings, key)))
        for sym, d in (("+", step), ("−", -step)):
            ctk.CTkButton(
                wrap, text=sym, width=38, height=30, corner_radius=0, fg_color="transparent",
                hover_color=C["card2"], text_color=C["text"], font=F(16),
                command=lambda d=d: self._nudge(key, d, lo, hi, cast),
            ).pack(side="right", padx=(0, 2) if sym == "+" else 0)
            ctk.CTkFrame(wrap, width=1, height=1, fg_color=C["border"]).pack(side="right", fill="y", pady=4)
        e.pack(side="left", fill="x", expand=True, padx=(8, 0))
        e.bind("<Return>", lambda _e: self._commit(key, lo, hi, cast))
        e.bind("<FocusOut>", lambda _e: self._commit(key, lo, hi, cast))
        self._quick[key] = e
        return wrap

    def _mini_entry(self, parent, key: str):
        e = ctk.CTkEntry(parent, width=58, height=32, corner_radius=8, font=F(14), justify="center",
                         fg_color=C["input"], border_color=C["border"])
        e.insert(0, str(getattr(self.settings, key)))
        e.bind("<Return>", lambda _e: self._commit(key, 1, 86400, int))
        e.bind("<FocusOut>", lambda _e: self._commit(key, 1, 86400, int))
        self._quick[key] = e
        return e

    def _on_cycle_switch(self):
        on = bool(self.sw_cycle.get())
        self._set_setting("cycle_enabled", on)
        s = self.settings
        self._log(f"[PARAM] Pause automatique {'activée' if on else 'désactivée'}"
                  + (f" : {s.cycle_run_s} s de marche, {s.cycle_pause_s} s de pause" if on else ""))

    def _on_spam_switch(self):
        on = bool(self.sw_spam.get())
        self._set_setting("anti_spam", on)
        s = self.settings
        self._log("[PARAM] Anti-spam " + (f"activé : n'appuie que sur un vrai mini-jeu, max {s.anti_spam_max} "
                                           f"appuis par {s.anti_spam_window_s} s" if on else "désactivé"))

    def _nudge(self, key, delta, lo, hi, cast):
        cur = float(getattr(self.settings, key))
        self._set_setting(key, cast(min(hi, max(lo, cur + delta))))

    def _commit(self, key, lo, hi, cast):
        try:
            val = cast(min(hi, max(lo, float(self._quick[key].get().replace(",", ".")))))
        except ValueError:
            val = getattr(self.settings, key)
        self._set_setting(key, val)

    def _set_setting(self, key: str, value):
        setattr(self.settings, key, value)
        self.settings.save()
        if key in self._entries:
            self._entries[key].delete(0, "end")
            self._entries[key].insert(0, str(value))
        self._sync_quick()

    def _sync_quick(self):
        for key, e in self._quick.items():
            if self.focus_get() is e:
                continue
            e.delete(0, "end")
            e.insert(0, str(getattr(self.settings, key)))
        if hasattr(self, "sw_spam"):
            (self.sw_spam.select if self.settings.anti_spam else self.sw_spam.deselect)()
        if hasattr(self, "sw_cycle"):
            (self.sw_cycle.select if self.settings.cycle_enabled else self.sw_cycle.deselect)()
        if hasattr(self, "arc_menu"):
            cur = {"blue_red": "blue", "red_red": "red"}.get(str(self.settings.target_color).lower(),
                                                                str(self.settings.target_color).lower())
            self.arc_menu.set(next((k for k, v in ARC_CHOICES.items() if v == cur), list(ARC_CHOICES)[0]))
        if hasattr(self, "keys_quick") and self.focus_get() is not self.keys_quick:
            self.keys_quick.delete(0, "end")
            self.keys_quick.insert(0, self.settings.keys_enabled)

    # ------------------------------------------------------------ dashboard
    def _page_dashboard(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(f, fg_color="transparent", height=104)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        head.grid_propagate(False)
        head.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(head, text="", image=banner(C["bg"], 560, 104)).place(relx=1.0, rely=0.0, anchor="ne")
        tile = ctk.CTkFrame(head, width=58, height=58, corner_radius=29, fg_color=C["card"],
                            border_width=1, border_color=C["border"])
        tile.grid(row=0, column=0, sticky="w", pady=14)
        tile.pack_propagate(False)
        ctk.CTkLabel(tile, text="", image=icon("wave", C["blue"], 30)).place(relx=0.5, rely=0.5, anchor="center")
        tx = ctk.CTkFrame(head, fg_color="transparent")
        tx.grid(row=0, column=1, sticky="w", padx=14, pady=14)
        ctk.CTkLabel(tx, text="Tableau de bord", font=F(30, True), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Contrôlez et surveillez votre bot de pêche", font=F(14),
                     text_color=C["blue"]).pack(anchor="w")
        self.header_status = ctk.CTkLabel(
            head, text="●  Système prêt", fg_color=C["accent_dim"], text_color=C["success"],
            corner_radius=24, font=F(16, True), width=230, height=48,
        )
        self.header_status.grid(row=0, column=3, padx=(0, 340), pady=14)

        stats = ctk.CTkFrame(f, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")
        self.lbl_fish, _ = self._stat(stats, 0, "fish", "Poissons pêchés", "0", "Depuis le lancement")
        self.lbl_ok, _ = self._stat(stats, 1, "hook", "Appuis réussis", "0", "Étapes validées")
        self.lbl_time, self.lbl_time_cap = self._stat(stats, 2, "clock", "Temps de pêche", "00:00", "Arrêté")
        self.lbl_rate, _ = self._stat(stats, 3, "check", "Réussite", "0%", "Étapes réussies")

        main = ctk.CTkFrame(f, fg_color="transparent")
        main.grid(row=2, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=11, uniform="col")
        main.grid_columnconfigure(1, weight=10, uniform="col")
        main.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ---- contrôle du bot
        ctl = self._card(left)
        ctl.pack(fill="x", pady=(0, 14))
        self._card_head(ctl, "hook", "Contrôle du bot")
        row = ctk.CTkFrame(ctl, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=10)
        self.big_btn = ctk.CTkButton(
            row, text="", width=88, height=88, fg_color="transparent", hover=False,
            image=self._big_img(False), command=self._toggle,
        )
        self.big_btn.pack(side="left", padx=(0, 16))
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left")
        ctk.CTkLabel(info, text="Statut", font=F(13), text_color=C["text2"]).pack(anchor="w")
        self.lbl_state = ctk.CTkLabel(info, text="Arrêté", font=F(26, True), text_color=C["text"])
        self.lbl_state.pack(anchor="w")
        self.lbl_key = ctk.CTkLabel(info, text="Prêt à pêcher", font=F(13), text_color=C["text2"])
        self.lbl_key.pack(anchor="w")
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right")
        self.btn_start = ctk.CTkButton(
            btns, text="  Démarrer", width=190, height=52, corner_radius=8,
            fg_color="#17b45a", hover_color="#139a4c", text_color="#ffffff", font=F(18, True),
            image=icon("play", "#ffffff", 20), compound="left", command=self.start_bot,
        )
        self.btn_start.pack(pady=(0, 10))
        self.btn_stop = ctk.CTkButton(
            btns, text="  Arrêter", width=190, height=42, corner_radius=8,
            fg_color=C["blue_dim"], hover_color="#12508f", text_color=C["text"], font=F(15, True),
            border_width=1, border_color=C["border"], image=icon("stop", C["blue"], 16),
            compound="left", state="disabled", command=self.stop_bot,
        )
        self.btn_stop.pack()

        cyc = ctk.CTkFrame(ctl, fg_color=C["card2"], corner_radius=10)
        cyc.pack(fill="x", padx=20, pady=(0, 8))
        self.sw_cycle = ctk.CTkSwitch(cyc, text="Pause automatique", font=F(14, True), text_color=C["text"],
                                      progress_color=C["accent"], command=self._on_cycle_switch)
        self.sw_cycle.pack(side="left", padx=(14, 18), pady=7)
        for label, key in (("marche", "cycle_run_s"), ("pause", "cycle_pause_s")):
            ctk.CTkLabel(cyc, text=label, font=F(13), text_color=C["text2"]).pack(side="left", padx=(0, 6))
            self._mini_entry(cyc, key).pack(side="left")
            ctk.CTkLabel(cyc, text="s", font=F(13), text_color=C["text2"]).pack(side="left", padx=(4, 16))

        asp = ctk.CTkFrame(ctl, fg_color=C["card2"], corner_radius=10)
        asp.pack(fill="x", padx=20, pady=(0, 12))
        self.sw_spam = ctk.CTkSwitch(asp, text="Anti-spam", font=F(14, True), text_color=C["text"],
                                     progress_color=C["accent"], command=self._on_spam_switch, width=140)
        self.sw_spam.pack(side="left", padx=(14, 18), pady=7)
        ctk.CTkLabel(asp, text="max", font=F(13), text_color=C["text2"]).pack(side="left", padx=(0, 6))
        self._mini_entry(asp, "anti_spam_max").pack(side="left")
        ctk.CTkLabel(asp, text="appuis par", font=F(13), text_color=C["text2"]).pack(side="left", padx=6)
        self._mini_entry(asp, "anti_spam_window_s").pack(side="left")
        ctk.CTkLabel(asp, text="s", font=F(13), text_color=C["text2"]).pack(side="left", padx=(4, 0))

        # ---- progression
        pg = self._card(left)
        pg.pack(fill="x", pady=(0, 14))
        self._card_head(pg, "fish", "Progression")
        cells = ctk.CTkFrame(pg, fg_color="transparent")
        cells.pack(fill="x", padx=20, pady=8)
        cells.grid_columnconfigure((0, 2, 4), weight=1, uniform="pg")
        self.lbl_step = self._pcell(cells, 0, "clock", "Étape en cours", "Arrêté")
        ctk.CTkFrame(cells, width=1, height=1, fg_color=C["border"]).grid(row=0, column=1, rowspan=2, sticky="ns", padx=10)
        self.lbl_okfail = self._pcell(cells, 2, "hook", "OK / échecs", "0 / 0")
        self.bar_rate = ctk.CTkProgressBar(cells, height=8, fg_color=C["card2"], progress_color=C["accent"])
        self.bar_rate.set(0)
        self.bar_rate.grid(row=1, column=2, sticky="ew", padx=(10, 6))
        ctk.CTkFrame(cells, width=1, height=1, fg_color=C["border"]).grid(row=0, column=3, rowspan=2, sticky="ns", padx=10)
        self.lbl_fph = self._pcell(cells, 4, "fish", "Captures / h", "0 / h")
        self.bar_fph = ctk.CTkProgressBar(cells, height=8, fg_color=C["card2"], progress_color=C["blue"])
        self.bar_fph.set(0)
        self.bar_fph.grid(row=1, column=4, sticky="ew", padx=(10, 6))

        # ---- journal
        lg = self._card(left)
        lg.pack(fill="both", expand=True)
        self._card_head(lg, "doc", "Journal d'activité", "Voir tout", lambda: self._show("journal"))
        self.log_box = self._make_log_box(lg)
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(8, 14))

        # ---- paramètres de pêche (rapides)
        pr = self._card(right)
        pr.pack(fill="x", pady=(0, 14))
        self._card_head(pr, "gear", "Paramètres de pêche")
        body = ctk.CTkFrame(pr, fg_color="transparent")
        body.pack(fill="x", padx=18, pady=(10, 14))

        def prow(ic, label, sub=None):
            r = ctk.CTkFrame(body, fg_color="transparent")
            r.pack(fill="x", pady=3)
            self._tile(r, ic, 36, 20).pack(side="left", padx=(0, 12))
            lab = ctk.CTkFrame(r, fg_color="transparent")
            lab.pack(side="left")
            ctk.CTkLabel(lab, text=label, font=F(14), text_color=C["text"]).pack(side="left")
            if sub:
                ctk.CTkLabel(lab, text=f" ({sub})", font=F(12), text_color=C["text2"]).pack(side="left")
            return r

        r = prow("wave", "Couleur de l'arc")
        self.arc_menu = ctk.CTkOptionMenu(
            r, values=list(ARC_CHOICES), width=230, height=34, corner_radius=8, font=F(14),
            fg_color=C["input"], button_color=C["input"], button_hover_color=C["card2"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["card2"], text_color=C["text"],
            command=self._on_arc_choice,
        )
        self.arc_menu.pack(side="right")
        r = prow("hook", "Touches du jeu")
        self.keys_quick = ctk.CTkEntry(r, width=230, height=34, corner_radius=8, font=F(14),
                                       fg_color=C["input"], border_color=C["border"])
        self.keys_quick.pack(side="right")
        self.keys_quick.bind("<Return>", lambda _e: self._commit_keys())
        self.keys_quick.bind("<FocusOut>", lambda _e: self._commit_keys())
        r = prow("rod", "Tolérance", "degrés")
        self._spinner(r, "tolerance_deg", 1, 1, 45, float).pack(side="right")
        r = prow("clock", "Délai de réaction", "ms")
        self._spinner(r, "reaction_delay_ms", 5, 0, 500, int).pack(side="right")
        r = prow("bag", "Pause après appui", "ms")
        self._spinner(r, "post_catch_cooldown_ms", 50, 0, 5000, int).pack(side="right")
        self._sync_quick()

        # ---- fenêtre debug : dernière image capturée, en direct
        dbg = self._card(right)
        dbg.pack(fill="both", expand=True)
        self._card_head(dbg, "wave", "Fenêtre debug")
        leg = ctk.CTkFrame(dbg, fg_color="transparent")
        leg.pack(fill="x", padx=20, pady=(6, 0))
        for txt, col in (("● cercle", "#50dc5a"), ("● lettre", "#ffaa00"),
                         ("● arc", "#00c8ff"), ("● curseur", "#ff4d4d")):
            ctk.CTkLabel(leg, text=txt, font=F(12), text_color=col).pack(side="left", padx=(0, 14))
        self.debug_label = self._debug_box(dbg, "L'image du jeu apparaît ici")
        return f

    def _debug_box(self, parent, placeholder: str):
        """Zone d'affichage de l'image debug ; retourne le label (l'image s'adapte à la place)."""
        box = ctk.CTkFrame(parent, fg_color=C["input"], corner_radius=10)
        box.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        box.pack_propagate(False)
        lab = ctk.CTkLabel(box, text=placeholder, text_color=C["muted"], font=F(13), image=None)
        lab.place(relx=0.5, rely=0.5, anchor="center")
        self._debug_targets.append((lab, box))
        return lab
        return f

    def _pcell(self, parent, col, ic, label, value):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=0, column=col, sticky="nsew", padx=(10, 6))
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(anchor="w")
        ctk.CTkLabel(top, text="", image=icon(ic, C["blue"], 18)).pack(side="left")
        ctk.CTkLabel(top, text=f" {label}", font=F(13), text_color=C["text"]).pack(side="left")
        v = ctk.CTkLabel(box, text=value, font=F(22, True), text_color=C["text"])
        v.pack(anchor="w", pady=(0, 6))
        return v

    def _big_img(self, running: bool):
        if running:
            return round_button("stop", "#1d6fb8", "#0a2a4d", C["blue"], 84)
        return round_button("play", "#1a7a54", "#0b3a2c", C["success"], 84)

    def _on_arc_choice(self, label: str):
        self._set_setting("target_color", ARC_CHOICES.get(label, "red"))
        self._log(f"[PARAM] Arc cible : {self.settings.target_color}")

    def _commit_keys(self):
        raw = self.keys_quick.get().strip().lower()
        if raw and raw != self.settings.keys_enabled:
            self.settings.keys_enabled = raw
            self.settings.save()
            if hasattr(self, "keys_entry"):
                self.keys_entry.delete(0, "end")
                self.keys_entry.insert(0, raw)
            self._log(f"[PARAM] Touches : {raw}")

    # ------------------------------------------------------------ pêche (aperçu + détection)
    def _page_fishing(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1, uniform="fc")
        f.grid_columnconfigure(1, weight=1, uniform="fc")
        f.grid_rowconfigure(1, weight=1)
        self._title(f, "Pêche", "Aperçu du cercle, zone de capture, couleurs et touches.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        prev = self._card(f)
        prev.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._card_head(prev, "wave", "Aperçu de la détection")
        self.bot_detail = ctk.CTkLabel(prev, text="Arrêté", font=F(14), text_color=C["text2"])
        self.bot_detail.pack(anchor="w", padx=20, pady=(10, 6))
        self._debug_box(prev, "L'image du jeu apparaît ici")

        sc = ctk.CTkScrollableFrame(f, fg_color="transparent")
        sc.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        sc.grid_columnconfigure(0, weight=1)

        def green_btn(parent, text, cmd, **kw):
            return ctk.CTkButton(parent, text=text, height=40, corner_radius=8, fg_color="#17b45a",
                                 hover_color="#139a4c", text_color="#ffffff", font=F(14, True),
                                 command=cmd, **kw)

        def dark_btn(parent, text, cmd, **kw):
            return ctk.CTkButton(parent, text=text, height=40, corner_radius=8, fg_color=C["blue_dim"],
                                 hover_color="#12508f", text_color=C["text"], font=F(14), command=cmd, **kw)

        c1 = self._card(sc)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._card_head(c1, "rod", "Zone de capture")
        ctk.CTkLabel(c1, text="Dessine un carré autour du cercle de pêche.", text_color=C["text2"],
                     font=F(13)).pack(anchor="w", padx=20, pady=(10, 8))
        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 8))
        green_btn(row, "Sélectionner la zone", self._open_region_picker).pack(side="left")
        dark_btn(row, "Centrer", self._center_capture, width=90).pack(side="left", padx=8)
        dark_btn(row, "Aperçu", self._snap_calib_once, width=90).pack(side="left")
        self.calib_zone_info = ctk.CTkLabel(
            c1, text=f"Zone : X={self.settings.capture_left}  Y={self.settings.capture_top}  "
                     f"Taille={self.settings.capture_size}", text_color=C["blue"], font=F(13))
        self.calib_zone_info.pack(anchor="w", padx=20, pady=(6, 6))
        self.calib_preview = ctk.CTkLabel(c1, text="Aperçu zone", text_color=C["muted"])
        self.calib_preview.pack(padx=20, pady=(0, 16))

        c2 = self._card(sc)
        c2.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self._card_head(c2, "wave", "Couleurs (arc et curseur)")
        ctk.CTkLabel(c2, text=("Si le bot ne voit pas le cercle, l'arc ou le curseur : ouvre le mini-jeu, "
                               "puis clique sur « Calibration automatique »."),
                     text_color=C["text2"], font=F(13), wraplength=430, justify="left", anchor="w"
                     ).pack(anchor="w", padx=20, pady=(10, 8))
        self.btn_autocal = ctk.CTkButton(
            c2, text="Calibration automatique", height=52, corner_radius=10, fg_color="#17b45a",
            hover_color="#139a4c", text_color="#ffffff", font=F(16, True), command=self._auto_calibrate)
        self.btn_autocal.pack(anchor="w", padx=20, pady=(0, 8), fill="x")
        self.lbl_cal = ctk.CTkLabel(c2, text="", font=F(13), text_color=C["text2"], wraplength=430,
                                    justify="left", anchor="w")
        self.lbl_cal.pack(anchor="w", padx=20)
        dark_btn(c2, "Réglage manuel (avancé)", self._open_color_calib, width=230).pack(
            anchor="w", padx=20, pady=(8, 16))

        c3 = self._card(sc)
        c3.grid(row=2, column=0, sticky="ew")
        self._card_head(c3, "hook", "Touches")
        rowk = ctk.CTkFrame(c3, fg_color="transparent")
        rowk.pack(fill="x", padx=20, pady=(14, 8))
        self.keys_entry = ctk.CTkEntry(rowk, width=200, height=38, corner_radius=8, font=F(14),
                                       fg_color=C["input"], border_color=C["border"])
        self.keys_entry.insert(0, getattr(self.settings, "keys_enabled", "z,q,s,d"))
        self.keys_entry.pack(side="left")
        green_btn(rowk, "Enregistrer", self._save_keys, width=120).pack(side="left", padx=8)
        rowb = ctk.CTkFrame(c3, fg_color="transparent")
        rowb.pack(fill="x", padx=20, pady=(0, 16))
        dark_btn(rowb, "Capturer template", self._capture_key_template, width=170).pack(side="left")
        green_btn(rowb, "Tester les touches", lambda: KeyTestDialog(self), width=170).pack(side="left", padx=8)
        return f

    def _title(self, parent, title: str, sub: str):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(box, text=title, font=F(30, True), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(box, text=sub, font=F(14), text_color=C["blue"]).pack(anchor="w")
        return box

    # ------------------------------------------------------------ paramètres
    def _page_settings(self, parent):
        outer = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        outer.grid_columnconfigure(0, weight=1)
        self._title(outer, "Paramètres", "Timing et comportement.").grid(row=0, column=0, sticky="w", pady=(0, 14))
        card = self._card(outer)
        card.grid(row=1, column=0, sticky="ew")
        self._card_head(card, "gear", "Réglages du bot")
        fields = [
            ("capture_left", "Capture X"),
            ("capture_top", "Capture Y"),
            ("capture_size", "Taille zone"),
            ("target_color", "Couleur de l'arc (blue / red / red_blue)"),
            ("key_send_mode", "Envoi des touches (layout / classic)"),
            ("anti_spam_pause_s", "Anti-spam : durée de la pause (s)"),
            ("anti_spam_fail_limit", "Anti-spam : échecs avant pause"),
            ("tolerance_deg", "Tolérance (°)"),
            ("poll_interval_ms", "Intervalle (ms)"),
            ("reaction_delay_ms", "Délai réaction (ms)"),
            ("post_catch_cooldown_ms", "Cooldown (ms)"),
            ("min_key_interval_ms", "Intervalle touches (ms)"),
            ("max_wait_ms", "Attente max (ms)"),
            ("hotkey_toggle", "Raccourci Start/Stop"),
        ]
        for key, label in fields:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=6)
            ctk.CTkLabel(row, text=label, width=260, anchor="w", font=F(14),
                         text_color=C["text"]).pack(side="left")
            e = ctk.CTkEntry(row, width=140, height=36, corner_radius=8, font=F(14),
                             fg_color=C["input"], border_color=C["border"])
            e.insert(0, str(getattr(self.settings, key)))
            e.pack(side="right")
            self._entries[key] = e
        ctk.CTkButton(
            card, text="Enregistrer", width=150, height=42, corner_radius=8, fg_color="#17b45a",
            hover_color="#139a4c", text_color="#ffffff", font=F(14, True),
            command=lambda: self._save_settings(),
        ).pack(anchor="e", padx=20, pady=16)
        return outer

    # ------------------------------------------------------------ journal / à propos
    def _page_journal(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(f, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._title(head, "Journal", "Toute l'activité du bot.").pack(side="left")
        ctk.CTkButton(head, text="Vider", width=90, height=36, corner_radius=8, fg_color=C["blue_dim"],
                      hover_color="#12508f", font=F(14), command=self._clear_logs).pack(side="right")
        card = self._card(f)
        card.grid(row=1, column=0, sticky="nsew")
        box = self._make_log_box(card)
        box.pack(fill="both", expand=True, padx=14, pady=14)
        return f

    def _page_about(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        self._title(f, "À propos", f"{APP_NAME} · version {VERSION}").grid(row=0, column=0, sticky="w", pady=(0, 14))
        card = self._card(f)
        card.grid(row=1, column=0, sticky="ew")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=24)
        ctk.CTkLabel(row, text="", image=icon("fish", C["blue"], 72)).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(
            row, justify="left", anchor="w", font=F(14), text_color=C["text"],
            text=("AUTO FISHER observe le cercle du mini-jeu de pêche, lit la lettre (Z, Q, S ou D),\n"
                  "suit l'arc cible et le curseur, puis appuie sur la bonne touche quand\n"
                  "le curseur est aligné sur l'arc.\n\n"
                  "Il contient aussi un auto-clic indépendant (page « Auto-clic »)."),
        ).pack(side="left")
        help_ = self._card(f)
        help_.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._card_head(help_, "info", "Pour commencer")
        ctk.CTkLabel(
            help_, justify="left", anchor="w", font=F(14), text_color=C["text"],
            text=("1.  Page « Pêche » : clique sur « Sélectionner la zone » et entoure le cercle de pêche.\n"
                  "2.  Ouvre le mini-jeu, puis clique sur « Calibration automatique ».\n"
                  "3.  Retourne au tableau de bord et clique sur « Démarrer ».\n"
                  "4.  La fenêtre debug te montre ce que le bot voit : cercle, lettre, arc et curseur."),
        ).pack(anchor="w", padx=22, pady=16)
        sc = self._card(f)
        sc.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        r2 = ctk.CTkFrame(sc, fg_color="transparent")
        r2.pack(fill="x", padx=22, pady=16)
        ctk.CTkButton(r2, text="Créer un raccourci sur le bureau", height=48, corner_radius=10, font=F(15, True),
                      fg_color=C["blue_dim"], hover_color="#12508f", text_color=C["text"],
                      command=self._make_shortcut).pack(side="left")
        self.lbl_shortcut = ctk.CTkLabel(r2, text="", font=F(13), text_color=C["text2"])
        self.lbl_shortcut.pack(side="left", padx=16)
        up = self._card(f)
        up.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._card_head(up, "check", "Mises à jour")
        r3 = ctk.CTkFrame(up, fg_color="transparent")
        r3.pack(fill="x", padx=22, pady=(14, 6))
        ctk.CTkLabel(r3, text=f"Version installée : {VERSION}", font=F(15, True), text_color=C["text"]).pack(side="left")
        ctk.CTkButton(r3, text="Vérifier les mises à jour", height=44, corner_radius=10, font=F(14, True),
                      fg_color=C["blue_dim"], hover_color="#12508f", text_color=C["text"],
                      command=lambda: self.check_updates(manual=True)).pack(side="right")
        self.lbl_update = ctk.CTkLabel(up, text="" if self._update_repo() else "Les mises à jour ne sont pas configurées.",
                                       font=F(13), text_color=C["text2"], wraplength=800, justify="left", anchor="w")
        self.lbl_update.pack(anchor="w", padx=22)
        self.sw_autoupd = ctk.CTkSwitch(up, text="Chercher une mise à jour au lancement (rien n'est installé sans ton clic)",
                                        font=F(13), progress_color=C["accent"], text_color=C["text2"],
                                        command=self._toggle_auto_update)
        self.sw_autoupd.pack(anchor="w", padx=22, pady=(8, 16))
        if self.settings.auto_check_updates:
            self.sw_autoupd.select()
        return f

    # ----- helpers calibrage -----
    def _save_keys(self):
        raw = self.keys_entry.get().strip().lower()
        self.settings.keys_enabled = raw
        self.settings.save()
        self._log(f"[CALIB] Touches : {raw}")

    def _capture_key_template(self):
        from tkinter import simpledialog
        frame = self._last_frame if self._last_frame is not None else self.engine.capture.grab()
        if frame is None:
            self._log("[WARN] Aucune image")
            return
        key = simpledialog.askstring("Touche", "Lettre ? (ex: d)", parent=self)
        if not key:
            return
        key = key.strip().lower()[:1]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        m = min(h, w) // 4
        crop = gray[h // 2 - m : h // 2 + m, w // 2 - m : w // 2 + m]
        reader = self.engine.key_reader  # même dossier que le moteur (réglages)
        path = reader.save_template(key, crop)
        self._log(f"[CALIB] Templates actifs : {', '.join(k.upper() for k in reader.loaded) or 'aucun'}")
        self._log(f"[CALIB] Template {key} → {path}")

    def _open_region_picker(self):
        from interface.region_picker import pick_region

        def done(left, top, size):
            for k, v in (("capture_left", left), ("capture_top", top), ("capture_size", size)):
                if k in getattr(self, "_entries", {}):
                    self._entries[k].delete(0, "end")
                    self._entries[k].insert(0, str(v))
            self.settings.capture_left = left
            self.settings.capture_top = top
            self.settings.capture_size = size
            self.settings.save()
            self.engine.capture.set_region(left, top, size)
            self.calib_zone_info.configure(
                text=f"Zone : X={left}  Y={top}  Taille={size}"
            )
            self._log(f"[CALIB] Zone : {left}, {top}, {size}")
            self._snap_calib_once()

        pick_region(
            self,
            initial=(self.settings.capture_left, self.settings.capture_top, self.settings.capture_size),
            on_done=done,
        )

    def _open_color_calib(self):
        from interface.color_calib import ColorCalibWindow
        self.engine.capture.set_region(
            self.settings.capture_left,
            self.settings.capture_top,
            self.settings.capture_size,
        )
        ColorCalibWindow(
            self, self.settings, self.engine.capture,
            on_save=lambda: self._log("[CALIB] HSV enregistré"),
            on_auto=self._auto_calibrate,
        )

    def _center_capture(self):
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            r.destroy()
        except Exception:
            sw, sh = 1920, 1080
        size = int(getattr(self.settings, "capture_size", 220) or 220)
        left = max(0, (sw - size) // 2)
        top = max(0, (sh - size) // 2)
        self.settings.capture_left = left
        self.settings.capture_top = top
        self.settings.capture_size = size
        self.settings.save()
        self.engine.capture.set_region(left, top, size)
        if hasattr(self, "calib_zone_info"):
            self.calib_zone_info.configure(
                text=f"Zone : X={left}  Y={top}  Taille={size}"
            )
        self._log(f"[CALIB] Centré → {left}, {top}, {size}")
        self._snap_calib_once()

    def _snap_calib_once(self):
        self.engine.capture.set_region(
            self.settings.capture_left,
            self.settings.capture_top,
            self.settings.capture_size,
        )
        frame = self.engine.capture.grab()
        if frame is None:
            self.calib_preview.configure(text="Capture impossible")
            return
        try:
            vis = frame.copy()
            h, w = vis.shape[:2]
            cv2.rectangle(vis, (2, 2), (w - 3, h - 3), (32, 212, 137), 2)
            cv2.line(vis, (w // 2, 0), (w // 2, h), (32, 212, 137), 1)
            cv2.line(vis, (0, h // 2), (w, h // 2), (32, 212, 137), 1)
            rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            max_w = 300
            if w > max_w:
                sc = max_w / w
                rgb = cv2.resize(rgb, (int(w * sc), int(h * sc)))
            photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._calib_photo = photo
            self.calib_preview.configure(image=photo, text="")
        except Exception as ex:
            self.calib_preview.configure(text=str(ex))

    # ------------------------------------------------------------ bot control
    def _toggle(self):
        if self.engine.running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.engine.running:
            return
        if self.ac.running:
            self._log("[WARN] Arrête l'auto-clic avant de lancer la pêche")
            self.lbl_key.configure(text="Arrête d'abord l'auto-clic")
            return
        self._save_settings(silent=True)
        self._stop = False
        self._session_start = time.time()
        self._elapsed = 0
        self._press_n = 0
        self.engine.start()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.big_btn.configure(image=self._big_img(True))
        self.status_dot.configure(fg_color=C["success"])
        self.status_side.configure(text="ACTIF", text_color=C["success"])
        self.header_status.configure(text="●  Bot actif")
        self.lbl_state.configure(text="En cours")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_bot(self):
        self._stop = True
        self.engine.stop()
        if self._session_start:
            self._elapsed = int(time.time() - self._session_start)
        self._session_start = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.big_btn.configure(image=self._big_img(False))
        self.status_dot.configure(fg_color=C["accent"])
        self.status_side.configure(text="INACTIF", text_color=C["text2"])
        self.header_status.configure(text="●  Système prêt")
        self.lbl_state.configure(text="Arrêté")
        self.lbl_key.configure(text="Prêt à pêcher")

    def _loop(self):
        while not self._stop and self.engine.running:
            self.engine.step()
            time.sleep(max(0.01, self.settings.poll_interval_ms / 1000))

    def _save_settings(self, silent: bool = False):
        for key, e in getattr(self, "_entries", {}).items():
            if not hasattr(self.settings, key):
                continue
            raw = e.get().strip()
            cur = getattr(self.settings, key)
            try:
                if isinstance(cur, bool):
                    setattr(self.settings, key, raw.lower() in ("1", "true", "oui", "yes"))
                elif isinstance(cur, float):
                    setattr(self.settings, key, float(raw))
                elif isinstance(cur, int):
                    setattr(self.settings, key, int(float(raw)))
                else:
                    setattr(self.settings, key, raw)
            except ValueError:
                pass
        if str(self.settings.target_color).lower() not in ("red", "blue"):
            self.settings.target_color = "red"
        self.settings.save()
        self.engine.capture.set_region(
            self.settings.capture_left,
            self.settings.capture_top,
            self.settings.capture_size,
        )
        self._sync_quick()
        if not silent:
            self._log("[PARAM] Paramètres enregistrés")

    # ------------------------------------------------------------ journal
    _TAG_RE = re.compile(r"^\[(\w+)\]\s*(.*)$")

    def _log(self, msg: str):
        m = self._TAG_RE.match(msg)
        tag, text = (m.group(1).upper(), m.group(2)) if m else ("INFO", msg)
        ts = time.strftime("%H:%M:%S")

        def append():
            self._history.append((ts, tag, text))
            del self._history[:-300]
            for box in self._log_boxes:
                self._write(box, ts, tag, text)
            if tag == "PRESS":
                self._press_n += 1

        self.after(0, append)

    def _clear_logs(self):
        for box in self._log_boxes:
            box.delete("1.0", "end")
        self._history.clear()

    def _on_state(self, state: State):
        def upd():
            name = STATE_FR.get(state.name, state.name)
            self.lbl_step.configure(text=name)
            if hasattr(self, "bot_detail"):
                self.bot_detail.configure(text=name)
        self.after(0, upd)

    def _on_frame(self, frame: np.ndarray):
        """Appelé par le moteur (autre thread) : image annotée de la pêche en cours."""
        self._last_frame = frame
        self._safe_after(lambda: self._show_debug(frame))

    def _show_debug(self, frame: Optional[np.ndarray], message: str = ""):
        """Affiche l'image debug (BGR) dans toutes les zones debug, à la taille disponible."""
        for lab, box in self._debug_targets:
            try:
                if frame is None:
                    lab.configure(image=None, text=message or "L'image du jeu apparaît ici")
                    lab._photo = None
                    continue
                bw, bh = max(60, box.winfo_width() - 8), max(60, box.winfo_height() - 8)
                h, w = frame.shape[:2]
                sc = min(bw / w, bh / h)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb = cv2.resize(rgb, (max(1, int(w * sc)), max(1, int(h * sc))),
                                 interpolation=cv2.INTER_LINEAR if sc > 1 else cv2.INTER_AREA)
                photo = ImageTk.PhotoImage(Image.fromarray(rgb))
                lab._photo = photo                     # garde une référence
                lab.configure(image=photo, text="")
            except Exception:
                pass

    def _safe_after(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass                                        # fenêtre déjà fermée

    def _preview_loop(self):
        """Quand le bot est arrêté : aperçu en direct (mêmes détecteurs, aucune touche envoyée)."""
        pv: Optional[Preview] = None
        missing = False
        while self._alive:
            busy = self.engine.running or self.ac.running or self._pv_pause
            if busy or self._page not in ("dashboard", "fishing"):
                time.sleep(0.25)
                continue
            try:
                if pv is None or settings_signature(self.settings) != pv.signature:
                    pv = Preview(self.settings)
                img = pv.frame()
                if img is None and not missing:
                    missing = True
                    self._safe_after(lambda: self._show_debug(
                        None, "Aperçu indisponible\n(capture d'écran non disponible ici)"))
                elif img is not None:
                    missing = False
                    self._safe_after(lambda i=img: self._show_debug(i))
            except Exception:
                pv = None
            time.sleep(0.25)

    # ------------------------------------------------------------ calibration automatique
    def _auto_calibrate(self, done=None):
        if self._cal_busy:
            return
        if self.engine.running or self.ac.running:
            self.lbl_cal.configure(text="Arrête d'abord la pêche / l'auto-clic.", text_color=C["warning"])
            return
        self._cal_busy = self._pv_pause = True
        self.btn_autocal.configure(state="disabled", text="Calibration en cours…")
        self.lbl_cal.configure(text="Je regarde le jeu pendant une seconde. Garde le cercle visible.",
                               text_color=C["text2"])
        st = self.settings

        def work():
            try:
                cap = ScreenCapture(st.capture_left, st.capture_top, st.capture_size)
                cal = AutoCalibrator(st, cap)
                res = cal.run(n_frames=24, interval=0.05)
            except Exception as exc:               # noqa: BLE001
                cal, res = None, None
                err = str(exc)
            self._safe_after(lambda: finish(cal, res, None if res else err))

        def finish(cal, res, err):
            self._cal_busy = self._pv_pause = False
            self.btn_autocal.configure(state="normal", text="Calibration automatique")
            if res is None:
                self.lbl_cal.configure(text=f"Erreur : {err}", text_color=C["danger"])
            elif not res.ok:
                self.lbl_cal.configure(text=res.message, text_color=C["warning"])
                self._log("[WARN] Calibration : " + res.message)
            else:
                cal.apply(res)
                self.settings.save()
                for k in res.updates:
                    if k in self._entries:
                        self._entries[k].delete(0, "end")
                        self._entries[k].insert(0, str(getattr(self.settings, k)))
                self._sync_quick()
                self.lbl_cal.configure(text=res.message + " Enregistré.", text_color=C["success"])
                self._log("[CALIB] " + res.message)
            if done:
                done()

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ auto-clic : raccourcis
    def _hotkey_map(self):
        s = self.settings
        return {"start": s.ac_hk_start, "stop": s.ac_hk_stop, "toggle": s.ac_hk_toggle}

    def apply_hotkeys(self):
        self.hotkeys.set_keys(self._hotkey_map())

    # ------------------------------------------------------------ fenêtre, raccourci bureau, fermeture
    def _set_window_icon(self):
        ico = os.path.join(RES_DIR, "assets", "auto_fisher.ico")
        if sys.platform == "win32" and os.path.isfile(ico):
            def apply():
                try:
                    self.iconbitmap(ico)
                except Exception:
                    pass
            self.after(300, apply)              # CustomTkinter remet son icône au démarrage

    def _first_run_shortcut(self):
        def work():
            ok, msg = create_desktop_shortcut()
            if ok:
                self.settings.desktop_shortcut_done = True
                self.settings.save()
            self._safe_after(lambda: self._log(("[INFO] " if ok else "[WARN] ") + msg))
        threading.Thread(target=work, daemon=True).start()

    def _make_shortcut(self):
        ok, msg = create_desktop_shortcut()
        if ok:
            self.settings.desktop_shortcut_done = True
            self.settings.save()
        self.lbl_shortcut.configure(text=msg, text_color=C["success"] if ok else C["warning"])
        self._log(("[INFO] " if ok else "[WARN] ") + msg)

    # ------------------------------------------------------------ mises à jour
    def _update_repo(self) -> str:
        return (self.settings.update_repo or UPDATE_REPO or "").strip()

    def check_updates(self, manual: bool = True):
        """Cherche une nouvelle version (réseau dans un thread). manual=False : silencieux sauf nouveauté."""
        if manual and hasattr(self, "lbl_update"):
            self.lbl_update.configure(text="Vérification…", text_color=C["text2"])
        repo = self._update_repo()

        def work():
            status, res = updater.check(repo, VERSION)
            self._safe_after(lambda: self._on_update_result(status, res, manual))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, status: str, res, manual: bool):
        txt, color = "", C["text2"]
        if status == "available":
            self._update_info = res
            txt, color = f"Version {res.version} disponible.", C["success"]
            self.btn_update.configure(text=f"⬇  Mise à jour {res.version} disponible")
            self.btn_update.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
            self._log(f"[INFO] Mise à jour disponible : {res.version}")
            if res.mandatory and updater.can_self_update():
                self.open_update_dialog()
            elif manual:
                self.open_update_dialog()
        elif status == "uptodate":
            txt, color = f"Tu as la dernière version ({VERSION}).", C["success"]
        else:
            txt, color = str(res), (C["warning"] if status == "error" else C["text2"])
        if hasattr(self, "lbl_update") and (manual or status == "available"):
            self.lbl_update.configure(text=txt, text_color=color)

    def open_update_dialog(self):
        info = self._update_info
        if info is None:
            return
        UpdateDialog(self, info, mandatory=bool(info.mandatory and updater.can_self_update()))

    def _toggle_auto_update(self):
        self._set_setting("auto_check_updates", bool(self.sw_autoupd.get()))

    def _on_close(self):
        self._alive = False
        self._stop = True
        try:
            self.ac.stop()
            self.engine.stop()
            self.hotkeys.close()
        finally:
            self.destroy()

    def _tick_stats(self):
        st = self.engine.stats
        ok, fail = st.stage_ok, st.stage_fail
        total = ok + fail
        rate = ok / total if total else 0.0
        self.lbl_fish.configure(text=str(st.fish_caught))
        self.lbl_ok.configure(text=str(ok))
        self.lbl_rate.configure(text=f"{int(100 * rate)}%")
        self.lbl_okfail.configure(text=f"{ok} / {fail}")
        self.bar_rate.set(rate)
        sec = int(time.time() - self._session_start) if self._session_start else self._elapsed
        self.lbl_time.configure(text=f"{sec // 60:02d}:{sec % 60:02d}")
        self.lbl_time_cap.configure(text="En cours" if self._session_start else "Arrêté")
        fph = st.fish_caught * 3600.0 / sec if sec >= 10 else 0.0
        self.lbl_fph.configure(text=f"{fph:.0f} / h")
        self.bar_fph.set(min(1.0, fph / 120.0))
        if self.engine.running:
            key = self.engine.current_key
            self.lbl_key.configure(text=f"Touche : {key.upper()}" if key else "Recherche du cercle…")
        self.after(300, self._tick_stats)


def run():
    app = App()
    app.mainloop()
