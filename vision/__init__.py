"""Computer-vision package: webcam capture, MediaPipe hand tracking, fingertip smoothing."""
from .hand_tracker import VisionSystem, VisionSnapshot
from .fingertip import FingertipTracker, HAND_CONNECTIONS

__all__ = ["VisionSystem", "VisionSnapshot", "FingertipTracker", "HAND_CONNECTIONS"]
