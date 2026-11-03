from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Any

from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

from desktop_applications import DesktopApplicationLauncher


AT_SPI_ROOT = "/org/a11y/atspi/accessible/root"
AT_SPI_REGISTRY = "org.a11y.atspi.Registry"
AT_SPI_ACCESSIBLE = "org.a11y.atspi.Accessible"
AT_SPI_COMPONENT = "org.a11y.atspi.Component"
ACTIVE_STATE = 1 << 0
ARMED_STATE = 1 << 1
WINDOW_ROLES = {"alert", "dialog", "frame", "window"}
FUZZY_MIN_SCORE = 0.78
FUZZY_MIN_MARGIN = 0.1
FUZZY_MIN_WORD_SCORE = 0.7
SUGGESTION_MIN_SCORE = 0.45


@dataclass(frozen=True)
class AccessibleWindow:
    application: str
    title: str
    bus_name: str
    object_path: str


class AccessibleWindowController:
    def __init__(
        self, application_launcher: DesktopApplicationLauncher | None = None
    ) -> None:
        self.application_launcher = (
            application_launcher or DesktopApplicationLauncher()
        )

    def list_windows(self) -> list[AccessibleWindow]:
        return asyncio.run(self._list_windows())

    def focus_window(self, query: str, protected_title: str) -> AccessibleWindow:
        return asyncio.run(self._focus_window(query, protected_title))

    @staticmethod
    def select_window(
        windows: list[AccessibleWindow], query: str, protected_title: str
    ) -> AccessibleWindow:
        query = query.strip()
        if not query:
            raise ValueError("Provide a window title or application name.")

        exact = [
            window for window in windows
            if window.title.casefold() == query.casefold()
        ]
        matches = exact or [
            window for window in windows
            if query.casefold() in window.title.casefold()
            or query.casefold() in window.application.casefold()
        ]
        if not matches:
            normalized = "".join(ch for ch in query.casefold() if ch.isalnum())
            matches = [
                window for window in windows
                if len(window.application) >= 3
                and "".join(
                    ch for ch in window.application.casefold() if ch.isalnum()
                ) in normalized
            ]
        if not matches:
            ranked = AccessibleWindowController.rank_windows(windows, query)
            if (
                ranked
                and ranked[0][0] >= FUZZY_MIN_SCORE
                and (
                    len(ranked) == 1
                    or ranked[0][0] - ranked[1][0] >= FUZZY_MIN_MARGIN
                )
            ):
                matches = [ranked[0][1]]
            else:
                suggestions = [
                    window for score, window in ranked[:3]
                    if score >= SUGGESTION_MIN_SCORE
                ]
                message = f"No accessible window matches {query!r}."
                if suggestions:
                    options = "\n".join(
                        f"- {window.application}: {window.title}"
                        for window in suggestions
                    )
                    message += f" Closest windows (use an exact title):\n{options}"
                raise ValueError(message)
        if len(matches) > 1:
            options = "\n".join(
                f"- {window.application}: {window.title}" for window in matches
            )
            raise ValueError(
                f"{query!r} matches multiple windows. Use a unique title:\n{options}"
            )

        target = matches[0]
        if (
            target.title.casefold() == protected_title.casefold()
            or "green man" in target.application.casefold()
            or "greenman" in target.application.casefold()
        ):
            raise ValueError("Green Man's own window cannot be targeted.")
        return target

    @staticmethod
    def rank_windows(
        windows: list[AccessibleWindow], query: str
    ) -> list[tuple[float, AccessibleWindow]]:
        """Score windows by how closely they resemble a query, best first.

        Each query word is compared with the closest word of the window's
        application name and title, so typos, missing words and reordered words
        still score well. A window where any query word has no
        close counterpart is penalized.
        """

        def words(text: str) -> list[str]:
            return re.findall(r"[a-z0-9]+", text.casefold())

        query_words = words(query)
        if not query_words:
            return []
        scored: list[tuple[float, AccessibleWindow]] = []
        for window in windows:
            candidates = words(f"{window.application} {window.title}")
            if not candidates:
                continue
            word_scores = [
                max(
                    SequenceMatcher(None, word, candidate).ratio()
                    for candidate in candidates
                )
                for word in query_words
            ]
            score = sum(word_scores) / len(word_scores)
            if min(word_scores) < FUZZY_MIN_WORD_SCORE:
                score *= 0.75
            scored.append((score, window))
        return sorted(
            scored,
            key=lambda item: (-item[0], item[1].application, item[1].title),
        )

    async def _connect(self) -> tuple[MessageBus, MessageBus]:
        session_bus = await MessageBus().connect()
        try:
            introspection = await session_bus.introspect(
                "org.a11y.Bus", "/org/a11y/bus"
            )
            bus_object = session_bus.get_proxy_object(
                "org.a11y.Bus", "/org/a11y/bus", introspection
            )
            address = await bus_object.get_interface(
                "org.a11y.Bus"
            ).call_get_address()
            accessibility_bus = await MessageBus(bus_address=address).connect()
        except Exception as error:
            session_bus.disconnect()
            raise RuntimeError(
                "Could not connect to the desktop accessibility service. "
                "Enable accessibility support (AT-SPI) in the desktop session."
            ) from error
        return session_bus, accessibility_bus

    async def _list_windows(self) -> list[AccessibleWindow]:
        session_bus, accessibility_bus = await self._connect()
        try:
            windows = await self._list_windows_on_bus(accessibility_bus)
            return sorted(
                windows,
                key=lambda item: (
                    item.application.casefold(),
                    item.title.casefold(),
                ),
            )
        finally:
            accessibility_bus.disconnect()
            session_bus.disconnect()

    async def _focus_window(
        self, query: str, protected_title: str
    ) -> AccessibleWindow:
        session_bus, accessibility_bus = await self._connect()
        try:
            windows = await self._list_windows_on_bus(accessibility_bus)
            target = self.select_window(windows, query, protected_title)

            component = await self._interface(
                accessibility_bus,
                target.bus_name,
                target.object_path,
                AT_SPI_COMPONENT,
            )
            try:
                focused = await component.call_grab_focus()
            except DBusError:
                # Wayland compositors may refuse focus requests from AT-SPI.
                focused = False
            if focused:
                await asyncio.sleep(0.15)
            accessible = await self._interface(
                accessibility_bus,
                target.bus_name,
                target.object_path,
                AT_SPI_ACCESSIBLE,
            )
            states = await accessible.call_get_state()
            if states and states[0] & ACTIVE_STATE:
                return target

            raise RuntimeError(
                f"Could not safely activate {target.title!r}. Desktop "
                "accessibility could not confirm that the same window became "
                "active. No close shortcut was sent, and the application was not "
                "launched."
            )
        finally:
            accessibility_bus.disconnect()
            session_bus.disconnect()

    async def _list_windows_on_bus(
        self, accessibility_bus: MessageBus
    ) -> list[AccessibleWindow]:
        root = await self._interface(
            accessibility_bus, AT_SPI_REGISTRY, AT_SPI_ROOT, AT_SPI_ACCESSIBLE
        )
        windows: list[AccessibleWindow] = []
        for app_bus, app_path in await root.call_get_children():
            app = await self._interface(
                accessibility_bus, app_bus, app_path, AT_SPI_ACCESSIBLE
            )
            application = (await app.get_name()).strip()
            for window_bus, window_path in await app.call_get_children():
                window = await self._interface(
                    accessibility_bus,
                    window_bus,
                    window_path,
                    AT_SPI_ACCESSIBLE,
                )
                role = (await window.call_get_role_name()).casefold()
                title = (await window.get_name()).strip()
                if title and role in WINDOW_ROLES:
                    windows.append(
                        AccessibleWindow(
                            application, title, window_bus, window_path
                        )
                    )
        return windows

    @staticmethod
    async def _interface(
        bus: MessageBus, bus_name: str, object_path: str, interface: str
    ) -> Any:
        introspection = await bus.introspect(bus_name, object_path)
        proxy = bus.get_proxy_object(bus_name, object_path, introspection)
        return proxy.get_interface(interface)
