"""Blade-vs-object collision (swept segment against circle)."""
from __future__ import annotations

import math
from typing import Tuple

Point = Tuple[float, float]


def closest_point_on_segment(a: Point, b: Point, p: Point) -> Point:
    """Closest point to p on the segment a-b."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    length_sq = abx * abx + aby * aby
    if length_sq < 1e-9:
        return a
    # Project p onto the infinite line, then clamp the parameter to the segment [0, 1].
    t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / length_sq
    t = max(0.0, min(1.0, t))
    return a[0] + abx * t, a[1] + aby * t


def segment_hits_circle(a: Point, b: Point, center: Point, radius: float) -> bool:
    """True if the blade segment a->b touches the circle.

    Because the whole path travelled this frame is tested (not only the end
    point), a very fast swipe cannot "jump over" a fruit between two frames.
    """
    cx, cy = closest_point_on_segment(a, b, center)
    return math.hypot(cx - center[0], cy - center[1]) <= radius
