"""
Fenêtre de calibrage : sélection visuelle de la zone de capture.
Overlay plein écran → drag pour dessiner le carré.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Tuple


def pick_region(
    parent,
    initial: Optional[Tuple[int, int, int]] = None,
    on_done: Optional[Callable[[int, int, int], None]] = None,
) -> None:
    """
    Ouvre un overlay semi-transparent. L'utilisateur dessine un rectangle.
    on_done(left, top, size) avec size = côté du carré (max côté du rectangle).
    """
    overlay = tk.Toplevel(parent)
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-alpha", 0.35)
    overlay.attributes("-topmost", True)
    overlay.configure(bg="#000000")
    overlay.title("Calibrage zone")

    canvas = tk.Canvas(overlay, cursor="cross", bg="#000000", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    state = {"x0": 0, "y0": 0, "rect": None, "text": None}

    # hint
    hint = canvas.create_text(
        overlay.winfo_screenwidth() // 2,
        40,
        text="Clique + glisse pour sélectionner la zone du mini-jeu  ·  Entrée = valider  ·  Échap = annuler",
        fill="#ffffff",
        font=("Segoe UI", 14),
    )

    if initial:
        left, top, size = initial
        state["rect"] = canvas.create_rectangle(
            left, top, left + size, top + size,
            outline="#3b82f6", width=3,
        )
        state["text"] = canvas.create_text(
            left + size // 2, top - 12,
            text=f"{size}×{size}", fill="#3b82f6", font=("Segoe UI", 11),
        )

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"]:
            canvas.delete(state["rect"])
        if state["text"]:
            canvas.delete(state["text"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#22d3ee", width=3)
        state["text"] = canvas.create_text(e.x, e.y - 12, text="", fill="#22d3ee", font=("Segoe UI", 11))

    def on_drag(e):
        if not state["rect"]:
            return
        canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)
        w = abs(e.x - state["x0"])
        h = abs(e.y - state["y0"])
        canvas.coords(state["text"], (state["x0"] + e.x) // 2, min(state["y0"], e.y) - 14)
        canvas.itemconfigure(state["text"], text=f"{w}×{h}")

    def finish(cancel: bool = False):
        result = None
        if not cancel and state["rect"]:
            x1, y1, x2, y2 = canvas.coords(state["rect"])
            left = int(min(x1, x2))
            top = int(min(y1, y2))
            w = int(abs(x2 - x1))
            h = int(abs(y2 - y1))
            size = max(w, h, 40)
            result = (left, top, size)
        try:
            overlay.destroy()
        except Exception:
            pass
        if result and on_done:
            on_done(*result)

    def on_release(e):
        # garde le rectangle, valide avec Entrée
        pass

    def on_key(e):
        if e.keysym in ("Return", "KP_Enter"):
            finish(False)
        elif e.keysym == "Escape":
            finish(True)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    overlay.bind("<Key>", on_key)
    overlay.focus_force()
