import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from window_accessibility import (
    ARMED_STATE,
    ACTIVE_STATE,
    AccessibleWindow,
    AccessibleWindowController,
)


class AccessibleWindowSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.windows = [
            AccessibleWindow(
                "Google Chrome",
                "Green Man settings - Google Chrome",
                ":1.11",
                "/org/a11y/atspi/window/1",
            ),
            AccessibleWindow(
                "Visual Studio Code",
                "Preview README.md - GreenMan - Visual Studio Code",
                ":1.12",
                "/org/a11y/atspi/window/2",
            ),
            AccessibleWindow(
                "Local Green Man Assistant",
                "Local Green Man Assistant",
                ":1.13",
                "/org/a11y/atspi/window/3",
            ),
        ]

    def test_selects_exact_title_before_partial_matches(self) -> None:
        selected = AccessibleWindowController.select_window(
            self.windows, "Green Man settings - Google Chrome", "Local Green Man Assistant"
        )

        self.assertEqual(selected, self.windows[0])

    def test_unique_application_match_selects_its_window(self) -> None:
        selected = AccessibleWindowController.select_window(
            self.windows, "Google Chrome", "Local Green Man Assistant"
        )

        self.assertEqual(selected, self.windows[0])

    def test_ambiguous_application_match_requires_a_title(self) -> None:
        windows = [
            self.windows[0],
            AccessibleWindow(
                "Google Chrome",
                "Downloads - Google Chrome",
                ":1.11",
                "/org/a11y/atspi/window/4",
            ),
        ]

        with self.assertRaisesRegex(ValueError, "matches multiple windows"):
            AccessibleWindowController.select_window(
                windows, "Google Chrome", "Local Green Man Assistant"
            )

    def test_cannot_select_green_man(self) -> None:
        with self.assertRaisesRegex(ValueError, "Green Man's own window"):
            AccessibleWindowController.select_window(
                self.windows, "Local Green Man Assistant", "Local Green Man Assistant"
            )

    def test_missing_and_empty_queries_are_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "No accessible window"):
            AccessibleWindowController.select_window(
                self.windows, "Firefox", "Local Green Man Assistant"
            )

        with self.assertRaisesRegex(ValueError, "Provide a window title"):
            AccessibleWindowController.select_window(
                self.windows, "  ", "Local Green Man Assistant"
            )

    def test_focus_requires_accessibility_to_confirm_active_window(self) -> None:
        controller = AccessibleWindowController()
        session_bus = Mock()
        accessibility_bus = Mock()
        component = Mock()
        component.call_grab_focus = AsyncMock(return_value=True)
        accessible = Mock()
        accessible.call_get_state = AsyncMock(return_value=[ACTIVE_STATE, 0])
        controller._connect = AsyncMock(
            return_value=(session_bus, accessibility_bus)
        )
        controller._list_windows_on_bus = AsyncMock(
            return_value=[self.windows[0]]
        )
        controller._interface = AsyncMock(side_effect=[component, accessible])

        selected = asyncio.run(
            controller._focus_window(
                self.windows[0].title, "Local Green Man Assistant"
            )
        )

        self.assertEqual(selected, self.windows[0])
        component.call_grab_focus.assert_awaited_once_with()
        session_bus.disconnect.assert_called_once_with()
        accessibility_bus.disconnect.assert_called_once_with()

    def test_focus_failure_does_not_claim_window_is_active(self) -> None:
        launcher = Mock()
        launcher.list_applications.return_value = ["chrome"]
        launcher.resolve_application.return_value = "chrome"
        controller = AccessibleWindowController(launcher)
        session_bus = Mock()
        accessibility_bus = Mock()
        component = Mock()
        component.call_grab_focus = AsyncMock(return_value=True)
        accessible = Mock()
        accessible.call_get_state = AsyncMock(return_value=[0, 0])
        current_accessible = Mock()
        current_accessible.call_get_state = AsyncMock(return_value=[0, 0])
        controller._connect = AsyncMock(
            return_value=(session_bus, accessibility_bus)
        )
        controller._list_windows_on_bus = AsyncMock(
            side_effect=[[self.windows[0]], [self.windows[0]]]
        )
        controller._interface = AsyncMock(
            side_effect=[component, accessible, current_accessible]
        )

        with self.assertRaisesRegex(RuntimeError, "same window became active"):
            asyncio.run(
                controller._focus_window(
                    self.windows[0].title, "Local Green Man Assistant"
                )
            )

        launcher.launch.assert_not_called()
        session_bus.disconnect.assert_called_once_with()
        accessibility_bus.disconnect.assert_called_once_with()

    def test_armed_state_does_not_count_as_active_window(self) -> None:
        launcher = Mock()
        launcher.list_applications.return_value = ["chrome"]
        launcher.resolve_application.return_value = "chrome"
        controller = AccessibleWindowController(launcher)
        session_bus = Mock()
        accessibility_bus = Mock()
        component = Mock()
        component.call_grab_focus = AsyncMock(return_value=True)
        accessible = Mock()
        accessible.call_get_state = AsyncMock(return_value=[ARMED_STATE, 0])
        current_accessible = Mock()
        current_accessible.call_get_state = AsyncMock(return_value=[ARMED_STATE, 0])
        controller._connect = AsyncMock(
            return_value=(session_bus, accessibility_bus)
        )
        controller._list_windows_on_bus = AsyncMock(
            side_effect=[[self.windows[0]], [self.windows[0]]]
        )
        controller._interface = AsyncMock(
            side_effect=[component, accessible, current_accessible]
        )

        with self.assertRaisesRegex(RuntimeError, "No close shortcut was sent"):
            asyncio.run(
                controller._focus_window(
                    self.windows[0].title, "Local Green Man Assistant"
                )
            )

        launcher.launch.assert_not_called()
        session_bus.disconnect.assert_called_once_with()
        accessibility_bus.disconnect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
