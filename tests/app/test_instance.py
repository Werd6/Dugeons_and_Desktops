from pathlib import Path

from PySide6.QtWidgets import QApplication

from dungeons_desktops.desktop.instance import (
    INSTANCE_SERVER,
    acquire_desktop_instance,
    acquire_desktop_lock,
    notify_running_desktop,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_second_launch_wakes_the_running_desktop(tmp_path: Path):
    app = _app()
    path = tmp_path / "desktop.lock"
    woken: list[bool] = []
    instance = acquire_desktop_instance(lambda: woken.append(True), path=path)
    assert instance is not None

    try:
        assert notify_running_desktop()
        app.processEvents()
        assert woken == [True]
        assert acquire_desktop_instance(lambda: None, path=path) is None
    finally:
        instance.server.close()
        QApplication.instance()  # keep app alive
        from PySide6.QtNetwork import QLocalServer

        QLocalServer.removeServer(INSTANCE_SERVER)
        instance.lock.unlock()


def test_desktop_instance_lock_rejects_a_second_owner(tmp_path: Path):
    path = tmp_path / "desktop.lock"
    first = acquire_desktop_lock(path)
    assert first is not None

    try:
        assert acquire_desktop_lock(path) is None
    finally:
        first.unlock()

    replacement = acquire_desktop_lock(path)
    assert replacement is not None
    replacement.unlock()


def test_notification_fails_without_a_running_desktop():
    from PySide6.QtNetwork import QLocalServer

    QLocalServer.removeServer(INSTANCE_SERVER)
    _app()
    assert not notify_running_desktop()
