"""Frozen-app entry: always launch the desktop pet (never the rig preview)."""

from __future__ import annotations

import sys


def main() -> int:
    from dungeons_desktops.desktop.overlay import run_desktop

    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
