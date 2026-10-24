"""Test du clavier : le logiciel tape Z, Q, S, D dans une zone de saisie et compare."""
from __future__ import annotations

import customtkinter as ctk

from interface.theme import COLORS, FONT

C = COLORS
EXPECTED = "zqsd"


def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


class KeyTestDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Test du clavier")
        self.geometry("560x430")
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        ctk.CTkLabel(self, text="Test du clavier", font=F(22, True), text_color=C["text"]).pack(
            anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, justify="left", anchor="w", font=F(13), text_color=C["text2"], wraplength=510,
                     text=("Le logiciel va taper Z, Q, S, D dans la case ci-dessous, comme il le fera dans le jeu. "
                           "Si tu vois « zqsd », tout est bon.")).pack(anchor="w", padx=22)
        api = getattr(app.engine.keyboard, "api", None)
        layout = api.layout_name() if api is not None and getattr(api, "available", False) else "inconnue"
        self.lbl_layout = ctk.CTkLabel(self, text=f"Disposition du clavier détectée : {layout}",
                                       font=F(13), text_color=C["blue"])
        self.lbl_layout.pack(anchor="w", padx=22, pady=(10, 6))
        self.entry = ctk.CTkEntry(self, height=56, font=F(26, True), justify="center",
                                  fg_color=C["input"], border_color=C["border"])
        self.entry.pack(fill="x", padx=22, pady=6)
        self.result = ctk.CTkLabel(self, text="", font=F(15, True), wraplength=510, justify="left",
                                   anchor="w", text_color=C["text2"])
        self.result.pack(anchor="w", padx=22, pady=10)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=22, pady=(4, 14))
        self.btn = ctk.CTkButton(bar, text="Lancer le test", height=50, corner_radius=10, font=F(16, True),
                                 fg_color="#17b45a", hover_color="#139a4c", command=self.run)
        self.btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(bar, text="Essayer l'autre mode d'envoi", height=50, corner_radius=10, font=F(14),
                      fg_color=C["blue_dim"], hover_color="#12508f", command=self.other_mode).pack(
            side="left", fill="x", expand=True, padx=(6, 0))
        self._mode_label()

    def _mode_label(self):
        mode = getattr(self.app.settings, "key_send_mode", "layout")
        txt = "selon ton clavier (recommandé)" if mode == "layout" else "ancien mode (QWERTY)"
        self.title(f"Test du clavier — envoi : {txt}")

    def run(self):
        self.btn.configure(state="disabled")
        self.entry.delete(0, "end")
        self.result.configure(text="Ne touche à rien…", text_color=C["text2"])
        kb = self.app.engine.keyboard
        kb.mode = self.app.settings.key_send_mode
        self.lift()
        self.focus_force()
        self.entry.focus_force()
        self.after(1200, lambda: self._send(0))

    def _send(self, i: int):
        if i >= len(EXPECTED):
            return self.after(500, self._verdict)
        self.app.engine.keyboard.press(EXPECTED[i])
        self.after(200, lambda: self._send(i + 1))

    def _verdict(self):
        got = self.entry.get().strip().lower()
        self.btn.configure(state="normal")
        if got == EXPECTED:
            self.result.configure(text="Parfait : Z, Q, S, D sont bien envoyées.", text_color=C["success"])
            self.app._log("[INFO] Test du clavier réussi (zqsd)")
        elif not got:
            self.result.configure(
                text=("Rien n'a été tapé. Clique dans la case puis relance le test. Si ça ne marche toujours pas, "
                      "lance le programme en administrateur (clic droit > Exécuter en tant qu'administrateur)."),
                text_color=C["warning"])
        else:
            self.result.configure(
                text=(f"Problème : le logiciel a tapé « {got} » au lieu de « zqsd ». "
                      "Clique sur « Essayer l'autre mode d'envoi »."), text_color=C["warning"])
            self.app._log(f"[WARN] Test du clavier : reçu « {got} » au lieu de « zqsd »")

    def other_mode(self):
        new = "classic" if self.app.settings.key_send_mode == "layout" else "layout"
        self.app._set_setting("key_send_mode", new)
        self._mode_label()
        self.run()
