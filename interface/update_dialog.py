"""Fenêtre « Mise à jour disponible » : notes de version, progression, jamais d'installation sans clic."""
from __future__ import annotations

import sys
import threading

import customtkinter as ctk

from config import updater
from config.version import __version__
from interface.theme import COLORS, FONT

C = COLORS


def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, app, info: updater.UpdateInfo, mandatory: bool = False):
        super().__init__(app)
        self.app, self.info, self.mandatory = app, info, mandatory
        self._busy = False
        self.title("Mise à jour disponible")
        self.geometry("580x520")
        self.configure(fg_color=C["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        ctk.CTkLabel(self, text=f"Version {info.version} disponible", font=F(22, True),
                     text_color=C["text"]).pack(anchor="w", padx=22, pady=(18, 0))
        ctk.CTkLabel(self, text=f"Tu as la version {__version__}.", font=F(13),
                     text_color=C["text2"]).pack(anchor="w", padx=22)
        if mandatory:
            ctk.CTkLabel(self, text="Cette mise à jour est obligatoire pour continuer à utiliser le programme.",
                         font=F(13, True), text_color=C["warning"], wraplength=520, justify="left").pack(
                anchor="w", padx=22, pady=(8, 0))
        ctk.CTkLabel(self, text="Ce qui change :", font=F(14, True), text_color=C["text"]).pack(
            anchor="w", padx=22, pady=(12, 4))
        self.notes = ctk.CTkTextbox(self, height=190, corner_radius=10, fg_color=C["card"], text_color=C["text"],
                                    font=F(13), wrap="word", border_width=1, border_color=C["border"])
        self.notes.pack(fill="x", padx=22)
        notes = info.notes.replace(updater.MANDATORY_TAG, "").replace(updater.MANDATORY_TAG.lower(), "").strip()
        self.notes.insert("1.0", notes or "Pas de détails fournis pour cette version.")
        self.notes.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(self, height=10, progress_color=C["accent"], fg_color=C["card2"])
        self.bar.set(0)
        self.status = ctk.CTkLabel(self, text="", font=F(13), text_color=C["text2"], wraplength=520, justify="left")
        self.status.pack(anchor="w", padx=22, pady=(10, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=14)
        self.btn_go = ctk.CTkButton(row, text="Mettre à jour maintenant", height=52, corner_radius=10,
                                    font=F(16, True), fg_color="#17b45a", hover_color="#139a4c", command=self.go)
        self.btn_go.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_later = ctk.CTkButton(
            row, text="Quitter le programme" if mandatory else "Plus tard", height=52, corner_radius=10,
            font=F(15), fg_color=C["blue_dim"], hover_color="#12508f",
            command=self.app._on_close if mandatory else self.destroy)
        self.btn_later.pack(side="left", fill="x", expand=True, padx=(6, 0))
        if not updater.can_self_update():
            self.status.configure(text="La mise à jour automatique marche dans la version AUTO_FISHER.exe. "
                                       "Ici (lancé depuis le code), télécharge la nouvelle version à la main.",
                                  text_color=C["warning"])
            self.btn_go.configure(state="disabled")
        self.protocol("WM_DELETE_WINDOW", (lambda: None) if mandatory else self.destroy)

    def go(self):
        if self._busy:
            return
        if self.app.engine.running or self.app.ac.running:
            self.status.configure(text="Arrête d'abord la pêche et l'auto-clic, puis relance la mise à jour.",
                                  text_color=C["warning"])
            return
        self._busy = True
        self.btn_go.configure(state="disabled", text="Téléchargement…")
        self.btn_later.configure(state="disabled")
        self.bar.pack(fill="x", padx=22, before=self.status)
        self.status.configure(text="Téléchargement en cours… ne ferme pas le programme.", text_color=C["text2"])
        exe = sys.executable
        threading.Thread(target=self._work, args=(exe,), daemon=True).start()

    def _work(self, exe: str):
        try:
            new = updater.download(self.info, exe + ".new",
                                   progress=lambda p: self.app._safe_after(lambda: self.bar.set(p)))
            updater.install(new, exe)
        except updater.UpdateError as e:
            msg = str(e)                                   # (e n'existe plus après le bloc : on garde le texte)
            self.app._safe_after(lambda m=msg: self._fail(m))
            return
        except Exception as e:                      # noqa: BLE001
            msg = f"Erreur inattendue : {e}"
            self.app._safe_after(lambda m=msg: self._fail(m))
            return
        self.app._safe_after(lambda: self._done(exe))

    def _fail(self, msg: str):
        self._busy = False
        self.status.configure(text=msg, text_color=C["danger"])
        self.btn_go.configure(state="normal", text="Réessayer")
        if not self.mandatory:
            self.btn_later.configure(state="normal")
        self.app._log("[WARN] Mise à jour : " + msg)

    def _done(self, exe: str):
        self.status.configure(text="Mise à jour installée : redémarrage…", text_color=C["success"])
        self.bar.set(1)
        self.app._log(f"[INFO] Mise à jour {self.info.version} installée, redémarrage")
        try:
            updater.relaunch(exe)
        finally:
            self.after(600, self.app._on_close)
