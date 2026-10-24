"""
ui/app.py — FishBot interface (Dashboard maquette)
Backend StageManager inchangé.
"""
from __future__ import annotations

import os
import time
import queue
import threading
from typing import Optional, Dict

import customtkinter as ctk
from tkinter import messagebox, Canvas
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np

from config import Config
from core.stage_manager import StageManager, State
from detection.inventory_detector import InventoryDetector
from ui.theme import COLORS, RARITY_FR, RARITY_COLORS, VERSION, APP_NAME
from ui import sounds

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

UI_FPS = 24
UI_MIN_INTERVAL = 1.0 / UI_FPS
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "assets", "icon_fishing.jpg")


class FastPreview:
    def __init__(self, max_w=360, max_h=240):
        self.max_w = max_w
        self.max_h = max_h

    def process(self, frame, circle, red_line, key_result, timing_pred, target_angle):
        h, w = frame.shape[:2]
        scale = min(self.max_w / w, self.max_h / h, 1.0)
        small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
        if circle is not None:
            cx = int(circle.x * scale)
            cy = int(circle.y * scale)
            r = max(2, int(circle.r * scale))
            cv2.circle(small, (cx, cy), r, (59, 130, 246), 2)
            cv2.circle(small, (cx, cy), 2, (34, 197, 94), -1)
        if red_line is not None and hasattr(red_line, "angle_deg") and circle is not None:
            ang = float(red_line.angle_deg)
            rad = np.deg2rad(ang)
            x2 = int(cx + r * np.cos(rad))
            y2 = int(cy - r * np.sin(rad))
            cv2.line(small, (cx, cy), (x2, y2), (239, 68, 68), 2)
        if key_result is not None:
            cv2.putText(
                small, key_result.key.upper(), (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 80), 2, cv2.LINE_AA,
            )
        return Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))


def _draw_ring(size: int, key: str = "—", progress: float = 0.0) -> Image.Image:
    """Cercle de détection style maquette (anneau bleu + trait rouge)."""
    img = Image.new("RGB", (size, size), (11, 18, 32))
    d = ImageDraw.Draw(img)
    m = size // 10
    d.ellipse([m, m, size - m, size - m], fill=(17, 26, 43))
    width = max(6, size // 18)
    d.ellipse([m, m, size - m, size - m], outline=(59, 130, 246), width=width)
    if progress > 0.02:
        extent = int(360 * min(1.0, progress))
        d.arc([m, m, size - m, size - m], start=-90, end=-90 + extent, fill=(34, 197, 94), width=width)
    cy = size // 2
    d.line([(size // 2, cy), (size - m - 4, cy)], fill=(239, 68, 68), width=3)
    r = size // 8
    d.ellipse([size // 2 - r, size // 2 - r, size // 2 + r, size // 2 + r], fill=(15, 23, 42))
    text = (key or "-")[:2]
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", max(12, size // 7))
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) // 2, (size - th) // 2 - 2), text, fill=(232, 238, 248), font=font)
    except Exception:
        d.text((size // 2 - 6, size // 2 - 8), text, fill=(232, 238, 248))
    return img


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} · {VERSION}")
        self.geometry("1200x780")
        self.minsize(1020, 660)
        self.configure(fg_color=COLORS["bg"])

        try:
            if os.path.exists(ICON):
                self._icon = ImageTk.PhotoImage(Image.open(ICON).resize((32, 32)))
                self.iconphoto(True, self._icon)
        except Exception:
            pass

        self.cfg = Config.load()
        sounds.configure(
            getattr(self.cfg, "sounds_dir", os.path.join(ROOT, "assets", "sounds")),
            getattr(self.cfg, "sounds_enabled", True),
        )

        self.manager = StageManager(
            self.cfg,
            on_log=self._on_log,
            on_state_change=self._on_state,
            on_debug_frame=self._on_debug,
            on_rarity=self._on_rarity_cb,
            on_circle=lambda: sounds.play("circle"),
            on_success=lambda: sounds.play("success"),
        )
        self.inventory = InventoryDetector(self.cfg)
        self._preview = FastPreview()

        self.is_running = False
        self.is_paused = False
        self._thread = None
        self._stop = False
        self._session_start = None
        self._pending = None
        self._render_sched = False
        self._last_render = 0.0
        self._photo = None
        self._ring_photo = None
        self._log_q: queue.Queue = queue.Queue(maxsize=2000)
        self._hotkey_listener = None
        self._nav = "dashboard"
        self._pages: Dict[str, ctk.CTkFrame] = {}
        self._nav_btns: Dict[str, ctk.CTkButton] = {}
        self._ui_rarity = {k: 0 for k in RARITY_COLORS}
        self._current_key = "—"
        self._captures = 0
        self._success_rate = 0.0

        self._build()
        self._start_hotkeys()
        self.after(40, self._drain_logs)
        self.after(400, self._tick)
        self.after(500, self._stats)
        self.after(1000, self._poll_inventory)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ═══════════════════ BUILD ═══════════════════
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        side = ctk.CTkFrame(self, width=200, fg_color=COLORS["sidebar"], corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)

        # Logo
        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(22, 24))
        ctk.CTkLabel(
            logo, text="🎃  FishBot", text_color=COLORS["accent"],
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo, text="FiveM · Pêche", text_color=COLORS["text_faint"],
            font=ctk.CTkFont(size=11), anchor="w",
        ).pack(anchor="w", padx=(22, 0))

        nav_spec = [
            ("dashboard", "Dashboard"),
            ("bot", "Bot"),
            ("detection", "Détection"),
            ("parametres", "Paramètres"),
        ]
        for key, label in nav_spec:
            btn = ctk.CTkButton(
                side, text=f"  {label}", anchor="w", height=42,
                fg_color="transparent", hover_color=COLORS["hover"],
                text_color=COLORS["text_dim"],
                font=ctk.CTkFont(size=13),
                corner_radius=10,
                command=lambda k=key: self._switch_nav(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._nav_btns[key] = btn

        # Main
        self.main = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        self._build_dashboard()
        self._build_bot_page()
        self._build_detection_page()
        self._build_parametres()
        self._switch_nav("dashboard")

    def _card(self, parent, **kw):
        return ctk.CTkFrame(
            parent, fg_color=COLORS["card"],
            border_width=1, border_color=COLORS["card_border"],
            corner_radius=14, **kw,
        )

    def _switch_nav(self, key: str):
        self._nav = key
        for k, page in self._pages.items():
            page.grid_remove()
        if key in self._pages:
            self._pages[key].grid(row=0, column=0, sticky="nsew", padx=28, pady=(22, 18))
        for k, btn in self._nav_btns.items():
            if k == key:
                btn.configure(fg_color=COLORS["sidebar_active"], text_color=COLORS["text"])
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text_dim"])

    # ─── DASHBOARD (maquette) ────────────────────────────────
    def _build_dashboard(self):
        page = ctk.CTkFrame(self.main, fg_color="transparent")
        self._pages["dashboard"] = page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        # Header
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        top.grid_columnconfigure(0, weight=1)

        left_h = ctk.CTkFrame(top, fg_color="transparent")
        left_h.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            left_h, text="Dashboard", text_color=COLORS["text"],
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            left_h, text="Contrôle et surveillance du système",
            text_color=COLORS["text_dim"], font=ctk.CTkFont(size=13),
        ).pack(anchor="w")

        self.badge_ready = ctk.CTkLabel(
            top, text="  ●  Système prêt  ",
            text_color=COLORS["badge_text"], fg_color=COLORS["badge_bg"],
            corner_radius=20, font=ctk.CTkFont(size=12, weight="bold"),
            height=30,
        )
        self.badge_ready.grid(row=0, column=1, sticky="e")

        # Stats 4 cards
        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1)

        self.stat_captures = self._mini_stat(stats, 0, "Captures", "0")
        self.stat_rate = self._mini_stat(stats, 1, "Réussite", "0%")
        self.stat_ok = self._mini_stat(stats, 2, "Étapes OK", "0")
        self.stat_time = self._mini_stat(stats, 3, "Temps actif", "00:00")

        # Contrôle principal
        ctrl = self._card(page)
        ctrl.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)
        inner.grid_columnconfigure(0, weight=1)

        left_c = ctk.CTkFrame(inner, fg_color="transparent")
        left_c.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            left_c, text="Contrôle principal", text_color=COLORS["text"],
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w")
        self.bot_state_lbl = ctk.CTkLabel(
            left_c, text="FishBot", text_color=COLORS["text"],
            font=ctk.CTkFont(size=13),
        )
        self.bot_state_lbl.pack(anchor="w", pady=(4, 0))
        self.key_lbl = ctk.CTkLabel(
            left_c, text="En attente · Touche : —",
            text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12),
        )
        self.key_lbl.pack(anchor="w")

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e")
        self.btn_stop = ctk.CTkButton(
            btns, text="  Stop", width=90, height=38,
            fg_color="#2a1520", hover_color="#3d1f2e",
            text_color=COLORS["text_dim"],
            font=ctk.CTkFont(size=13), corner_radius=10,
            command=self.stop,
        )
        self.btn_stop.pack(side="left", padx=(0, 10))
        self.btn_start = ctk.CTkButton(
            btns, text="  ▶  Démarrer", width=130, height=38,
            fg_color=COLORS["accent"], hover_color="#e05a00",
            text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"), corner_radius=10,
            command=self.start,
        )
        self.btn_start.pack(side="left")

        # Bottom row: détection live + activité
        bottom = ctk.CTkFrame(page, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="nsew")
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        # Détection live
        det = self._card(bottom)
        det.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(
            det, text="Détection live", text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ring_box = ctk.CTkFrame(det, fg_color="transparent")
        ring_box.pack(fill="both", expand=True, padx=10, pady=8)
        self.ring_lbl = ctk.CTkLabel(ring_box, text="")
        self.ring_lbl.pack(expand=True)
        self._update_ring("—", 0.0)
        self.det_hint = ctk.CTkLabel(
            det, text="En attente — démarrer le bot",
            text_color=COLORS["text_faint"], font=ctk.CTkFont(size=12),
        )
        self.det_hint.pack(pady=(0, 12))

        # Activité récente
        act = self._card(bottom)
        act.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        act_top = ctk.CTkFrame(act, fg_color="transparent")
        act_top.pack(fill="x", padx=14, pady=(14, 6))
        act_top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            act_top, text="Activité récente", text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            act_top, text="Vider", width=70, height=28,
            fg_color="#2a1520", hover_color="#3d1f2e",
            text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12),
            command=self._clear_activity,
        ).grid(row=0, column=1, sticky="e")

        self.activity_box = ctk.CTkTextbox(
            act, fg_color=COLORS["input_bg"], text_color=COLORS["text_dim"],
            font=ctk.CTkFont(size=12), border_width=0, wrap="word",
            activate_scrollbars=True,
        )
        self.activity_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._add_activity("Application démarrée")
        self._add_activity("Système prêt")

        # Hidden debug image holder (for live camera if needed)
        self.debug_lbl = self.ring_lbl
        self.timer_lbl = self.stat_time  # alias for _tick

    def _mini_stat(self, parent, col, label, value):
        card = self._card(parent)
        card.grid(row=0, column=col, sticky="ew", padx=5)
        ctk.CTkLabel(
            card, text=label, text_color=COLORS["text_dim"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=16, pady=(14, 2))
        lbl = ctk.CTkLabel(
            card, text=value, text_color=COLORS["text"],
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        lbl.pack(anchor="w", padx=16, pady=(0, 14))
        return lbl

    def _update_ring(self, key: str, progress: float = 0.0):
        pil = _draw_ring(200, key=key or "—", progress=progress)
        img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(200, 200))
        self._ring_photo = img
        if hasattr(self, "ring_lbl"):
            self.ring_lbl.configure(image=img, text="")

    def _add_activity(self, msg: str):
        if not hasattr(self, "activity_box"):
            return
        ts = time.strftime("%H:%M:%S")
        self.activity_box.insert("end", f"  ●  {msg}\n")
        self.activity_box.see("end")

    def _clear_activity(self):
        if hasattr(self, "activity_box"):
            self.activity_box.delete("1.0", "end")

    # ─── Bot page (simplifiée) ───────────────────────────────
    def _build_bot_page(self):
        page = ctk.CTkFrame(self.main, fg_color="transparent")
        self._pages["bot"] = page
        ctk.CTkLabel(
            page, text="Bot", text_color=COLORS["text"],
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))
        card = self._card(page)
        card.pack(fill="x")
        ctk.CTkLabel(
            card, text="Contrôle rapide", text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 8))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            row, text="▶  Démarrer", width=140, height=40,
            fg_color=COLORS["accent"], hover_color="#e05a00",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.start,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            row, text="Stop", width=100, height=40,
            fg_color="#2a1520", hover_color="#3d1f2e",
            text_color=COLORS["text"], command=self.stop,
        ).pack(side="left")
        ctk.CTkLabel(
            card, text="F8 = Démarrer / Stop  ·  F7 = Paramètres",
            text_color=COLORS["text_faint"], font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    # ─── Détection page ──────────────────────────────────────
    def _build_detection_page(self):
        page = ctk.CTkFrame(self.main, fg_color="transparent")
        self._pages["detection"] = page
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            page, text="Détection", text_color=COLORS["text"],
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        card = self._card(page)
        card.grid(row=1, column=0, sticky="nsew")
        self.debug_big = ctk.CTkLabel(
            card, text="Aperçu caméra — démarre le bot",
            text_color=COLORS["text_faint"], fg_color="#0a0610", corner_radius=12,
        )
        self.debug_big.pack(fill="both", expand=True, padx=14, pady=14)

        # calibrage rapide
        tools = ctk.CTkFrame(page, fg_color="transparent")
        tools.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkButton(
            tools, text="Recapturer templates Z/Q/S/D", height=34,
            fg_color="#2a1520", hover_color="#3d1f2e", text_color=COLORS["text"],
            command=self._run_capture_templates,
        ).pack(side="left")

    def _run_capture_templates(self):
        script = os.path.join(ROOT, "tools", "capture_templates.py")
        if os.path.exists(script):
            try:
                import subprocess, sys
                subprocess.Popen([sys.executable, script], cwd=ROOT)
                self._append("[INFO] Outil capture templates lancé")
            except Exception as e:
                messagebox.showerror("Erreur", str(e))
        else:
            messagebox.showinfo("Templates", "Place z/q/s/d.png dans templates/")

    # ─── Paramètres ──────────────────────────────────────────
    def _build_parametres(self):
        page = ctk.CTkFrame(self.main, fg_color="transparent")
        self._pages["parametres"] = page
        page.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="Paramètres", text_color=COLORS["text"],
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            top, text="Enregistrer", width=110, height=34,
            fg_color=COLORS["green"], hover_color=COLORS["green_btn"],
            command=self._save_params,
        ).grid(row=0, column=1, sticky="e")

        card = self._card(page)
        card.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(
            card, text="Comportement", text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        self.debug_var = ctk.BooleanVar(value=bool(getattr(self.cfg, "debug_mode", True)))
        self._toggle_row(card, "Mode debug", "Aperçu détection live", self.debug_var)
        self.sounds_var = ctk.BooleanVar(value=bool(getattr(self.cfg, "sounds_enabled", True)))
        self._toggle_row(card, "Sons", "Notifications sonores", self.sounds_var)

        self.tol_var = ctk.DoubleVar(value=float(getattr(self.cfg, "tolerance_deg", 7.0)))
        self._entry_row(card, "Tolérance alignement (°)", self.tol_var)
        self.react_var = ctk.IntVar(value=int(getattr(self.cfg, "reaction_delay_ms", 15)))
        self._entry_row(card, "Délai réaction (ms)", self.react_var)
        self.poll_var = ctk.IntVar(value=int(getattr(self.cfg, "poll_interval_ms", 20)))
        self._entry_row(card, "Intervalle poll (ms)", self.poll_var)
        self.cap_size_var = ctk.IntVar(value=int(getattr(self.cfg, "capture_size", 600)))
        self._entry_row(card, "Taille capture (px)", self.cap_size_var)
        ctk.CTkLabel(card, text="").pack(pady=4)

    def _toggle_row(self, parent, title, desc, var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=7)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=title, text_color=COLORS["text"], font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkLabel(left, text=desc, text_color=COLORS["text_faint"], font=ctk.CTkFont(size=11)).pack(anchor="w")
        ctk.CTkSwitch(
            row, text="", variable=var, width=44,
            progress_color=COLORS["accent"], button_color="#ffffff",
            fg_color="#2a1520",
        ).pack(side="right")

    def _entry_row(self, parent, title, var):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=7)
        ctk.CTkLabel(row, text=title, text_color=COLORS["text"], font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkEntry(
            row, textvariable=var, width=100, justify="right",
            fg_color=COLORS["input_bg"], border_color=COLORS["card_border"],
        ).pack(side="right")

    def _save_params(self):
        try:
            self.cfg.debug_mode = bool(self.debug_var.get())
            self.cfg.sounds_enabled = bool(self.sounds_var.get())
            self.cfg.tolerance_deg = float(self.tol_var.get())
            self.cfg.reaction_delay_ms = int(self.react_var.get())
            self.cfg.poll_interval_ms = int(self.poll_var.get())
            self.cfg.capture_size = int(self.cap_size_var.get())
            self.cfg.save()
            try:
                self.manager.capture.set_size(self.cfg.capture_size)
            except Exception:
                pass
            sounds.configure(
                getattr(self.cfg, "sounds_dir", os.path.join(ROOT, "assets", "sounds")),
                self.cfg.sounds_enabled,
            )
            self._append("[INFO] Paramètres enregistrés")
            messagebox.showinfo("Paramètres", "Enregistrés.")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    # ═══════════════════ BOT CONTROL ═══════════════════
    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False
        self._stop = False
        self._session_start = time.time()
        self.manager.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.badge_ready.configure(text="  ●  En cours  ", text_color="#ff7a18", fg_color="#3d1f0a")
        self.bot_state_lbl.configure(text="FishBot · RUNNING")
        self.key_lbl.configure(text="En cours · Touche : —")
        self.det_hint.configure(text="Détection active…")
        self.btn_start.configure(state="disabled")
        try:
            sounds.play("start")
        except Exception:
            pass
        self._append("[INFO] Bot démarré")
        self._add_activity("Bot démarré")

    def stop(self):
        if not self.is_running and not self._stop:
            return
        self._stop = True
        self.is_running = False
        self.is_paused = False
        try:
            self.manager.stop()
        except Exception:
            pass
        self.badge_ready.configure(
            text="  ●  Système prêt  ",
            text_color=COLORS["badge_text"], fg_color=COLORS["badge_bg"],
        )
        self.bot_state_lbl.configure(text="FishBot")
        self.key_lbl.configure(text="En attente · Touche : —")
        self.det_hint.configure(text="En attente — démarrer le bot")
        self.btn_start.configure(state="normal")
        self._update_ring("—", 0.0)
        try:
            sounds.play("stop")
        except Exception:
            pass
        self._append("[INFO] Bot arrêté")
        self._add_activity("Bot arrêté")

    def _loop(self):
        while not self._stop:
            try:
                if self.is_running and not self.is_paused:
                    self.manager.step()
            except Exception as e:
                self._on_log(f"[ERROR] Boucle : {e}")
            time.sleep(max(0.01, self.cfg.poll_interval_ms / 1000.0))

    def _on_state(self, state: State):
        name = state.name if hasattr(state, "name") else str(state)
        self.after(0, lambda: self.bot_state_lbl.configure(
            text=f"FishBot · {name}" if self.is_running else "FishBot",
        ))

    def _on_rarity_cb(self, rarity: str, conf: float = 0.0):
        if rarity in self._ui_rarity:
            self._ui_rarity[rarity] += 1
        self.after(0, lambda: self._add_activity(f"Rareté : {rarity}"))

    def _on_log(self, msg: str):
        try:
            self._log_q.put_nowait(msg)
        except queue.Full:
            try:
                self._log_q.get_nowait()
                self._log_q.put_nowait(msg)
            except queue.Empty:
                pass
        if "Touche détectée" in msg or "Touche corrigée" in msg:
            parts = msg.split(":")
            if len(parts) >= 2:
                key = parts[-1].strip().split()[0]
                self._current_key = key
                self.after(0, lambda: self.key_lbl.configure(
                    text=f"En cours · Touche : {key}"
                ))
                self.after(0, lambda: self._update_ring(key, 0.65))
        if "Cercle détecté" in msg:
            self._captures += 1
            self.after(0, lambda: self._add_activity("Cercle détecté"))
        if "Étape réussie" in msg or "[SUCCESS]" in msg:
            self.after(0, lambda: self._add_activity("Étape réussie"))

    def _append(self, msg: str):
        self._on_log(msg)

    def _drain_logs(self):
        batch = []
        try:
            while True:
                batch.append(self._log_q.get_nowait())
        except queue.Empty:
            pass
        # activity already fed from key events; keep light
        self.after(100, self._drain_logs)

    def _tick(self):
        if self.is_running and self._session_start:
            elapsed = int(time.time() - self._session_start)
            m, s = divmod(elapsed, 60)
            h, m = divmod(m, 60)
            if h > 0:
                self.stat_time.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
            else:
                self.stat_time.configure(text=f"{m:02d}:{s:02d}")
        if self.is_running and not self.is_paused and not self._stop:
            if self._thread is None or not self._thread.is_alive():
                self._append("[WARN] Thread mort — redémarrage auto")
                self._stop = False
                self.manager.start()
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
        self.after(400, self._tick)

    def _stats(self):
        try:
            st = self.manager.stats
            self.stat_ok.configure(text=str(st.stage_success))
            total = st.stage_success + st.stage_fail
            rate = int(100 * st.stage_success / total) if total else 0
            self.stat_rate.configure(text=f"{rate}%")
            self.stat_captures.configure(text=str(max(self._captures, st.fish_caught)))
        except Exception:
            pass
        self.after(500, self._stats)

    def _poll_inventory(self):
        try:
            if self.is_running and hasattr(self.inventory, "detect"):
                self.inventory.detect()
        except Exception:
            pass
        self.after(1500, self._poll_inventory)

    def _on_debug(self, frame, circle, blue_zone, red_line, key_result, timing_pred, target_angle, region):
        self._pending = (frame, circle, red_line, key_result, timing_pred, target_angle)
        if key_result is not None:
            k = key_result.key.upper()
            self._current_key = k
            prog = 0.7
            if timing_pred is not None and hasattr(timing_pred, "angle_to_target"):
                try:
                    prog = max(0.1, min(1.0, 1.0 - abs(float(timing_pred.angle_to_target)) / 180.0))
                except Exception:
                    pass
            self.after(0, lambda: self.key_lbl.configure(text=f"En cours · Touche : {k}"))
            self.after(0, lambda: self._update_ring(k, prog))
        if not self._render_sched:
            self._render_sched = True
            self.after(0, self._flush)

    def _flush(self):
        self._render_sched = False
        args = self._pending
        if not self.is_running:
            self._pending = None
            return
        if not args:
            return
        now = time.time()
        wait = UI_MIN_INTERVAL - (now - self._last_render)
        if wait > 0.002:
            self._render_sched = True
            self.after(int(wait * 1000), self._flush)
            return
        self._last_render = now
        self._pending = None
        try:
            frame, circle, red_line, key_result, timing_pred, target_angle = args
            pil = self._preview.process(frame, circle, red_line, key_result, timing_pred, target_angle)
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=pil.size)
            self._photo = img
            if hasattr(self, "debug_big"):
                self.debug_big.configure(image=img, text="")
        except Exception as e:
            print("[UI]", e)
        if self._pending and not self._render_sched:
            self._render_sched = True
            self.after(0, self._flush)

    # ─── Hotkeys ─────────────────────────────────────────────
    def _parse_hotkey(self, spec: str):
        spec = (spec or "").strip().lower()
        if not spec:
            return None
        return [p.strip() for p in spec.replace("+", " ").split()]

    def _start_hotkeys(self):
        try:
            from pynput import keyboard
        except ImportError:
            return
        self._hk_toggle = self._parse_hotkey(getattr(self.cfg, "hotkey_toggle", "f8") or "f8")
        self._hk_panel = self._parse_hotkey(getattr(self.cfg, "hotkey_panel", "f7") or "f7")
        pressed = set()

        def norm(key):
            try:
                if hasattr(key, "name"):
                    return key.name.lower()
                if hasattr(key, "char") and key.char:
                    return key.char.lower()
            except Exception:
                pass
            return str(key).lower().replace("'", "")

        def match(combo):
            return bool(combo) and all(p in pressed for p in combo)

        def on_press(key):
            pressed.add(norm(key))
            if match(self._hk_toggle):
                self.after(0, self._hotkey_toggle)
            if match(self._hk_panel):
                self.after(0, lambda: self._switch_nav("parametres"))

        def on_release(key):
            pressed.discard(norm(key))

        try:
            self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
        except Exception:
            pass

    def _hotkey_toggle(self):
        if self.is_running:
            self.stop()
        else:
            self.start()

    def _close(self):
        self._stop = True
        self.is_running = False
        try:
            self.manager.stop()
        except Exception:
            pass
        try:
            if self._hotkey_listener:
                self._hotkey_listener.stop()
        except Exception:
            pass
        try:
            self.inventory.close()
        except Exception:
            pass
        self.destroy()


def run():
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("[FATAL UI]", e)
        print(tb)
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(tb + "\n")
        except Exception:
            pass
        raise
