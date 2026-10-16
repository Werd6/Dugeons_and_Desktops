"""Names and shared timing for adventurer condition state."""

from enum import StrEnum


class Condition(StrEnum):
    STUNNED = "stunned"
    THRALL = "thrall"
    BLIND = "blind"
    BURNING = "burning"
    ENGULFED = "engulfed"
    RAGDOLL = "ragdoll"


__all__ = ["Condition"]
