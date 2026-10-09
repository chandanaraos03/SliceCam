"""Camera diagnostic. Run:  python camera_test.py
Shows which camera configurations work, then saves a snapshot to camera_test.jpg."""
import time

import cv2

from vision.camera import CameraStream

cam = CameraStream(0, (1280, 720))
cam.start()
t0 = time.time()
while cam.status == "starting" and time.time() - t0 < 30:
    time.sleep(0.1)
print("\n--- attempts ---")
print("\n".join(cam.log) or "(none)")
print("\nstatus:", cam.status, "|", cam.error)
if cam.status == "running":
    time.sleep(1.0)
    fid, frame = cam.latest()
    if frame is not None:
        cv2.imwrite("camera_test.jpg", frame)
        print(f"Got frame {frame.shape[1]}x{frame.shape[0]}; saved camera_test.jpg - open it to check the picture.")
cam.stop()
