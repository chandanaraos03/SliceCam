"""Particles, juice splats, shock-wave rings and floating text."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import numpy as np
import pygame

Color = Tuple[int, int, int]

_glow_cache: Dict[tuple, pygame.Surface] = {}
_circle_cache: Dict[tuple, pygame.Surface] = {}


def get_glow(radius: int, color: Color, intensity: float = 1.0) -> pygame.Surface:
    """Soft radial glow (RGB, black falloff). Blit with BLEND_RGB_ADD."""
    radius = max(2, int(radius) // 2 * 2)
    level = max(0, min(8, int(round(intensity * 8))))
    key = (radius, color, level)
    surf = _glow_cache.get(key)
    if surf is None:
        size = radius * 2
        xs = np.arange(size)[:, None]
        ys = np.arange(size)[None, :]
        d = np.hypot(xs - radius, ys - radius) / radius
        falloff = np.clip(1.0 - d, 0.0, 1.0) ** 2 * (level / 8.0)
        arr = (falloff[..., None] * np.array(color, dtype=np.float32)).astype(np.uint8)
        surf = pygame.surfarray.make_surface(arr)
        _glow_cache[key] = surf
    return surf


def get_circle(radius: int, color: Color, alpha: int) -> pygame.Surface:
    """Cached translucent circle (alpha is bucketed to keep the cache small)."""
    radius = max(1, int(radius))
    alpha = max(0, min(255, int(alpha) // 16 * 16))
    key = (radius, color, alpha)
    surf = _circle_cache.get(key)
    if surf is None:
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), radius)
        _circle_cache[key] = surf
    return surf


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "gravity", "drag", "glow")

    def __init__(self, x, y, vx, vy, life, size, color, gravity=900.0, drag=0.99, glow=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color = size, color
        self.gravity, self.drag, self.glow = gravity, drag, glow


class Splat:
    """Juice stain that lingers on the background and fades."""

    def __init__(self, x: float, y: float, color: Color, rng: random.Random) -> None:
        size = 170
        self.surface = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        pygame.draw.circle(self.surface, (*color, 120), (c, c), rng.randint(14, 22))
        for _ in range(rng.randint(8, 14)):
            ang = rng.uniform(0, math.tau)
            dist = rng.uniform(14, 60)
            pygame.draw.circle(self.surface, (*color, 100),
                               (int(c + math.cos(ang) * dist), int(c + math.sin(ang) * dist)),
                               max(2, int(rng.uniform(2, 12) * (1 - dist / 90))))
        self.x, self.y = x, y
        self.life = self.max_life = 1.8

    def draw(self, target: pygame.Surface) -> None:
        self.surface.set_alpha(int(255 * max(0.0, self.life / self.max_life)))
        target.blit(self.surface, (self.x - 85, self.y - 85))


class Ring:
    """Expanding shock-wave ring."""

    def __init__(self, x, y, max_radius, color, life=0.5, width=6):
        self.x, self.y, self.max_radius = x, y, max_radius
        self.color, self.width = color, width
        self.life = self.max_life = life

    def draw(self, target: pygame.Surface) -> None:
        t = 1.0 - self.life / self.max_life
        fade = max(0.0, 1.0 - t)
        radius = int(self.max_radius * (1 - (1 - t) ** 3))
        col = tuple(int(c * fade) for c in self.color)
        width = max(1, int(self.width * fade))
        if radius > 2:
            pygame.draw.circle(target, col, (int(self.x), int(self.y)), radius, width)


class FloatingText:
    """Score pop-ups like '+25' that drift upward and fade."""

    def __init__(self, text: str, x: float, y: float, font: pygame.font.Font, color: Color):
        self.base = font.render(text, True, color)
        self.x, self.y = x, y
        self.life = self.max_life = 0.9

    def draw(self, target: pygame.Surface) -> None:
        t = 1.0 - self.life / self.max_life
        scale = 1.0 + 0.35 * max(0.0, 1.0 - t * 6.0)  # quick "pop" at the start
        w, h = self.base.get_size()
        img = pygame.transform.smoothscale(self.base, (max(1, int(w * scale)), max(1, int(h * scale))))
        img.set_alpha(int(255 * min(1.0, self.life / (self.max_life * 0.5))))
        target.blit(img, img.get_rect(center=(self.x, self.y - 50 * t)))


class ParticleSystem:
    def __init__(self) -> None:
        self.particles: List[Particle] = []
        self.splats: List[Splat] = []
        self.rings: List[Ring] = []
        self.texts: List[FloatingText] = []
        self.rng = random.Random()

    # ------------------------------------------------------------- emitters
    def juice_burst(self, x: float, y: float, color: Color, direction: Tuple[float, float],
                    count: int = 28) -> None:
        r = self.rng
        dx, dy = direction
        nx, ny = -dy, dx  # sprays out on both sides of the cut line
        for i in range(count):
            side = 1 if i % 2 else -1
            spread = r.uniform(80, 420)
            vx = nx * side * spread + dx * r.uniform(-120, 120) + r.uniform(-60, 60)
            vy = ny * side * spread + dy * r.uniform(-120, 120) - r.uniform(40, 220)
            self.particles.append(Particle(x, y, vx, vy, r.uniform(0.45, 1.0),
                                           r.uniform(3, 7), color, 900.0, 0.985))
        for _ in range(count // 2):  # tiny glowing sparks
            a = r.uniform(0, math.tau)
            sp = r.uniform(120, 500)
            self.particles.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp,
                                           r.uniform(0.25, 0.55), r.uniform(8, 16),
                                           (255, 255, 255), 200.0, 0.95, glow=True))
        self.splats.append(Splat(x, y, color, r))

    def explosion(self, x: float, y: float) -> None:
        r = self.rng
        palette = [(255, 200, 60), (255, 120, 30), (255, 60, 40), (90, 90, 100)]
        for _ in range(170):
            a = r.uniform(0, math.tau)
            sp = r.uniform(100, 900) * r.random()
            col = r.choice(palette)
            self.particles.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp,
                                           r.uniform(0.5, 1.5), r.uniform(4, 12), col,
                                           300.0, 0.97))
        for _ in range(60):
            a = r.uniform(0, math.tau)
            sp = r.uniform(200, 1000)
            self.particles.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp,
                                           r.uniform(0.3, 0.9), r.uniform(18, 34),
                                           (255, 170, 60), 100.0, 0.94, glow=True))
        self.rings.append(Ring(x, y, 420, (255, 190, 90), 0.7, 10))
        self.rings.append(Ring(x, y, 260, (255, 255, 255), 0.45, 6))

    def add_text(self, text, x, y, font, color) -> None:
        self.texts.append(FloatingText(text, x, y, font, color))

    # ------------------------------------------------------------- update/draw
    def update(self, dt: float) -> None:
        for p in self.particles:
            p.vx *= p.drag ** (dt * 60)
            p.vy = p.vy * p.drag ** (dt * 60) + p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]
        for group in (self.splats, self.rings, self.texts):
            for item in group:
                item.life -= dt
        self.splats = [s for s in self.splats if s.life > 0]
        self.rings = [s for s in self.rings if s.life > 0]
        self.texts = [s for s in self.texts if s.life > 0]

    def draw_background_layer(self, target: pygame.Surface) -> None:
        for s in self.splats:
            s.draw(target)

    def draw(self, target: pygame.Surface) -> None:
        for ring in self.rings:
            ring.draw(target)
        for p in self.particles:
            f = max(0.0, p.life / p.max_life)
            size = max(1, int(p.size * (0.4 + 0.6 * f)))
            if p.glow:
                g = get_glow(size * 2, p.color, f)
                target.blit(g, (p.x - g.get_width() // 2, p.y - g.get_height() // 2),
                            special_flags=pygame.BLEND_RGB_ADD)
            else:
                c = get_circle(size, p.color, 255 * min(1.0, f * 1.6))
                target.blit(c, (p.x - size, p.y - size))
        for t in self.texts:
            t.draw(target)
