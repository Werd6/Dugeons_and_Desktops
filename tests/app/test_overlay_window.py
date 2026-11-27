from types import SimpleNamespace

from dungeons_desktops.desktop import overlay


def test_native_macos_overlay_accepts_native_qt_platform_names(monkeypatch):
    monkeypatch.setattr(overlay.sys, "platform", "darwin")

    assert overlay._supports_native_macos_overlay("cocoa")
    assert overlay._supports_native_macos_overlay("macos")


def test_native_macos_overlay_rejects_headless_qt_platforms(monkeypatch):
    monkeypatch.setattr(overlay.sys, "platform", "darwin")

    assert not overlay._supports_native_macos_overlay("offscreen")
    assert not overlay._supports_native_macos_overlay("minimal")
    assert not overlay._supports_native_macos_overlay("vnc")


def test_native_overlay_is_disabled_off_macos(monkeypatch):
    monkeypatch.setattr(overlay.sys, "platform", "linux")

    assert not overlay._supports_native_macos_overlay("cocoa")


def test_native_overlay_uses_cross_application_fullscreen_role():
    appkit = SimpleNamespace(
        NSWindowCollectionBehaviorCanJoinAllSpaces=1,
        NSWindowCollectionBehaviorMoveToActiveSpace=2,
        NSWindowCollectionBehaviorFullScreenPrimary=128,
        NSWindowCollectionBehaviorFullScreenAuxiliary=256,
        NSWindowCollectionBehaviorFullScreenNone=512,
        NSWindowCollectionBehaviorStationary=16,
        NSWindowCollectionBehaviorIgnoresCycle=64,
        NSWindowCollectionBehaviorPrimary=65536,
        NSWindowCollectionBehaviorAuxiliary=131072,
        NSWindowCollectionBehaviorCanJoinAllApplications=262144,
    )

    behavior = overlay._native_overlay_collection_behavior(appkit, 2 | 128 | 256 | 65536)

    assert behavior & appkit.NSWindowCollectionBehaviorCanJoinAllApplications
    assert behavior & appkit.NSWindowCollectionBehaviorCanJoinAllSpaces
    assert not behavior & appkit.NSWindowCollectionBehaviorMoveToActiveSpace
    assert not behavior & appkit.NSWindowCollectionBehaviorFullScreenPrimary
    assert behavior & appkit.NSWindowCollectionBehaviorFullScreenAuxiliary
    assert not behavior & appkit.NSWindowCollectionBehaviorPrimary


def test_native_overlay_falls_back_to_legacy_fullscreen_auxiliary_role():
    appkit = SimpleNamespace(
        NSWindowCollectionBehaviorCanJoinAllSpaces=1,
        NSWindowCollectionBehaviorFullScreenAuxiliary=256,
        NSWindowCollectionBehaviorStationary=16,
        NSWindowCollectionBehaviorIgnoresCycle=64,
    )

    behavior = overlay._native_overlay_collection_behavior(appkit, 0)

    assert behavior == 1 | 16 | 64 | 256
