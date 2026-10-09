# SliceCam

A real-time computer-vision arcade game: **slice virtual fruit with your index finger**, tracked through your webcam.
Move your fingertip through the air, cut fruit, avoid bombs, build combos.

## Features
- Real-time hand tracking and **index-fingertip detection** (MediaPipe landmark 8)
- Glowing **virtual blade** with a fading trail (not just a dot)
- 2D fruit physics: 6 fruits (apple, orange, banana, peach, pineapple, watermelon)
- **Swept-segment collision detection** - fast swipes never skip a fruit
- Slicing animation: fruit splits into two spinning halves, juice particles, splats
- Bombs with explosion, shake and instant game over
- Combo system, score, 3 lives, best score (saved)
- Smooth difficulty progression (Normal / Hard)
- **Camera Mode** and **Mouse Mode** (identical physics - handy for testing)
- Camera background: Normal / Darkened / Black (hand skeleton + blade only)
- Procedural sound effects and music (drop your own files in `assets/sounds/`)
- Graceful handling of: no camera, hand lost, multiple hands, missing assets/audio

## Tech Stack
Python 3.9-3.12 - OpenCV (capture/image processing) - MediaPipe (hand landmarks) - Pygame (engine, rendering, audio) - NumPy

## Installation (Windows)
```bash
git clone <your-repo-url> fruit-slicer
cd fruit-slicer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Leave the virtual environment with:
```bash
deactivate
```
> macOS/Linux: `python3 -m venv venv && source venv/bin/activate`.
> MediaPipe 0.10.14 supports Python 3.9-3.12 (not 3.13).

## Camera Setup
1. Connect your webcam (close Zoom/Teams/etc. so they aren't using it).
2. Run `python main.py`.
3. Choose **CAMERA MODE** and allow camera access if asked.
4. Show **one** hand with the index finger raised. Wait for "Hand detected".
5. Press **SPACE** and slice with your fingertip.

Tips: face a light source, avoid a busy background, keep your hand ~40-80 cm from the camera.

## Controls
| Input | Action |
|---|---|
| Index finger (Camera Mode) / Mouse (Mouse Mode) | Blade |
| ESC | Pause / resume (back in menus) |
| R | Restart |
| M | Flip camera mirroring (Camera Mode) |
| SPACE | Start from calibration screen |
| F3 | FPS / vision debug overlay |
| F11 | Fullscreen |

## Mirroring
By default the camera is shown like a mirror: move your hand right and the blade moves right.
The image is flipped **once** inside the vision thread, so video, landmarks and blade always share one coordinate
system, and MediaPipe's Left/Right label is corrected. If it feels reversed on your setup, press **M** (or
Settings -> Mirror Camera).

## Project structure
```
main.py            entry point
game/              settings, game loop/states, fruit, bomb, player/blade, particles, collision, ui, audio, input
vision/            camera (threaded capture), hand_tracker (MediaPipe + worker thread), fingertip (smoothing)
assets/            optional: fruits/<name>.png, sounds/{slice,combo,bomb,click,gameover,miss,music}.wav|ogg|mp3, fonts/*.ttf
```

## Computer-vision pipeline
`CameraStream` thread grabs 1280x720 frames -> `VisionWorker` thread downsizes to 640 px, mirrors, converts to RGB
-> MediaPipe Hands (2 hands max) -> one **primary hand** is chosen (the one nearest last frame's fingertip, else the
largest) -> landmark 8 -> `FingertipTracker` maps it to 1280x720 and applies speed-adaptive smoothing at 60 Hz,
producing `previous_x/y` and `current_x/y` each frame. The hand must be missing for 0.25 s before the blade is hidden.

## Collision detection
Each frame the blade is the segment **previous fingertip -> current fingertip**. For every fruit we find the closest
point on that segment to the fruit centre (project onto the segment, clamp to [0, 1]) and test whether its distance is
<= the fruit's hit radius. Testing the whole path, not only the end point, means fast swipes can't tunnel through a fruit.
`is_sliced` is set instantly so nothing is cut twice. The segment direction also defines the cut line of the two halves.

## Known limitations / ideas
- Single-hand blade; tracking quality depends on lighting and camera frame rate (~30 fps cameras add latency).
- No hand segmentation: "Black" mode shows the landmark skeleton instead of a cut-out hand.
- Menus are mouse-driven (could add finger-hover menus).
- Ideas: freeze/frenzy power-ups, two-player mode, fruit PNG art, leaderboard, gesture to pause.
