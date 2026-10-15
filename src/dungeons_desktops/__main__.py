from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="dungeons_desktops", description="Creature rig preview")
    parser.add_argument(
        "--quit-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="close the preview automatically (used for smoke tests)",
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
    args = parser.parse_args()

    if args.desktop or args.mock_desktop:
        from dungeons_desktops.desktop.overlay import run_desktop

        return run_desktop(quit_after=args.quit_after, mock=args.mock_desktop)

    from dungeons_desktops.preview.window import run_preview

    return run_preview(quit_after=args.quit_after)


if __name__ == "__main__":
    raise SystemExit(main())
