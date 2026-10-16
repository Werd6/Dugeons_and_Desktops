"""Import and dependency boundaries for the feature-first package layout."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[4] / "src" / "dungeons_desktops"


def imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_simulation_has_no_qt_dependency():
    for path in (SOURCE / "game" / "world").glob("*.py"):
        assert all(not name.startswith("PySide6") for name in imports(path)), path


def test_feature_renderers_do_not_import_scene_dispatch():
    for path in (SOURCE / "game").glob("**/render.py"):
        assert "dungeons_desktops.render.scene" not in imports(path), path


def test_canonical_source_does_not_import_compatibility_modules():
    roots = [SOURCE / "game", SOURCE / "desktop", SOURCE / "preview", SOURCE / "render"]
    forbidden = (
        "dungeons_desktops.systems",
        "dungeons_desktops.creatures",
        "dungeons_desktops.render.draw",
        "dungeons_desktops.rig.weapons",
    )
    for root in roots:
        for path in root.glob("**/*.py"):
            if path == SOURCE / "render" / "draw.py":
                continue
            for name in imports(path):
                assert not name.startswith(forbidden), (path, name)


def test_foundation_packages_do_not_import_game_features():
    for package in ("core", "navigation", "rig"):
        for path in (SOURCE / package).glob("**/*.py"):
            assert all(
                not name.startswith("dungeons_desktops.game") for name in imports(path)
            ), path


@pytest.mark.parametrize("reverse", [False, True])
def test_all_canonical_modules_import_in_fresh_process(reverse: bool):
    code = f"""
import importlib, pkgutil
import dungeons_desktops.game as game
names = [m.name for m in pkgutil.walk_packages(game.__path__, game.__name__ + '.')]
names += [
    'dungeons_desktops.render.primitives',
    'dungeons_desktops.render.equipment',
    'dungeons_desktops.render.effects',
    'dungeons_desktops.render.hud',
    'dungeons_desktops.render.scene',
]
for name in sorted(set(names), reverse={reverse!r}):
    importlib.import_module(name)
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
