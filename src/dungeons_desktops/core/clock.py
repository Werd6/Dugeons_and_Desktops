"""Fixed-timestep accumulator shared by animation and physics."""

from __future__ import annotations


class FixedStepClock:
    def __init__(self, step: float = 1.0 / 60.0, max_steps: int = 5) -> None:
        self.step = step
        self.max_steps = max_steps
        self._accumulator = 0.0

    def advance(self, real_dt: float) -> int:
        """Return how many fixed steps to run for `real_dt` seconds of wall time.

        Excess time beyond `max_steps` is dropped so a stall or sleep does not
        produce a burst of catch-up motion.
        """
        self._accumulator += max(0.0, real_dt)
        steps = int(self._accumulator / self.step)
        if steps > self.max_steps:
            steps = self.max_steps
            self._accumulator = 0.0
        else:
            self._accumulator -= steps * self.step
        return steps
