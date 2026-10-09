"""Input sources. Both produce the same BladeInput, so physics/collision are identical
in Mouse Mode and Camera Mode - only where the blade position comes from changes."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import pygame

from . import settings as S
from vision import FingertipTracker, VisionSnapshot, VisionSystem


@dataclass
class BladeInput:
    visible: bool
    prev: Tuple[float, float]
    cur: Tuple[float, float]


class MouseInput:
    name = "mouse"

    def __init__(self, get_pos: Callable[[], Tuple[float, float]]) -> None:
        self._get_pos = get_pos
        self._last: Optional[Tuple[float, float]] = None

    def reset(self) -> None:
        self._last = None

    def update(self, dt: float) -> BladeInput:
        pos = self._get_pos()
        prev = self._last if self._last is not None else pos
        self._last = pos
        return BladeInput(pygame.mouse.get_focused(), prev, pos)


class CameraInput:
    name = "camera"

    def __init__(self, vision: VisionSystem) -> None:
        self.vision = vision
        self.tracker = FingertipTracker(S.SCREEN_W, S.SCREEN_H, S.CAMERA_MARGIN, S.HAND_LOST_TIMEOUT)
        self.snapshot: VisionSnapshot = vision.snapshot()

    def reset(self) -> None:
        self.tracker.visible = False

    @property
    def hand_detected(self) -> bool:
        return self.snapshot.hand is not None and (time.time() - self.snapshot.timestamp) < S.HAND_LOST_TIMEOUT

    def update(self, dt: float) -> BladeInput:
        self.snapshot = self.vision.snapshot()
        tip = self.snapshot.tip if self.hand_detected else None
        self.tracker.update(tip, dt)
        t = self.tracker
        return BladeInput(t.visible, (t.previous_x, t.previous_y), (t.current_x, t.current_y))

    def hand_screen_points(self):
        if self.snapshot.hand is None:
            return None
        return self.tracker.landmarks_to_screen(self.snapshot.hand.landmarks)
