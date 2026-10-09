"""UI toolkit: fonts, glowing text, animated buttons, hearts, backgrounds."""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
import pygame

from . import settings as S

Color = Tuple[int, int, int]


class Fonts:
    """Cached fonts. Drop any .ttf into assets/fonts/ to use your own typeface."""

    def __init__(self) -> None:
        self._cache: Dict[tuple, pygame.font.Font] = {}
        self._file: Optional[str] = None
        fonts_dir = S.ASSETS_DIR / "fonts"
        if fonts_dir.exists():
            for f in sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf")):
                self._file = str(f)
                break

    def get(self, size: int, bold: bool = True) -> pygame.font.Font:
        key = (size, bold)
        font = self._cache.get(key)
        if font is None:
            try:
                if self._file:
                    font = pygame.font.Font(self._file, size)
                else:
                    font = pygame.font.SysFont("segoeui,helveticaneue,arial,dejavusans,liberationsans", size, bold=bold)
            except Exception:
                font = pygame.font.Font(None, int(size * 1.2))
            self._cache[key] = font
        return font


_glow_text_cache: Dict[tuple, pygame.Surface] = {}


def _glow_layer(text: str, font: pygame.font.Font, color: Color) -> pygame.Surface:
    key = (text, id(font), color)
    layer = _glow_text_cache.get(key)
    if layer is None:
        base = font.render(text, True, color)
        pad = 28
        canvas = pygame.Surface((base.get_width() + pad * 2, base.get_height() + pad * 2), pygame.SRCALPHA)
        canvas.blit(base, (pad, pad))
        small = pygame.transform.smoothscale(canvas, (max(1, canvas.get_width() // 6), max(1, canvas.get_height() // 6)))
        layer = pygame.transform.smoothscale(small, canvas.get_size())
        if len(_glow_text_cache) > 300:
            _glow_text_cache.clear()
        _glow_text_cache[key] = layer
    return layer


def draw_text(target: pygame.Surface, text: str, font: pygame.font.Font, color: Color,
              pos: Tuple[float, float], anchor: str = "center", glow: Optional[Color] = None,
              shadow: bool = True, alpha: int = 255, scale: float = 1.0) -> pygame.Rect:
    img = font.render(text, True, color)
    if scale != 1.0:
        img = pygame.transform.smoothscale(img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))
    rect = img.get_rect()
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))
    if glow is not None and scale == 1.0:
        layer = _glow_layer(text, font, glow)
        lr = layer.get_rect(center=rect.center)
        layer.set_alpha(alpha)
        target.blit(layer, lr)
        target.blit(layer, lr)
    if shadow:
        sh = font.render(text, True, (0, 0, 0))
        if scale != 1.0:
            sh = pygame.transform.smoothscale(sh, img.get_size())
        sh.set_alpha(int(alpha * 0.55))
        target.blit(sh, rect.move(2, 3))
    if alpha < 255:
        img.set_alpha(alpha)
    target.blit(img, rect)
    return rect


def panel(target: pygame.Surface, rect: pygame.Rect, color=(14, 16, 36), alpha=205,
          border: Optional[Color] = S.CYAN, radius: int = 22) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (*color, alpha), layer.get_rect(), border_radius=radius)
    if border:
        pygame.draw.rect(layer, (*border, 140), layer.get_rect(), width=2, border_radius=radius)
    target.blit(layer, rect.topleft)


class Button:
    """Rounded neon button with a smooth hover animation."""

    def __init__(self, label: str, center: Tuple[int, int], size: Tuple[int, int] = (340, 62),
                 accent: Color = S.CYAN, font_size: int = 26) -> None:
        self.label = label
        self.rect = pygame.Rect(0, 0, *size)
        self.rect.center = center
        self.accent = accent
        self.font_size = font_size
        self.hover = 0.0
        self.press = 0.0

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos)

    def update(self, mouse_pos, dt: float) -> None:
        target = 1.0 if self.rect.collidepoint(mouse_pos) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)

    def draw(self, target: pygame.Surface, fonts: Fonts) -> None:
        grow = 1.0 + 0.06 * self.hover
        r = self.rect.inflate(self.rect.w * (grow - 1), self.rect.h * (grow - 1))
        layer = pygame.Surface((r.w + 12, r.h + 12), pygame.SRCALPHA)
        inner = pygame.Rect(6, 6, r.w, r.h)
        if self.hover > 0.02:  # soft outer glow
            pygame.draw.rect(layer, (*self.accent, int(55 * self.hover)), inner.inflate(12, 12), border_radius=26)
        pygame.draw.rect(layer, (*self.accent, int(34 + 90 * self.hover)), inner, border_radius=20)
        pygame.draw.rect(layer, (*self.accent, int(150 + 105 * self.hover)), inner, width=2, border_radius=20)
        target.blit(layer, (r.x - 6, r.y - 6))
        draw_text(target, self.label, fonts.get(int(self.font_size * (1 + 0.04 * self.hover))),
                  S.WHITE, r.center, glow=self.accent if self.hover > 0.3 else None)


def heart_points(cx: float, cy: float, size: float):
    pts = []
    for i in range(40):
        t = i / 40 * math.tau
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * size / 34, cy + y * size / 34))
    return pts


def draw_heart(target: pygame.Surface, cx: float, cy: float, size: float, filled: bool, pulse: float = 0.0) -> None:
    size *= 1 + 0.35 * pulse
    pts = heart_points(cx, cy, size)
    if filled:
        glow = pygame.Surface((int(size * 2), int(size * 2)), pygame.SRCALPHA)
        pygame.draw.polygon(glow, (255, 60, 100, 60), heart_points(size, size, size * 1.35))
        target.blit(glow, (cx - size, cy - size))
        pygame.draw.polygon(target, (255, 70, 110), pts)
        pygame.draw.polygon(target, (255, 170, 190), heart_points(cx - size * 0.12, cy - size * 0.1, size * 0.5))
        pygame.draw.polygon(target, (255, 120, 150), pts, 2)
    else:
        pygame.draw.polygon(target, (90, 60, 90), pts, 3)


def make_background(w: int, h: int) -> pygame.Surface:
    """Dark gradient with soft neon glows and a faint grid."""
    y = np.linspace(0, 1, h)[None, :, None]
    x = np.linspace(0, 1, w)[:, None, None]
    top, bot = np.array(S.BG_TOP, float), np.array(S.BG_BOTTOM, float)
    arr = top + (bot - top) * y + np.zeros((w, h, 3))
    for (cx, cy, rad, col) in [(0.15, 0.2, 0.45, (0, 90, 130)), (0.85, 0.85, 0.5, (130, 20, 110))]:
        d = np.hypot((x - cx) * (w / h), y - cy) / rad
        arr = arr + np.clip(1 - d, 0, 1) ** 2 * np.array(col, float)
    surf = pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8))
    grid = pygame.Surface((w, h), pygame.SRCALPHA)
    for gx in range(0, w, 80):
        pygame.draw.line(grid, (120, 160, 255, 10), (gx, 0), (gx, h))
    for gy in range(0, h, 80):
        pygame.draw.line(grid, (120, 160, 255, 10), (0, gy), (w, gy))
    surf.blit(grid, (0, 0))
    return surf


def make_vignette(w: int, h: int) -> pygame.Surface:
    y = np.linspace(-1, 1, h)[None, :]
    x = np.linspace(-1, 1, w)[:, None]
    d = np.clip(np.hypot(x * 0.9, y) - 0.55, 0, 1)
    alpha = (d ** 1.6 * 190).astype(np.uint8)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.surfarray.pixels_alpha(surf)[:] = alpha
    return surf
