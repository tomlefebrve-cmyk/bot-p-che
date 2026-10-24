"""Icônes et bannière dessinées avec Pillow (aucun fichier image requis)."""
from __future__ import annotations

import math
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw

S = 256  # toile de dessin (réduite ensuite → bords lisses)


def _mask(draw_fn) -> Image.Image:
    m = Image.new("L", (S, S), 0)
    draw_fn(ImageDraw.Draw(m))
    return m


def _fish(d, ink=255, erase=0):
    d.ellipse((24, 76, 184, 180), fill=ink)                      # corps
    d.polygon([(170, 128), (236, 70), (222, 128), (236, 186)], fill=ink)  # queue
    d.polygon([(70, 82), (110, 40), (140, 84)], fill=ink)        # nageoire
    d.ellipse((52, 112, 72, 132), fill=erase)                    # oeil


def _home(d):
    d.line([(30, 124), (128, 38), (226, 124)], fill=255, width=20, joint="curve")
    d.rounded_rectangle((52, 112, 204, 224), 12, outline=255, width=18)
    d.rectangle((112, 164, 144, 224), fill=255)


def _rod(d):
    d.line([(34, 226), (198, 40)], fill=255, width=18)
    d.line([(198, 40), (226, 96)], fill=255, width=9)
    d.arc((200, 90, 244, 150), 300, 180, fill=255, width=10)


def _gear(d):
    c = 128
    for i in range(8):
        a = math.radians(i * 45)
        d.line([(c + 70 * math.cos(a), c + 70 * math.sin(a)), (c + 106 * math.cos(a), c + 106 * math.sin(a))],
               fill=255, width=34)
    d.ellipse((c - 84, c - 84, c + 84, c + 84), fill=255)
    d.ellipse((c - 36, c - 36, c + 36, c + 36), fill=0)


def _doc(d):
    d.rounded_rectangle((52, 24, 204, 232), 22, outline=255, width=16)
    for y in (88, 126, 164):
        d.line([(84, y), (172, y)], fill=255, width=14)


def _info(d):
    d.ellipse((24, 24, 232, 232), outline=255, width=16)
    d.ellipse((116, 66, 140, 90), fill=255)
    d.line([(128, 112), (128, 184)], fill=255, width=20)


def _clock(d):
    d.ellipse((24, 24, 232, 232), outline=255, width=16)
    d.line([(128, 68), (128, 132), (170, 156)], fill=255, width=16, joint="curve")


def _hook(d):
    d.line([(140, 24), (140, 150)], fill=255, width=16)
    d.arc((60, 100, 190, 230), 0, 180, fill=255, width=16)
    d.line([(60, 166), (46, 134)], fill=255, width=14)
    d.ellipse((118, 14, 162, 50), outline=255, width=10)


def _bag(d):
    d.rounded_rectangle((44, 100, 212, 232), 30, outline=255, width=16)
    d.arc((86, 30, 170, 130), 180, 360, fill=255, width=16)
    d.line([(70, 150), (186, 150)], fill=255, width=12)


def _wave(d):
    for dy in (-28, 28):
        pts = [(24 + x, 128 + dy + 26 * math.sin(x / 34.0 * math.pi)) for x in range(0, 210, 6)]
        d.line(pts, fill=255, width=16, joint="curve")


def _play(d):
    d.polygon([(70, 34), (70, 222), (226, 128)], fill=255)


def _stop(d):
    d.rounded_rectangle((48, 48, 208, 208), 26, fill=255)


def _check(d):
    d.line([(40, 140), (100, 200), (216, 60)], fill=255, width=26, joint="curve")


def _cursor(d):
    d.polygon([(64, 24), (64, 208), (112, 164), (142, 232), (176, 217), (146, 152), (206, 152)], fill=255)


_DRAW = {
    "cursor": _cursor,
    "fish": _fish, "home": _home, "rod": _rod, "gear": _gear, "doc": _doc, "info": _info,
    "clock": _clock, "hook": _hook, "bag": _bag, "wave": _wave, "play": _play,
    "stop": _stop, "check": _check,
}


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=256)
def pil_icon(name: str, color: str, px: int) -> Image.Image:
    m = _mask(_DRAW[name])
    img = Image.new("RGBA", (S, S), _hex(color) + (0,))
    img.putalpha(m)
    return img.resize((px, px), Image.LANCZOS)


@lru_cache(maxsize=256)
def icon(name: str, color: str, size: int = 22) -> ctk.CTkImage:
    img = pil_icon(name, color, size * 2)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


@lru_cache(maxsize=16)
def round_button(kind: str, ring: str, fill: str, fg: str, size: int = 96) -> ctk.CTkImage:
    """Grand bouton rond (play / stop) pour le panneau de contrôle."""
    px = size * 3
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, px - 3, px - 3), fill=_hex(fill), outline=_hex(ring), width=max(4, px // 24))
    glyph = pil_icon(kind, fg, int(px * 0.42))
    off = (px - glyph.width) // 2 + (int(px * 0.03) if kind == "play" else 0)
    img.alpha_composite(glyph, (off, (px - glyph.height) // 2))
    img = img.resize((size * 2, size * 2), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


@lru_cache(maxsize=4)
def banner(bg: str, w: int = 560, h: int = 150) -> ctk.CTkImage:
    """Lac de nuit : ciel, lune, sapins, barque et pêcheur (fondu vers le fond à gauche)."""
    k = 3
    W, H = w * k, h * k
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, hor = (7, 22, 52), (22, 62, 110)
    horizon = int(H * 0.66)
    for y in range(horizon):
        t = y / horizon
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (hor[i] - top[i]) * t) for i in range(3)))
    for y in range(horizon, H):
        t = (y - horizon) / (H - horizon)
        d.line([(0, y), (W, y)], fill=tuple(int(hor[i] * (0.55 - 0.3 * t)) for i in range(3)))
    mx, my, mr = int(W * 0.80), int(H * 0.30), int(H * 0.15)
    for g, a in ((2.0, 8), (1.5, 16), (1.2, 28)):
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        ImageDraw.Draw(glow).ellipse((mx - mr * g, my - mr * g, mx + mr * g, my + mr * g), fill=(a, a * 2, a * 3))
        img = ImageChops.add(img, glow)
    d = ImageDraw.Draw(img)
    d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=(190, 215, 240))
    d.rectangle((mx - mr // 2, horizon + 6, mx + mr // 2, horizon + 12), fill=(60, 110, 160))  # reflet
    pine = (4, 14, 28)
    for cx, th in ((0.62, 0.30), (0.67, 0.42), (0.72, 0.34), (0.90, 0.48), (0.95, 0.38), (0.99, 0.52), (0.55, 0.22)):
        x, base, tall = int(W * cx), horizon + 4, int(H * th)
        for i in range(4):
            wdt = int(tall * (0.20 + 0.10 * i))
            y0 = base - tall + i * tall // 4 - tall // 6
            d.polygon([(x, y0), (x - wdt, y0 + tall // 3), (x + wdt, y0 + tall // 3)], fill=pine)
        d.rectangle((x - 3, base - tall // 6, x + 3, base + 4), fill=pine)
    d.rectangle((0, horizon, W, horizon + 5), fill=(5, 16, 32))
    bx, by = int(W * 0.78), int(H * 0.80)
    d.polygon([(bx - 70, by), (bx + 74, by), (bx + 52, by + 18), (bx - 48, by + 18)], fill=pine)
    d.ellipse((bx - 6, by - 36, bx + 8, by - 22), fill=pine)                     # tête
    d.polygon([(bx - 14, by), (bx - 6, by - 24), (bx + 12, by - 24), (bx + 20, by)], fill=pine)
    d.line([(bx + 6, by - 20), (bx + 112, by - 96)], fill=(10, 24, 44), width=4)  # canne
    d.line([(bx + 112, by - 96), (bx + 128, by + 14)], fill=(120, 160, 200), width=1)
    img = img.resize((w, h), Image.LANCZOS)
    # fondu vers la couleur de fond (gauche + bas)
    bgc = _hex(bg)
    solid = Image.new("RGB", (w, h), bgc)
    mask = Image.new("L", (w, h), 255)
    md = ImageDraw.Draw(mask)
    for x in range(w):
        a = int(255 * min(1.0, max(0.0, (x / (w * 0.50)))) ** 1.4)
        md.line([(x, 0), (x, h)], fill=a)
    img = Image.composite(img, solid, mask)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
