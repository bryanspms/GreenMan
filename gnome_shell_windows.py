from __future__ import annotations

import asyncio
import json

from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

BUS_NAME = "com.greenman.Windows"
OBJECT_PATH = "/com/greenman/Windows"
INTERFACE = "com.greenman.Windows"


class GnomeShellWindows:
    """Client for the optional Green Man GNOME Shell extension."""

    def is_available(self) -> bool:
        try:
            asyncio.run(self._call("List"))
        except Exception:
            return False
        return True

    def activate(self, title: str) -> None:
        self._check(asyncio.run(self._call("Activate", title)), title, "activate")

    def close(self, title: str) -> None:
        self._check(asyncio.run(self._call("Close", title)), title, "close")

    def has_window(self, title: str) -> bool:
        windows = json.loads(asyncio.run(self._call("List")))
        return any(window.get("title") == title for window in windows)

    @staticmethod
    def _check(result: str, title: str, action: str) -> None:
        if result == "ok":
            return
        reasons = {
            "not_found": "no window with that exact title exists",
            "ambiguous": "several windows share that exact title",
        }
        raise RuntimeError(
            f"Could not {action} {title!r}: {reasons.get(result, result)}."
        )

    async def _call(self, method: str, *args: str) -> str:
        bus = await MessageBus().connect()
        try:
            introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
            proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
            interface = proxy.get_interface(INTERFACE)
            return await getattr(interface, f"call_{method.lower()}")(*args)
        except DBusError as error:
            raise RuntimeError(f"Green Man shell extension error: {error.text}") from error
        finally:
            bus.disconnect()
