import os
import subprocess
import struct
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

from dbus_next import Message, MessageType

from wayland_portal import (
    WaylandDesktopPortal,
    keysym_for_character,
    png_dimensions,
    pointer_coordinates,
    pipewire_serial_for_node,
    process_output_text,
)


class WaylandPortalUtilityTests(unittest.TestCase):
    def test_dbus_call_resolves_unix_fd_index_to_descriptor(self) -> None:
        portal = WaylandDesktopPortal.__new__(WaylandDesktopPortal)
        reply = Message(
            message_type=MessageType.METHOD_RETURN,
            reply_serial=1,
            signature="h",
            body=[0],
            unix_fds=[42],
        )
        portal._bus = AsyncMock()
        portal._bus.call.return_value = reply

        result = asyncio.run(
            portal._call("org.example.Interface", "Method", "", [])
        )

        self.assertEqual(result, [42])

    def test_dbus_call_rejects_unix_fd_index_without_descriptor(self) -> None:
        portal = WaylandDesktopPortal.__new__(WaylandDesktopPortal)
        reply = Message(
            message_type=MessageType.METHOD_RETURN,
            reply_serial=1,
            signature="h",
            body=[0],
            unix_fds=[],
        )
        portal._bus = AsyncMock()
        portal._bus.call.return_value = reply

        with self.assertRaisesRegex(RuntimeError, "invalid file descriptor index"):
            asyncio.run(portal._call("org.example.Interface", "Method", "", []))

    def test_png_dimensions_reads_ihdr(self) -> None:
        image = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 1920, 1080)
        )
        self.assertEqual(png_dimensions(image), (1920, 1080))

    def test_png_dimensions_rejects_invalid_data(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "valid PNG"):
            png_dimensions(b"not a png")

    def test_keysym_for_ascii_and_unicode(self) -> None:
        self.assertEqual(keysym_for_character("A"), ord("A"))
        self.assertEqual(keysym_for_character("\n"), 0xFF0D)
        self.assertEqual(keysym_for_character("é"), ord("é"))
        self.assertEqual(keysym_for_character("中"), 0x01004E2D)

    def test_keysym_rejects_control_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "control character"):
            keysym_for_character("\x01")

    def test_pointer_coordinates_scale_to_logical_size(self) -> None:
        self.assertEqual(
            pointer_coordinates(100, 50, (200, 100), (100, 50)),
            (50.0, 25.0),
        )

    def test_pointer_coordinates_reject_out_of_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "screenshot size 200x100"):
            pointer_coordinates(200, 50, (200, 100), (200, 100))

    def test_process_output_text_decodes_timeout_bytes(self) -> None:
        self.assertEqual(process_output_text(b"PipeWire: no frame"), "PipeWire: no frame")

    def test_process_output_text_handles_missing_output(self) -> None:
        self.assertEqual(process_output_text(None), "")

    def test_pipewire_serial_resolves_node_metadata(self) -> None:
        result = subprocess.CompletedProcess(
            ["pw-cli", "info", "73"],
            0,
            stdout='id: 73\n*\t\tobject.serial = "95"\n',
            stderr="",
        )
        with (
            patch("wayland_portal.shutil.which", return_value="/usr/bin/pw-cli"),
            patch("wayland_portal.subprocess.run", return_value=result) as run,
        ):
            self.assertEqual(pipewire_serial_for_node(73), "95")
        run.assert_called_once_with(
            ["/usr/bin/pw-cli", "info", "73"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    def test_pipewire_serial_requires_pw_cli_when_portal_omits_serial(self) -> None:
        with (
            patch("wayland_portal.shutil.which", return_value=None),
            self.assertRaisesRegex(RuntimeError, "pipewire-bin on Ubuntu"),
        ):
            pipewire_serial_for_node(73)

    def test_pipewire_serial_reports_missing_serial(self) -> None:
        result = subprocess.CompletedProcess(
            ["pw-cli", "info", "73"], 0, stdout="id: 73\n", stderr=""
        )
        with (
            patch("wayland_portal.shutil.which", return_value="/usr/bin/pw-cli"),
            patch("wayland_portal.subprocess.run", return_value=result),
            self.assertRaisesRegex(RuntimeError, "did not report a serial"),
        ):
            pipewire_serial_for_node(73)

    def test_capture_timeout_includes_gstreamer_output(self) -> None:
        portal = WaylandDesktopPortal.__new__(WaylandDesktopPortal)
        portal._pipewire_fd = os.open(os.devnull, os.O_RDONLY)
        portal._target_object = "monitor"
        portal._stream_id = 1
        try:
            with (
                patch("wayland_portal.shutil.which", return_value="/usr/bin/gst-launch-1.0"),
                patch(
                    "wayland_portal.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(
                        "gst-launch-1.0", 20, output=b"pipeline output", stderr=b"capture error"
                    ),
                ),
                self.assertRaisesRegex(
                    RuntimeError, "(?s)GStreamer output:.*pipeline output.*capture error"
                ),
            ):
                portal._capture_png()
        finally:
            os.close(portal._pipewire_fd)

    def test_capture_targets_pipewire_serial_when_available(self) -> None:
        portal = WaylandDesktopPortal.__new__(WaylandDesktopPortal)
        portal._pipewire_fd = os.open(os.devnull, os.O_RDONLY)
        portal._target_object = "95"
        portal._stream_id = 73
        portal._image_size = None
        image = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 10, 10)
        )

        def capture(command, **kwargs):
            self.assertEqual(kwargs["env"]["GST_DEBUG"], "2,pipewiresrc:5")
            filename = next(
                arg.removeprefix("location=")
                for arg in command
                if arg.startswith("location=")
            )
            with open(filename, "wb") as output:
                output.write(image)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        try:
            with (
                patch("wayland_portal.shutil.which", return_value="/usr/bin/gst-launch-1.0"),
                patch("wayland_portal.subprocess.run", side_effect=capture) as run,
            ):
                self.assertEqual(portal._capture_png(), image)
            command = run.call_args.args[0]
            self.assertIn("target-object=95", command)
            self.assertNotIn("path=73", command)
        finally:
            os.close(portal._pipewire_fd)

    def test_capture_timeout_without_output_suggests_restarting_app(self) -> None:
        portal = WaylandDesktopPortal.__new__(WaylandDesktopPortal)
        portal._pipewire_fd = os.open(os.devnull, os.O_RDONLY)
        portal._target_object = "monitor"
        portal._stream_id = 1
        try:
            with (
                patch("wayland_portal.shutil.which", return_value="/usr/bin/gst-launch-1.0"),
                patch(
                    "wayland_portal.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("gst-launch-1.0", 20),
                ),
                self.assertRaisesRegex(
                    RuntimeError, "GStreamer produced no diagnostic output"
                ),
            ):
                portal._capture_png()
        finally:
            os.close(portal._pipewire_fd)


if __name__ == "__main__":
    unittest.main()
