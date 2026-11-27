from __future__ import annotations

import argparse
import sys


def main() -> int:
    frozen = bool(getattr(sys, "frozen", False))
    parser = argparse.ArgumentParser(
        prog="dungeons_desktops",
        description="Dungeons & Desktops desktop pet",
    )
    parser.add_argument(
        "--quit-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="close automatically (used for smoke tests)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--desktop",
        action="store_true",
        help="desktop pet: monsters hunting stickmen across your real windows",
    )
    mode.add_argument(
        "--mock-desktop",
        action="store_true",
        help="desktop pet on made-up windows (outlined) instead of your real ones",
    )
    mode.add_argument(
        "--preview",
        action="store_true",
        help="open the creature rig preview (local development)",
    )
    args = parser.parse_args()

    if frozen or args.desktop or args.mock_desktop:
        from dungeons_desktops.desktop.overlay import run_desktop

        return run_desktop(
            quit_after=args.quit_after,
            mock=bool(args.mock_desktop) and not frozen,
        )

    # Opening the app again while the desktop overlay is running shows the menu
    # instead of starting a second process / preview.
    if args.quit_after is None:
        from dungeons_desktops.desktop.instance import notify_running_desktop

        if notify_running_desktop():
            return 0

    from dungeons_desktops.preview.window import run_preview

    return run_preview(quit_after=args.quit_after)


if __name__ == "__main__":
    raise SystemExit(main())
