import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_applications import (
    DesktopApplication,
    DesktopApplicationLauncher,
)


class DesktopApplicationLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.applications = [
            DesktopApplication(
                "Google Chrome",
                "google-chrome.desktop",
                Path("/usr/share/applications/google-chrome.desktop"),
            ),
            DesktopApplication(
                "Text Editor",
                "org.gnome.TextEditor.desktop",
                Path("/usr/share/applications/org.gnome.TextEditor.desktop"),
            ),
        ]

    def test_resolves_exact_name_or_desktop_id(self) -> None:
        self.assertEqual(
            DesktopApplicationLauncher.resolve_application(
                self.applications, "Google Chrome"
            ),
            self.applications[0],
        )
        self.assertEqual(
            DesktopApplicationLauncher.resolve_application(
                self.applications, "org.gnome.TextEditor.desktop"
            ),
            self.applications[1],
        )

    def test_resolves_unique_partial_name(self) -> None:
        self.assertEqual(
            DesktopApplicationLauncher.resolve_application(
                self.applications, "Text Edit"
            ),
            self.applications[1],
        )

    def test_ambiguous_names_require_a_more_specific_query(self) -> None:
        applications = self.applications + [
            DesktopApplication(
                "Google Chrome Beta",
                "google-chrome-beta.desktop",
                Path("/usr/share/applications/google-chrome-beta.desktop"),
            )
        ]

        with self.assertRaisesRegex(ValueError, "matches multiple applications"):
            DesktopApplicationLauncher.resolve_application(
                applications, "Google"
            )

    def test_missing_and_empty_queries_are_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "No installed application"):
            DesktopApplicationLauncher.resolve_application(
                self.applications, "Firefox"
            )
        with self.assertRaisesRegex(ValueError, "Provide an application name"):
            DesktopApplicationLauncher.resolve_application(self.applications, "  ")

    def test_skips_hidden_desktop_entries(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "hidden.desktop"
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Hidden App\n"
                "Hidden=true\n"
                "Exec=hidden-app\n",
                encoding="utf-8",
            )

            self.assertIsNone(
                DesktopApplicationLauncher._read_application(path, "hidden.desktop")
            )

    def test_skips_invalid_desktop_entry_boolean(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.desktop"
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Invalid App\n"
                "NoDisplay=maybe\n",
                encoding="utf-8",
            )

            with self.assertLogs("desktop_applications", level="WARNING"):
                self.assertIsNone(
                    DesktopApplicationLauncher._read_application(
                        path, "invalid.desktop"
                    )
                )


if __name__ == "__main__":
    unittest.main()
