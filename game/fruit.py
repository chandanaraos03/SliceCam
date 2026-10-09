"""Flying objects: fruit, fruit halves, and procedurally drawn fruit sprites.

Sprites are drawn with pygame shapes (3x supersampled for smooth edges) so the game
needs no art assets. If assets/fruits/<name>.png exists it is used instead.
"""
from __future__ import annotations

import math
import random
from typing import Dict, Optional, Tuple

import pygame

from . import settings as S

Color = Tuple[int, int, int]
SS = 3  # supersampling factor for procedural sprites


# ---------------------------------------------------------------- drawing helpers
def _lerp(a: Color, b: Color, t: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore


def shaded_circle(surf, cx, cy, r, dark: Color, base: Color, light: Color) -> None:
    """Fake 3-D sphere: stacked circles that shrink toward a top-left highlight."""
    steps = 22
    for i in range(steps):
        t = i / (steps - 1)
        col = _lerp(dark, base, min(1.0, t * 1.6)) if t < 0.62 else _lerp(base, light, (t - 0.62) / 0.38)
        pygame.draw.circle(surf, col, (cx - 0.22 * r * t, cy - 0.28 * r * t), r * (1 - 0.82 * t))


def shaded_ellipse(surf, cx, cy, rx, ry, dark: Color, base: Color, light: Color) -> None:
    steps = 22
    for i in range(steps):
        t = i / (steps - 1)
        col = _lerp(dark, base, min(1.0, t * 1.6)) if t < 0.62 else _lerp(base, light, (t - 0.62) / 0.38)
        w, h = rx * 2 * (1 - 0.8 * t), ry * 2 * (1 - 0.8 * t)
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (cx - 0.2 * rx * t, cy - 0.25 * ry * t)
        pygame.draw.ellipse(surf, col, rect)


def specular(surf, cx, cy, r, strength=110) -> None:
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, (255, 255, 255, strength),
                        pygame.Rect(cx - 0.55 * r, cy - 0.62 * r, 0.42 * r, 0.26 * r))
    surf.blit(layer, (0, 0))


def leaf(surf, x, y, length, angle_deg, color: Color) -> None:
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for u, v in [(0, 0), (0.3, -0.28), (0.7, -0.22), (1.0, 0), (0.7, 0.22), (0.3, 0.28)]:
        pts.append((x + (u * ca - v * sa) * length, y + (u * sa + v * ca) * length))
    pygame.draw.polygon(surf, color, pts)


# ---------------------------------------------------------------- fruit painters
def paint_apple(s, cx, cy, r):
    shaded_circle(s, cx, cy, r, (120, 12, 36), (218, 38, 52), (255, 120, 105))
    pygame.draw.circle(s, (110, 14, 30), (cx, cy - r * 0.86), r * 0.2)
    pygame.draw.line(s, (96, 62, 30), (cx, cy - r * 0.8), (cx + r * 0.12, cy - r * 1.28), int(r * 0.12))
    leaf(s, cx + r * 0.1, cy - r * 1.08, r * 0.55, -25, (70, 170, 70))
    specular(s, cx, cy, r)


def paint_orange(s, cx, cy, r):
    shaded_circle(s, cx, cy, r, (200, 88, 8), (255, 148, 28), (255, 205, 100))
    rng = random.Random(4)
    for _ in range(40):
        a, d = rng.uniform(0, math.tau), r * math.sqrt(rng.random()) * 0.92
        pygame.draw.circle(s, (205, 100, 12), (cx + math.cos(a) * d, cy + math.sin(a) * d), r * 0.022)
    pygame.draw.circle(s, (70, 130, 50), (cx, cy - r * 0.9), r * 0.1)
    leaf(s, cx, cy - r * 0.9, r * 0.45, -40, (80, 160, 60))
    specular(s, cx, cy, r)


def paint_watermelon(s, cx, cy, r):
    shaded_circle(s, cx, cy, r, (22, 84, 42), (58, 148, 68), (118, 205, 116))
    for k in (-0.82, -0.45, -0.1, 0.25, 0.6, 0.9):  # meridian stripes that converge at the poles
        pts = [(cx + r * k * math.sqrt(max(0.0, 1 - t * t)), cy + r * t)
               for t in [i / 20 * 2 - 1 for i in range(21)]]
        pygame.draw.lines(s, (24, 92, 46), False, pts, max(2, int(r * 0.13)))
    pygame.draw.line(s, (96, 62, 30), (cx, cy - r * 0.95), (cx + r * 0.05, cy - r * 1.2), int(r * 0.1))
    specular(s, cx, cy, r, 90)


def paint_banana(s, cx, cy, r):
    center = (cx, cy - 0.95 * r)
    arc_r = 1.38 * r
    pts = []
    for i in range(41):
        u = i / 40
        a = math.radians(24 + 132 * u)
        w = r * (0.12 + 0.30 * math.sin(math.pi * u) ** 0.7)
        pts.append((center[0] + math.cos(a) * arc_r, center[1] + math.sin(a) * arc_r, w))
    for x, y, w in pts:
        pygame.draw.circle(s, (170, 128, 20), (x, y), w + r * 0.045)
    for x, y, w in pts:
        pygame.draw.circle(s, (255, 214, 50), (x, y), w)
    for x, y, w in pts:
        pygame.draw.circle(s, (255, 238, 140), (x - w * 0.2, y - w * 0.3), w * 0.45)
    pygame.draw.circle(s, (92, 64, 28), pts[0][:2], r * 0.1)
    pygame.draw.circle(s, (92, 64, 28), pts[-1][:2], r * 0.1)


def paint_pineapple(s, cx, cy, r):
    ry, rx, by = r * 0.98, r * 0.74, cy + r * 0.2
    for i in range(9):  # crown behind the body
        ang = -90 + (i - 4) * 17
        a = math.radians(ang)
        col = (46, 140, 62) if i % 2 else (84, 180, 80)
        leaf(s, cx, by - ry * 0.85, r * (0.95 - abs(i - 4) * 0.07), ang, col)
    shaded_ellipse(s, cx, by, rx, ry, (170, 100, 10), (240, 170, 30), (255, 220, 100))
    lattice = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    step = r * 0.34
    for k in range(-8, 9):
        pygame.draw.line(lattice, (140, 80, 10, 190), (cx + k * step - 2 * r, by - 2 * r),
                         (cx + k * step + 2 * r, by + 2 * r), max(2, int(r * 0.05)))
        pygame.draw.line(lattice, (140, 80, 10, 190), (cx + k * step + 2 * r, by - 2 * r),
                         (cx + k * step - 2 * r, by + 2 * r), max(2, int(r * 0.05)))
    mask = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    pygame.draw.ellipse(mask, (255, 255, 255, 255), pygame.Rect(cx - rx, by - ry, rx * 2, ry * 2))
    lattice.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(lattice, (0, 0))
    specular(s, cx - r * 0.05, by, r * 0.9, 80)


def paint_peach(s, cx, cy, r):
    shaded_circle(s, cx, cy, r, (225, 100, 90), (255, 168, 118), (255, 222, 170))
    blush = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(blush, (255, 80, 90, 90), (cx + r * 0.35, cy + r * 0.25), r * 0.6)
    mask = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), r)
    blush.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(blush, (0, 0))
    crease = [(cx + r * 0.14 * math.sin(t * 3.0), cy - r * 0.9 + t * r * 1.6) for t in [i / 14 for i in range(15)]]
    pygame.draw.lines(s, (205, 92, 82), False, crease, max(2, int(r * 0.05)))
    pygame.draw.line(s, (96, 62, 30), (cx, cy - r * 0.92), (cx - r * 0.05, cy - r * 1.2), int(r * 0.1))
    leaf(s, cx - r * 0.02, cy - r * 1.05, r * 0.6, -150, (74, 172, 74))
    specular(s, cx, cy, r)


PAINTERS = {
    "apple": paint_apple, "orange": paint_orange, "watermelon": paint_watermelon,
    "banana": paint_banana, "pineapple": paint_pineapple, "peach": paint_peach,
}

_sprite_cache: Dict[str, pygame.Surface] = {}
_shadow_cache: Dict[int, pygame.Surface] = {}


def fruit_sprite(kind: str) -> pygame.Surface:
    """Cached whole-fruit sprite (centered in a square surface)."""
    sprite = _sprite_cache.get(kind)
    if sprite is not None:
        return sprite
    r = S.FRUITS[kind]["radius"]
    side = int(r * 2.9)
    path = S.ASSETS_DIR / "fruits" / f"{kind}.png"
    if path.exists():
        try:
            img = pygame.image.load(str(path)).convert_alpha()
            sprite = pygame.transform.smoothscale(img, (side, side))
        except Exception:
            sprite = None
    if sprite is None:
        big = pygame.Surface((side * SS, side * SS), pygame.SRCALPHA)
        PAINTERS[kind](big, side * SS / 2, side * SS / 2, r * SS)
        sprite = pygame.transform.smoothscale(big, (side, side))
    _sprite_cache[kind] = sprite
    return sprite


def shadow_sprite(radius: int) -> pygame.Surface:
    sh = _shadow_cache.get(radius)
    if sh is None:
        sh = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        c = radius * 3 // 2
        for i in range(10):
            pygame.draw.circle(sh, (0, 0, 0, 9), (c, c), int(radius * (1.15 - i * 0.07)))
        _shadow_cache[radius] = sh
    return sh


def draw_shadow(target: pygame.Surface, x: float, y: float, radius: int) -> None:
    sh = shadow_sprite(radius)
    target.blit(sh, (x - sh.get_width() / 2 + 8, y - sh.get_height() / 2 + 12))


# ---------------------------------------------------------------- game objects
class FlyingObject:
    """Shared physics for fruit and bombs."""
    kind = "object"

    def __init__(self, x, y, vx, vy, gravity, radius, rot_speed):
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(vx, vy)
        self.gravity = gravity
        self.radius = radius
        self.angle = random.uniform(0, 360)
        self.rotation_speed = rot_speed  # degrees / second
        self.is_sliced = False

    def update(self, dt: float) -> None:
        self.vel.y += self.gravity * dt
        self.pos += self.vel * dt
        self.angle += self.rotation_speed * dt

    def is_missed(self) -> bool:
        """Fell below the screen while moving down (never true right after spawning)."""
        return self.vel.y > 0 and self.pos.y - self.radius * 1.5 > S.SCREEN_H

    def hit_radius(self) -> float:
        return self.radius * S.FRUIT_HIT_SCALE


class Fruit(FlyingObject):
    kind = "fruit"

    def __init__(self, fruit_type, x, y, vx, vy, gravity, rot_speed):
        spec = S.FRUITS[fruit_type]
        super().__init__(x, y, vx, vy, gravity, spec["radius"], rot_speed)
        self.fruit_type = fruit_type
        self.score_value = spec["score"]
        self.flesh = spec["flesh"]
        self.juice = spec["juice"]

    def draw(self, target: pygame.Surface) -> None:
        draw_shadow(target, self.pos.x, self.pos.y, self.radius)
        img = pygame.transform.rotate(fruit_sprite(self.fruit_type), self.angle)
        target.blit(img, img.get_rect(center=(self.pos.x, self.pos.y)))

    def make_halves(self, blade_dir: Tuple[float, float], blade_speed: float):
        """Cut the sprite along the blade direction into two physical halves."""
        rotated = pygame.transform.rotate(fruit_sprite(self.fruit_type), self.angle)
        w, h = rotated.get_size()
        dx, dy = blade_dir
        nx, ny = -dy, dx
        cx, cy = w / 2, h / 2
        big = max(w, h)
        silhouette = pygame.mask.from_surface(rotated, 40)
        halves = []
        for side in (1, -1):
            # polygon covering one side of the cut line
            poly = [(cx - dx * big, cy - dy * big), (cx + dx * big, cy + dy * big),
                    (cx + dx * big + nx * big * side, cy + dy * big + ny * big * side),
                    (cx - dx * big + nx * big * side, cy - dy * big + ny * big * side)]
            region = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.polygon(region, (255, 255, 255, 255), poly)
            half = rotated.copy()
            half.blit(region, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            # flesh strip along the cut edge
            band = pygame.Surface((w, h), pygame.SRCALPHA)
            t = 9
            bpoly = [(cx - dx * big, cy - dy * big), (cx + dx * big, cy + dy * big),
                     (cx + dx * big + nx * t * side, cy + dy * big + ny * t * side),
                     (cx - dx * big + nx * t * side, cy - dy * big + ny * t * side)]
            pygame.draw.polygon(band, (255, 255, 255, 255), bpoly)
            flesh = silhouette.to_surface(setcolor=(*self.flesh, 255), unsetcolor=(0, 0, 0, 0))
            flesh.blit(band, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            half.blit(flesh, (0, 0))
            rect = half.get_bounding_rect(min_alpha=10)
            if rect.width < 2 or rect.height < 2:
                continue
            cropped = half.subsurface(rect).copy()
            offset = (rect.centerx - cx, rect.centery - cy)  # so the half starts exactly where it was
            halves.append((cropped, offset, side))
        result = []
        for cropped, offset, side in halves:
            vel = self.vel * 0.55 + pygame.Vector2(nx, ny) * side * (150 + blade_speed * 0.08)
            vel.y -= 60
            result.append(FruitHalf(cropped, self.pos.x + offset[0], self.pos.y + offset[1],
                                    vel.x, vel.y, self.gravity,
                                    side * random.uniform(120, 260)))
        return result


class FruitHalf:
    """One side of a sliced fruit: falls, spins, then leaves the screen."""

    def __init__(self, sprite, x, y, vx, vy, gravity, rot_speed):
        self.sprite = sprite
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(vx, vy)
        self.gravity = gravity
        self.angle = 0.0
        self.rotation_speed = rot_speed
        self.radius = max(sprite.get_size()) // 2

    def update(self, dt: float) -> None:
        self.vel.y += self.gravity * dt
        self.pos += self.vel * dt
        self.angle += self.rotation_speed * dt

    @property
    def gone(self) -> bool:
        return self.pos.y - self.radius > S.SCREEN_H + 40

    def draw(self, target: pygame.Surface) -> None:
        img = pygame.transform.rotate(self.sprite, self.angle)
        target.blit(img, img.get_rect(center=(self.pos.x, self.pos.y)))
