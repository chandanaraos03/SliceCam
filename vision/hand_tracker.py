"""MediaPipe hand detection + the background vision pipeline.

Pipeline (all off the main thread):
    CameraStream (capture)  ->  VisionWorker (resize, mirror, MediaPipe)  ->  VisionSnapshot
The game thread only ever reads the newest snapshot.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .camera import CameraStream

LOG_FILE = Path(__file__).resolve().parent.parent / "slicecam_log.txt"


def log_error(text: str) -> None:
    """Append a diagnostic message to slicecam_log.txt (never raises)."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + text + "\n")
    except Exception:
        pass
from .fingertip import INDEX_TIP, select_primary_hand


@dataclass
class HandDetection:
    landmarks: np.ndarray   # (21, 2) normalised x, y in the *displayed* (possibly mirrored) frame
    label: str              # "Left" / "Right" from the user's point of view
    score: float
    area: float             # bounding-box area, used to pick the primary hand


@dataclass
class VisionSnapshot:
    frame_id: int
    frame_rgb: Optional[np.ndarray]
    hand: Optional[HandDetection]
    num_hands: int
    fps: float
    timestamp: float = 0.0

    @property
    def tip(self) -> Optional[Tuple[float, float]]:
        if self.hand is None:
            return None
        x, y = self.hand.landmarks[INDEX_TIP]
        return float(x), float(y)


class HandTracker:
    """Thin wrapper around mediapipe.solutions.hands."""

    def __init__(self) -> None:
        import mediapipe as mp  # imported here so a failure can be reported nicely
        hands_api = getattr(mp, "solutions", None)
        if hands_api is None:
            try:  # some builds only expose the legacy API at this path
                from mediapipe.python import solutions as hands_api
            except Exception:
                hands_api = None
        if hands_api is None or not hasattr(hands_api, "hands"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                f"Your MediaPipe ({version}) is too new: it no longer includes the hand-tracking API this game uses. "
                "Fix: pip uninstall -y mediapipe   then   pip install mediapipe==0.10.14")
        self._hands = hands_api.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=1,            # 1 = more accurate than 0, still real-time on CPU
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

    def detect(self, rgb: np.ndarray, mirrored: bool) -> List[HandDetection]:
        rgb.flags.writeable = False  # lets MediaPipe avoid a copy
        result = self._hands.process(rgb)
        rgb.flags.writeable = True
        hands: List[HandDetection] = []
        if not result.multi_hand_landmarks:
            return hands
        for i, lm in enumerate(result.multi_hand_landmarks):
            pts = np.array([(p.x, p.y) for p in lm.landmark], dtype=np.float32)
            label, score = "Right", 0.0
            if result.multi_handedness and i < len(result.multi_handedness):
                cls = result.multi_handedness[i].classification[0]
                label, score = cls.label, float(cls.score)
            # MediaPipe assumes a selfie (mirrored) image. If we feed it an un-mirrored
            # image the Left/Right labels come out swapped, so swap them back.
            if not mirrored:
                label = "Left" if label == "Right" else "Right"
            span = pts.max(axis=0) - pts.min(axis=0)
            hands.append(HandDetection(pts, label, score, float(span[0] * span[1])))
        return hands

    def close(self) -> None:
        try:
            self._hands.close()
        except Exception:
            pass


class VisionWorker(threading.Thread):
    def __init__(self, camera: CameraStream, mirror: bool) -> None:
        super().__init__(name="VisionWorker", daemon=True)
        self.camera = camera
        self.mirror = mirror
        self.status = "starting"     # starting | running | error | stopped
        self.error = ""
        self.last_error = ""       # most recent per-frame problem (shown on the calibration screen)
        self._snap = VisionSnapshot(0, None, None, 0, 0.0)
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> VisionSnapshot:
        with self._lock:
            return self._snap

    def run(self) -> None:
        try:
            tracker = HandTracker()
        except BaseException as exc:  # includes ImportError / DLL load failures
            self.status = "error"
            self.error = f"{type(exc).__name__}: {exc}"
            log_error("MediaPipe failed to start:\n" + traceback.format_exc())
            return
        self.status = "running"
        last_id, last_tip = -1, None
        times: List[float] = []
        try:
            while not self._stop.is_set():
                frame_id, frame = self.camera.latest()
                if frame is None or frame_id == last_id:
                    time.sleep(0.002)
                    continue
                last_id = frame_id
                try:
                    h, w = frame.shape[:2]
                    if w > 640:  # detect on a smaller image; the game still draws it full-size
                        frame = cv2.resize(frame, (640, max(1, int(640 * h / w))),
                                           interpolation=cv2.INTER_AREA)
                    mirror = self.mirror
                    if mirror:  # mirror ONCE here so image + landmarks share one coordinate system
                        frame = cv2.flip(frame, 1)
                    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    hands = tracker.detect(rgb, mirror)
                    primary = select_primary_hand(hands, last_tip)
                    if primary is not None:
                        last_tip = tuple(primary.landmarks[INDEX_TIP])
                    else:
                        last_tip = None
                    now = time.time()
                    times.append(now)
                    times = [t for t in times if now - t < 1.0]
                    snap = VisionSnapshot(frame_id, rgb, primary, len(hands), float(len(times)), now)
                    with self._lock:
                        self._snap = snap
                except Exception as exc:  # one bad frame must never kill tracking
                    msg = f"{type(exc).__name__}: {exc}"
                    if msg != self.last_error:
                        log_error("Frame processing error:\n" + traceback.format_exc())
                    self.last_error = msg
                    time.sleep(0.01)
        finally:
            tracker.close()
            self.status = "stopped" if self.status != "error" else "error"


class VisionSystem:
    """Facade used by the game: owns the camera thread and the vision thread."""

    def __init__(self, camera_index: int = 0, mirror: bool = True,
                 request_size: Tuple[int, int] = (1280, 720)) -> None:
        self.camera = CameraStream(camera_index, request_size)
        self.worker = VisionWorker(self.camera, mirror)

    def start(self) -> None:
        self.camera.start()
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()
        self.camera.stop()

    def set_mirror(self, mirror: bool) -> None:
        self.worker.mirror = mirror

    @property
    def mirror(self) -> bool:
        return self.worker.mirror

    @property
    def error_source(self) -> str:
        """"camera" or "tracking" - which half of the pipeline failed."""
        return "camera" if self.camera.status == "error" else "tracking"

    @property
    def warning(self) -> str:
        return self.worker.last_error

    @property
    def status(self) -> str:
        """starting | running | error"""
        if self.camera.status == "error" or self.worker.status == "error":
            return "error"
        if self.camera.status == "running" and self.worker.status == "running":
            return "running"
        return "starting"

    @property
    def error(self) -> str:
        return self.camera.error if self.camera.status == "error" else self.worker.error

    def snapshot(self) -> VisionSnapshot:
        return self.worker.snapshot()
