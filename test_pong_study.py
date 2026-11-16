import asyncio
import base64
import io
import unittest
from threading import Event
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from app import DesktopAgent, prepare_pong_screenshot
from gnome_shell_windows import GnomeShellWindows


class PongStudyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DesktopAgent.__new__(DesktopAgent)
        self.agent.root = Mock()
        self.agent._finish = Mock()
        self.agent.cancel_event = Event()
        self.agent.cancel_event.wait = Mock(return_value=False)
        self.agent._execute_tool = Mock()
        self.agent._request_approval = Mock(return_value=True)
        self.agent.wayland_desktop = Mock()
        image = Image.new("RGB", (800, 600), "black")
        output = io.BytesIO()
        image.save(output, format="PNG")
        self.agent.wayland_desktop.screenshot.return_value = base64.b64encode(
            output.getvalue()
        ).decode()
        self.agent.wayland_desktop.screenshot_stream_geometry.return_value = (
            (0, 0), (800, 600)
        )
        self.process = Mock(pid=1234)
        self.process.poll.return_value = None
        self.shell = Mock()
        self.shell.is_available.return_value = True
        self.shell.owned_geometry.return_value = {
            "status": "ok", "frame": [0, 0, 800, 600],
            "monitor": [0, 0, 800, 600], "monitor_count": 1,
        }
        self.agent.shell_windows = self.shell
        self.action = {
            "message": {
                "tool_calls": [
                    {"function": {"name": "press_key", "arguments": {
                        "keys": "i", "duration_seconds": 0.3,
                        "ball_visible": True, "paddle_visible": True,
                    }}}
                ]
            }
        }
        self.agent._chat = Mock(return_value=self.action)

    def run_study(self) -> None:
        self.agent._run_pong_study("http://127.0.0.1:11434", "model", self.process)

    def error(self) -> str:
        return self.agent.root.after.call_args.args[3]

    def test_runs_more_than_normal_round_limit_until_cancelled(self) -> None:
        def stop_after_fifteen(*args) -> None:
            if self.agent.wayland_desktop.press_keys.call_count == 15:
                self.agent.cancel_event.set()

        self.agent.wayland_desktop.press_keys.side_effect = stop_after_fifteen
        self.run_study()
        self.assertEqual(self.agent.wayland_desktop.press_keys.call_count, 15)
        self.assertEqual(self.agent._chat.call_count, 15)
        self.assertEqual(self.agent.wayland_desktop.screenshot.call_count, 15)
        self.shell.activate_owned.assert_called_with("Pong", 1234)
        self.shell.require_owned_focus.assert_called_with("Pong", 1234)
        self.agent._request_approval.assert_called_with(
            "press_key",
            {
                "keys": "i", "duration_seconds": 0.3, "target_window": "Pong",
                "target_process_id": 1234, "focus_target_after_approval": True,
            },
        )
        self.assertTrue(self.agent.root.after.call_args.args[4])

    def test_denial_stops_without_focusing_or_sending_input(self) -> None:
        self.agent._request_approval.return_value = False
        self.run_study()
        self.assertIn("denied", self.error())
        self.assertEqual(self.shell.activate_owned.call_count, 1)
        self.agent.wayland_desktop.press_keys.assert_not_called()

    def test_model_can_choose_i_then_k(self) -> None:
        down_action = {
            "message": {"tool_calls": [
                {"function": {"name": "press_key", "arguments": {
                    "keys": "k", "duration_seconds": 0.2,
                    "ball_visible": True, "paddle_visible": True,
                }}}
            ]}
        }
        self.agent._chat.side_effect = [self.action, down_action]
        self.agent.wayland_desktop.press_keys.side_effect = (
            lambda *args: self.agent.cancel_event.set()
            if self.agent.wayland_desktop.press_keys.call_count == 2 else None
        )

        self.run_study()

        self.assertEqual(
            [call.args[:2] for call in self.agent.wayland_desktop.press_keys.call_args_list],
            [("i", 0.3), ("k", 0.2)],
        )

    def test_model_observation_is_shown_before_the_action(self) -> None:
        self.action["message"]["tool_calls"][0]["function"]["arguments"].update({
            "keys": "k",
            "observation": "The ball is below the right paddle.",
        })
        self.agent._request_approval.return_value = False

        self.run_study()

        self.agent.root.after.assert_any_call(
            0, self.agent._append, "Pong study",
            "Model observation: The ball is below the right paddle.",
        )
        tools = self.agent._chat.call_args.kwargs["tools"]
        for tool in tools:
            self.assertIn("observation", tool["function"]["parameters"]["required"])
        self.agent._request_approval.assert_called_once()

    def test_invalid_model_observation_stops_before_approval(self) -> None:
        self.action["message"]["tool_calls"][0]["function"]["arguments"]["observation"] = 42
        self.run_study()
        self.assertIn("observation must be text", self.error())
        self.agent._request_approval.assert_not_called()

    def test_missing_model_observation_is_visible(self) -> None:
        self.agent._request_approval.return_value = False
        self.run_study()
        self.agent.root.after.assert_any_call(
            0, self.agent._append, "Pong study",
            "Model observation: (not provided)",
        )

    def test_lost_focus_stops_without_sending_input(self) -> None:
        self.shell.require_owned_focus.side_effect = RuntimeError("not focused")
        self.run_study()
        self.assertIn("not focused", self.error())
        self.agent.wayland_desktop.press_keys.assert_not_called()

    def test_cancellation_after_approval_sends_no_input(self) -> None:
        self.agent._request_approval.side_effect = lambda *args: (
            self.agent.cancel_event.set() or True
        )
        self.run_study()
        self.assertEqual(self.shell.activate_owned.call_count, 1)
        self.agent.wayland_desktop.press_keys.assert_not_called()
        self.assertTrue(self.agent.root.after.call_args.args[4])

    def test_missing_tool_call_reports_model_response(self) -> None:
        self.agent._chat.return_value = {"message": {"content": "I cannot see Pong."}}
        self.run_study()
        self.assertIn("I cannot see Pong", self.error())
        self.agent._request_approval.assert_not_called()

    def test_invalid_key_or_duration_is_rejected(self) -> None:
        for key, duration in (("space", 0.2), ("i", 1), ("k", float("nan"))):
            with self.subTest(key=key, duration=duration):
                self.action["message"]["tool_calls"][0]["function"]["arguments"] = {
                    "keys": key, "duration_seconds": duration,
                    "ball_visible": True, "paddle_visible": True,
                }
                self.run_study()
                self.agent._request_approval.assert_not_called()
                self.agent.wayland_desktop.press_keys.assert_not_called()
                self.assertIsNotNone(self.error())

    def test_move_is_skipped_when_ball_or_paddle_is_not_visible(self) -> None:
        self.action["message"]["tool_calls"][0]["function"]["arguments"]["ball_visible"] = False
        self.agent.cancel_event.wait.side_effect = (
            lambda seconds: self.agent.cancel_event.set()
            if self.agent._chat.called and seconds == 0.2 else None
        )
        self.run_study()
        self.agent._request_approval.assert_not_called()
        self.agent.wayland_desktop.press_keys.assert_not_called()
        self.agent.root.after.assert_any_call(
            0, self.agent._append, "Pong study",
            "Move skipped: the model could not see both the ball and paddle.",
        )

    def test_move_requires_visibility_information(self) -> None:
        del self.action["message"]["tool_calls"][0]["function"]["arguments"]["paddle_visible"]
        self.run_study()
        self.assertIn("no key was sent", self.error())
        self.agent._request_approval.assert_not_called()

    def test_missing_or_outdated_focus_helper_stops_before_screenshot(self) -> None:
        self.shell.check_owned_window.side_effect = RuntimeError("extension out of date")
        self.run_study()
        self.assertIn("extension out of date", self.error())
        self.agent.wayland_desktop.screenshot.assert_not_called()

    def test_screenshot_failure_stops_before_model_call(self) -> None:
        self.agent.wayland_desktop.screenshot.side_effect = RuntimeError("capture failed")
        self.run_study()
        self.assertIn("capture failed", self.error())
        self.agent._chat.assert_not_called()

    def test_closed_pong_stops_study(self) -> None:
        self.process.poll.side_effect = [None, 0]
        self.run_study()
        self.assertIn("Pong closed", self.error())
        self.agent.wayland_desktop.screenshot.assert_not_called()

    def test_wait_can_be_cancelled_without_keyboard_input(self) -> None:
        self.agent._chat.return_value = {"message": {"tool_calls": [
            {"function": {"name": "wait", "arguments": {"seconds": 0.1}}}
        ]}}
        self.agent.cancel_event.wait.side_effect = (
            lambda seconds: self.agent.cancel_event.set() if seconds == 0.1 else None
        )
        self.run_study()
        self.agent.wayland_desktop.press_keys.assert_not_called()
        self.assertTrue(self.agent.root.after.call_args.args[4])

    def test_wait_remains_available_after_repeated_waits(self) -> None:
        self.agent._chat.return_value = {"message": {"tool_calls": [
            {"function": {"name": "wait", "arguments": {"seconds": 0.1}}}
        ]}}
        def wait(seconds) -> None:
            if seconds == 0.1 and self.agent._chat.call_count == 3:
                self.agent.cancel_event.set()
        self.agent.cancel_event.wait.side_effect = wait
        self.run_study()
        self.assertEqual(self.agent._chat.call_count, 3)
        self.assertEqual(
            [tool["function"]["name"] for tool in self.agent._chat.call_args.kwargs["tools"]],
            ["press_key", "wait"],
        )
        self.agent.wayland_desktop.press_keys.assert_not_called()


class PongScreenshotTests(unittest.TestCase):
    def test_crop_scales_monitor_coordinates_and_excludes_desktop(self) -> None:
        image = Image.new("RGB", (400, 200), "red")
        for x in range(100, 300):
            for y in range(40, 160):
                image.putpixel((x, y), (0, 0, 0))
        output = io.BytesIO()
        image.save(output, format="PNG")
        geometry = {
            "frame": [-150, 20, 100, 60],
            "monitor": [-200, 0, 200, 100],
            "monitor_count": 2,
        }
        encoded = prepare_pong_screenshot(
            base64.b64encode(output.getvalue()).decode(), geometry, (-200, 0), (200, 100)
        )
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as cropped:
            self.assertEqual(cropped.size, (1024, 614))
            self.assertEqual(cropped.getpixel((0, 0)), (0, 0, 0))
            self.assertEqual(cropped.getpixel((1023, 613)), (0, 0, 0))

    def test_rejects_unknown_or_wrong_shared_monitor(self) -> None:
        geometry = {
            "frame": [10, 10, 100, 60], "monitor": [0, 0, 200, 100],
            "monitor_count": 2,
        }
        with self.assertRaisesRegex(RuntimeError, "monitor position"):
            prepare_pong_screenshot("", geometry, None, (200, 100))
        with self.assertRaisesRegex(RuntimeError, "Share the monitor"):
            prepare_pong_screenshot("", geometry, (200, 0), (200, 100))
        geometry["frame"] = [190, 10, 100, 60]
        with self.assertRaisesRegex(RuntimeError, "entire Pong window"):
            prepare_pong_screenshot("", geometry, (0, 0), (200, 100))


class ShellFocusTests(unittest.TestCase):
    def test_owned_geometry_is_validated(self) -> None:
        shell = GnomeShellWindows()
        with patch.object(shell, "_call", new=AsyncMock(return_value=(
            '{"status":"ok","frame":[10,20,800,600],'
            '"monitor":[0,0,1920,1080],"monitor_count":1}'
        ))):
            self.assertEqual(shell.owned_geometry("Pong", 1234)["frame"], [10, 20, 800, 600])
        with patch.object(shell, "_call", new=AsyncMock(return_value='{"status":"wrong_process"}')):
            with self.assertRaisesRegex(RuntimeError, "does not belong"):
                shell.owned_geometry("Pong", 1234)
        with patch.object(shell, "_call", new=AsyncMock(return_value='{"status":"ok","frame":[]}')):
            with self.assertRaisesRegex(RuntimeError, "invalid window geometry"):
                shell.owned_geometry("Pong", 1234)

    def test_ownership_and_focus_errors_are_explicit(self) -> None:
        shell = GnomeShellWindows()
        with patch.object(shell, "_call", new=AsyncMock(return_value="not_focused")):
            shell.check_owned_window("Pong", 1234)
            with self.assertRaisesRegex(RuntimeError, "does not have keyboard focus"):
                shell.require_owned_focus("Pong", 1234)
        with patch.object(shell, "_call", new=AsyncMock(return_value="wrong_process")):
            with self.assertRaisesRegex(RuntimeError, "does not belong"):
                shell.activate_owned("Pong", 1234)

    def test_older_extension_reports_update_needed(self) -> None:
        bus = Mock()
        bus.introspect = AsyncMock()
        bus.get_proxy_object.return_value.get_interface.return_value = object()
        with patch("gnome_shell_windows.MessageBus") as factory:
            factory.return_value.connect = AsyncMock(return_value=bus)
            with self.assertRaisesRegex(RuntimeError, "out of date"):
                asyncio.run(GnomeShellWindows()._call("IsOwnedFocused", "Pong", 1234))


if __name__ == "__main__":
    unittest.main()
