from __future__ import annotations

import asyncio
import json
import re

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

    def activate_owned(self, title: str, pid: int) -> None:
        self._check(
            asyncio.run(self._call("ActivateOwned", title, pid)), title, "activate"
        )

    def require_owned_focus(self, title: str, pid: int) -> None:
        self._check(
            asyncio.run(self._call("IsOwnedFocused", title, pid)), title, "verify focus"
        )

    def check_owned_window(self, title: str, pid: int) -> None:
        result = asyncio.run(self._call("IsOwnedFocused", title, pid))
        if result != "not_focused":
            self._check(result, title, "find")

    def owned_geometry(self, title: str, pid: int) -> dict:
        try:
            result = json.loads(asyncio.run(self._call("OwnedGeometry", title, pid)))
        except (TypeError, ValueError) as error:
            raise RuntimeError("The GNOME extension returned invalid window geometry.") from error
        if not isinstance(result, dict) or not isinstance(result.get("status"), str):
            raise RuntimeError("The GNOME extension returned invalid window geometry.")
        self._check(result["status"], title, "find")
        for key in ("frame", "monitor"):
            rect = result.get(key)
            if (
                not isinstance(rect, list) or len(rect) != 4
                or any(type(value) is not int for value in rect)
                or rect[2] <= 0 or rect[3] <= 0
            ):
                raise RuntimeError("The GNOME extension returned invalid window geometry.")
        if type(result.get("monitor_count")) is not int or result["monitor_count"] < 1:
            raise RuntimeError("The GNOME extension returned invalid monitor information.")
        return result

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
            "wrong_process": "the window does not belong to the launched process",
            "not_focused": "the window does not have keyboard focus",
        }
        raise RuntimeError(
            f"Could not {action} {title!r}: {reasons.get(result, result)}."
        )

    async def _call(self, method: str, *args: str | int) -> str:
        bus = await MessageBus().connect()
        try:
            introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
            proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
            interface = proxy.get_interface(INTERFACE)
            try:
                snake_name = re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()
                method_call = getattr(interface, f"call_{snake_name}")
            except AttributeError as error:
                raise RuntimeError(
                    "The Green Man GNOME extension is out of date. Install the "
                    "updated extension and reload it before using Pong study mode."
                ) from error
            return await method_call(*args)
        except DBusError as error:
            raise RuntimeError(f"Green Man shell extension error: {error.text}") from error
        finally:
            bus.disconnect()
