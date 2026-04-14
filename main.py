"""Starfish Tap Game - main entry point.

Run with:  python main.py

Controls:
  F1   Toggle debug overlay (camera preview + finger coords)
  R    Restart after game over
  ESC  Quit
"""

from __future__ import annotations

import sys
from typing import Optional

import pygame

from game import Game, GameState
from hand_tracker import HandTracker, DEBUG_WIDTH, DEBUG_HEIGHT


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
WINDOW_TITLE = "Starfish Tap Game"

# Bottom-right placement for the debug preview (with a small margin).
DEBUG_PREVIEW_MARGIN = 10
DEBUG_PREVIEW_POS = (
    SCREEN_WIDTH - DEBUG_WIDTH - DEBUG_PREVIEW_MARGIN,
    SCREEN_HEIGHT - DEBUG_HEIGHT - DEBUG_PREVIEW_MARGIN,
)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    game = Game(SCREEN_WIDTH, SCREEN_HEIGHT)
    tracker = HandTracker(
        camera_index=0,
        screen_width=SCREEN_WIDTH,
        screen_height=SCREEN_HEIGHT,
    )
    tracker.start()

    show_debug: bool = True  # on by default during development
    running: bool = True

    # Fonts used only by debug overlay.
    debug_font = pygame.font.SysFont("Arial", 18)
    warning_font = pygame.font.SysFont("Arial", 24, bold=True)

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0

            # ---- Event handling ----
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_F1:
                        show_debug = not show_debug
                    elif event.key == pygame.K_r:
                        if game.state == GameState.GAME_OVER:
                            game.reset()

            # Snapshot the finger position once per frame to avoid it changing
            # mid-frame from the camera thread.
            finger_pos = tracker.finger_pos

            # ---- Update ----
            game.update(dt, finger_pos)

            # ---- Draw ----
            game.draw_background(screen)
            game.draw(screen, finger_pos)

            if show_debug:
                _draw_debug(screen, tracker, finger_pos, debug_font, warning_font)

            pygame.display.flip()
    finally:
        tracker.stop()
        pygame.quit()
        sys.exit()


def _draw_debug(
    screen: pygame.Surface,
    tracker: HandTracker,
    finger_pos: Optional[tuple[int, int]],
    font: pygame.font.Font,
    warning_font: pygame.font.Font,
) -> None:
    """Draw the camera preview, finger coordinates, and any warnings."""
    preview = tracker.debug_frame
    if preview is not None:
        rect = preview.get_rect(topleft=DEBUG_PREVIEW_POS)
        pygame.draw.rect(
            screen, (255, 255, 255), rect.inflate(4, 4), width=2
        )
        screen.blit(preview, DEBUG_PREVIEW_POS)

    # Finger coordinates above the preview.
    label_y = DEBUG_PREVIEW_POS[1] - 24
    if finger_pos is not None:
        text = font.render(
            f"Finger: ({finger_pos[0]}, {finger_pos[1]})",
            True,
            (220, 220, 220),
        )
        screen.blit(text, (DEBUG_PREVIEW_POS[0], label_y))
    else:
        text = font.render("Finger: (no hand detected)", True, (180, 180, 180))
        screen.blit(text, (DEBUG_PREVIEW_POS[0], label_y))

    # Warnings if hardware/software unavailable.
    warning_y = 20
    if not tracker.has_camera:
        warn = warning_font.render(
            "No camera detected", True, (255, 80, 80)
        )
        warn_rect = warn.get_rect()
        warn_rect.centerx = SCREEN_WIDTH // 2
        warn_rect.top = warning_y
        screen.blit(warn, warn_rect)
    elif not tracker.mediapipe_ready:
        warn = warning_font.render(
            "MediaPipe unavailable - hand tracking disabled",
            True, (255, 200, 80),
        )
        warn_rect = warn.get_rect()
        warn_rect.centerx = SCREEN_WIDTH // 2
        warn_rect.top = warning_y
        screen.blit(warn, warn_rect)


if __name__ == "__main__":
    main()
