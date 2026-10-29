from __future__ import annotations

import configparser
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger(__name__)

SNAP_ENV_VARS = (
    "GSETTINGS_SCHEMA_DIR",
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GIO_MODULE_DIR",
    "GDK_PIXBUF_MODULE_FILE",
    "GDK_PIXBUF_MODULEDIR",
    "GTK_IM_MODULE_FILE",
    "LOCPATH",
)


def launch_environment() -> dict[str, str]:
    """Environment for launched apps without a parent snap's (e.g. VS Code) overrides."""
    env = dict(os.environ)
    for key in list(env):
        if key.endswith("_VSCODE_SNAP_ORIG"):
            original = env.pop(key)
            base = key.removesuffix("_VSCODE_SNAP_ORIG")
            if original:
                env[base] = original
            else:
                env.pop(base, None)
    if "SNAP" in env:
        for key in SNAP_ENV_VARS:
            env.pop(key, None)
    # Qt apps (e.g. OBS) only register with AT-SPI when this is set.
    env.setdefault("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "1")
    return env


@dataclass(frozen=True)
class DesktopApplication:
    name: str
    desktop_id: str
    desktop_file: Path


class DesktopApplicationLauncher:
    def __init__(self) -> None:
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
        )
        self.application_directories = [
            data_home / "applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
        ]

    def list_applications(self) -> list[DesktopApplication]:
        applications: dict[str, DesktopApplication] = {}
        for directory in self.application_directories:
            if not directory.is_dir():
                continue
            for desktop_file in directory.rglob("*.desktop"):
                desktop_id = desktop_file.relative_to(directory).as_posix().replace(
                    "/", "-"
                )
                if desktop_id in applications:
                    continue
                application = self._read_application(desktop_file, desktop_id)
                if application is not None:
                    applications[desktop_id] = application
        return sorted(
            applications.values(),
            key=lambda item: (item.name.casefold(), item.desktop_id.casefold()),
        )

    @staticmethod
    def resolve_application(
        applications: list[DesktopApplication], query: str
    ) -> DesktopApplication:
        query = query.strip().casefold()
        if not query:
            raise ValueError("Provide an application name.")
        exact = [
            application for application in applications
            if application.name.casefold() == query
            or application.desktop_id.casefold() == query
        ]
        matches = exact or [
            application for application in applications
            if query in application.name.casefold()
            or query in application.desktop_id.casefold()
        ]
        if not matches:
            raise ValueError(f"No installed application matches {query!r}.")
        if len(matches) > 1:
            options = "\n".join(
                f"- {application.name} ({application.desktop_id})"
                for application in matches
            )
            raise ValueError(
                f"{query!r} matches multiple applications. Use a unique name:\n"
                f"{options}"
            )
        return matches[0]

    def launch(self, application: DesktopApplication) -> None:
        gio = shutil.which("gio")
        gapplication = shutil.which("gapplication")
        if gio is None and gapplication is None:
            raise RuntimeError(
                "The GNOME GIO launcher is unavailable. Install the GLib GIO "
                "command-line tools to launch desktop applications."
            )
        # `gio launch` only starts the background service of D-Bus activatable
        # apps (e.g. GNOME Text Editor) without opening a window.
        if gapplication is not None and self._is_dbus_activatable(
            application.desktop_file
        ):
            command = [gapplication, "launch", application.desktop_id.removesuffix(".desktop")]
        elif gio is not None:
            command = [gio, "launch", str(application.desktop_file)]
        else:
            raise RuntimeError("The GNOME GIO launcher is unavailable.")
        # Output goes to a file, not pipes: the launched app inherits the
        # descriptors and would otherwise keep a pipe open until it exits.
        try:
            with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as output:
                result = subprocess.run(
                    command,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=10,
                    check=False,
                    env=launch_environment(),
                )
                output.seek(0)
                result.stdout = output.read()
                result.stderr = ""
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"Timed out launching {application.name!r}."
            ) from error
        except OSError as error:
            raise RuntimeError(
                f"Could not launch {application.name!r}: {error}"
            ) from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"Could not launch {application.name!r}."
                + (f"\n{detail}" if detail else "")
            )

    @staticmethod
    def _is_dbus_activatable(desktop_file: Path) -> bool:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(desktop_file, encoding="utf-8")
            return parser["Desktop Entry"].getboolean("DBusActivatable", fallback=False)
        except (OSError, UnicodeError, configparser.Error, KeyError, ValueError):
            return False

    @staticmethod
    def _read_application(
        desktop_file: Path, desktop_id: str
    ) -> DesktopApplication | None:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(desktop_file, encoding="utf-8")
            entry = parser["Desktop Entry"]
        except (OSError, UnicodeError, configparser.Error, KeyError) as error:
            LOGGER.warning("Skipping invalid desktop entry %s: %s", desktop_file, error)
            return None

        try:
            if (
                entry.get("Type") != "Application"
                or entry.getboolean("Hidden", fallback=False)
                or entry.getboolean("NoDisplay", fallback=False)
            ):
                return None
        except ValueError as error:
            LOGGER.warning("Skipping invalid desktop entry %s: %s", desktop_file, error)
            return None
        name = entry.get("Name", "").strip()
        if not name:
            return None
        return DesktopApplication(name, desktop_id, desktop_file)
