from __future__ import annotations

import asyncio
import base64
import os
import re
import secrets
import shutil
import struct
import subprocess
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Any

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus


PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"
SCREEN_CAST = "org.freedesktop.portal.ScreenCast"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
SESSION_INTERFACE = "org.freedesktop.portal.Session"
PIPEWIRE_INTERFACE = "org.freedesktop.portal.ScreenCast"
LEFT_BUTTON = 0x110


def png_dimensions(image: bytes) -> tuple[int, int]:
    if len(image) < 24 or image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR":
        raise RuntimeError("PipeWire did not return a valid PNG screenshot.")
    width, height = struct.unpack(">II", image[16:24])
    if width < 1 or height < 1:
        raise RuntimeError("PipeWire returned a screenshot with invalid dimensions.")
    return width, height


def keysym_for_character(character: str) -> int:
    if character == "\n" or character == "\r":
        return 0xFF0D
    if character == "\t":
        return 0xFF09
    if len(character) != 1:
        raise ValueError("Expected exactly one character.")
    if unicodedata.category(character).startswith("C"):
        raise ValueError(f"Cannot type control character U+{ord(character):04X}.")
    codepoint = ord(character)
    return codepoint if codepoint <= 0xFF else 0x01000000 | codepoint


def pointer_coordinates(
    x: int,
    y: int,
    image_size: tuple[int, int],
    logical_size: tuple[int, int],
) -> tuple[float, float]:
    image_width, image_height = image_size
    logical_width, logical_height = logical_size
    if not (0 <= x < image_width and 0 <= y < image_height):
        raise ValueError(
            f"Coordinates must be within the screenshot size "
            f"{image_width}x{image_height}."
        )
    logical_x = min(logical_width - 1, x * logical_width / image_width)
    logical_y = min(logical_height - 1, y * logical_height / image_height)
    return logical_x, logical_y


def process_output_text(output: str | bytes | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def pipewire_serial_for_node(node_id: int) -> str:
    pw_cli = shutil.which("pw-cli")
    if pw_cli is None:
        raise RuntimeError(
            "The desktop portal did not provide a PipeWire stream serial, and pw-cli "
            "is unavailable to resolve it. Install the PipeWire command-line tools "
            "(pipewire-bin on Ubuntu) and restart the app."
        )
    try:
        result = subprocess.run(
            [pw_cli, "info", str(node_id)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Timed out resolving PipeWire stream node {node_id}."
        ) from error
    except OSError as error:
        raise RuntimeError(f"Could not inspect PipeWire stream node {node_id}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip()[-1000:]
        raise RuntimeError(
            f"Could not inspect PipeWire stream node {node_id}."
            + (f"\n{detail}" if detail else "")
        )
    match = re.search(
        r'^\s*\*?\s*object\.serial\s*=\s*"([^"]+)"\s*$',
        result.stdout,
        re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(
            f"PipeWire did not report a serial for stream node {node_id}."
        )
    return match.group(1)


def _unpack(value: Any) -> Any:
    if isinstance(value, Variant):
        return _unpack(value.value)
    if isinstance(value, dict):
        return {key: _unpack(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_unpack(item) for item in value)
    return value


class WaylandDesktopPortal:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._bus: MessageBus | None = None
        self._pending_requests: dict[str, asyncio.Future[tuple[int, dict[str, Any]]]] = {}
        self._session_handle: str | None = None
        self._pipewire_fd: int | None = None
        self._stream_id: int | None = None
        self._target_object: str | None = None
        self._logical_size: tuple[int, int] | None = None
        self._image_size: tuple[int, int] | None = None
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _submit(self, coroutine: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(timeout=310)

    async def _connect(self) -> None:
        if self._bus is not None:
            return
        try:
            self._bus = await MessageBus(negotiate_unix_fd=True).connect()
        except Exception as error:
            raise RuntimeError(
                "Could not connect to the desktop portal. Start the app from your "
                "logged-in Wayland desktop session."
            ) from error
        self._bus.add_message_handler(self._on_message)

    def _on_message(self, message: Message) -> bool:
        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == REQUEST_INTERFACE
            and message.member == "Response"
            and message.path in self._pending_requests
        ):
            future = self._pending_requests[message.path]
            if not future.done():
                future.set_result((message.body[0], _unpack(message.body[1])))
            return True
        return False

    async def _call(
        self,
        interface: str,
        method: str,
        signature: str,
        body: list[Any],
        path: str = PORTAL_PATH,
    ) -> list[Any]:
        assert self._bus is not None
        reply = await self._bus.call(
            Message(
                destination=PORTAL_SERVICE,
                path=path,
                interface=interface,
                member=method,
                signature=signature,
                body=body,
            )
        )
        if reply is None:
            raise RuntimeError(f"The desktop portal did not reply to {method}.")
        if reply.message_type == MessageType.ERROR:
            detail = reply.body[0] if reply.body else reply.error_name
            raise RuntimeError(f"Desktop portal {method} failed: {detail}")
        if reply.signature == "h":
            if len(reply.body) != 1 or not isinstance(reply.body[0], int):
                raise RuntimeError(f"Desktop portal {method} returned an invalid file descriptor.")
            fd_index = reply.body[0]
            if fd_index < 0 or fd_index >= len(reply.unix_fds):
                raise RuntimeError(
                    f"Desktop portal {method} returned an invalid file descriptor index."
                )
            return [reply.unix_fds[fd_index]]
        return reply.body

    async def _request(
        self,
        interface: str,
        method: str,
        signature: str,
        body: list[Any],
        options: dict[str, Variant],
    ) -> dict[str, Any]:
        assert self._bus is not None and self._bus.unique_name is not None
        token = secrets.token_hex(12)
        options = {**options, "handle_token": Variant("s", token)}
        sender = self._bus.unique_name[1:].replace(".", "_")
        expected_path = f"{PORTAL_PATH}/request/{sender}/{token}"
        future: asyncio.Future[tuple[int, dict[str, Any]]] = self._loop.create_future()
        self._pending_requests[expected_path] = future
        try:
            result = await self._call(interface, method, signature, [*body, options])
            request_path = result[0]
            if request_path != expected_path:
                self._pending_requests[request_path] = future
            try:
                response, results = await asyncio.wait_for(future, timeout=300)
            except TimeoutError as error:
                raise RuntimeError(
                    f"Timed out waiting for the desktop portal to finish {method}."
                ) from error
            if response != 0:
                raise RuntimeError(
                    "Desktop access was canceled or denied in the portal dialog."
                )
            return results
        finally:
            for path, pending in list(self._pending_requests.items()):
                if pending is future:
                    del self._pending_requests[path]

    async def _ensure_session(self) -> None:
        if self._session_handle is not None:
            return
        await self._connect()
        session_token = secrets.token_hex(12)
        created = await self._request(
            REMOTE_DESKTOP,
            "CreateSession",
            "a{sv}",
            [],
            {"session_handle_token": Variant("s", session_token)},
        )
        session_handle = created.get("session_handle")
        if not isinstance(session_handle, str):
            raise RuntimeError("The desktop portal did not return a session handle.")
        self._session_handle = session_handle
        try:
            await self._request(
                REMOTE_DESKTOP,
                "SelectDevices",
                "oa{sv}",
                [session_handle],
                {"types": Variant("u", 3)},
            )
            await self._request(
                SCREEN_CAST,
                "SelectSources",
                "oa{sv}",
                [session_handle],
                {"types": Variant("u", 1), "multiple": Variant("b", False)},
            )
            started = await self._request(
                REMOTE_DESKTOP,
                "Start",
                "osa{sv}",
                [session_handle, ""],
                {},
            )
            if started.get("devices", 0) & 3 != 3:
                raise RuntimeError(
                    "The portal did not grant both pointer and keyboard access."
                )
            streams = started.get("streams", [])
            if len(streams) != 1:
                raise RuntimeError(
                    "The portal did not provide exactly one selected monitor stream."
                )
            node_id, properties = streams[0]
            self._stream_id = node_id
            self._target_object = properties.get("pipewire-serial")
            if self._target_object is None:
                self._target_object = pipewire_serial_for_node(node_id)
            self._logical_size = properties.get("size")
            pipewire_result = await self._call(
                PIPEWIRE_INTERFACE,
                "OpenPipeWireRemote",
                "oa{sv}",
                [session_handle, {}],
            )
            self._pipewire_fd = pipewire_result[0]
            if not isinstance(self._pipewire_fd, int) or self._pipewire_fd < 0:
                raise RuntimeError("The portal returned an invalid PipeWire connection.")
        except Exception as error:
            try:
                await self._close_session()
            except Exception as close_error:
                raise RuntimeError(
                    f"{error} (could not close the portal session: {close_error})"
                ) from error
            raise

    async def _close_session(self) -> None:
        if self._pipewire_fd is not None:
            os.close(self._pipewire_fd)
            self._pipewire_fd = None
        if self._session_handle is not None and self._bus is not None:
            session_handle = self._session_handle
            self._session_handle = None
            await self._call(
                SESSION_INTERFACE, "Close", "", [], path=session_handle
            )

    def _capture_png(self) -> bytes:
        assert self._pipewire_fd is not None
        gst_launch = shutil.which("gst-launch-1.0")
        if gst_launch is None:
            raise RuntimeError(
                "Wayland screenshots need GStreamer. On Ubuntu, install "
                "gstreamer1.0-tools, gstreamer1.0-pipewire, and "
                "gstreamer1.0-plugins-good."
            )

        temporary_fd, filename = tempfile.mkstemp(suffix=".png")
        os.close(temporary_fd)
        pipewire_fd = os.dup(self._pipewire_fd)
        try:
            source = ["pipewiresrc", f"fd={pipewire_fd}", "num-buffers=1"]
            if self._target_object is not None:
                source.append(f"target-object={self._target_object}")
            command = [
                gst_launch,
                *source,
                "!",
                "videoconvert",
                "!",
                "pngenc",
                "snapshot=true",
                "!",
                "filesink",
                f"location={filename}",
            ]
            try:
                env = os.environ.copy()
                env.setdefault("GST_DEBUG", "2,pipewiresrc:5")
                env.setdefault("GST_DEBUG_NO_COLOR", "1")
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    pass_fds=(pipewire_fd,),
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                output = "\n".join(
                    text
                    for text in (
                        process_output_text(error.stdout),
                        process_output_text(error.stderr),
                    )
                    if text
                )
                detail = f"\nGStreamer output:\n{output[-2000:]}" if output else ""
                if not detail:
                    detail = (
                        "\nGStreamer produced no diagnostic output. Fully quit and "
                        "relaunch the app to ensure the updated capture code is running."
                    )
                raise RuntimeError(
                    f"Timed out capturing a frame from the Wayland screen.{detail}"
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip()[-2000:]
                raise RuntimeError(f"PipeWire screenshot failed: {detail}")
            image = Path(filename).read_bytes()
            self._image_size = png_dimensions(image)
            return image
        finally:
            os.close(pipewire_fd)
            Path(filename).unlink(missing_ok=True)

    def screenshot(self) -> str:
        self._submit(self._ensure_session())
        image = self._capture_png()
        return base64.b64encode(image).decode("ascii")

    async def _move_pointer(self, x: int, y: int) -> None:
        assert self._session_handle is not None and self._stream_id is not None
        assert self._image_size is not None
        logical_width, logical_height = self._logical_size or self._image_size
        logical_x, logical_y = pointer_coordinates(
            x, y, self._image_size, (logical_width, logical_height)
        )
        await self._call(
            REMOTE_DESKTOP,
            "NotifyPointerMotionAbsolute",
            "oa{sv}udd",
            [self._session_handle, {}, self._stream_id, logical_x, logical_y],
        )

    def click(self, x: int, y: int) -> None:
        self._submit(self._click(x, y))

    async def _click(self, x: int, y: int) -> None:
        await self._ensure_session()
        assert self._session_handle is not None
        await self._move_pointer(x, y)
        await self._call(
            REMOTE_DESKTOP,
            "NotifyPointerButton",
            "oa{sv}iu",
            [self._session_handle, {}, LEFT_BUTTON, 1],
        )
        try:
            await asyncio.sleep(0.02)
        finally:
            await self._call(
                REMOTE_DESKTOP,
                "NotifyPointerButton",
                "oa{sv}iu",
                [self._session_handle, {}, LEFT_BUTTON, 0],
            )

    def type_text(self, text: str) -> None:
        self._submit(self._type_text(text))

    async def _type_text(self, text: str) -> None:
        await self._ensure_session()
        assert self._session_handle is not None
        for character in text:
            keysym = keysym_for_character(character)
            await self._call(
                REMOTE_DESKTOP,
                "NotifyKeyboardKeysym",
                "oa{sv}iu",
                [self._session_handle, {}, keysym, 1],
            )
            try:
                await asyncio.sleep(0.01)
            finally:
                await self._call(
                    REMOTE_DESKTOP,
                    "NotifyKeyboardKeysym",
                    "oa{sv}iu",
                    [self._session_handle, {}, keysym, 0],
                )
