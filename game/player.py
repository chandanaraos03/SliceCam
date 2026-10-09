"""Blade (trail + swept segment) and player state (score, lives, combo)."""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Optional, Tuple

import pygame

from . import settings as S
from .particles import get_glow

Point = Tuple[float, float]


class Blade:
    """Keeps the recent fingertip path, draws the glowing trail and exposes the
    current swept segment (previous -> current) used for slicing."""

    def __init__(self, trail_level: str = "Medium") -> None:
        self.points: Deque[Tuple[float, float, float]] = deque()
        self.segment: Optional[Tuple[Point, Point]] = None
        self.speed = 0.0
        self.set_level(trail_level)

    def set_level(self, level: str) -> None:
        self.max_points, self.lifetime, self.glow = S.TRAIL_LEVELS.get(level, S.TRAIL_LEVELS["Medium"])

    def clear(self) -> None:
        self.points.clear()
        self.segment = None

    def update(self, visible: bool, prev: Point, cur: Point, now: float, dt: float) -> None:
        self.segment, self.speed = None, 0.0
        if visible:
            step = math.hypot(cur[0] - prev[0], cur[1] - prev[1])
            self.speed = step / max(dt, 1e-4)
            if step >= S.MIN_BLADE_STEP:
                self.segment = (prev, cur)
            if step > 0.8:  # only extend the trail when actually moving -> it vanishes when you stop
                if not self.points:
                    self.points.append((prev[0], prev[1], now))
                self.points.append((cur[0], cur[1], now))
        while self.points and (now - self.points[0][2] > self.lifetime or len(self.points) > self.max_points):
            self.points.popleft()

    def direction(self) -> Tuple[float, float]:
        if not self.segment:
            return 1.0, 0.0
        (ax, ay), (bx, by) = self.segment
        d = math.hypot(bx - ax, by - ay) or 1.0
        return (bx - ax) / d, (by - ay) / d

    def draw(self, target: pygame.Surface, now: float) -> None:
        pts = list(self.points)
        if len(pts) < 2:
            return
        pad = 40
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
        w, h = int(max(xs)) - x0 + pad, int(max(ys)) - y0 + pad
        layer = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
        n = len(pts)
        passes = [  # (colour, base width, alpha)
            ((0, 200, 255), 26 * self.glow, 40),
            ((80, 230, 255), 15 * self.glow, 110),
            ((255, 255, 255), 6 * self.glow, 255),
        ]
        for color, width, alpha in passes:
            for i in range(1, n):
                age = (now - pts[i][2]) / self.lifetime
                fade = max(0.0, 1.0 - age)
                taper = (i / (n - 1)) ** 0.8  # thin tail, thick head
                wdt = max(1, int(width * (0.25 + 0.75 * taper) * (0.5 + 0.5 * fade)))
                a = (pts[i - 1][0] - x0, pts[i - 1][1] - y0)
                b = (pts[i][0] - x0, pts[i][1] - y0)
                col = (*color, int(alpha * fade))
                pygame.draw.line(layer, col, a, b, wdt)
                if wdt > 3:
                    pygame.draw.circle(layer, col, b, wdt // 2)
        target.blit(layer, (x0, y0))
        hx, hy = pts[-1][0], pts[-1][1]
        gl = get_glow(int(34 * self.glow), (0, 200, 255), 1.0)
        target.blit(gl, (hx - gl.get_width() / 2, hy - gl.get_height() / 2), special_flags=pygame.BLEND_RGB_ADD)


class PlayerState:
    """Score, lives and combo bookkeeping."""

    def __init__(self, best_score: int = 0) -> None:
        self.best_score = best_score
        self.reset()

    def reset(self) -> None:
        self.score = 0
        self.lives = S.START_LIVES
        self.combo = 0
        self.combo_timer = 0.0
        self.combo_flash = 0.0      # drives the combo pop animation
        self.last_multiplier = 1
        self.fruits_sliced = 0

    def update(self, dt: float) -> None:
        if self.combo > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0
        self.combo_flash = max(0.0, self.combo_flash - dt)

    def register_slice(self, base_value: int) -> Tuple[int, int]:
        """Returns (points_awarded, multiplier)."""
        self.combo = self.combo + 1 if self.combo_timer > 0 else 1
        self.combo_timer = S.COMBO_WINDOW
        multiplier = min(self.combo, S.MAX_MULTIPLIER)
        points = base_value * multiplier
        self.score += points
        self.fruits_sliced += 1
        if self.combo >= 2:
            self.combo_flash = 0.9
            self.last_multiplier = self.combo
        self.best_score = max(self.best_score, self.score)
        return points, multiplier

    def lose_life(self) -> None:
        self.lives = max(0, self.lives - 1)
        self.combo = 0
