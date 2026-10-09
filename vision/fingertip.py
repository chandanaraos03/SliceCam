"""Fingertip selection, coordinate mapping and smoothing (game-side)."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

INDEX_TIP = 8  # MediaPipe landmark id of the index fingertip

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


def select_primary_hand(hands: list, last_tip: Optional[Tuple[float, float]]):
    """Pick ONE hand to control the blade and stick with it.

    * If we were tracking a hand last frame, choose the hand whose index tip is
      closest to where it was -> no flipping between two hands.
    * Otherwise choose the largest hand (usually the one closest to the camera).
    """
    if not hands:
        return None
    if last_tip is not None:
        lx, ly = last_tip
        return min(hands, key=lambda h: math.hypot(h.landmarks[INDEX_TIP][0] - lx,
                                                   h.landmarks[INDEX_TIP][1] - ly))
    return max(hands, key=lambda h: h.area)


class FingertipTracker:
    """Turns raw (normalised, ~30 Hz) fingertip detections into a smooth 60 Hz blade.

    Exposes previous_x/y and current_x/y for every frame, as required by the
    slicing logic (the blade is the segment previous -> current).
    """

    def __init__(self, width: int, height: int, margin: float = 0.0,
                 lost_timeout: float = 0.25) -> None:
        self.width, self.height = width, height
        self.margin = margin
        self.lost_timeout = lost_timeout
        self.previous_x = self.previous_y = 0.0
        self.current_x = self.current_y = 0.0
        self.visible = False
        self._target: Optional[Tuple[float, float]] = None
        self._since_seen = 999.0

    def map_point(self, nx: float, ny: float) -> Tuple[float, float]:
        """Normalised camera coords (0..1, already mirrored) -> game pixels."""
        m = self.margin
        span = max(1e-6, 1.0 - 2 * m)
        x = min(1.0, max(0.0, (nx - m) / span)) * self.width
        y = min(1.0, max(0.0, (ny - m) / span)) * self.height
        return x, y

    def update(self, tip_norm: Optional[Tuple[float, float]], dt: float) -> None:
        self.previous_x, self.previous_y = self.current_x, self.current_y
        if tip_norm is not None:
            self._target = self.map_point(*tip_norm)
            self._since_seen = 0.0
        else:
            self._since_seen += dt

        if self._target is None or self._since_seen > self.lost_timeout:
            self.visible = False  # hand gone: freeze blade, trail fades out
            return

        tx, ty = self._target
        if not self.visible:  # (re)acquired: jump to the finger, no streak across the screen
            self.visible = True
            self.current_x, self.current_y = tx, ty
            self.previous_x, self.previous_y = tx, ty
            return

        # Speed-adaptive exponential smoothing: heavy smoothing when slow (kills jitter),
        # light smoothing when fast (keeps the blade snappy).
        dist = math.hypot(tx - self.current_x, ty - self.current_y)
        rate = 18.0 + dist * 0.10
        alpha = 1.0 - math.exp(-rate * dt)
        if dist < 5.0:               # soft dead-zone around the current position
            alpha *= dist / 5.0
        self.current_x += (tx - self.current_x) * alpha
        self.current_y += (ty - self.current_y) * alpha

    def landmarks_to_screen(self, landmarks: np.ndarray) -> List[Tuple[float, float]]:
        return [self.map_point(float(x), float(y)) for x, y in landmarks]
