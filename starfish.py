"""Starfish entity: star-shaped polygon with sine-curve bobbing animation."""

import math
import random
from typing import Optional

import pygame


class Starfish:
    """A single starfish that bobs on a sine curve and can be tapped.

    The starfish is drawn as a 5-pointed orange star polygon. It has a
    5-second lifespan after which `alive` becomes False; the owner is
    expected to call `respawn()` to put it in a new random position.
    """

    LIFESPAN: float = 5.0          # seconds
    HIT_RADIUS: int = 40           # pixels (~2/3 of previous 60)
    NUM_POINTS: int = 5
    OUTER_RADIUS: int = 34         # ~2/3 of previous 50 (for projector)
    INNER_RADIUS: int = 17         # ~2/3 of previous 25
    COLOR = (255, 140, 0)          # orange
    OUTLINE_COLOR = (200, 80, 0)
    BOB_AMPLITUDE: float = 20.0    # pixels
    BOB_SPEED: float = 2.0         # radians per second
    ROTATION_SPEED: float = 0.5    # radians per second
    FADE_OUT_TIME: float = 1.0     # fade during last N seconds of life

    # Margins to keep starfish away from the UI areas
    MARGIN_TOP: int = 80
    MARGIN_BOTTOM: int = 200       # leaves room for the debug preview
    MARGIN_SIDE: int = 80

    def __init__(self, screen_width: int = 1280, screen_height: int = 720) -> None:
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._base_x: float = 0.0
        self._base_y: float = 0.0
        self._age: float = 0.0
        self._bob_phase: float = 0.0
        self._rotation: float = 0.0
        self.respawn()

    @property
    def alive(self) -> bool:
        return self._age < self.LIFESPAN

    @property
    def center(self) -> tuple[float, float]:
        cx = self._base_x
        cy = self._base_y + self.BOB_AMPLITUDE * math.sin(self._bob_phase)
        return (cx, cy)

    def update(self, dt: float) -> None:
        self._age += dt
        self._bob_phase += self.BOB_SPEED * dt
        self._rotation += self.ROTATION_SPEED * dt

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self.center
        points = self._star_polygon_points(
            cx, cy,
            self.OUTER_RADIUS, self.INNER_RADIUS,
            self.NUM_POINTS, self._rotation,
        )

        # In the final FADE_OUT_TIME seconds of life, fade the starfish out so
        # the player can visually distinguish natural expiry from a tap hit
        # (which produces a white flash + score popup instead).
        remaining = self.LIFESPAN - self._age
        if remaining < self.FADE_OUT_TIME:
            progress = max(0.0, remaining / self.FADE_OUT_TIME)
            alpha = int(70 + 185 * progress)  # 255 -> 70
            pad = 4
            box = self.OUTER_RADIUS * 2 + pad * 2
            temp = pygame.Surface((box, box), pygame.SRCALPHA)
            offset_x = box / 2.0 - cx
            offset_y = box / 2.0 - cy
            local = [(p[0] + offset_x, p[1] + offset_y) for p in points]
            pygame.draw.polygon(temp, (*self.COLOR, alpha), local)
            pygame.draw.polygon(temp, (*self.OUTLINE_COLOR, alpha), local, width=2)
            surface.blit(temp, (cx - box / 2.0, cy - box / 2.0))
        else:
            pygame.draw.polygon(surface, self.COLOR, points)
            pygame.draw.polygon(surface, self.OUTLINE_COLOR, points, width=2)

    def check_hit(self, point: Optional[tuple[int, int]]) -> bool:
        if point is None:
            return False
        cx, cy = self.center
        dx = point[0] - cx
        dy = point[1] - cy
        return (dx * dx + dy * dy) <= (self.HIT_RADIUS * self.HIT_RADIUS)

    def respawn(self) -> None:
        min_x = self.MARGIN_SIDE
        max_x = self._screen_width - self.MARGIN_SIDE
        min_y = self.MARGIN_TOP
        max_y = self._screen_height - self.MARGIN_BOTTOM
        self._base_x = float(random.randint(min_x, max_x))
        self._base_y = float(random.randint(min_y, max_y))
        self._age = 0.0
        self._bob_phase = random.uniform(0.0, 2.0 * math.pi)
        self._rotation = random.uniform(0.0, 2.0 * math.pi)

    @staticmethod
    def _star_polygon_points(
        cx: float,
        cy: float,
        outer_r: float,
        inner_r: float,
        num_points: int,
        rotation: float = 0.0,
    ) -> list[tuple[float, float]]:
        total_vertices = num_points * 2
        step = (2.0 * math.pi) / total_vertices
        start = rotation - (math.pi / 2.0)
        points: list[tuple[float, float]] = []
        for i in range(total_vertices):
            angle = start + i * step
            r = outer_r if (i % 2 == 0) else inner_r
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return points


def _standalone_test() -> None:
    pygame.init()
    width, height = 1280, 720
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Starfish Test")
    clock = pygame.time.Clock()

    fish = [Starfish(width, height) for _ in range(3)]
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        for f in fish:
            f.update(dt)
            if not f.alive:
                f.respawn()

        screen.fill((10, 20, 60))
        for f in fish:
            f.draw(screen)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    _standalone_test()
