"""Threaded webcam capture so a slow camera never blocks the game loop.

Windows webcam drivers are picky, so instead of forcing one configuration we try
several (backend / resolution combinations), check that frames really arrive, and
keep the first one that works. Any camera exception is caught and reported.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np


def _safe_release(cap) -> None:
    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass


class CameraStream:
    """Continuously grabs frames on a background thread and keeps only the newest.

    status: "starting" | "running" | "error" | "stopped"
    """

    def __init__(self, index: int = 0, size: Tuple[int, int] = (1280, 720)) -> None:
        self.index = index
        self.size = size
        self.status = "starting"
        self.error = ""
        self.log: List[str] = []           # what was tried (used by camera_test.py)
        self._frame: Optional[np.ndarray] = None
        self._frame_id = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="CameraStream", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> Tuple[int, Optional[np.ndarray]]:
        """Return (frame_id, BGR frame). frame_id increases with every new frame."""
        with self._lock:
            return self._frame_id, self._frame

    # ------------------------------------------------------------------ opening
    def _configs(self):
        """(backend, backend name, (width, height) or None) in the order we try them."""
        w, h = self.size
        if sys.platform.startswith("win"):
            return [(cv2.CAP_DSHOW, "DSHOW", (w, h)), (cv2.CAP_DSHOW, "DSHOW", (640, 480)),
                    (cv2.CAP_MSMF, "MSMF", (w, h)), (cv2.CAP_MSMF, "MSMF", None),
                    (cv2.CAP_ANY, "ANY", None)]
        return [(cv2.CAP_ANY, "ANY", (w, h)), (cv2.CAP_ANY, "ANY", None)]

    def _try_config(self, idx: int, backend: int, name: str, size) -> Tuple[Optional[cv2.VideoCapture], float]:
        """Open one configuration and verify that 10 frames can be read. Returns (cap, fps)."""
        cap = None
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                self.log.append(f"index {idx} {name} {size}: could not open")
                _safe_release(cap)
                return None, 0.0
            if size:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
            good, start = 0, time.time()
            while good < 10 and time.time() - start < 4.0 and not self._stop.is_set():
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    good += 1
                else:
                    time.sleep(0.03)
            elapsed = max(time.time() - start, 1e-3)
            if good < 10:
                self.log.append(f"index {idx} {name} {size}: opened but only {good}/10 frames")
                _safe_release(cap)
                return None, 0.0
            fps = good / elapsed
            shape = frame.shape[1], frame.shape[0]
            self.log.append(f"index {idx} {name} {size}: OK, {shape[0]}x{shape[1]}, ~{fps:.0f} fps")
            return cap, fps
        except Exception as exc:  # OpenCV can raise cv2.error / "Unknown C++ exception"
            self.log.append(f"index {idx} {name} {size}: exception {exc}")
            _safe_release(cap)
            return None, 0.0

    def _open(self) -> Optional[cv2.VideoCapture]:
        indices = [self.index] + [i for i in range(3) if i != self.index]
        for idx in indices:
            slow: Tuple[Optional[cv2.VideoCapture], float] = (None, 0.0)
            for backend, name, size in self._configs():
                if self._stop.is_set():
                    _safe_release(slow[0])
                    return None
                cap, fps = self._try_config(idx, backend, name, size)
                if cap is None:
                    continue
                if fps >= 12:                      # good enough: use it
                    _safe_release(slow[0])
                    return cap
                if slow[0] is None:                # works but slow: remember as a fallback
                    slow = (cap, fps)
                else:
                    _safe_release(cap)
            if slow[0] is not None:
                return slow[0]
        return None

    # ------------------------------------------------------------------ thread
    def _run(self) -> None:
        cap = None
        try:
            cap = self._open()
            if cap is None:
                self.status = "error"
                self.error = "No working camera found. " + (self.log[-1] if self.log else "")
                return
            self.status = "running"
            failures, last_exc = 0, ""
            while not self._stop.is_set():
                try:
                    ok, frame = cap.read()
                except Exception as exc:
                    ok, frame, last_exc = False, None, str(exc)
                if not ok or frame is None or frame.size == 0:  # invalid frame
                    failures += 1
                    if failures > 90:
                        self.status = "error"
                        self.error = "The camera stopped sending frames. " + last_exc
                        break
                    time.sleep(0.01)
                    continue
                failures = 0
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
        except Exception as exc:  # absolutely nothing here may kill the game
            self.status = "error"
            self.error = f"Camera error: {exc}"
        finally:
            _safe_release(cap)
            if self.status != "error":
                self.status = "stopped"
