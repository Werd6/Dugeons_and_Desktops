"""A floating skull focus using the regular sorcerer's casting animation."""

from dungeons_desktops.rig.equipment import FireOrb


class SkullFocus(FireOrb):
    name = "floating skull"
    missile_kind = "life_drain"

    NORMAL_DURATION = 0.7
    NORMAL_RELEASE = 0.3
    RAPID_DURATION = 0.32
    RAPID_RELEASE = 0.11

    def set_rapid(self, rapid: bool) -> None:
        """Tighten both windup and recovery for the rotation's closing volley."""
        self.duration = self.RAPID_DURATION if rapid else self.NORMAL_DURATION
        self.release_time = self.RAPID_RELEASE if rapid else self.NORMAL_RELEASE
