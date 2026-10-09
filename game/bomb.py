"""Bomb object: visually distinct (dark sphere, skull, pulsing red glow, sparking fuse)."""
from __future__ import annotations

import math
import random

import pygame

from . import settings as S
from .fruit import SS, FlyingObject, draw_shadow, shaded_circle
from .particles import get_glow

_bomb_sprite = None


def bomb_sprite() -> pygame.Surface:
    global _bomb_sprite
    if _bomb_sprite is not None:
        return _bomb_sprite
    r = S.BOMB_RADIUS
    side = int(r * 2.9)
    big = pygame.Surface((side * SS, side * SS), pygame.SRCALPHA)
    cx = cy = side * SS / 2
    R = r * SS
    shaded_circle(big, cx, cy + R * 0.08, R * 0.96, (8, 8, 14), (40, 42, 58), (115, 118, 145))
    pygame.draw.circle(big, (255, 60, 70), (cx, cy + R * 0.08), R * 0.96, max(2, int(R * 0.06)))
    # metal cap
    cap = pygame.Rect(0, 0, R * 0.55, R * 0.3)
    cap.center = (cx + R * 0.1, cy - R * 0.9)
    pygame.draw.rect(big, (90, 92, 110), cap, border_radius=int(R * 0.08))
    # fuse
    pts = [(cx + R * 0.1 + math.sin(t * 2.4) * R * 0.18 + t * R * 0.2,
            cy - R * 1.0 - t * R * 0.5) for t in [i / 10 for i in range(11)]]
    pygame.draw.lines(big, (170, 130, 80), False, pts, max(3, int(R * 0.07)))
    # skull
    sx, sy = cx, cy + R * 0.12
    pygame.draw.circle(big, (236, 236, 242), (sx, sy - R * 0.06), R * 0.36)
    pygame.draw.rect(big, (236, 236, 242), pygame.Rect(sx - R * 0.18, sy + R * 0.12, R * 0.36, R * 0.26),
                     border_radius=int(R * 0.06))
    for ex in (-0.14, 0.14):
        pygame.draw.circle(big, (30, 20, 30), (sx + R * ex, sy - R * 0.06), R * 0.095)
    pygame.draw.polygon(big, (30, 20, 30), [(sx, sy + R * 0.06), (sx - R * 0.04, sy + R * 0.14),
                                            (sx + R * 0.04, sy + R * 0.14)])
    for tx in (-0.08, 0.0, 0.08):
        pygame.draw.line(big, (30, 20, 30), (sx + R * tx, sy + R * 0.2), (sx + R * tx, sy + R * 0.36), max(1, int(R * 0.02)))
    _bomb_sprite = pygame.transform.smoothscale(big, (side, side))
    return _bomb_sprite


class Bomb(FlyingObject):
    kind = "bomb"

    def __init__(self, x, y, vx, vy, gravity, rot_speed):
        super().__init__(x, y, vx, vy, gravity, S.BOMB_RADIUS, rot_speed * 0.4)
        self.age = 0.0

    def hit_radius(self) -> float:
        return self.radius * S.BOMB_HIT_SCALE

    def update(self, dt: float) -> None:
        super().update(dt)
        self.age += dt

    def draw(self, target: pygame.Surface) -> None:
        draw_shadow(target, self.pos.x, self.pos.y, self.radius)
        pulse = 0.55 + 0.45 * math.sin(self.age * 9)
        glow = get_glow(int(self.radius * 2.1), (255, 40, 60), pulse * 0.7)
        target.blit(glow, (self.pos.x - glow.get_width() / 2, self.pos.y - glow.get_height() / 2),
                    special_flags=pygame.BLEND_RGB_ADD)
        img = pygame.transform.rotate(bomb_sprite(), self.angle)
        target.blit(img, img.get_rect(center=(self.pos.x, self.pos.y)))
        # flickering spark at the fuse tip (rotates with the bomb)
        r = self.radius
        tip = pygame.Vector2(r * 0.3, -r * 1.5 + r * 0.05).rotate(-self.angle)
        sx, sy = self.pos.x + tip.x, self.pos.y + tip.y
        g = get_glow(random.randint(10, 16), (255, 200, 80), 1.0)
        target.blit(g, (sx - g.get_width() / 2, sy - g.get_height() / 2), special_flags=pygame.BLEND_RGB_ADD)
