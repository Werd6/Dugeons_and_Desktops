"""Single-instance coordination for the desktop overlay."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

INSTANCE_NAME = "dungeons-desktops"
INSTANCE_LOCK = Path(tempfile.gettempdir()) / f"{INSTANCE_NAME}.lock"
INSTANCE_SERVER = f"{INSTANCE_NAME}-wake"
MENU_COMMAND = b"menu\n"


@dataclass
class DesktopInstance:
    """Holds the process lock and the local wake server for a primary launch."""

    lock: QLockFile
    server: QLocalServer


def notify_running_desktop(_path: Path = INSTANCE_LOCK) -> bool:
    """Ask the primary desktop process to show its settings menu."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_SERVER)
    if not socket.waitForConnected(300):
        return False
    socket.write(MENU_COMMAND)
    socket.waitForBytesWritten(300)
    socket.flush()
    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(300)
    return True


def acquire_desktop_lock(path: Path = INSTANCE_LOCK) -> QLockFile | None:
    """Hold the desktop-instance lock, or return ``None`` for a secondary launch."""
    lock = QLockFile(str(path))
    if lock.tryLock(0):
        return lock
    if lock.removeStaleLockFile() and lock.tryLock(0):
        return lock
    return None


def acquire_desktop_instance(
    on_menu: Callable[[], None],
    path: Path = INSTANCE_LOCK,
) -> DesktopInstance | None:
    """Become the primary desktop process, or return ``None`` if one is already running."""
    lock = acquire_desktop_lock(path)
    if lock is None:
        return None
    QLocalServer.removeServer(INSTANCE_SERVER)
    server = QLocalServer()
    if not server.listen(INSTANCE_SERVER):
        lock.unlock()
        return None

    def _accept() -> None:
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            if conn is None:
                continue
            if conn.waitForReadyRead(200):
                payload = bytes(conn.readAll())
                if MENU_COMMAND.strip() in payload or b"menu" in payload:
                    on_menu()
            conn.disconnectFromServer()

    server.newConnection.connect(_accept)
    return DesktopInstance(lock=lock, server=server)
