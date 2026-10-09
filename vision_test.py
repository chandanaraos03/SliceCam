"""Full vision pipeline test (camera + MediaPipe, no game window).
Run:  python vision_test.py     - hold your hand up for ~10 seconds."""
import time
import traceback

print("1) importing MediaPipe ...")
try:
    import mediapipe as mp
    print("   OK, version", mp.__version__)
except BaseException:
    print("   FAILED:\n" + traceback.format_exc())
    raise SystemExit(1)

from vision import VisionSystem

print("2) starting camera + hand tracking ...")
v = VisionSystem(0, True)
v.start()
t0 = time.time()
while v.status == "starting" and time.time() - t0 < 40:
    time.sleep(0.1)
print("   status:", v.status, "|", v.error)
if v.status != "running":
    print("\n".join(v.camera.log))
    raise SystemExit(1)
print("3) hold your hand up (index finger raised) for 10 seconds ...")
seen = frames = 0
last = -1
for _ in range(100):
    time.sleep(0.1)
    s = v.snapshot()
    if s.frame_id != last:
        last, frames = s.frame_id, frames + 1
        if s.hand is not None:
            seen += 1
            if seen % 15 == 1:
                x, y = s.tip
                print(f"   hand: {s.hand.label}  fingertip=({x:.2f}, {y:.2f})  hands={s.num_hands}  fps={s.fps:.0f}")
print(f"\nframes processed: {frames}, frames with a hand: {seen}")
print("last tracking error:", v.warning or "none")
v.stop()
