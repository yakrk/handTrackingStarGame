"""Game state management: starfish pool, scoring, timer, flash effects, UI."""

from enum import Enum, auto
from typing import Optional

import pygame

from starfish import Starfish


class GameState(Enum):
    PLAYING = auto()
    GAME_OVER = auto()


class FlashEffect:
    """Expanding white circle that fades out at a hit location."""

    DURATION: float = 0.4   # seconds
    MAX_RADIUS: int = 80

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self._age: float = 0.0

    @property
    def finished(self) -> bool:
        return self._age >= self.DURATION

    def update(self, dt: float) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.finished:
            return
        progress = self._age / self.DURATION
        radius = max(1, int(self.MAX_RADIUS * progress))
        alpha = max(0, min(255, int(255 * (1.0 - progress))))

        size = radius * 2
        temp = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(temp, (255, 255, 255, alpha), (radius, radius), radius)
        surface.blit(temp, (int(self.x) - radius, int(self.y) - radius))


class Game:
    """Owns the score, timer, starfish pool, flash effects, and state machine.

    Does not own the Pygame display or main clock; those are managed by main.py.
    """

    MAX_STARFISH: int = 3
    GAME_DURATION: float = 60.0    # seconds
    BACKGROUND_COLOR = (10, 20, 60)
    MAX_DT: float = 0.1            # clamp to prevent spikes on pause/drag

    def __init__(self, screen_width: int = 1280, screen_height: int = 720) -> None:
        self._screen_width = screen_width
        self._screen_height = screen_height

        self._starfish: list[Starfish] = [
            Starfish(screen_width, screen_height) for _ in range(self.MAX_STARFISH)
        ]
        self._flashes: list[FlashEffect] = []

        # Font caching
        self._font_score = pygame.font.SysFont("Arial", 48, bold=True)
        self._font_timer = pygame.font.SysFont("Arial", 48, bold=True)
        self._font_game_over = pygame.font.SysFont("Arial", 96, bold=True)
        self._font_final_score = pygame.font.SysFont("Arial", 48)
        self._font_restart = pygame.font.SysFont("Arial", 32)

        self._score: int = 0
        self._timer: float = self.GAME_DURATION
        self._state: GameState = GameState.PLAYING

        self.reset()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def state(self) -> GameState:
        return self._state

    @property
    def score(self) -> int:
        return self._score

    @property
    def time_remaining(self) -> float:
        return max(0.0, self._timer)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._score = 0
        self._timer = self.GAME_DURATION
        self._state = GameState.PLAYING
        self._flashes.clear()
        for fish in self._starfish:
            fish.respawn()

    def update(self, dt: float, finger_pos: Optional[tuple[int, int]]) -> None:
        if dt > self.MAX_DT:
            dt = self.MAX_DT

        # Flash effects always update so residual effects finish on game over.
        for flash in self._flashes:
            flash.update(dt)
        self._flashes = [f for f in self._flashes if not f.finished]

        if self._state != GameState.PLAYING:
            return

        self._timer -= dt
        if self._timer <= 0.0:
            self._timer = 0.0
            self._state = GameState.GAME_OVER
            return

        for fish in self._starfish:
            fish.update(dt)

        self._manage_starfish_pool()
        self._check_hits(finger_pos)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw_background(self, surface: pygame.Surface) -> None:
        """Fill with dark blue. Separated so Step 2 can swap in video."""
        surface.fill(self.BACKGROUND_COLOR)

    def draw(self, surface: pygame.Surface, finger_pos: Optional[tuple[int, int]] = None) -> None:
        for fish in self._starfish:
            fish.draw(surface)

        for flash in self._flashes:
            flash.draw(surface)

        if finger_pos is not None:
            self._draw_finger_cursor(surface, finger_pos)

        self._draw_ui(surface)

        if self._state == GameState.GAME_OVER:
            self._draw_game_over(surface)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _manage_starfish_pool(self) -> None:
        for fish in self._starfish:
            if not fish.alive:
                fish.respawn()

    def _check_hits(self, finger_pos: Optional[tuple[int, int]]) -> None:
        if finger_pos is None:
            return
        for fish in self._starfish:
            if fish.check_hit(finger_pos):
                cx, cy = fish.center
                self._flashes.append(FlashEffect(cx, cy))
                self._score += 10
                fish.respawn()
                # Only score one hit per frame to avoid double-counting.
                break

    def _draw_finger_cursor(self, surface: pygame.Surface, pos: tuple[int, int]) -> None:
        x, y = int(pos[0]), int(pos[1])
        pygame.draw.circle(surface, (255, 255, 255), (x, y), 10, width=2)
        pygame.draw.circle(surface, (255, 255, 255), (x, y), 3)

    def _draw_ui(self, surface: pygame.Surface) -> None:
        # Score top-left
        score_text = self._font_score.render(
            f"Score: {self._score}", True, (255, 255, 255)
        )
        surface.blit(score_text, (20, 10))

        # Timer top-right
        timer_text = self._font_timer.render(
            f"{self.time_remaining:.1f}s", True, (255, 255, 255)
        )
        timer_rect = timer_text.get_rect()
        timer_rect.topright = (self._screen_width - 20, 10)
        surface.blit(timer_text, timer_rect)

    def _draw_game_over(self, surface: pygame.Surface) -> None:
        # Semi-transparent overlay for readability
        overlay = pygame.Surface(
            (self._screen_width, self._screen_height), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        cx = self._screen_width // 2
        cy = self._screen_height // 2

        title = self._font_game_over.render("GAME OVER", True, (255, 255, 255))
        title_rect = title.get_rect(center=(cx, cy - 80))
        surface.blit(title, title_rect)

        score = self._font_final_score.render(
            f"Final Score: {self._score}", True, (255, 220, 120)
        )
        score_rect = score.get_rect(center=(cx, cy + 10))
        surface.blit(score, score_rect)

        restart = self._font_restart.render(
            "Press R to Restart", True, (200, 200, 200)
        )
        restart_rect = restart.get_rect(center=(cx, cy + 80))
        surface.blit(restart, restart_rect)
