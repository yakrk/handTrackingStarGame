"""Threaded webcam capture + MediaPipe Hands detection.

Runs OpenCV camera I/O and MediaPipe inference in a background daemon thread so
the Pygame render loop is never blocked. Exposes the most recent finger tip
position and an annotated debug frame via thread-safe properties.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import numpy as np
import pygame

try:
    import mediapipe as mp
    _MP_AVAILABLE = True
except Exception as exc:  # pragma: no cover - import-time guard
    mp = None  # type: ignore
    _MP_AVAILABLE = False
    _MP_IMPORT_ERROR = exc


# MediaPipe landmark index for the tip of the index finger.
INDEX_FINGER_TIP = 8

DEBUG_WIDTH = 320
DEBUG_HEIGHT = 180

CAMERA_READ_MAX_FAILURES = 5


class HandTracker:
    """Captures webcam frames and runs MediaPipe Hands in a background thread.

    Thread-safe read access is provided through the `finger_pos` and
    `debug_frame` properties. The main (game) thread should read these values
    once per frame.

    If the camera cannot be opened or MediaPipe is unavailable, the tracker
    degrades gracefully: `has_camera` becomes False, `finger_pos` stays None,
    and the game continues to run without hand input.
    """

    def __init__(
        self,
        camera_index: int = 0,
        screen_width: int = 1280,
        screen_height: int = 720,
    ) -> None:
        self._camera_index = camera_index
        self._screen_width = screen_width
        self._screen_height = screen_height

        self._lock = threading.Lock()
        self._finger_pos: Optional[tuple[int, int]] = None
        self._debug_surface: Optional[pygame.Surface] = None

        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        self._cap: Optional[cv2.VideoCapture] = None
        self._hands = None
        self._mp_drawing = None
        self._mp_hands_module = None

        self._has_camera: bool = False
        self._mediapipe_ready: bool = False

        self._init_camera()
        self._init_mediapipe()

    # ------------------------------------------------------------------
    # Thread-safe public properties
    # ------------------------------------------------------------------
    @property
    def finger_pos(self) -> Optional[tuple[int, int]]:
        with self._lock:
            return self._finger_pos

    @property
    def debug_frame(self) -> Optional[pygame.Surface]:
        with self._lock:
            return self._debug_surface

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def has_camera(self) -> bool:
        return self._has_camera

    @property
    def mediapipe_ready(self) -> bool:
        return self._mediapipe_ready

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self._has_camera:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, name="HandTrackerThread", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:
                pass
            self._hands = None

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------
    def _init_camera(self) -> None:
        try:
            cap = cv2.VideoCapture(self._camera_index)
            if not cap or not cap.isOpened():
                print(
                    f"[HandTracker] Could not open camera at index {self._camera_index}. "
                    "Game will run without hand input."
                )
                self._has_camera = False
                if cap is not None:
                    cap.release()
                return
            self._cap = cap
            self._has_camera = True
        except Exception as exc:
            print(f"[HandTracker] Camera init failed: {exc}")
            self._has_camera = False

    def _init_mediapipe(self) -> None:
        if not _MP_AVAILABLE:
            print(
                "[HandTracker] MediaPipe is not available: "
                f"{_MP_IMPORT_ERROR!r}. Hand tracking disabled."
            )
            self._mediapipe_ready = False
            return
        try:
            self._mp_hands_module = mp.solutions.hands
            self._mp_drawing = mp.solutions.drawing_utils
            self._hands = self._mp_hands_module.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5,
            )
            self._mediapipe_ready = True
        except Exception as exc:
            print(f"[HandTracker] MediaPipe init failed: {exc}")
            self._mediapipe_ready = False

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------
    def _capture_loop(self) -> None:
        consecutive_failures = 0
        while self._running:
            if self._cap is None:
                break
            try:
                ret, frame = self._cap.read()
            except Exception as exc:
                print(f"[HandTracker] cap.read() raised: {exc}")
                ret, frame = False, None

            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= CAMERA_READ_MAX_FAILURES:
                    print(
                        "[HandTracker] Too many consecutive camera read failures; "
                        "stopping capture."
                    )
                    with self._lock:
                        self._finger_pos = None
                    break
                time.sleep(0.05)
                continue
            consecutive_failures = 0

            try:
                self._process_frame(frame)
            except Exception as exc:
                # Never let a transient MediaPipe failure kill the thread.
                print(f"[HandTracker] Frame processing error: {exc}")

        self._running = False

    def _process_frame(self, frame: np.ndarray) -> None:
        # Mirror horizontally so the user sees themselves as a reflection.
        frame = cv2.flip(frame, 1)

        # MediaPipe expects RGB.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_h, frame_w = rgb.shape[:2]

        finger_pos: Optional[tuple[int, int]] = None

        if self._mediapipe_ready and self._hands is not None:
            # Writeable=False can speed up MediaPipe slightly.
            rgb.flags.writeable = False
            results = self._hands.process(rgb)
            rgb.flags.writeable = True

            if results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0]
                tip = landmarks.landmark[INDEX_FINGER_TIP]
                # Normalized [0,1] coordinates -> screen pixel coordinates.
                sx = int(tip.x * self._screen_width)
                sy = int(tip.y * self._screen_height)
                sx = max(0, min(self._screen_width - 1, sx))
                sy = max(0, min(self._screen_height - 1, sy))
                finger_pos = (sx, sy)

                # Draw landmarks on the RGB image for the debug preview.
                if self._mp_drawing is not None and self._mp_hands_module is not None:
                    self._mp_drawing.draw_landmarks(
                        rgb,
                        landmarks,
                        self._mp_hands_module.HAND_CONNECTIONS,
                    )

        # Build a 320x180 Pygame surface for the debug overlay.
        try:
            small = cv2.resize(rgb, (DEBUG_WIDTH, DEBUG_HEIGHT))
            # Pygame.image.frombuffer expects bytes and image dimensions in
            # (width, height) order.
            surface = pygame.image.frombuffer(
                small.tobytes(), (DEBUG_WIDTH, DEBUG_HEIGHT), "RGB"
            )
        except Exception as exc:
            print(f"[HandTracker] Debug surface conversion failed: {exc}")
            surface = None

        with self._lock:
            self._finger_pos = finger_pos
            if surface is not None:
                self._debug_surface = surface


# ----------------------------------------------------------------------
# Standalone smoke test.
# Run: python hand_tracker.py
# ----------------------------------------------------------------------
def _standalone_test() -> None:
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("HandTracker Test")
    clock = pygame.time.Clock()

    tracker = HandTracker()
    tracker.start()

    running = True
    try:
        while running:
            clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            screen.fill((30, 30, 30))
            pos = tracker.finger_pos
            dbg = tracker.debug_frame
            if dbg is not None:
                screen.blit(dbg, (1280 - DEBUG_WIDTH - 10, 720 - DEBUG_HEIGHT - 10))
            if pos is not None:
                pygame.draw.circle(screen, (255, 80, 80), pos, 20, 2)
            pygame.display.flip()
    finally:
        tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    _standalone_test()
