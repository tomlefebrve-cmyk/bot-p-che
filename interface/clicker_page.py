"""Page « Auto-clic » : réglages, raccourcis modifiables, choix d'un point à l'écran."""
from __future__ import annotations

import sys
import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from bot.autoclicker import VK_DEFAULTS, relaunch_as_admin, scan_pressed, vk_name
from interface.icons import icon
from interface.theme import COLORS, FONT

C = COLORS
BUTTON_LABELS = {"Gauche": "left", "Droit": "right"}
DEFAULTS = dict(ac_hours=0, ac_minutes=0, ac_seconds=1, ac_ms=0, ac_infinite=True, ac_count=10,
                ac_button="left", ac_fixed=False, ac_x=0, ac_y=0,
                ac_cycle=False, ac_cycle_run=10, ac_cycle_pause=10)
START_DELAY = 3.0       # compte à rebours quand on démarre avec le bouton (placer la souris)


def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


class PointPicker(tk.Toplevel):
    """Voile plein écran : un clic = un point (X, Y). Échap annule."""

    def __init__(self, master, on_pick, on_cancel=None):
        super().__init__(master)
        self.on_pick, self.on_cancel = on_pick, on_cancel
        x, y, w, h = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        if sys.platform == "win32":
            import ctypes
            gm = ctypes.windll.user32.GetSystemMetrics
            x, y, w, h = gm(76), gm(77), gm(78), gm(79)           # tous les écrans
        self.overrideredirect(True)
        self.geometry(f"{w}x{h}{x:+d}{y:+d}")
        self.configure(bg="black", cursor="crosshair")
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.30)
        except tk.TclError:
            pass
        tk.Label(self, text="Clique à l'endroit où l'auto-clic doit cliquer\n(Échap pour annuler)",
                 bg="black", fg="white", font=(FONT, 22)).place(relx=0.5, rely=0.45, anchor="center")
        self.bind("<Button-1>", self._click)
        self.bind("<Escape>", self._cancel)
        self.after(50, self.focus_force)

    def _click(self, e):
        x, y = e.x_root, e.y_root
        self.destroy()
        self.on_pick(x, y)

    def _cancel(self, _e=None):
        self.destroy()
        if self.on_cancel:
            self.on_cancel()


class ShortcutsDialog(ctk.CTkToplevel):
    """Changer les raccourcis Démarrer / Arrêter / Basculer."""

    ROWS = (("start", "Démarrer"), ("stop", "Arrêter"), ("toggle", "Basculer"))

    def __init__(self, page):
        super().__init__(page)
        self.page, self.app = page, page.app
        self.title("Raccourcis clavier")
        self.geometry("520x380")
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self._cap: Optional[str] = None
        self._t0 = 0.0
        ctk.CTkLabel(self, text="Raccourcis clavier", font=F(22, True), text_color=C["text"]).pack(
            anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text="Ils marchent même quand le jeu est au premier plan.",
                     font=F(13), text_color=C["text2"]).pack(anchor="w", padx=22, pady=(0, 12))
        self._labels = {}
        for name, title in self.ROWS:
            row = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=10, border_width=1,
                               border_color=C["border"])
            row.pack(fill="x", padx=22, pady=5)
            ctk.CTkLabel(row, text=title, font=F(16), text_color=C["text"], width=120,
                         anchor="w").pack(side="left", padx=16, pady=14)
            lab = ctk.CTkLabel(row, text="", font=F(16, True), text_color=C["blue"], width=170, anchor="w")
            lab.pack(side="left")
            self._labels[name] = lab
            ctk.CTkButton(row, text="Modifier", width=100, height=36, corner_radius=8, font=F(14),
                          fg_color=C["blue_dim"], hover_color="#12508f",
                          command=lambda n=name: self._begin(n)).pack(side="right", padx=14)
        self.msg = ctk.CTkLabel(self, text="", font=F(13), text_color=C["warning"])
        self.msg.pack(pady=(6, 0))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=14)
        ctk.CTkButton(bar, text="Valeurs par défaut", height=40, corner_radius=8, font=F(14),
                      fg_color=C["blue_dim"], hover_color="#12508f", command=self._reset).pack(side="left")
        ctk.CTkButton(bar, text="Fermer", height=40, width=110, corner_radius=8, font=F(14, True),
                      fg_color="#17b45a", hover_color="#139a4c", command=self._close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh()

    def _refresh(self):
        for name, _ in self.ROWS:
            self._labels[name].configure(text=vk_name(getattr(self.app.settings, f"ac_hk_{name}")))

    def _begin(self, name):
        self._cap, self._t0 = name, time.time()
        self.app.hotkeys.paused = True
        self._labels[name].configure(text="Appuie sur une touche…", text_color=C["warning"])
        self.msg.configure(text="Échap pour annuler")
        self.after(150, self._poll)

    def _poll(self):
        if self._cap is None:
            return
        b = self.app.backend
        if b.is_down(0x1B) or time.time() - self._t0 > 10:
            return self._end()
        vk = scan_pressed(b)
        if vk is None:
            return self.after(30, self._poll)
        used = {n: getattr(self.app.settings, f"ac_hk_{n}") for n, _ in self.ROWS if n != self._cap}
        if vk in used.values():
            self.msg.configure(text=f"« {vk_name(vk)} » est déjà utilisée par un autre raccourci.")
        else:
            setattr(self.app.settings, f"ac_hk_{self._cap}", vk)
            self.app.settings.save()
            self.app.apply_hotkeys()
            self.msg.configure(text="")
        self._end()

    def _end(self):
        self._cap = None
        self.app.hotkeys.paused = False
        for n, _ in self.ROWS:
            self._labels[n].configure(text_color=C["blue"])
        self._refresh()
        self.page.refresh_labels()

    def _reset(self):
        for n, vk in VK_DEFAULTS.items():
            setattr(self.app.settings, f"ac_hk_{n}", vk)
        self.app.settings.save()
        self.app.apply_hotkeys()
        self._end()

    def _close(self):
        self.app.hotkeys.paused = False
        self.destroy()


class ClickerPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app, self.s, self.ac = app, app.settings, app.ac
        self.grid_columnconfigure(0, weight=1)
        self._dialog: Optional[ShortcutsDialog] = None
        self._build()
        self.refresh_labels()
        self.after(200, self._tick)

    # ---------------------------------------------------------------- UI
    def _card(self, title: str, ic: str):
        card = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=12, border_width=1,
                            border_color=C["border"])
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(14, 8))
        ctk.CTkLabel(head, text="", image=icon(ic, C["blue"], 26)).pack(side="left")
        ctk.CTkLabel(head, text=title, font=F(17, True), text_color=C["text"]).pack(side="left", padx=12)
        ctk.CTkFrame(card, height=1, fg_color=C["border"]).pack(fill="x", padx=20)
        return card

    def _entry(self, parent, value, width=92):
        e = ctk.CTkEntry(parent, width=width, height=40, corner_radius=8, font=F(16), justify="center",
                         fg_color=C["input"], border_color=C["border"])
        e.insert(0, str(value))
        return e

    def _big(self, parent, text, cmd, kind="blue", width=250, **kw):
        colors = {"green": ("#17b45a", "#139a4c"), "blue": (C["blue_dim"], "#12508f"),
                  "red": ("#a8323e", "#8c2832")}[kind]
        return ctk.CTkButton(parent, text=text, command=cmd, height=52, width=width, corner_radius=10,
                             font=F(16, True), fg_color=colors[0], hover_color=colors[1],
                             text_color="#ffffff", border_width=1, border_color=C["border"], **kw)

    def _build(self):
        s = self.s
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        box = ctk.CTkFrame(top, fg_color="transparent")
        box.pack(side="left")
        ctk.CTkLabel(box, text="Auto-clic", font=F(30, True), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(box, text="Clique tout seul à la vitesse que tu veux. Indépendant de la pêche.",
                     font=F(14), text_color=C["blue"]).pack(anchor="w")
        self.pill = ctk.CTkLabel(top, text="●  Arrêté", font=F(16, True), fg_color=C["card2"],
                                 text_color=C["text2"], corner_radius=24, width=260, height=48)
        self.pill.pack(side="right")

        # --- intervalle
        c = self._card("Intervalle entre les clics", "clock")
        c.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=16)
        self.e_int = {}
        for key, label in (("ac_hours", "heures"), ("ac_minutes", "minutes"),
                           ("ac_seconds", "secondes"), ("ac_ms", "millisecondes")):
            e = self._entry(row, getattr(s, key))
            e.pack(side="left")
            ctk.CTkLabel(row, text=label, font=F(14), text_color=C["text2"]).pack(side="left", padx=(8, 22))
            self.e_int[key] = e

        # --- répéter + options
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        mid.grid_columnconfigure((0, 1), weight=1, uniform="m")
        rep = self._card("Répéter", "hook")
        rep.grid(in_=mid, row=0, column=0, sticky="nsew", padx=(0, 6))
        self.var_inf = tk.BooleanVar(value=bool(s.ac_infinite))
        self.r1 = ctk.CTkRadioButton(rep, text="Infini (jusqu'à l'arrêt)", variable=self.var_inf, value=True,
                                     font=F(15), fg_color=C["accent"], text_color=C["text"])
        self.r1.pack(anchor="w", padx=22, pady=(16, 8))
        line = ctk.CTkFrame(rep, fg_color="transparent")
        line.pack(anchor="w", padx=22, pady=(0, 16))
        self.r2 = ctk.CTkRadioButton(line, text="", variable=self.var_inf, value=False, width=26,
                                     fg_color=C["accent"])
        self.r2.pack(side="left")
        self.e_count = self._entry(line, s.ac_count, 90)
        self.e_count.pack(side="left")
        ctk.CTkLabel(line, text="clics", font=F(15), text_color=C["text2"]).pack(side="left", padx=8)

        opt = self._card("Options", "gear")
        opt.grid(in_=mid, row=0, column=1, sticky="nsew", padx=(6, 0))
        for i, (label, widget) in enumerate((("Bouton de la souris", "btn"), ("Type de clic", "type"))):
            r = ctk.CTkFrame(opt, fg_color="transparent")
            r.pack(fill="x", padx=22, pady=(14 if i == 0 else 4, 10 if i else 4))
            ctk.CTkLabel(r, text=label, font=F(15), text_color=C["text"]).pack(side="left")
            if widget == "btn":
                self.menu_btn = self._menu(r, list(BUTTON_LABELS))
                self.menu_btn.pack(side="right")
            else:
                m = self._menu(r, ["Simple"])
                m.configure(state="disabled")
                m.pack(side="right")

        # --- emplacement
        loc = self._card("Emplacement du clic", "cursor")
        loc.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.var_fixed = tk.BooleanVar(value=bool(s.ac_fixed))
        ctk.CTkRadioButton(loc, text="Position actuelle du curseur", variable=self.var_fixed, value=False,
                           font=F(15), fg_color=C["accent"], text_color=C["text"]).pack(anchor="w", padx=22, pady=(16, 8))
        row = ctk.CTkFrame(loc, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 16))
        ctk.CTkRadioButton(row, text="", variable=self.var_fixed, value=True, width=26,
                           fg_color=C["accent"]).pack(side="left")
        ctk.CTkLabel(row, text="X", font=F(15), text_color=C["text"]).pack(side="left", padx=(0, 6))
        self.e_x = self._entry(row, s.ac_x, 100)
        self.e_x.pack(side="left")
        ctk.CTkLabel(row, text="Y", font=F(15), text_color=C["text"]).pack(side="left", padx=(18, 6))
        self.e_y = self._entry(row, s.ac_y, 100)
        self.e_y.pack(side="left")
        self._big(row, "Choisir l'emplacement", self.choose_point, "blue", width=230).pack(side="left", padx=20)

        # --- pause automatique
        cyc = self._card("Pause automatique", "clock")
        cyc.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        rowc = ctk.CTkFrame(cyc, fg_color="transparent")
        rowc.pack(fill="x", padx=22, pady=16)
        self.var_cycle = tk.BooleanVar(value=bool(s.ac_cycle))
        ctk.CTkSwitch(rowc, text="Activer", variable=self.var_cycle, onvalue=True, offvalue=False,
                      font=F(15, True), progress_color=C["accent"], text_color=C["text"]).pack(side="left", padx=(0, 22))
        ctk.CTkLabel(rowc, text="Clique pendant", font=F(15), text_color=C["text"]).pack(side="left", padx=(0, 8))
        self.e_crun = self._entry(rowc, s.ac_cycle_run, 80)
        self.e_crun.pack(side="left")
        ctk.CTkLabel(rowc, text="s, puis pause de", font=F(15), text_color=C["text"]).pack(side="left", padx=8)
        self.e_cpause = self._entry(rowc, s.ac_cycle_pause, 80)
        self.e_cpause.pack(side="left")
        ctk.CTkLabel(rowc, text="s, et ça recommence.", font=F(15), text_color=C["text"]).pack(side="left", padx=8)

        # --- boutons
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        bar.grid_columnconfigure((0, 1, 2), weight=1, uniform="b")
        self.b_start = self._big(bar, "", lambda: self.start(True), "green", width=10)
        self.b_stop = self._big(bar, "", self.stop, "red", width=10)
        self.b_toggle = self._big(bar, "", lambda: self.toggle(True), "blue", width=10)
        for i, b in enumerate((self.b_start, self.b_stop, self.b_toggle)):
            b.grid(row=0, column=i, sticky="ew", padx=4, pady=4)
        for i, (t, cmd) in enumerate((("Enregistrer les paramètres", self.save),
                                      ("Réinitialiser les options", self.reset),
                                      ("Raccourcis", self.open_shortcuts))):
            self._big(bar, t, cmd, "blue", width=10).grid(row=1, column=i, sticky="ew", padx=4, pady=4)

        self.note = ctk.CTkLabel(self, text="", font=F(13), text_color=C["warning"], wraplength=900,
                                 justify="left", anchor="w")
        self.note.grid(row=6, column=0, sticky="w", pady=(8, 0))
        ctk.CTkLabel(self, text=(f"Avec le bouton « Démarrer », tu as {int(START_DELAY)} secondes pour placer la "
                                 "souris. Avec le raccourci clavier, ça démarre tout de suite."),
                     font=F(13), text_color=C["text2"], wraplength=900, justify="left", anchor="w"
                     ).grid(row=7, column=0, sticky="w", pady=(4, 0))
        self.admin_row = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=12, border_width=1,
                                      border_color=C["border"])
        self.admin_row.grid(row=8, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(self.admin_row, justify="left", anchor="w", font=F(13), text_color=C["text2"], wraplength=640,
                     text=("Ça ne clique pas dans un jeu ou un programme ? Il est peut-être lancé en administrateur : "
                           "Windows interdit alors les clics venant d'un programme normal. Relance AUTO FISHER "
                           "en administrateur.")).pack(side="left", padx=18, pady=14)
        self.btn_admin = self._big(self.admin_row, "Relancer en administrateur", self.run_as_admin, "blue", width=250)
        self.btn_admin.pack(side="right", padx=14, pady=12)
        self.menu_btn.set(next(k for k, v in BUTTON_LABELS.items() if v == s.ac_button))
        if not self.app.backend.available or self.app.backend.is_admin():
            self.admin_row.grid_remove()                  # déjà administrateur : inutile
        if not self.app.backend.available:
            self.note.configure(text="L'auto-clic ne fonctionne que sous Windows : les boutons sont "
                                     "affichés mais aucun clic n'est envoyé ici.")

    def _menu(self, parent, values):
        return ctk.CTkOptionMenu(parent, values=values, width=150, height=40, corner_radius=8, font=F(15),
                                 fg_color=C["input"], button_color=C["blue_dim"], button_hover_color="#12508f",
                                 dropdown_fg_color=C["card"], dropdown_hover_color=C["card2"],
                                 text_color=C["text"])

    # ---------------------------------------------------------------- réglages
    @staticmethod
    def _num(entry, lo=0, hi=10 ** 9) -> int:
        try:
            v = int(float(entry.get().strip().replace(",", ".")))
        except ValueError:
            v = lo
        v = max(lo, min(hi, v))
        entry.delete(0, "end")
        entry.insert(0, str(v))
        return v

    def read(self) -> bool:
        """Lit l'écran → réglages. Corrige les valeurs bizarres. False si inutilisable."""
        s = self.s
        s.ac_hours = self._num(self.e_int["ac_hours"], 0, 999)
        s.ac_minutes = self._num(self.e_int["ac_minutes"], 0, 59 * 100)
        s.ac_seconds = self._num(self.e_int["ac_seconds"], 0, 59 * 100)
        s.ac_ms = self._num(self.e_int["ac_ms"], 0, 999 * 100)
        s.ac_infinite = bool(self.var_inf.get())
        s.ac_count = self._num(self.e_count, 1, 10 ** 7)
        s.ac_button = BUTTON_LABELS.get(self.menu_btn.get(), "left")
        s.ac_fixed = bool(self.var_fixed.get())
        s.ac_x = self._num(self.e_x, -20000, 20000)
        s.ac_y = self._num(self.e_y, -20000, 20000)
        s.ac_cycle = bool(self.var_cycle.get())
        s.ac_cycle_run = self._num(self.e_crun, 1, 86400)
        s.ac_cycle_pause = self._num(self.e_cpause, 1, 86400)
        total = ((s.ac_hours * 60 + s.ac_minutes) * 60 + s.ac_seconds) * 1000 + s.ac_ms
        self.note.configure(text="")
        if total < 1:
            total = 1
            self.note.configure(text="Intervalle trop court : minimum 1 milliseconde.")
        self.ac.configure(total, s.ac_button, 0 if s.ac_infinite else s.ac_count,
                          (s.ac_x, s.ac_y) if s.ac_fixed else None,
                          s.ac_cycle_run if s.ac_cycle else 0, s.ac_cycle_pause if s.ac_cycle else 0)
        return True

    def save(self):
        self.read()
        self.s.save()
        self.app._log("[PARAM] Réglages de l'auto-clic enregistrés")
        self.note.configure(text="Paramètres enregistrés.", text_color=C["success"])
        self.after(2500, lambda: self.note.configure(text="", text_color=C["warning"]))

    def reset(self):
        if self.ac.running:
            self.ac.stop()
        for k, v in DEFAULTS.items():
            setattr(self.s, k, v)
        for key, e in self.e_int.items():
            e.delete(0, "end"); e.insert(0, str(getattr(self.s, key)))
        self.var_inf.set(True); self.var_fixed.set(False); self.var_cycle.set(False)
        for e, v in ((self.e_crun, 10), (self.e_cpause, 10)):
            e.delete(0, "end"); e.insert(0, str(v))
        for e, v in ((self.e_count, self.s.ac_count), (self.e_x, 0), (self.e_y, 0)):
            e.delete(0, "end"); e.insert(0, str(v))
        self.menu_btn.set("Gauche")
        self.s.save()
        self.app._log("[PARAM] Auto-clic : options réinitialisées")

    # ---------------------------------------------------------------- actions
    def start(self, from_button: bool = False):
        if self.app.engine.running:
            self.note.configure(text="La pêche est en cours : arrête-la avant de lancer l'auto-clic.",
                                text_color=C["warning"])
            self.app._log("[WARN] Auto-clic refusé : la pêche est en cours")
            return
        self.read()
        self.s.save()
        s = self.s
        if self.ac.start(START_DELAY if from_button else 0.0):
            where = f"X={s.ac_x} Y={s.ac_y}" if s.ac_fixed else "position du curseur"
            self.app._log(f"[INFO] Auto-clic démarré · {self.ac.interval_ms} ms · "
                          f"{'gauche' if s.ac_button == 'left' else 'droit'} · {where}")
            delay_ms = int((START_DELAY if from_button else 0.0) * 1000) + 400
            self.after(delay_ms, self._check_target)

    def _check_target(self):
        """Le programme visé tourne-t-il en administrateur ? Alors Windows bloque nos clics."""
        if not self.ac.running:
            return
        s = self.s
        blocked = self.app.backend.target_blocked((s.ac_x, s.ac_y) if s.ac_fixed else None)
        if blocked:
            msg = ("La fenêtre visée est lancée en administrateur : Windows bloque l'auto-clic. "
                   "Clique sur « Relancer en administrateur » (en bas de cette page).")
            self.note.configure(text=msg, text_color=C["warning"])
            self.app._log("[WARN] " + msg)

    def run_as_admin(self):
        if relaunch_as_admin():
            self.app._on_close()                         # l'instance administrateur prend le relais
        else:
            self.note.configure(text="Relance annulée (ou impossible). Ferme puis rouvre AUTO FISHER "
                                     "avec un clic droit > Exécuter en tant qu'administrateur.",
                                text_color=C["warning"])

    def stop(self):
        was = self.ac.running
        self.ac.stop()
        if was:
            self.refresh()

    def toggle(self, from_button: bool = False):
        if self.ac.running:
            self.stop()
        else:
            self.start(from_button)

    def on_hotkey(self, name: str):
        if name == "start":
            self.start(False)
        elif name == "stop":
            self.stop()
        else:
            self.toggle(False)

    def choose_point(self):
        was_running = self.ac.running
        if was_running:
            self.ac.stop()
        self.app.iconify()

        def done(x, y):
            self.app.deiconify()
            self.e_x.delete(0, "end"); self.e_x.insert(0, str(x))
            self.e_y.delete(0, "end"); self.e_y.insert(0, str(y))
            self.var_fixed.set(True)

        def cancel():
            self.app.deiconify()

        self.after(350, lambda: PointPicker(self.app, done, cancel))

    def open_shortcuts(self):
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.focus()
            return
        self._dialog = ShortcutsDialog(self)

    # ---------------------------------------------------------------- affichage
    def refresh_labels(self):
        k = lambda n: vk_name(getattr(self.s, f"ac_hk_{n}"))
        self.b_start.configure(text=f"Démarrer ({k('start')})")
        self.b_stop.configure(text=f"Arrêter ({k('stop')})")
        self.b_toggle.configure(text=f"Basculer ({k('toggle')})")

    def refresh(self):
        st = self.ac.state
        if st == "countdown":
            self.pill.configure(text=f"●  Démarre dans {self.ac.remaining:.0f} s…",
                                fg_color="#3a2f0b", text_color=C["warning"])
        elif st == "paused":
            self.pill.configure(text=f"●  En pause · reprise dans {self.ac.remaining:.0f} s",
                                fg_color="#3a2f0b", text_color=C["warning"])
        elif st == "running":
            self.pill.configure(text=f"●  En cours · {self.ac.count} clics",
                                fg_color=C["accent_dim"], text_color=C["success"])
        else:
            tail = f" · {self.ac.count} clics" if self.ac.count else ""
            self.pill.configure(text=f"●  Arrêté{tail}", fg_color=C["card2"], text_color=C["text2"])
        self.b_start.configure(state="disabled" if self.ac.running else "normal")
        self.b_stop.configure(state="normal" if self.ac.running else "disabled")

    def _tick(self):
        try:
            self.refresh()
        finally:
            self.after(150, self._tick)
