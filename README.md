# Starfish Tap Game

A webcam-based tap game built with Pygame, OpenCV, and MediaPipe. Orange starfish
bounce across the screen; touch them with your index finger (tracked through your
webcam) to score points. You have 60 seconds.

This is **Step 1** of a 3-step project:

1. **Step 1 (this)** - PC-screen prototype using a webcam.
2. **Step 2** - Fullscreen mode for projecting on a wall (Mars 3 projector).
3. **Step 3** - Four-corner calibration for accurate projector alignment.

## Requirements

- Windows (tested target), Python **3.10 or higher**
- A webcam accessible as device index `0`

## Installation

```powershell
# Clone the repo and enter the folder, then:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```powershell
python main.py
```

## Controls

| Key | Action |
|-----|--------|
| `F1` | Toggle the debug overlay (camera preview + finger coordinates) |
| `R`  | Restart after game over |
| `ESC` | Quit |

## How to Play

1. Stand so the webcam can see your hand.
2. Your view is mirrored, so moving your hand right moves the cursor right on screen.
3. Point your **index finger** and touch the orange starfish to score +10 points.
4. You have 60 seconds. At most 3 starfish are on screen at any time, each with a 5-second lifespan before they respawn elsewhere.

## Project Structure

```
starfish-tap-game/
├── main.py          # Main loop, event handling, debug overlay
├── game.py          # Game state, scoring, timer, UI, flash effects
├── starfish.py      # Starfish entity (polygon drawing, sine bobbing, hit test)
├── hand_tracker.py  # Threaded webcam + MediaPipe hand detection
├── requirements.txt
└── README.md
```

## Architecture Notes

- **Threaded camera capture.** OpenCV/MediaPipe work happens on a background
  daemon thread. The main Pygame loop reads the most recent finger position via
  a thread-safe property, so camera latency never stalls rendering.
- **Graceful degradation.** If the webcam is not present or MediaPipe fails to
  initialize, the game still runs (without hand input) and shows a warning.
- **Frame-rate-independent logic.** All animations use `dt` in seconds; `dt` is
  clamped to avoid jumps when the window is dragged.
- **Architecture ready for Step 2/3.**
  - `draw_background` in `game.py` is isolated so a video background can be
    swapped in.
  - `HandTracker` is parameterized on screen dimensions and can later be given a
    homography matrix for projector calibration.

## Troubleshooting

### "No camera detected"

- Check that your webcam is plugged in and not in use by another app (Zoom, Teams, etc.).
- If your camera is on a different index, edit `main.py` and change the
  `camera_index=0` argument to `HandTracker(...)`.
- On Windows, ensure your webcam privacy settings allow desktop apps to access it:
  *Settings → Privacy & security → Camera → "Let desktop apps access your camera"*.

### MediaPipe installation fails

- MediaPipe needs Python **3.10, 3.11, or 3.12** (as of `mediapipe>=0.10`).
  Python 3.13 support may lag; pin to 3.11 if you run into wheel issues.
- If pip cannot find a wheel, upgrade pip first: `python -m pip install --upgrade pip`.

### Game runs but detection is jittery or slow

- Good lighting dramatically improves MediaPipe accuracy.
- Close other camera-using apps to free up the device.
- The camera thread runs at the webcam's native rate (usually ~30 FPS);
  rendering stays at 60 FPS regardless.

### Window is unresponsive / very slow

- First-time MediaPipe calls load a model and may take a few seconds.
- If you are on a laptop, ensure it is not in a low-power state.

## License

Prototype code for a hackathon-style project. Adapt freely.
