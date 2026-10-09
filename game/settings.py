"""Central configuration: constants, fruit definitions and persisted user settings."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
SETTINGS_FILE = ROOT / "settings.json"

# ---- Window (logical resolution; pygame.SCALED stretches it to any window size)
TITLE = "SliceCam - Fruit Slicer"
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

# ---- Colours (modern arcade + neon + minimal dark UI)
BG_TOP = (8, 10, 24)
BG_BOTTOM = (28, 8, 42)
CYAN = (0, 229, 255)
MAGENTA = (255, 64, 200)
LIME = (160, 255, 90)
GOLD = (255, 214, 64)
RED = (255, 70, 90)
WHITE = (245, 247, 255)
GREY = (150, 156, 185)

# ---- Physics / gameplay
GRAVITY = 1150.0              # px / s^2
MIN_BLADE_STEP = 4.0          # px per frame; slower movement does not slice
FRUIT_HIT_SCALE = 1.15        # generous hit area on fruit
BOMB_HIT_SCALE = 0.9          # slightly forgiving on bombs
START_LIVES = 3
COMBO_WINDOW = 1.0            # seconds between slices that keep a combo alive
MAX_MULTIPLIER = 5

# ---- Computer vision
CAMERA_INDEX = 0
CAMERA_REQUEST_SIZE = (1280, 720)
DETECTION_WIDTH = 640         # frames are downscaled to this width for MediaPipe
HAND_LOST_TIMEOUT = 0.25      # s without a detection before the blade is hidden
# Fraction of the camera image (each side) that is ignored when mapping the
# fingertip to the screen. 0.0 keeps the blade exactly on top of your finger.
CAMERA_MARGIN = 0.0

# ---- Fruit definitions: collision radius, score and colours
FRUITS = {
    "apple":      dict(radius=42, score=10, flesh=(250, 240, 205), juice=(255, 120, 110)),
    "orange":     dict(radius=42, score=10, flesh=(255, 185, 40),  juice=(255, 170, 40)),
    "banana":     dict(radius=46, score=15, flesh=(250, 235, 170), juice=(255, 240, 150)),
    "peach":      dict(radius=40, score=15, flesh=(255, 200, 120), juice=(255, 170, 120)),
    "pineapple":  dict(radius=50, score=20, flesh=(255, 225, 90),  juice=(255, 230, 90)),
    "watermelon": dict(radius=58, score=25, flesh=(235, 40, 70),   juice=(255, 60, 100)),
}
BOMB_RADIUS = 44

# ---- Difficulty presets: (start, end) values interpolated by progress 0..1
DIFFICULTY = {
    "Normal": dict(interval=(1.55, 0.65), wave_max=(2, 5), bomb=(0.07, 0.20),
                   gravity=(1.0, 1.30), score_for_max=2500),
    "Hard":   dict(interval=(1.15, 0.45), wave_max=(3, 6), bomb=(0.12, 0.27),
                   gravity=(1.1, 1.45), score_for_max=1800),
}

TRAIL_LEVELS = {  # name -> (max points, lifetime seconds, glow width)
    "Low": (10, 0.12, 0.8),
    "Medium": (16, 0.20, 1.0),
    "High": (24, 0.30, 1.25),
}
CAMERA_BACKGROUNDS = ["Normal", "Darkened", "Black"]
DARKEN_FACTOR = 0.28


@dataclass
class UserSettings:
    """Options editable from the Settings menu (saved to settings.json)."""
    sound_on: bool = True
    music_on: bool = True
    camera_background: str = "Darkened"
    blade_trail: str = "Medium"
    difficulty: str = "Normal"
    mirror_camera: bool = True
    best_score: int = 0

    @classmethod
    def load(cls) -> "UserSettings":
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            s = cls(**valid)
        except Exception:
            s = cls()
        if s.camera_background not in CAMERA_BACKGROUNDS:
            s.camera_background = "Darkened"
        if s.blade_trail not in TRAIL_LEVELS:
            s.blade_trail = "Medium"
        if s.difficulty not in DIFFICULTY:
            s.difficulty = "Normal"
        return s

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass  # read-only folder etc. - not worth crashing for
