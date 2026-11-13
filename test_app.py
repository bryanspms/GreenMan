import json
import base64
import queue
from io import BytesIO
import socket
import subprocess
import sys
import tkinter as tk
import unittest
from tkinter import ttk
from threading import Event, Lock
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from tkinterdnd2 import TkinterDnD

from app import (
    DEFAULT_MODEL,
    IMAGE_DROP_HINT,
    IMAGE_CONTEXT_TOKENS,
    IMAGE_RESPONSE_TOKENS,
    IMAGE_TOOL_CALL_RESPONSE_TOKENS,
    MAX_SCREENSHOT_DIMENSION,
    TOOL_CALL_RESPONSE_TOKENS,
    OLLAMA_REQUEST_TIMEOUT_SECONDS,
    OLLAMA_IMAGE_TOOL_TIMEOUT_SECONDS,
    MAX_IMAGE_BYTES,
    SYSTEM_PROMPT,
    DesktopAgent,
    TOOL_MODES,
    calculate_cpu_utilization,
    format_elapsed_timer,
    format_elapsed_time,
    format_request_history,
    has_followup_action,
    get_app_title,
    get_app_version,
    is_desktop_action_request,
    is_valid_workspace,
    is_text_tool_call,
    load_dropped_image,
    load_ollama_model,
    list_ollama_models,
    current_step_index,
    local_ollama_url,
    split_request_steps,
    load_user_preferences,
    load_speech_volume_preference,
    load_speech_speed_preference,
    load_piper_voice_directory,
    list_piper_voice_models,
    ollama_model_capabilities,
    ollama_http_error_message,
    compact_desktop_messages,
    save_verification_screenshot,
    prepare_screenshot,
    piper_voice_directory,
    save_user_preferences,
    read_cpu_counters,
    read_system_status,
    scale_screenshot_coordinates,
    point_within_window,
    suggested_focus_coordinates,
    resolve_workspace_path,
    system_prompt_for_mode,
    set_window_icon,
    tools_for_desktop_screenshot,
    tools_for_mode,
    vosk_model_path,
)
from desktop_applications import DesktopApplication
from window_accessibility import AccessibleWindow


class EyeLegendIntegrationTests(unittest.TestCase):
    @staticmethod
    def _cancel_pending_callbacks(root: tk.Tk) -> None:
        for callback in root.tk.splitlist(root.tk.call("after", "info")):
            root.after_cancel(callback)

    def test_sleep_shortcut_survives_key_releases_and_activity_wakes(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(root.destroy)
        self.addCleanup(self._cancel_pending_callbacks, root)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(root)
            self.addCleanup(
                lambda: root.after_cancel(agent.face._eye_after)
                if agent.face._eye_after is not None else None
            )
            root.update()
            for widget in (agent.prompt, agent.url_entry):
                with self.subTest(widget=widget):
                    widget.focus_force()
                    root.update()
                    widget.event_generate("<Control-Shift-KeyPress-Z>")
                    self.assertIsNotNone(agent.face._sleep_transition_started)
                    for key in ("z", "Shift_L", "Control_L"):
                        widget.event_generate("<KeyRelease>", keysym=key)
                        self.assertIsNotNone(agent.face._sleep_transition_started)
                    widget.event_generate("<KeyPress>", keysym="x")
                    self.assertIsNone(agent.face._sleep_transition_started)

    def test_visitor_shortcut_from_prompt_and_entry(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(root.destroy)
        self.addCleanup(self._cancel_pending_callbacks, root)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(root)
            self.addCleanup(
                lambda: root.after_cancel(agent.face._eye_after)
                if agent.face._eye_after is not None else None
            )
            root.update()
            for widget in (agent.prompt, agent.url_entry):
                with self.subTest(widget=widget):
                    widget.focus_force()
                    root.update()
                    with patch.object(agent.face, "show_next_visitor") as preview:
                        widget.event_generate("<Control-Shift-KeyPress-A>")
                        preview.assert_called_once_with()
            self.assertEqual(agent.prompt.get("1.0", "end-1c"), "")

    def test_eye_guide_link_appears_below_title_and_opens_popup(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(root.destroy)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)):
            pending_before = set(root.tk.splitlist(root.tk.call("after", "info")))
            agent = DesktopAgent(root)
            pending_after = set(root.tk.splitlist(root.tk.call("after", "info")))
            for callback in pending_after - pending_before:
                self.addCleanup(root.after_cancel, callback)
            self.addCleanup(
                lambda: root.after_cancel(agent.face._eye_after)
                if agent.face._eye_after is not None else None
            )
            root.update_idletasks()
            brand_row = agent.face.canvas.master
            brand_title = next(
                child for child in brand_row.winfo_children()
                if isinstance(child, tk.Frame)
                and any(
                    isinstance(item, tk.Label)
                    and item.cget("text") == "Local Green Man Assistant"
                    for item in child.winfo_children()
                )
            )
            title = next(
                child for child in brand_title.winfo_children()
                if isinstance(child, tk.Label)
                and child.cget("text") == "Local Green Man Assistant"
            )
            link = next(
                child for child in brand_title.winfo_children()
                if isinstance(child, tk.Label) and child.cget("text") == "Eye Guide"
            )
            volume_scale = next(
                child for child in brand_title.winfo_children()
                if isinstance(child, ttk.Scale)
            )
            self.assertGreaterEqual(
                link.winfo_rooty(), title.winfo_rooty() + title.winfo_height()
            )
            self.assertGreaterEqual(
                volume_scale.winfo_rooty(), link.winfo_rooty() + link.winfo_height()
            )
            self.assertEqual(agent.speech_volume, 100)
            self.assertEqual(volume_scale.get(), 100)
            self.assertEqual(agent.speech._speech_volume(), 100)
            self.assertEqual(agent.speech_volume_label.cget("text"), "Speech volume: 100%")
            self.assertEqual(agent.speech_speed, 100)
            self.assertEqual(agent.speech_speed_scale.get(), 100)
            self.assertGreaterEqual(
                agent.speech_speed_scale.winfo_rooty(),
                volume_scale.winfo_rooty() + volume_scale.winfo_height(),
            )
            agent.speech_speed_scale.set(150)
            root.update()
            self.assertEqual(agent.speech_speed, 150)
            self.assertEqual(agent.speech._speech_speed(), 150)
            self.assertEqual(load_speech_speed_preference(agent.preferences_file), 150)
            volume_scale.set(0)
            root.update()
            self.assertEqual(agent.speech_volume, 0)
            self.assertEqual(agent.speech._speech_volume(), 0)
            self.assertEqual(load_speech_volume_preference(agent.preferences_file), 0)
            self.assertGreaterEqual(
                brand_title.winfo_rootx(),
                agent.face.canvas.winfo_rootx() + agent.face.canvas.winfo_width(),
            )
            with patch.object(agent.face, "note_activity") as activity:
                root.event_generate("<Motion>", x=5, y=5)
                root.event_generate("<ButtonPress-1>", x=5, y=5)
                agent.prompt.focus_force()
                root.update()
                agent.prompt.event_generate("<KeyRelease>", keysym="a")
                self.assertGreaterEqual(activity.call_count, 3)
            agent.face.sleeping = True
            agent.face._set_lids(1.0)
            agent.face._animate_sleep(agent.face._sleep_started)
            root.event_generate("<Motion>", x=10, y=10)
            self.assertFalse(agent.face.sleeping)
            self.assertTrue(
                all(
                    agent.face.canvas.itemcget(item, "state") == "hidden"
                    for item in agent.face._sleep_zs
                )
            )
            self.assertEqual(link.cget("cursor"), "hand2")
            self.assertEqual(str(link.cget("takefocus")), "1")
            link.event_generate("<Button-1>")
            self.assertIsNotNone(agent.eye_legend_dialog)
            assert agent.eye_legend_dialog is not None
            self.assertTrue(agent.eye_legend_dialog.winfo_exists())
            for key in ("<Return>", "<space>"):
                agent.eye_legend_dialog.destroy()
                link.focus_force()
                root.update()
                link.event_generate(key)
                self.assertTrue(agent.eye_legend_dialog.winfo_exists())

    def test_animation_toggle_updates_face_and_legend(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.animations_enabled = Mock()
        agent.face = Mock()
        agent.eye_legend = Mock()
        agent.eye_legend_dialog = Mock()
        agent._save_preferences = Mock()

        for enabled in (False, True):
            agent.animations_enabled.get.return_value = enabled
            agent._on_animations_toggled()
            agent.face.set_animations.assert_called_with(enabled)
            agent.eye_legend.set_animations.assert_called_with(enabled)
        self.assertEqual(agent._save_preferences.call_count, 2)

    def test_animation_toggle_without_open_guide(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.animations_enabled = Mock()
        agent.animations_enabled.get.return_value = False
        agent.face = Mock()
        agent.eye_legend = None
        agent.eye_legend_dialog = None
        agent._save_preferences = Mock()

        agent._on_animations_toggled()

        agent.face.set_animations.assert_called_once_with(False)
        agent._save_preferences.assert_called_once()

    def test_popup_reuses_window_and_reopens_with_current_preference(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(root.destroy)
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.root = root
        agent.eye_legend = None
        agent.eye_legend_dialog = None
        agent.animations_enabled = tk.BooleanVar(root, value=False)
        agent.face = Mock()
        agent._save_preferences = Mock()

        self.assertEqual(root.winfo_children(), [])
        agent._open_eye_guide()
        dialog = agent.eye_legend_dialog
        legend = agent.eye_legend
        self.assertIsNotNone(dialog)
        self.assertIsNotNone(legend)
        assert dialog is not None and legend is not None
        self.assertEqual(dialog.title(), "Eye Guide")
        self.assertIsNone(legend._after)
        self.assertEqual(legend.frame.master, dialog)
        root.update_idletasks()
        self.assertIs(root.grab_current(), dialog)
        self.assertEqual(dialog.resizable(), (0, 0))
        self.assertGreaterEqual(dialog.winfo_width(), 240)
        self.assertGreaterEqual(dialog.winfo_width(), dialog.winfo_reqwidth())
        self.assertEqual(str(dialog.transient()), str(root))

        agent._open_eye_guide()
        self.assertIs(agent.eye_legend_dialog, dialog)
        self.assertIs(agent.eye_legend, legend)
        self.assertEqual(len(root.winfo_children()), 1)

        agent.animations_enabled.set(True)
        agent._on_animations_toggled()
        self.assertIsNotNone(legend._after)
        pending = legend._after
        dialog.destroy()
        self.assertIsNone(root.grab_current())
        self.assertIsNone(legend._after)
        self.assertNotIn(pending, root.tk.splitlist(root.tk.call("after", "info")))
        agent._on_animations_toggled()
        agent.animations_enabled.set(True)
        agent._open_eye_guide()
        self.assertIsNot(agent.eye_legend_dialog, dialog)
        self.assertIsNot(agent.eye_legend, legend)
        assert agent.eye_legend is not None
        self.assertIsNotNone(agent.eye_legend._after)
        assert agent.eye_legend_dialog is not None
        self.assertIs(root.grab_current(), agent.eye_legend_dialog)
        close_button = next(
            child for child in agent.eye_legend_dialog.winfo_children()
            if isinstance(child, tk.Button) and child.cget("text") == "Close"
        )
        close_button.invoke()
        self.assertIsNone(root.grab_current())

        agent._open_eye_guide()
        dialog = agent.eye_legend_dialog
        assert dialog is not None
        root.update()
        dialog.focus_force()
        dialog.event_generate("<Escape>")
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNone(root.grab_current())


class SpeechControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = DesktopAgent.__new__(DesktopAgent)
        self.agent.root = Mock()
        self.agent.face = Mock()
        self.agent.speech = Mock()
        self.agent.stop_speech_button = Mock()
        self.agent.pause_speech_button = Mock()
        self.agent._speech_paused = False
        self.agent._speech_pause_pending = False
        self.agent._model_load_control_states = []
        self.agent._speech_events = queue.SimpleQueue()
        self.agent._speech_event = None
        self.agent._speech_events_after = None
        self.agent.system_status_after = None
        self.agent.busy = False

    def test_stop_interrupts_speech_and_prevents_queued_start(self) -> None:
        event = Event()
        self.agent.speech.speak_async.return_value = event
        self.agent.speech.stop.side_effect = event.set
        self.agent._speak("hello")
        self.agent.face.stop_speaking.reset_mock()
        self.agent.stop_speech_button.config.assert_called_with(state="normal")
        self.agent._speech_events.put(("start", event, (None, 0.04)))
        self.agent._stop_speech()
        self.agent._poll_speech_events()
        self.agent.face.start_speaking.assert_not_called()
        self.agent.face.stop_speaking.assert_called_once()
        self.agent.stop_speech_button.config.assert_called_with(state="disabled")
        self.assertTrue(event.is_set())

    def test_stale_callbacks_do_not_interrupt_new_speech(self) -> None:
        first, second = Event(), Event()
        self.agent.speech.speak_async.side_effect = [first, second]
        self.agent._speak("old")
        self.agent._speak("new")
        self.agent.face.stop_speaking.reset_mock()
        self.agent._speech_events.put(("stop", first, None))
        self.agent._speech_events.put(("start", second, ([0.5], 0.04)))
        self.agent._poll_speech_events()
        self.agent.face.stop_speaking.assert_not_called()
        self.agent.face.start_speaking.assert_called_once_with([0.5], 0.04)
        self.agent._speech_events.put(("stop", second, None))
        self.agent._poll_speech_events()
        self.agent.face.stop_speaking.assert_called_once()
        self.agent.stop_speech_button.config.assert_called_with(state="disabled")

    def test_pause_resume_and_stale_events(self) -> None:
        event = Event()
        self.agent.speech.speak_async.return_value = event
        self.agent.speech.set_paused.return_value = True
        self.agent._speak("hello")
        self.agent._speech_events.put(("start", event, (None, 0.04)))
        self.agent._poll_speech_events()
        self.agent.pause_speech_button.pack.assert_called_once()
        self.agent._toggle_speech_pause()
        self.agent.speech.set_paused.assert_called_once_with(True, event)
        self.agent._toggle_speech_pause()
        self.agent.speech.set_paused.assert_called_once()
        self.agent._speech_events.put(("pause", Event(), None))
        self.agent._speech_events.put(("pause", event, None))
        self.agent._poll_speech_events()
        self.agent.face.set_speech_paused.assert_called_once_with(True)
        self.agent.pause_speech_button.config.assert_called_with(
            text="Play", state="normal"
        )
        self.agent._toggle_speech_pause()
        self.agent.speech.set_paused.assert_called_with(False, event)
        self.agent._speech_events.put(("resume", event, None))
        self.agent._poll_speech_events()
        self.agent.face.set_speech_paused.assert_called_with(False)
        self.agent.pause_speech_button.config.assert_called_with(
            text="Pause", state="normal"
        )
        self.agent._speech_events.put(("stop", event, None))
        self.agent._poll_speech_events()
        self.agent.pause_speech_button.pack_forget.assert_called()

    def test_pause_error_is_reported(self) -> None:
        event = Event()
        self.agent._speech_event = event
        self.agent.speech.set_paused.side_effect = OSError("audio failure")
        self.agent._report_voice_error = Mock()
        self.agent._toggle_speech_pause()
        self.agent._report_voice_error.assert_called_once_with(
            "Could not change speech playback: audio failure", event
        )
        self.assertFalse(self.agent._speech_pause_pending)

    def test_close_stops_speech_before_destroying_window(self) -> None:
        calls = Mock()
        calls.attach_mock(self.agent.speech, "speech")
        calls.attach_mock(self.agent.root, "root")
        self.agent._speech_events_after = "timer"
        self.agent.system_status_after = "status-timer"
        self.agent._close()
        self.assertEqual(
            calls.mock_calls,
            [
                unittest.mock.call.speech.stop(),
                unittest.mock.call.root.after_cancel("status-timer"),
                unittest.mock.call.root.after_cancel("timer"),
                unittest.mock.call.root.destroy(),
            ],
        )


class VoiceDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root_path = Path(self.temp.name)
        self.old = self.root_path / "old"
        self.new = self.root_path / "new"
        self.old.mkdir()
        self.new.mkdir()
        self.voice = self.old / "old.onnx"
        self.voice.touch()
        self.new_voice = self.new / "new.onnx"
        self.new_voice.touch()
        self.agent = DesktopAgent.__new__(DesktopAgent)
        self.agent.root = Mock()
        self.agent.piper_voice_directory = self.old
        self.agent.piper_voice_models = [self.voice]
        self.agent.voice_model_path = self.voice
        self.agent.voice_choice = Mock()
        self.agent.voice_selector = Mock()
        self.agent.voice_directory_label = Mock()
        self.agent.speech = Mock()
        self.agent.status = Mock()
        self.agent._save_preferences = Mock()

    def test_select_directory_updates_models_and_saves(self) -> None:
        with patch("app.filedialog.askdirectory", return_value=str(self.new)) as chooser:
            self.agent._choose_voice_directory()
        chooser.assert_called_once_with(
            title="Choose a Piper voice model folder",
            initialdir=str(self.old),
            parent=self.agent.root,
            mustexist=True,
        )
        self.assertEqual(self.agent.piper_voice_directory, self.new)
        self.assertEqual(self.agent.piper_voice_models, [self.new_voice])
        self.agent.voice_selector.configure.assert_called_once_with(
            values=["System voice", self.new_voice.name]
        )
        self.agent.voice_directory_label.config.assert_called_once_with(text=str(self.new))
        self.assertIsNone(self.agent.voice_model_path)
        self.agent.voice_choice.set.assert_called_once_with("System voice")
        self.agent.speech.stop.assert_called_once()
        self.agent._save_preferences.assert_called_once()

    def test_cancel_and_invalid_folder_leave_selection_unchanged(self) -> None:
        for selected in ("", str(self.root_path / "missing")):
            with self.subTest(selected=selected), patch(
                "app.filedialog.askdirectory", return_value=selected
            ):
                self.agent._choose_voice_directory()
                self.assertEqual(self.agent.piper_voice_directory, self.old)
                self.assertEqual(self.agent.voice_model_path, self.voice)
                self.agent._save_preferences.assert_not_called()
        self.agent.status.set.assert_called_once()

    def test_listing_error_preserves_current_folder(self) -> None:
        with patch("app.filedialog.askdirectory", return_value=str(self.new)), patch(
            "app.list_piper_voice_models", return_value=([], "Could not list voices")
        ):
            self.agent._choose_voice_directory()
        self.assertEqual(self.agent.piper_voice_directory, self.old)
        self.assertEqual(self.agent.voice_model_path, self.voice)
        self.agent.status.set.assert_called_once_with("Could not list voices")
        self.agent._save_preferences.assert_not_called()

    def test_selecting_same_folder_keeps_current_voice(self) -> None:
        with patch("app.filedialog.askdirectory", return_value=str(self.old)):
            self.agent._choose_voice_directory()
        self.assertEqual(self.agent.voice_model_path, self.voice)
        self.agent.speech.stop.assert_not_called()
        self.agent._save_preferences.assert_called_once()


class VoiceDirectoryUITests(unittest.TestCase):
    def test_choice_survives_restart_and_system_prompt_save(self) -> None:
        with TemporaryDirectory() as folder:
            base = Path(folder)
            preferences = base / "preferences.json"
            voices = base / "voices"
            voices.mkdir()
            (voices / "voice.onnx").touch()
            (voices / "voice.onnx.json").touch()
            roots: list[tk.Tk] = []

            def cleanup_root(root: tk.Tk) -> None:
                for callback in root.tk.splitlist(root.tk.call("after", "info")):
                    root.after_cancel(callback)
                root.destroy()

            def cleanup() -> None:
                for root in roots:
                    cleanup_root(root)

            self.addCleanup(cleanup)
            try:
                root = TkinterDnD.Tk()
            except tk.TclError as error:
                self.skipTest(f"No display available: {error}")
            roots.append(root)
            with patch("app.preferences_path", return_value=preferences), patch(
                "app.piper_voice_directory", return_value=base / "default"
            ), patch("app.filedialog.askdirectory", return_value=str(voices)):
                agent = DesktopAgent(root)
                root.update_idletasks()
                buttons = [
                    widget for row in root.winfo_children()
                    for widget in row.winfo_children()
                    if isinstance(widget, tk.Button)
                    and widget.cget("text") == "Voice Model Folder"
                ]
                self.assertEqual(len(buttons), 1)
                for option in (
                    "background", "foreground", "activebackground",
                    "activeforeground", "disabledforeground", "relief",
                ):
                    self.assertEqual(
                        buttons[0].cget(option), agent.workspace_button.cget(option)
                    )
                buttons[0].invoke()
                agent.voice_choice.set("voice.onnx")
                agent._on_voice_selected()
                agent._open_system_prompt_editor()
                dialog = next(
                    child for child in root.winfo_children()
                    if isinstance(child, tk.Toplevel)
                    and child.title() == "Edit system prompt"
                )
                save_button = next(
                    button for row in dialog.winfo_children()
                    for button in row.winfo_children()
                    if isinstance(button, tk.Button) and button.cget("text") == "Save"
                )
                save_button.invoke()
                self.assertEqual(
                    json.loads(preferences.read_text())["piper_voice_directory"],
                    str(voices),
                )
                cleanup_root(root)
                roots.remove(root)
                second_root = TkinterDnD.Tk()
                roots.append(second_root)
                restored = DesktopAgent(second_root)
                self.assertEqual(restored.piper_voice_directory, voices)
                self.assertEqual(restored.voice_model_path, voices / "voice.onnx")
                self.assertEqual(restored.voice_choice.get(), "voice.onnx")
                self.assertEqual(restored.voice_directory_label.cget("text"), str(voices))


class ModelLoadingUITests(unittest.TestCase):
    def test_installed_models_populate_and_select_in_the_dropdown(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")

        def cleanup() -> None:
            for callback in root.tk.splitlist(root.tk.call("after", "info")):
                root.after_cancel(callback)
            root.destroy()

        self.addCleanup(cleanup)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch(
            "app.list_ollama_models", return_value=["custom:latest", "llama3.1:8b"]
        ), patch.object(DesktopAgent, "_begin_model_load") as load:
            agent = DesktopAgent(root)
            root.after(400, root.quit)
            root.mainloop()
            self.assertEqual(
                tuple(agent.model_selector.cget("values")),
                ("custom:latest", "llama3.1:8b"),
            )
            agent._finish_ollama_model_list(
                agent.url_entry.get(), agent.model_list_request_id, [], None
            )
            self.assertEqual(tuple(agent.model_selector.cget("values")), ())
            self.assertIn("No installed Ollama models", agent.status.get())
            agent._finish_ollama_model_list(
                agent.url_entry.get(), agent.model_list_request_id,
                ["custom:latest", "llama3.1:8b"], None,
            )
            agent.model_choice.set("custom:latest")
            agent._on_model_selected()
            load.assert_called_with("custom:latest")

    def test_controls_disable_while_loading_and_restore_on_success_or_failure(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")

        def cleanup() -> None:
            for callback in root.tk.splitlist(root.tk.call("after", "info")):
                root.after_cancel(callback)
            root.destroy()

        self.addCleanup(cleanup)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)):
            agent = DesktopAgent(root)
            agent._save_preferences = Mock()
            for button in (
                agent.stop_speech_button,
                agent.edit_system_prompt_button,
                agent.view_history_button,
            ):
                for option in (
                    "background", "foreground", "activebackground",
                    "activeforeground", "disabledforeground", "relief",
                ):
                    self.assertEqual(
                        button.cget(option), agent.workspace_button.cget(option)
                    )
            controls = [
                agent.workspace_button, agent.voice_directory_button,
                agent.voice_checkbox, agent.stop_speech_button, agent.pause_speech_button,
                agent.animations_checkbox,
                agent.edit_system_prompt_button, agent.view_history_button,
                agent.clear_attachment_button, agent.voice_selector,
                agent.microphone_button, agent.new_chat_button,
                agent.save_transcript_button, agent.model_selector, agent.send_button,
                *agent.mode_buttons,
            ]
            for error in (None, "model load failed"):
                with self.subTest(error=error):
                    with patch("app.threading.Thread"):
                        agent._begin_model_load("qwen3-vl:8b")
                    for control in controls:
                        self.assertEqual(str(control.cget("state")), "disabled")
                    agent._finish_model_load("qwen3-vl:8b", "llama3.1:8b", error)
                    for control in (
                        agent.workspace_button, agent.voice_directory_button,
                        agent.voice_checkbox, agent.animations_checkbox,
                        agent.edit_system_prompt_button, agent.view_history_button,
                        agent.microphone_button, agent.new_chat_button,
                        agent.save_transcript_button,
                    ):
                        self.assertEqual(str(control.cget("state")), "normal")
                    self.assertEqual(str(agent.voice_selector.cget("state")), "readonly")
                    self.assertEqual(str(agent.model_selector.cget("state")), "readonly")
                    self.assertEqual(
                        str(agent.clear_attachment_button.cget("state")), "disabled"
                    )
                    self.assertEqual(str(agent.send_button.cget("state")), "disabled")

            agent.clear_attachment_button.config(state="normal")
            stop_event = Event()
            agent.listening_event = stop_event
            agent.is_listening = False
            agent.microphone_button.config(state="disabled", cursor="")
            with patch("app.threading.Thread"):
                agent._begin_model_load("qwen3-vl:8b")
            agent._finish_listening(stop_event, None)
            self.assertEqual(str(agent.microphone_button.cget("state")), "disabled")
            agent._finish_model_load("qwen3-vl:8b", "llama3.1:8b", "load failed")
            self.assertEqual(str(agent.microphone_button.cget("state")), "normal")
            self.assertEqual(str(agent.clear_attachment_button.cget("state")), "normal")
            event = Event()
            with patch.object(agent.speech, "speak_async", return_value=event), patch.object(
                agent.speech, "stop", side_effect=event.set
            ) as stop:
                self.assertEqual(agent.pause_speech_button.winfo_manager(), "")
                for option in (
                    "background", "foreground", "activebackground",
                    "activeforeground", "disabledforeground", "relief",
                ):
                    self.assertEqual(
                        agent.pause_speech_button.cget(option),
                        agent.workspace_button.cget(option),
                    )
                agent._speak("test")
                self.assertEqual(str(agent.stop_speech_button.cget("state")), "normal")
                agent._speech_events.put(("start", event, (None, 0.04)))
                agent._poll_speech_events()
                self.assertEqual(agent.pause_speech_button.winfo_manager(), "pack")
                self.assertEqual(agent.pause_speech_button.cget("text"), "Pause")
                with patch.object(agent.speech, "set_paused", return_value=True) as pause:
                    agent.pause_speech_button.invoke()
                    pause.assert_called_with(True, event)
                    self.assertEqual(str(agent.pause_speech_button.cget("state")), "disabled")
                    agent._speech_events.put(("pause", event, None))
                    agent._poll_speech_events()
                    self.assertEqual(agent.pause_speech_button.cget("text"), "Play")
                    agent.pause_speech_button.invoke()
                    pause.assert_called_with(False, event)
                    agent._speech_events.put(("resume", event, None))
                    agent._poll_speech_events()
                    self.assertEqual(agent.pause_speech_button.cget("text"), "Pause")
                agent.stop_speech_button.invoke()
                stop.assert_called_once()
                self.assertTrue(event.is_set())
                self.assertEqual(str(agent.stop_speech_button.cget("state")), "disabled")
                self.assertEqual(agent.pause_speech_button.winfo_manager(), "")


class WorkspacePathTests(unittest.TestCase):
    def test_speech_speed_preferences_default_and_round_trip(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            self.assertEqual(load_speech_speed_preference(path), 100)
            for speed in (50, 100, 200):
                with self.subTest(speed=speed):
                    self.assertIsNone(
                        save_user_preferences(
                            path, None, "Questions only", speech_speed=speed
                        )
                    )
                    self.assertEqual(load_speech_speed_preference(path), speed)
            for value, expected in ((1, 50), (300, 200), (True, 100), ("fast", 100)):
                path.write_text(json.dumps({"speech_speed": value}))
                self.assertEqual(load_speech_speed_preference(path), expected)
            with self.assertRaises(ValueError):
                save_user_preferences(path, None, "Questions only", speech_speed=0)

    def test_speech_speed_slider_saves_current_level(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.speech_speed_label = Mock()
        agent._save_preferences = Mock()
        agent._on_speech_speed_changed("125")
        self.assertEqual(agent.speech_speed, 125)
        agent.speech_speed_label.config.assert_called_once_with(text="Speech speed: 125%")
        agent._save_preferences.assert_called_once()

    def test_speech_volume_preferences_round_trip_and_default(self) -> None:
        with TemporaryDirectory() as folder:
            preferences = Path(folder) / "preferences.json"
            self.assertEqual(load_speech_volume_preference(preferences), 100)
            self.assertIsNone(
                save_user_preferences(
                    preferences, None, "Questions only", speech_volume=35
                )
            )
            self.assertEqual(load_speech_volume_preference(preferences), 35)

    def test_speech_volume_preference_clamps_or_rejects_invalid_values(self) -> None:
        with TemporaryDirectory() as folder:
            preferences = Path(folder) / "preferences.json"
            for value, expected in ((-5, 0), (150, 100), ("quiet", 100), (True, 100)):
                preferences.write_text(json.dumps({"speech_volume": value}))
                with self.subTest(value=value):
                    self.assertEqual(load_speech_volume_preference(preferences), expected)

    def test_speech_volume_slider_saves_current_level(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.speech_volume_label = Mock()
        agent._save_preferences = Mock()

        agent._on_speech_volume_changed("42")

        self.assertEqual(agent.speech_volume, 42)
        agent.speech_volume_label.config.assert_called_once_with(
            text="Speech volume: 42%"
        )
        agent._save_preferences.assert_called_once()

    def test_voice_directory_preferences_round_trip_and_default(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            preferences = root / "preferences.json"
            default = root / "default"
            with patch("app.piper_voice_directory", return_value=default):
                self.assertEqual(load_piper_voice_directory(preferences), (default, None))
                self.assertIsNone(
                    save_user_preferences(
                        preferences, None, "Questions only", piper_directory=root
                    )
                )
                self.assertEqual(load_piper_voice_directory(preferences), (root, None))
                missing = root / "removed"
                self.assertIsNone(
                    save_user_preferences(
                        preferences, None, "Questions only", piper_directory=missing
                    )
                )
                restored, error = load_piper_voice_directory(preferences)
                self.assertEqual(restored, missing)
                self.assertIn("not available", error or "")

    def test_lists_piper_voice_models_in_filename_order(self) -> None:
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            second_voice = directory / "en_US-zeta.onnx"
            first_voice = directory / "en_US-alpha.onnx"
            first_voice.touch()
            second_voice.touch()
            (directory / "not-a-model.json").touch()
            (directory / "folder.onnx").mkdir()

            models, error = list_piper_voice_models(directory)

        self.assertEqual(models, [first_voice, second_voice])
        self.assertIsNone(error)

    def test_missing_piper_voice_directory_has_no_models_or_error(self) -> None:
        with TemporaryDirectory() as folder:
            models, error = list_piper_voice_models(Path(folder) / "missing")

        self.assertEqual(models, [])
        self.assertIsNone(error)

    def test_piper_voice_directory_uses_xdg_data_home(self) -> None:
        with TemporaryDirectory() as folder:
            with patch.dict("os.environ", {"XDG_DATA_HOME": folder}):
                directory = piper_voice_directory()

        self.assertEqual(directory, Path(folder) / "piper-voices")

    def test_vosk_model_path_uses_xdg_data_home(self) -> None:
        with TemporaryDirectory() as folder:
            with patch.dict("os.environ", {"XDG_DATA_HOME": folder}):
                model = vosk_model_path()

        self.assertEqual(
            model, Path(folder) / "vosk-model-small-en-us-0.15"
        )

    def test_sets_window_icon_and_returns_image_reference(self) -> None:
        root = Mock()
        icon = Mock()

        with patch("app.tk.PhotoImage", return_value=icon) as photo_image:
            retained_icon = set_window_icon(root, Path("assets/greenMan.png"))

        photo_image.assert_called_once_with(file="assets/greenMan.png")
        root.iconphoto.assert_called_once_with(True, icon)
        self.assertIs(retained_icon, icon)

    def test_workspace_is_valid_only_while_it_is_a_directory(self) -> None:
        with TemporaryDirectory() as folder:
            self.assertTrue(is_valid_workspace(Path(folder)))
            self.assertFalse(is_valid_workspace(Path(folder) / "missing"))
        self.assertFalse(is_valid_workspace(None))

    def test_preferences_restore_valid_workspace_and_assistant_mode(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = root / "workspace"
            workspace.mkdir()
            preferences_file = root / "config" / "preferences.json"

            self.assertIsNone(
                save_user_preferences(preferences_file, workspace, "Workspace files")
            )

            (
                restored_workspace,
                restored_mode,
                restored_model,
                voice_enabled,
                voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertEqual(restored_workspace, workspace)
        self.assertEqual(restored_mode, "Workspace files")
        self.assertEqual(restored_model, DEFAULT_MODEL)
        self.assertFalse(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_ignore_a_workspace_that_no_longer_exists(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            preferences_file = root / "preferences.json"
            preferences_file.write_text(
                json.dumps(
                    {
                        "workspace": str(root / "removed"),
                        "assistant_mode": "Screenshot",
                    }
                ),
                encoding="utf-8",
            )

            (
                workspace,
                mode,
                model,
                voice_enabled,
                voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Screenshot")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertFalse(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_default_to_questions_for_unknown_mode(self) -> None:
        with TemporaryDirectory() as folder:
            preferences_file = Path(folder) / "preferences.json"
            preferences_file.write_text(
                json.dumps({"workspace": None, "assistant_mode": "Unknown"}),
                encoding="utf-8",
            )

            (
                workspace,
                mode,
                model,
                voice_enabled,
                voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Questions only")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertFalse(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_restore_selected_model(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = root / "workspace"
            workspace.mkdir()
            preferences_file = root / "preferences.json"

            self.assertIsNone(
                save_user_preferences(
                    preferences_file, workspace, "Screenshot", "qwen3-vl:8b"
                )
            )

            (
                restored_workspace,
                mode,
                model,
                voice_enabled,
                voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertEqual(restored_workspace, workspace)
        self.assertEqual(mode, "Screenshot")
        self.assertEqual(model, "qwen3-vl:8b")
        self.assertFalse(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_preserve_custom_model_names(self) -> None:
        with TemporaryDirectory() as folder:
            preferences_file = Path(folder) / "preferences.json"
            model = "example/custom-model:latest"
            self.assertIsNone(
                save_user_preferences(preferences_file, None, "Questions only", model)
            )
            self.assertEqual(load_user_preferences(preferences_file)[2], model)
            with self.assertRaisesRegex(ValueError, "Model name"):
                save_user_preferences(preferences_file, None, "Questions only", " ")

    def test_preferences_restore_voice_enabled(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            preferences_file = root / "preferences.json"

            self.assertIsNone(
                save_user_preferences(
                    preferences_file,
                    None,
                    "Questions only",
                    voice_enabled=True,
                )
            )

            (
                workspace,
                mode,
                model,
                voice_enabled,
                voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Questions only")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertTrue(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_restore_piper_voice_model(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            preferences_file = root / "preferences.json"
            voice_model = root / "voice.onnx"

            self.assertIsNone(
                save_user_preferences(
                    preferences_file,
                    None,
                    "Questions only",
                    voice_model=voice_model,
                )
            )

            (
                workspace,
                mode,
                model,
                voice_enabled,
                restored_voice_model,
                system_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Questions only")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertFalse(voice_enabled)
        self.assertEqual(restored_voice_model, voice_model)
        self.assertEqual(system_prompt, SYSTEM_PROMPT)
        self.assertIsNone(error)

    def test_preferences_restore_custom_system_prompt(self) -> None:
        with TemporaryDirectory() as folder:
            preferences_file = Path(folder) / "preferences.json"
            custom_prompt = "You are a concise gardening assistant."

            self.assertIsNone(
                save_user_preferences(
                    preferences_file,
                    None,
                    "Questions only",
                    system_prompt=custom_prompt,
                )
            )

            (
                workspace,
                mode,
                model,
                voice_enabled,
                voice_model,
                restored_prompt,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Questions only")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertFalse(voice_enabled)
        self.assertIsNone(voice_model)
        self.assertEqual(restored_prompt, custom_prompt)
        self.assertIsNone(error)

    def test_resolves_path_inside_workspace(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(resolve_workspace_path(root, "notes.txt"), root / "notes.txt")
            self.assertEqual(resolve_workspace_path(root, "."), root)

    def test_rejects_parent_traversal(self) -> None:
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_workspace_path(Path(folder), "../outside.txt")

    def test_rejects_absolute_path_outside_workspace(self) -> None:
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_workspace_path(Path(folder), "/etc/passwd")
            with self.assertRaises(ValueError):
                resolve_workspace_path(Path(folder), "/")

    def test_rejects_symlink_escape(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder) / "workspace"
            outside = Path(folder) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "shortcut").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                resolve_workspace_path(root, "shortcut/file.txt")


class RequestHistoryTests(unittest.TestCase):
    def test_empty_history_has_a_placeholder(self) -> None:
        self.assertIn("No requests", format_request_history([]))

    def test_history_is_numbered_oldest_first(self) -> None:
        text = format_request_history(
            [("2026-01-01 09:00:00", "first"), ("2026-01-01 09:05:00", "second")]
        )
        self.assertEqual(
            text,
            "1. [2026-01-01 09:00:00]\nfirst\n\n2. [2026-01-01 09:05:00]\nsecond",
        )

    def test_recording_a_request_appends_with_timestamp(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.request_history = []
        agent._refresh_history_view = Mock()
        agent._record_request("open chrome")
        agent._record_request("close it")
        self.assertEqual(
            [request for _, request in agent.request_history],
            ["open chrome", "close it"],
        )
        self.assertEqual(agent._refresh_history_view.call_count, 2)


class FollowupActionTests(unittest.TestCase):
    def test_detects_actions_after_a_launch(self) -> None:
        for request in (
            'open terminal app. enter the text, "ls" and send enter key.',
            "launch google chrome and add a new tab to: http://example.com",
        ):
            with self.subTest(request=request):
                self.assertTrue(has_followup_action(request))

    def test_plain_launch_has_no_followup(self) -> None:
        for request in ("open google chrome", "launch the file manager"):
            with self.subTest(request=request):
                self.assertFalse(has_followup_action(request))


class SystemStatusTests(unittest.TestCase):
    def test_reads_aggregate_cpu_counters(self) -> None:
        with TemporaryDirectory() as folder:
            stat_path = Path(folder) / "stat"
            stat_path.write_text("cpu 100 20 30 800 50 0 0 0 0 0\n", encoding="utf-8")

            self.assertEqual(read_cpu_counters(stat_path), (1000, 850))

    def test_calculates_cpu_utilization_between_samples(self) -> None:
        self.assertEqual(calculate_cpu_utilization((1000, 800), (1200, 900)), 50)
        self.assertIsNone(calculate_cpu_utilization(None, (1200, 900)))

    def test_formats_elapsed_time_in_seconds_and_minutes(self) -> None:
        self.assertEqual(format_elapsed_time(12.34), "12.3 seconds")
        self.assertEqual(format_elapsed_time(125.6), "2 min 5.6 sec")

    def test_formats_live_elapsed_timer_as_minutes_and_seconds(self) -> None:
        self.assertEqual(format_elapsed_timer(65.9), "01:05")
        self.assertEqual(format_elapsed_timer(-2), "00:00")

    def test_reads_cpu_temperature_and_gpu_utilization_from_sysfs(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            cpu_sensor = root / "class/hwmon/hwmon0"
            gpu_device = root / "class/drm/card0/device"
            cpu_sensor.mkdir(parents=True)
            gpu_device.mkdir(parents=True)
            (cpu_sensor / "name").write_text("coretemp", encoding="utf-8")
            (cpu_sensor / "temp1_input").write_text("55250", encoding="utf-8")
            (cpu_sensor / "temp1_label").write_text("Package id 0", encoding="utf-8")
            (gpu_device / "gpu_busy_percent").write_text("60", encoding="utf-8")

            with patch("app.shutil.which", return_value=None):
                self.assertEqual(read_system_status(root), (55, 60))

    def test_reads_nvidia_gpu_utilization(self) -> None:
        with TemporaryDirectory() as folder:
            with patch("app.shutil.which", return_value="/usr/bin/nvidia-smi"):
                with patch(
                    "app.subprocess.run",
                    return_value=Mock(stdout="56\n"),
                ) as run:
                    self.assertEqual(
                        read_system_status(Path(folder)), (None, 56)
                    )

        self.assertEqual(
            run.call_args.args[0],
            [
                "/usr/bin/nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
        )

    def test_missing_sensors_are_reported_as_unavailable(self) -> None:
        with TemporaryDirectory() as folder:
            with patch("app.shutil.which", return_value=None):
                self.assertEqual(read_system_status(Path(folder)), (None, None))

    def test_loads_supported_dropped_image_as_base64(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nsample-image"
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "screenshot.png"
            image_path.write_bytes(image_bytes)

            name, encoded = load_dropped_image(image_path)

        self.assertEqual(name, "screenshot.png")
        self.assertEqual(encoded, base64.b64encode(image_bytes).decode("ascii"))

    def test_rejects_unsupported_dropped_file(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "notes.txt"
            image_path.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Image must use"):
                load_dropped_image(image_path)

    def test_rejects_dropped_image_over_size_limit(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "large.png"
            image_path.write_bytes(b"x" * (MAX_IMAGE_BYTES + 1))

            with self.assertRaisesRegex(ValueError, "10 MB image limit"):
                load_dropped_image(image_path)

    def test_prepares_screenshot_as_bounded_jpeg(self) -> None:
        from PIL import Image

        source = BytesIO()
        Image.new("RGB", (1920, 1080), "white").save(source, format="PNG")

        encoded, source_size, image_size = prepare_screenshot(
            base64.b64encode(source.getvalue()).decode("ascii")
        )

        with Image.open(BytesIO(base64.b64decode(encoded))) as prepared:
            self.assertEqual(prepared.format, "JPEG")
            self.assertEqual(
                prepared.size,
                (
                    MAX_SCREENSHOT_DIMENSION,
                    round(1080 * MAX_SCREENSHOT_DIMENSION / 1920),
                ),
            )
        self.assertEqual(source_size, (1920, 1080))
        self.assertEqual(
            image_size,
            (MAX_SCREENSHOT_DIMENSION, round(1080 * MAX_SCREENSHOT_DIMENSION / 1920)),
        )

    def test_scales_screenshot_coordinates_to_native_resolution(self) -> None:
        self.assertEqual(
            scale_screenshot_coordinates(640, 360, (1280, 720), (1920, 1080)),
            (960, 540),
        )

    def test_rejects_coordinates_outside_scaled_screenshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "screenshot size 1280x720"):
            scale_screenshot_coordinates(1280, 360, (1280, 720), (1920, 1080))

    def test_detects_points_inside_green_man_window_after_scaling(self) -> None:
        self.assertTrue(
            point_within_window(
                (668, 667),
                (1368, 768),
                (617, 112, 587, 642, 1368, 768),
            )
        )
        self.assertFalse(
            point_within_window(
                (500, 300),
                (1368, 768),
                (617, 112, 587, 642, 1368, 768),
            )
        )

    def test_suggests_safe_point_in_exposed_strip_above_window(self) -> None:
        self.assertEqual(
            suggested_focus_coordinates(
                (1024, 576),
                (1368, 768),
                (617, 112, 587, 642, 1368, 768),
            ),
            (499, 53),
        )


class OllamaUrlTests(unittest.TestCase):
    def test_accepts_local_http_urls(self) -> None:
        self.assertEqual(local_ollama_url("http://localhost:11434/"), "http://localhost:11434")
        self.assertEqual(local_ollama_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434")

    def test_rejects_non_local_urls(self) -> None:
        for url in ("https://localhost:11434", "http://example.com", "http://192.168.1.5:11434"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_ollama_url(url)


class SaveTranscriptTests(unittest.TestCase):
    def _agent(self, text: str, workspace=None) -> DesktopAgent:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.transcript = Mock()
        agent.transcript.get.return_value = text
        agent.status = Mock()
        agent.workspace = workspace
        return agent

    def test_saves_transcript_text_to_chosen_file(self) -> None:
        with TemporaryDirectory() as folder:
            target = Path(folder) / "out.txt"
            agent = self._agent("You: hi\n\nAssistant: hello\n\n", Path(folder))
            with patch("app.filedialog.asksaveasfilename", return_value=str(target)) as ask:
                agent._save_transcript()

            self.assertEqual(target.read_text(encoding="utf-8"), "You: hi\n\nAssistant: hello\n\n")
            self.assertEqual(ask.call_args.kwargs["initialdir"], folder)
            self.assertEqual(ask.call_args.kwargs["defaultextension"], ".txt")
        agent.status.set.assert_called_once_with(f"Saved output to {target}")

    def test_cancelled_dialog_writes_nothing(self) -> None:
        agent = self._agent("text")
        with patch("app.filedialog.asksaveasfilename", return_value=""):
            agent._save_transcript()
        agent.status.set.assert_not_called()

    def test_empty_transcript_is_not_saved(self) -> None:
        agent = self._agent("  \n")
        with patch("app.filedialog.asksaveasfilename") as ask:
            agent._save_transcript()
        ask.assert_not_called()
        agent.status.set.assert_called_once()

    def test_write_errors_are_reported(self) -> None:
        agent = self._agent("text")
        with patch("app.filedialog.asksaveasfilename", return_value="/nonexistent-dir/out.txt"):
            agent._save_transcript()
        self.assertIn("Could not save the output", agent.status.set.call_args.args[0])


class AppVersionTests(unittest.TestCase):
    def test_app_title_includes_version(self) -> None:
        with patch("app.get_app_version", return_value="v1.2.3"):
            self.assertEqual(
                get_app_title(), "Local Green Man Assistant - v1.2.3"
            )

    def test_reads_version_from_latest_reachable_git_tag(self) -> None:
        with patch(
            "app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["git"], returncode=0, stdout="v1.2.3\n", stderr=""
            ),
        ) as run:
            version = get_app_version()

        self.assertEqual(version, "v1.2.3")
        self.assertEqual(
            run.call_args.args[0], ["git", "describe", "--tags", "--abbrev=0"]
        )

    def test_uses_dev_when_no_git_tag_is_available(self) -> None:
        with patch(
            "app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["git"], returncode=128, stdout="", stderr="no tags"
            ),
        ):
            self.assertEqual(get_app_version(), "dev")


class ToolCallResponseTests(unittest.TestCase):
    def test_desktop_context_budget_accounts_for_screenshot_request(self) -> None:
        self.assertEqual(IMAGE_CONTEXT_TOKENS, 16384)

    def test_approval_releases_dialog_before_waking_action_thread(self) -> None:
        calls = []
        dialog = Mock()
        dialog.grab_release.side_effect = lambda: calls.append("grab_release")
        dialog.destroy.side_effect = lambda: calls.append("destroy")
        completed = Mock()
        completed.set.side_effect = lambda: calls.append("set")
        decision = []

        DesktopAgent._complete_approval(dialog, decision, True, completed)

        self.assertEqual(decision, [True])
        self.assertEqual(calls, ["grab_release", "destroy", "set"])
        dialog.grab_release.assert_called_once_with()
        dialog.destroy.assert_called_once_with()
        completed.set.assert_called_once_with()

    def test_saves_verification_screenshot_to_cache(self) -> None:
        image_bytes = b"\xff\xd8\xffexample"
        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            screenshot_path = save_verification_screenshot(
                base64.b64encode(image_bytes).decode("ascii")
            )

            self.assertEqual(
                screenshot_path,
                Path(home) / ".cache" / "greenman" / "last-desktop-verification.jpg",
            )
            self.assertEqual(screenshot_path.read_bytes(), image_bytes)

    def test_compacts_desktop_history_but_preserves_confirmation_context(self) -> None:
        old_image = {"role": "user", "content": "The current desktop screenshot is attached.", "images": ["old"]}
        prior_assistant = {
            "role": "assistant",
            "content": "I can close Chrome. Please confirm.",
        }
        confirmation = {"role": "user", "content": "yes"}
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Old request."},
            old_image,
            prior_assistant,
            confirmation,
        ]

        self.assertEqual(
            compact_desktop_messages(messages),
            [
                messages[0],
                prior_assistant,
                confirmation,
            ],
        )

    def test_compacts_desktop_history_to_latest_request(self) -> None:
        current_request = {"role": "user", "content": "Close Chrome."}
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Old request."},
            {
                "role": "user",
                "content": "The current desktop screenshot is attached.",
                "images": ["old screenshot"],
            },
            {"role": "assistant", "content": "Old answer."},
            current_request,
        ]

        self.assertEqual(
            compact_desktop_messages(messages),
            [messages[0], current_request],
        )

    def test_desktop_control_prompt_uses_in_app_approval_instead_of_chat_confirmation(
        self,
    ) -> None:
        prompt = system_prompt_for_mode("Custom base instructions.", "Desktop control")

        self.assertIn("do not ask for verbal", prompt)
        self.assertIn("Green Man will show its own approval dialog", prompt)
        self.assertIn("If the user says yes", prompt)
        self.assertIn("partly covered", prompt)
        self.assertIn("or behind Green Man is still open", prompt)
        self.assertIn("captures and attaches a fresh screenshot", prompt)
        self.assertIn("close_named_window", prompt)
        self.assertIn("list_windows", prompt)
        self.assertIn("exact title", prompt)
        self.assertIn("tool result or verification screenshot confirms it", prompt)
        self.assertIn("application exited", prompt)
        self.assertIn("coordinates are outside the screenshot bounds", SYSTEM_PROMPT)
        self.assertIn("the blocked action sent no input", SYSTEM_PROMPT)
        self.assertEqual(
            system_prompt_for_mode("Custom base instructions.", "Questions only"),
            "Custom base instructions.",
        )
        desktop_prompt = system_prompt_for_mode(
            "Custom base instructions.", "Desktop control"
        )
        self.assertIn("Never target Green Man itself", desktop_prompt)

    def test_model_selector_default(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "llama3.1:8b")

    def test_list_models_uses_installed_model_api(self) -> None:
        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"models":[{"name":"z:latest"},{"name":"a:4b"},'
                b'{"name":"z:latest"}]}'
            )
            models = list_ollama_models("http://127.0.0.1:11434")
        self.assertEqual(models, ["a:4b", "z:latest"])
        self.assertEqual(
            urlopen.call_args.args[0], "http://127.0.0.1:11434/api/tags"
        )

    def test_model_list_errors_are_reported(self) -> None:
        for payload in (b"{}", b'{"models":[{}]}', b"not json"):
            with self.subTest(payload=payload), patch("app.urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.read.return_value = payload
                with self.assertRaises(RuntimeError):
                    list_ollama_models("http://127.0.0.1:11434")
        with patch("app.urlopen", side_effect=URLError("Connection refused")):
            with self.assertRaisesRegex(RuntimeError, "Could not list installed"):
                list_ollama_models("http://127.0.0.1:11434")
        with self.assertRaises(ValueError):
            list_ollama_models("http://example.com")

    def test_model_list_ignores_stale_results_and_reports_errors(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.model_list_request_id = 2
        agent.url_entry = Mock()
        agent.url_entry.get.return_value = "http://localhost:11434"
        agent.model_selector = Mock()
        agent.status = Mock()
        agent.model_list_url = None

        agent._finish_ollama_model_list(
            "http://localhost:11434", 1, ["stale"], None
        )
        agent._finish_ollama_model_list(
            "http://localhost:11435", 2, ["other"], None
        )
        agent.model_selector.config.assert_not_called()
        agent._finish_ollama_model_list(
            "http://localhost:11434", 2, ["custom:latest"], None
        )
        agent.model_selector.config.assert_called_once_with(values=["custom:latest"])
        agent._finish_ollama_model_list(
            "http://localhost:11434", 2, None, "connection refused"
        )
        agent.status.set.assert_called_once_with(
            "Could not refresh the Ollama model list: connection refused"
        )

    def test_image_tool_response_budget_allows_longer_tool_calls(self) -> None:
        self.assertEqual(IMAGE_TOOL_CALL_RESPONSE_TOKENS, 1024)

    def test_model_load_request_uses_ollama_generate_load_api(self) -> None:
        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"model":"qwen3-vl:8b","done":true,"done_reason":"load"}'
            )

            load_ollama_model("http://127.0.0.1:11434", "qwen3-vl:8b")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(payload["model"], "qwen3-vl:8b")
        self.assertEqual(payload["prompt"], "")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["keep_alive"], "5m")

    def test_model_load_failure_is_reported(self) -> None:
        with (
            patch(
                "app.urlopen",
                side_effect=URLError("Connection refused"),
            ),
            self.assertRaisesRegex(RuntimeError, "Could not load qwen3-vl:8b"),
        ):
            load_ollama_model(
                "http://127.0.0.1:11434", "qwen3-vl:8b"
            )

    def test_model_capability_check_reads_ollama_show_response(self) -> None:
        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"capabilities":["completion","vision","tools"]}'
            )

            capabilities = ollama_model_capabilities(
                "http://127.0.0.1:11434", "qwen3-vl:8b"
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/show")
        self.assertEqual(json.loads(request.data), {"model": "qwen3-vl:8b"})
        self.assertEqual(capabilities, frozenset({"completion", "vision", "tools"}))

    def test_model_capability_check_requires_capabilities_metadata(self) -> None:
        with (
            patch("app.urlopen") as urlopen,
            self.assertRaisesRegex(RuntimeError, "did not provide model capabilities"),
        ):
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"
            ollama_model_capabilities(
                "http://127.0.0.1:11434", "llama3.1:8b"
            )

    def test_modes_expose_only_their_tools(self) -> None:
        expected = {
            "Questions only": set(),
            "Screenshot": {"take_screenshot"},
            "Desktop control": {
                "take_screenshot",
                "list_windows",
                "list_applications",
                "launch_application",
                "activate_window",
                "click",
                "type_text",
                "press_key",
                "wait",
                "focus_window",
                "close_window",
                "close_named_window",
            },
            "Workspace files": {
                "list_files",
                "read_file",
                "view_image",
                "write_file",
            },
            "Run command": {"run_command"},
        }
        self.assertEqual(set(TOOL_MODES), set(expected))
        for mode, names in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(
                    {tool["function"]["name"] for tool in tools_for_mode(mode)},
                    names,
                )

    def test_non_vision_model_does_not_receive_image_tools(self) -> None:
        self.assertEqual(
            tools_for_mode("Screenshot", frozenset({"completion", "tools"})),
            [],
        )
        self.assertEqual(
            {
                tool["function"]["name"]
                for tool in tools_for_mode(
                    "Workspace files", frozenset({"completion", "tools"})
                )
            },
            {"list_files", "read_file", "write_file"},
        )
        desktop_tools = {
            tool["function"]["name"]
            for tool in tools_for_mode(
                "Desktop control", frozenset({"completion", "tools"})
            )
        }
        self.assertIn("list_windows", desktop_tools)
        self.assertIn("close_named_window", desktop_tools)
        self.assertIn("list_applications", desktop_tools)
        self.assertIn("launch_application", desktop_tools)
        self.assertNotIn("take_screenshot", desktop_tools)
        self.assertNotIn("click", desktop_tools)

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown assistant mode"):
            tools_for_mode("Everything")

    def test_screenshot_action_tools_are_bounded_and_close_only_when_requested(self) -> None:
        original_tools = tools_for_mode("Desktop control")
        tools = tools_for_desktop_screenshot(
            original_tools,
            (1024, 576),
            close_only=True,
        )

        self.assertEqual(
            [tool["function"]["name"] for tool in tools],
            ["close_window"],
        )
        properties = tools[0]["function"]["parameters"]["properties"]
        self.assertEqual(properties["x"]["minimum"], 0)
        self.assertEqual(properties["x"]["maximum"], 1023)
        self.assertEqual(properties["y"]["minimum"], 0)
        self.assertEqual(properties["y"]["maximum"], 575)
        original_close = next(
            tool for tool in original_tools
            if tool["function"]["name"] == "close_window"
        )
        self.assertNotIn(
            "maximum",
            original_close["function"]["parameters"]["properties"]["x"],
        )

    def test_chat_request_includes_only_selected_tools(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Take a screenshot."}]
        agent.active_response_lock = Lock()
        agent.active_response = None

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"content":"Done."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=tools_for_mode("Screenshot"),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            [tool["function"]["name"] for tool in payload["tools"]],
            ["take_screenshot"],
        )

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"content":"Hello."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=tools_for_mode("Questions only"),
            )

        question_request = urlopen.call_args.args[0]
        self.assertNotIn("tools", json.loads(question_request.data))

    def test_qwen_image_request_uses_larger_context_and_disables_thinking(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.active_response_lock = Lock()
        agent.active_response = None
        agent.messages = [
            {
                "role": "user",
                "content": "Describe this image.",
                "images": ["aGVsbG8="],
            }
        ]

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"A test image."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "qwen3-vl:8b",
                tools=[],
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["think"])
        self.assertEqual(
            payload["options"],
            {
                "num_ctx": IMAGE_CONTEXT_TOKENS,
                "num_predict": IMAGE_RESPONSE_TOKENS,
            },
        )

    def test_non_qwen_image_request_does_not_get_qwen_options(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.active_response_lock = Lock()
        agent.active_response = None
        agent.messages = [
            {"role": "user", "content": "Describe this image.", "images": ["aGVsbG8="]}
        ]

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"A test image."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("think", payload)
        self.assertNotIn("options", payload)

    def test_qwen_tool_request_uses_bounded_generation_options(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Use one tool call per response."},
            {"role": "user", "content": "Take a screenshot."},
        ]
        agent.active_response_lock = Lock()
        agent.active_response = None

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"Done."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "qwen3-vl:8b",
                tools=tools_for_mode("Desktop control"),
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["think"])
        self.assertEqual(
            payload["options"],
            {"num_predict": TOOL_CALL_RESPONSE_TOKENS, "temperature": 0.2},
        )

    def test_qwen_image_tool_request_uses_bounded_generation_options(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Use one tool call per response."},
            {"role": "user", "content": "Focus the app and select its tab."},
            {"role": "tool", "tool_name": "take_screenshot", "content": "Captured."},
            {
                "role": "user",
                "content": "The image is attached. Inspect it.",
                "images": ["aGVsbG8="],
            },
        ]
        agent.active_response_lock = Lock()
        agent.active_response = None

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"Done."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "qwen3-vl:8b",
                tools=tools_for_mode("Desktop control"),
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["think"])
        self.assertEqual(
            payload["options"],
            {
                "num_ctx": IMAGE_CONTEXT_TOKENS,
                "num_predict": IMAGE_TOOL_CALL_RESPONSE_TOKENS,
                "temperature": 0.2,
            },
        )
        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            OLLAMA_IMAGE_TOOL_TIMEOUT_SECONDS,
        )

    def test_qwen_four_billion_image_tool_request_uses_bounded_generation_options(
        self,
    ) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {
                "role": "user",
                "content": "Describe this screenshot.",
                "images": ["aGVsbG8="],
            }
        ]
        agent.active_response_lock = Lock()
        agent.active_response = None

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"Done."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "qwen3-vl:4b",
                tools=tools_for_mode("Screenshot"),
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["think"])
        self.assertEqual(
            payload["options"],
            {
                "num_ctx": IMAGE_CONTEXT_TOKENS,
                "num_predict": IMAGE_TOOL_CALL_RESPONSE_TOKENS,
                "temperature": 0.2,
            },
        )

    def test_qwen_instruct_models_receive_qwen_generation_options(self) -> None:
        for model in ("qwen3-vl:4b-instruct", "qwen3-vl:8b-instruct"):
            with self.subTest(model=model):
                agent = DesktopAgent.__new__(DesktopAgent)
                agent.messages = [
                    {
                        "role": "user",
                        "content": "Describe this screenshot.",
                        "images": ["aGVsbG8="],
                    }
                ]
                agent.active_response_lock = Lock()
                agent.active_response = None

                with patch("app.urlopen") as urlopen:
                    urlopen.return_value.__enter__.return_value.read.return_value = (
                        b'{"message":{"role":"assistant","content":"Done."}}'
                    )
                    agent._chat(
                        "http://localhost:11434/api/chat",
                        model,
                        tools=tools_for_mode("Desktop control"),
                    )

                payload = json.loads(urlopen.call_args.args[0].data)
                self.assertFalse(payload["think"])
                self.assertEqual(payload["model"], model)
                self.assertEqual(
                    payload["options"]["num_ctx"],
                    IMAGE_CONTEXT_TOKENS,
                )
                self.assertEqual(
                    payload["options"]["num_predict"],
                    IMAGE_TOOL_CALL_RESPONSE_TOKENS,
                )

    def test_desktop_action_gets_verification_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the untitled tab."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent.screenshot_image_size = (1024, 576)
        observed_requests = []
        observed_tools = []

        def chat(*_args, **_kwargs):
            observed_requests.append([dict(message) for message in agent.messages])
            observed_tools.append(_kwargs["tools"])
            if len(observed_requests) == 1:
                return {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "click",
                                    "arguments": {"x": 10, "y": 20},
                                }
                            }
                        ],
                    }
                }
            return {"message": {"role": "assistant", "content": "Done."}}

        agent._chat = Mock(side_effect=chat)
        agent._execute_tool = Mock(
            side_effect=[
                (
                    "Screenshot captured.",
                    [base64.b64encode(b"\xff\xd8\xfffirst").decode("ascii")],
                ),
                ("Click input sent; the screenshot must confirm its effect.", None),
                (
                    "Screenshot captured.",
                    [base64.b64encode(b"\xff\xd8\xffsecond").decode("ascii")],
                ),
            ]
        )
        agent.agent_window_bounds = (617, 112, 587, 642, 1368, 768)
        agent.screenshot_source_size = (1368, 768)
        agent.screenshot_image_size = (1024, 576)

        agent._run_turn("http://localhost:11434", "qwen3-vl:8b", "Desktop control")

        self.assertEqual(
            observed_requests[0][-1]["images"],
            [base64.b64encode(b"\xff\xd8\xfffirst").decode("ascii")],
        )
        self.assertIn(
            "x=432..930, y=54..575", observed_requests[0][-1]["content"]
        )
        first_tool_names = [
            tool["function"]["name"] for tool in observed_tools[0]
        ]
        self.assertNotIn("take_screenshot", first_tool_names)
        click_tool = next(
            tool
            for tool in observed_tools[0]
            if tool["function"]["name"] == "click"
        )
        click_properties = click_tool["function"]["parameters"]["properties"]
        self.assertEqual(click_properties["x"]["maximum"], 1023)
        self.assertEqual(click_properties["y"]["maximum"], 575)
        screenshot_messages = [
            message
            for message in agent.messages
            if message.get("images")
        ]
        self.assertEqual(len(screenshot_messages), 1)
        self.assertEqual(
            screenshot_messages[0]["images"],
            [base64.b64encode(b"\xff\xd8\xffsecond").decode("ascii")],
        )
        self.assertIn("verification screenshot", screenshot_messages[0]["content"])
        initial_screenshot = next(
            message
            for message in agent.messages
            if message.get("content", "").startswith(
                "The current desktop screenshot is attached."
            )
        )
        self.assertNotIn("images", initial_screenshot)
        click_result = next(
            message
            for message in agent.messages
            if message.get("tool_name") == "click"
        )
        self.assertIn("screenshot must confirm", click_result["content"])
        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["take_screenshot", "click", "take_screenshot"],
        )
        self.assertEqual(completed, [("Done.", None)])

    def test_blocked_coordinate_action_can_be_corrected_without_extra_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Focus Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "focus_window",
                                    "arguments": {"x": 1024, "y": 576},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "I will retry within bounds."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                (
                    "Screenshot captured and attached at 1024x576.",
                    [base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")],
                ),
                (
                    "Action blocked: coordinates are outside the screenshot bounds. "
                    "Valid screenshot coordinates are x=0..1023 and y=0..575. "
                    "No input was sent.",
                    None,
                ),
            ]
        )

        agent._run_turn("http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control")

        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["take_screenshot", "focus_window"],
        )
        self.assertEqual(agent._chat.call_count, 2)
        self.assertIn("No desktop action was taken", completed[0][0])
        self.assertIsNone(completed[0][1])

    def test_focus_blocked_by_green_man_allows_one_corrected_attempt(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Focus Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        screenshot_data = base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "focus_window",
                                    "arguments": {"x": 500, "y": 500},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "focus_window",
                                    "arguments": {"x": 180, "y": 45},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Chrome is focused."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                ("Screenshot captured.", [screenshot_data]),
                (
                    "Action blocked: the chosen point is inside or too close to the "
                    "Green Man window. No input was sent.",
                    None,
                ),
                ("Focused the visible Chrome window.", None),
                ("Verification screenshot.", [screenshot_data]),
            ]
        )
        agent.agent_window_bounds = (617, 112, 587, 642, 1368, 768)
        agent.screenshot_image_size = (1024, 576)

        agent._run_turn(
            "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
        )

        self.assertEqual(agent._chat.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["take_screenshot", "focus_window", "focus_window", "take_screenshot"],
        )
        blocked_result = next(
            item
            for item in agent.messages
            if item.get("tool_name") == "focus_window"
            and "Action blocked:" in item["content"]
        )
        self.assertIn("Chrome visible behind Green Man", blocked_result["content"])
        self.assertIn("visible strip above it is y=0..43", blocked_result["content"])
        self.assertEqual(completed, [("Chrome is focused.", None)])

    def test_second_green_man_blocked_focus_stops_without_looping(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Focus Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        screenshot_data = base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")
        focus_call = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "focus_window",
                            "arguments": {"x": 500, "y": 500},
                        }
                    }
                ],
            }
        }
        agent._chat = Mock(
            side_effect=[
                focus_call,
                focus_call,
            ]
        )
        blocked_result = (
            "Action blocked: the chosen point is inside or too close to the "
            "Green Man window. No input was sent.",
            None,
        )
        agent._execute_tool = Mock(
            side_effect=[
                ("Screenshot captured.", [screenshot_data]),
                blocked_result,
                blocked_result,
            ]
        )

        agent._run_turn(
            "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
        )

        self.assertEqual(agent._chat.call_count, 2)
        self.assertIn("could not focus Chrome safely", completed[0][0])
        self.assertIsNone(completed[0][1])

    def test_out_of_bounds_focus_provides_exact_safe_retry_coordinate(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Focus Chrome."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        screenshot_data = base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "focus_window",
                                    "arguments": {"x": 1024, "y": 576},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "focus_window",
                                    "arguments": {"x": 499, "y": 53},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Chrome is focused."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                ("Screenshot captured.", [screenshot_data]),
                (
                    "Action blocked: Coordinates must be within the screenshot size "
                    "1024x576. Valid screenshot coordinates are x=0..1023 and "
                    "y=0..575. No input was sent.",
                    None,
                ),
                ("Focused the visible Chrome window.", None),
                ("Verification screenshot.", [screenshot_data]),
            ]
        )
        agent.agent_window_bounds = (617, 112, 587, 642, 1368, 768)
        agent.screenshot_image_size = (1024, 576)
        agent.screenshot_source_size = (1368, 768)

        agent._run_turn(
            "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
        )

        self.assertEqual(agent._chat.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["take_screenshot", "focus_window", "focus_window", "take_screenshot"],
        )
        blocked_result = next(
            item
            for item in agent.messages
            if item.get("tool_name") == "focus_window"
            and "Action blocked:" in item["content"]
        )
        self.assertIn("exactly x=499, y=53", blocked_result["content"])
        self.assertEqual(completed, [("Chrome is focused.", None)])

    def test_action_saves_verification_screenshot_and_reports_path(self) -> None:
        screenshot_data = base64.b64encode(b"\xff\xd8\xffexample").decode("ascii")
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the untitled tab."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (100, 50)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        agent._finish = Mock()
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "click",
                                    "arguments": {"x": 10, "y": 20},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Clicked."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                ("Initial screenshot.", [screenshot_data]),
                ("Click sent.", None),
                ("Verification screenshot.", [screenshot_data]),
            ]
        )

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434",
                "qwen3-vl:4b-instruct",
                "Desktop control",
            )
            path = Path(home) / ".cache" / "greenman" / "last-desktop-verification.jpg"
            saved_screenshot = path.read_bytes()

        self.assertEqual(saved_screenshot, b"\xff\xd8\xffexample")
        self.assertEqual(agent._finish.call_args.args[1], None)
        action_result = next(
            item for item in agent.messages if item.get("tool_name") == "click"
        )
        self.assertIn(str(path), action_result["content"])

    def test_close_request_uses_named_window_discovery_and_verification(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Close Google Chrome."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        target = AccessibleWindow(
            "Google Chrome",
            "Green Man docs - Google Chrome",
            ":1.11",
            "/org/a11y/atspi/window/1",
        )
        agent.last_named_close_window = target
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "list_windows", "arguments": {}}}
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_named_window",
                                    "arguments": {
                                        "title_or_app": target.title,
                                    },
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "list_windows", "arguments": {}}}
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "It is closed."}},
            ]
        )

        def execute_tool(name, _arguments):
            if name == "list_windows":
                close_sent = any(
                    call.args[0] == "close_named_window"
                    for call in agent._execute_tool.call_args_list
                )
                if close_sent:
                    return "[]", None
                return (
                    json.dumps(
                        [
                            {
                                "application": target.application,
                                "title": target.title,
                            }
                        ]
                    ),
                    None,
                )
            return "Sent the close-window shortcut.", None

        agent._execute_tool = Mock(side_effect=execute_tool)
        agent._run_turn(
            "http://localhost:11434", "llama3.1:8b", "Desktop control"
        )

        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["list_windows", "close_named_window", "list_windows"],
        )
        self.assertIn("no longer contains", completed[0][0])
        self.assertIn(target.title, completed[0][0])
        self.assertIsNone(completed[0][1])

    def test_open_request_uses_catalog_approval_and_window_verification(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Open Google Chrome."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        application = DesktopApplication(
            "Google Chrome",
            "google-chrome.desktop",
            Path("/usr/share/applications/google-chrome.desktop"),
        )
        agent.last_launched_application = application
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "list_applications",
                                    "arguments": {},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "launch_application",
                                    "arguments": {"title_or_app": "Google Chrome"},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "list_windows", "arguments": {}}}
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "It is open."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                (
                    json.dumps(
                        [
                            {
                                "name": application.name,
                                "desktop_id": application.desktop_id,
                            }
                        ]
                    ),
                    None,
                ),
                (f"Launched {application.name!r}.", None),
                (
                    json.dumps(
                        [
                            {
                                "application": application.name,
                                "title": "Google Chrome",
                            }
                        ]
                    ),
                    None,
                ),
            ]
        )

        agent._run_turn(
            "http://localhost:11434", "llama3.1:8b", "Desktop control"
        )

        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            ["list_applications", "launch_application", "list_windows"],
        )
        self.assertIn("Its window is open", completed[0][0])
        self.assertIsNone(completed[0][1])

    def test_actions_after_launch_keep_the_model_final_answer(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "(1) Open Google Chrome.\n(2) Press Ctrl+T."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        application = DesktopApplication(
            "Google Chrome",
            "google-chrome.desktop",
            Path("/usr/share/applications/google-chrome.desktop"),
        )
        agent.last_launched_application = application
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "list_applications",
                                    "arguments": {},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "launch_application",
                                    "arguments": {"title_or_app": "Google Chrome"},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {"function": {"name": "list_windows", "arguments": {}}}
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "activate_window",
                                    "arguments": {"title_or_app": "Google Chrome"},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "press_key",
                                    "arguments": {"key": "ctrl+t"},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Opened a new tab."}},
            ]
        )
        agent._execute_tool = Mock(
            side_effect=[
                ("Screenshot captured.", ["screenshot"]),
                (
                    json.dumps(
                        [
                            {
                                "name": application.name,
                                "desktop_id": application.desktop_id,
                            }
                        ]
                    ),
                    None,
                ),
                (f"Launched {application.name!r}.", None),
                (
                    json.dumps(
                        [{"application": application.name, "title": "Google Chrome"}]
                    ),
                    None,
                ),
                ("Brought 'Google Chrome' to the foreground.", None),
                ("Screenshot captured.", ["/9j/ZXhhbXBsZQ=="]),
                ("Pressed ctrl+t.", None),
                ("Screenshot captured.", ["/9j/ZXhhbXBsZQ=="]),
            ]
        )

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "llama3.1:8b", "Desktop control"
            )

        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            [
                "take_screenshot",
                "list_applications",
                "launch_application",
                "list_windows",
                "activate_window",
                "take_screenshot",
                "press_key",
                "take_screenshot",
            ],
        )
        self.assertEqual(completed[0][0], "Opened a new tab.")
        self.assertIsNone(completed[0][1])

    def test_close_window_turn_does_not_repeat_model_success_claim(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 750, "y": 40},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Chrome is still open."}},
            ]
        )
        screenshot_data = base64.b64encode(b"\xff\xd8\xffx").decode("ascii")

        def execute_tool(name, _arguments):
            if name == "close_window":
                return "Clicked approved close button at (1000, 60).", None
            return "Screenshot captured.", [screenshot_data]

        agent._execute_tool = Mock(side_effect=execute_tool)

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
            )

        self.assertIn("approved close-button click was sent", completed[0][0])
        self.assertIn("cannot confirm that Chrome exited", completed[0][0])
        self.assertIn("Chrome is still open", completed[0][0])
        self.assertIn("Inspect the verification screenshot", completed[0][0])
        self.assertIn("last-desktop-verification.jpg", completed[0][0])
        self.assertIn("No further click was sent", completed[0][0])
        self.assertEqual(agent._chat.call_count, 2)

    def test_close_window_allows_one_distinct_approved_retry(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 750, "y": 40},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 760, "y": 40},
                                }
                            }
                        ],
                    }
                },
            ]
        )
        screenshot_data = base64.b64encode(b"\xff\xd8\xffx").decode("ascii")
        agent._execute_tool = Mock(
            side_effect=lambda name, _arguments: (
                ("Clicked approved close button.", None)
                if name == "close_window"
                else ("Screenshot captured.", [screenshot_data])
            )
        )

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
            )

        close_calls = [
            call for call in agent._execute_tool.call_args_list
            if call.args[0] == "close_window"
        ]
        self.assertEqual(len(close_calls), 2)
        self.assertEqual(
            [call.args[1] for call in close_calls],
            [{"x": 750, "y": 40}, {"x": 760, "y": 40}],
        )
        self.assertEqual(agent._chat.call_count, 2)
        self.assertEqual(
            agent._chat.call_args.kwargs["tools"],
            tools_for_desktop_screenshot(
                tools_for_mode("Desktop control"),
                (1024, 576),
                close_only=True,
            ),
        )
        self.assertIn("user must approve this second click", agent.messages[-4]["content"])
        self.assertIn("A close-button click was sent on the second attempt", completed[0][0])
        self.assertIn("does not confirm that Chrome exited", completed[0][0])

    def test_close_window_blocks_retry_at_same_point(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        same_point_call = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "close_window",
                            "arguments": {"x": 750, "y": 40},
                        }
                    }
                ],
            }
        }
        agent._chat = Mock(side_effect=[same_point_call, same_point_call])
        screenshot_data = base64.b64encode(b"\xff\xd8\xffx").decode("ascii")
        agent._execute_tool = Mock(
            side_effect=lambda name, _arguments: (
                ("Clicked approved close button.", None)
                if name == "close_window"
                else ("Screenshot captured.", [screenshot_data])
            )
        )

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
            )

        close_calls = [
            call for call in agent._execute_tool.call_args_list
            if call.args[0] == "close_window"
        ]
        self.assertEqual(len(close_calls), 1)
        self.assertIn("same point again", completed[0][0])
        self.assertIn("No second close click was sent", completed[0][0])

    def test_close_window_stops_when_corrected_retry_is_blocked(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 750, "y": 40},
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 760, "y": 40},
                                }
                            }
                        ],
                    }
                },
            ]
        )
        screenshot_data = base64.b64encode(b"\xff\xd8\xffx").decode("ascii")
        agent._execute_tool = Mock(
            side_effect=[
                ("Screenshot captured.", [screenshot_data]),
                ("Clicked approved close button.", None),
                ("Screenshot captured.", [screenshot_data]),
                ("Action blocked: Green Man covers that point.", None),
            ]
        )

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
            )

        self.assertEqual(agent._chat.call_count, 2)
        self.assertEqual(
            [
                call.args[0]
                for call in agent._execute_tool.call_args_list
                if call.args[0] == "close_window"
            ],
            ["close_window", "close_window"],
        )
        self.assertIn("second close attempt did not send a click", completed[0][0])
        self.assertIn("first approved click was sent", completed[0][0])
        self.assertIn("last-desktop-verification.jpg", completed[0][0])

    def test_failed_desktop_turn_clears_stale_tool_and_image_history(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Describe my desktop."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            return_value={
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "take_screenshot", "arguments": {}}}
                    ],
                }
            }
        )
        agent._execute_tool = Mock(
            return_value=(
                "Screenshot captured.",
                [base64.b64encode(b"\xff\xd8\xffimage").decode("ascii")],
            )
        )

        agent._run_turn(
            "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
        )

        self.assertIn("14 tool rounds", completed[0][1])
        self.assertIn(
            "Tool sequence: take_screenshot -> take_screenshot -> take_screenshot",
            completed[0][1],
        )
        self.assertEqual(len(agent.messages), 2)
        self.assertEqual(agent.messages[0]["role"], "system")
        self.assertIn("Desktop instructions.", agent.messages[0]["content"])
        self.assertEqual(agent.messages[1]["content"], "Describe my desktop.")

    def test_ollama_read_timeout_has_actionable_error(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Hello."}]
        agent.active_response_lock = Lock()
        agent.active_response = None

        with (
            patch("app.urlopen", side_effect=TimeoutError("timed out")),
            self.assertRaisesRegex(
                RuntimeError,
                f"Ollama did not respond within {OLLAMA_REQUEST_TIMEOUT_SECONDS} seconds",
            ),
        ):
            agent._chat(
                "http://127.0.0.1:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

    def test_chat_connection_error_includes_underlying_reason(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Hello."}]
        with (
            patch("app.urlopen", side_effect=URLError("Connection refused")),
            self.assertRaisesRegex(RuntimeError, "Connection refused"),
        ):
            agent._chat(
                "http://127.0.0.1:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

    def test_chat_http_error_is_reported_as_http_error(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Hello."}]
        error = HTTPError(
            "http://127.0.0.1:11434/api/chat",
            500,
            "Internal Server Error",
            {},
            None,
        )
        error.read = Mock(return_value=b"model runner failed")
        with (
            patch("app.urlopen", side_effect=error),
            self.assertRaisesRegex(
                RuntimeError, "(?s)HTTP 500.*model runner failed"
            ),
        ):
            agent._chat(
                "http://127.0.0.1:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

    def test_multimodal_http_error_explains_vision_model_requirement(self) -> None:
        error_body = json.dumps(
            {
                "error": json.dumps(
                    {
                        "error": {
                            "code": 400,
                            "message": (
                                "Multimodal data provided, but model does not support "
                                "multimodal requests."
                            ),
                            "type": "invalid_request_error",
                        }
                    }
                )
            }
        )

        message = ollama_http_error_message(
            "http://127.0.0.1:11434/api/chat", 400, error_body
        )

        self.assertIn("selected model does not support images", message)
        self.assertIn("vision and tool calling", message)

    def test_other_http_errors_keep_server_details(self) -> None:
        message = ollama_http_error_message(
            "http://127.0.0.1:11434/api/chat", 500, '{"error":"server failure"}'
        )
        self.assertIn("HTTP 500", message)
        self.assertIn("server failure", message)

    def test_detects_tool_request_returned_as_text(self) -> None:
        response = '{"name":"screenshot","parameters":{"filename":"screenshot.png"}}'
        self.assertTrue(is_text_tool_call(response))

    def test_does_not_match_regular_json_or_text(self) -> None:
        self.assertFalse(is_text_tool_call('{"name":"Ada"}'))
        self.assertFalse(is_text_tool_call("Hello, how can I help?"))

    def test_detects_desktop_action_requests_without_matching_how_to_questions(self) -> None:
        self.assertTrue(is_desktop_action_request("Close Google Chrome."))
        self.assertTrue(is_desktop_action_request("Can you click the close button?"))
        self.assertFalse(is_desktop_action_request("How do I close Google Chrome?"))
        self.assertFalse(is_desktop_action_request("What is open on my desktop?"))

    def test_retries_generic_response_to_desktop_action_and_reports_no_action(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Google Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        generic_answer = (
            "I'm ready to assist you. Please let me know what you'd like to do next."
        )
        screenshot_data = base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")
        agent._chat = Mock(
            side_effect=[
                {"message": {"role": "assistant", "content": generic_answer}},
                {"message": {"role": "assistant", "content": generic_answer}},
            ]
        )
        agent._execute_tool = Mock(
            return_value=("Screenshot captured.", [screenshot_data])
        )

        agent._run_turn(
            "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
        )

        self.assertEqual(agent._chat.call_count, 2)
        self.assertIn(
            "The user's latest message requests a desktop action",
            agent._chat.call_args.kwargs["messages"][0]["content"],
        )
        self.assertEqual(
            agent._chat.call_args.kwargs["tools"],
            tools_for_desktop_screenshot(
                tools_for_mode("Desktop control"),
                (1024, 576),
                close_only=False,
            ),
        )
        retry_messages = agent._chat.call_args.kwargs["messages"]
        self.assertEqual(retry_messages[-1]["images"], [screenshot_data])
        self.assertIn("current desktop screenshot is attached", retry_messages[-1]["content"])
        self.assertEqual(agent._execute_tool.call_count, 2)
        self.assertEqual(
            [call.args for call in agent._execute_tool.call_args_list],
            [("take_screenshot", {}), ("take_screenshot", {})],
        )
        self.assertIn("No desktop action was taken", completed[0][0])
        self.assertIn("No desktop action was taken", completed[0][0])

    def test_desktop_action_retry_can_use_the_fresh_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "Desktop instructions."},
            {"role": "user", "content": "Click the upper-right button in Google Chrome."},
        ]
        agent.root = Mock()
        agent.screenshot_image_size = (1024, 576)
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        screenshot_data = base64.b64encode(b"\xff\xd8\xffscreen").decode("ascii")
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "content": "I'm ready to assist you.",
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "close_window",
                                    "arguments": {"x": 40, "y": 10},
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Chrome remains open."}},
            ]
        )

        def execute_tool(name, _arguments):
            if name == "take_screenshot":
                return "Screenshot captured.", [screenshot_data]
            return "Clicked approved close button at (40, 10).", None

        agent._execute_tool = Mock(side_effect=execute_tool)

        with TemporaryDirectory() as home, patch.dict("os.environ", {"HOME": home}):
            agent._run_turn(
                "http://localhost:11434", "qwen3-vl:4b-instruct", "Desktop control"
            )

        self.assertEqual(agent._chat.call_count, 3)
        self.assertEqual(
            agent._chat.call_args_list[1].kwargs["messages"][-1]["images"],
            [screenshot_data],
        )
        self.assertEqual(
            [call.args[0] for call in agent._execute_tool.call_args_list],
            [
                "take_screenshot",
                "take_screenshot",
                "close_window",
                "take_screenshot",
            ],
        )
        self.assertIn("approved close-button click was sent", completed[0][0])
        self.assertIn("cannot confirm that Chrome exited", completed[0][0])

    def test_retries_plain_text_tool_request_without_tools(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "What is your name?"},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"name":"screenshot","parameters":{"filename":"screenshot.png"}}',
                    }
                },
                {"message": {"role": "assistant", "content": "I am a local assistant."}},
            ]
        )

        agent._run_turn("http://localhost:11434", "llama3.1:8b")

        self.assertEqual(completed, [("I am a local assistant.", None)])
        self.assertEqual(agent._chat.call_args.kwargs["tools"], [])
        self.assertEqual(agent._chat.call_args_list[0].kwargs["tools"], [])
        self.assertEqual(agent.messages[-1]["content"], "I am a local assistant.")

    def test_empty_length_limited_response_is_reported_clearly(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Describe this image."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            return_value={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "Still reasoning" * 20,
                },
                "done_reason": "length",
                "eval_count": 4096,
            }
        )

        agent._run_turn("http://localhost:11434", "qwen3-vl:8b", "Workspace files")

        self.assertEqual(completed[0][0], "")
        self.assertIn("extended internal reasoning", completed[0][1])
        self.assertIn("4096 tokens", completed[0][1])
        self.assertIn("qwen3-vl:4b-instruct", completed[0][1])

    def test_workspace_turn_corrects_blocked_root_path(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "inside.txt").write_text("inside", encoding="utf-8")
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = root
            agent.messages = [
                {"role": "system", "content": "System prompt."},
                {"role": "user", "content": "What files are in your workspace folder?"},
            ]
            agent.root = Mock()
            agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
            completed = []
            agent._finish = lambda answer, error: completed.append((answer, error))
            agent._track_step = Mock()
            agent._chat = Mock(side_effect=[
                {"message": {"role": "assistant", "tool_calls": [
                    {"function": {"name": "list_files", "arguments": {"path": "/"}}}
                ]}},
                {"message": {"role": "assistant", "tool_calls": [
                    {"function": {"name": "list_files", "arguments": {"path": "."}}}
                ]}},
                {"message": {"role": "assistant", "content": "inside.txt"}},
            ])

            agent._run_turn("http://localhost:11434", "llama3.1:8b", "Workspace files")

            tool_messages = [
                message for message in agent.messages if message.get("role") == "tool"
            ]
            self.assertEqual(len(tool_messages), 2)
            self.assertIn("Action blocked: Path must stay", tool_messages[0]["content"])
            self.assertIn("Use '.'", tool_messages[0]["content"])
            self.assertEqual(json.loads(tool_messages[1]["content"]), ["inside.txt"])
            self.assertIn("Use '.'", agent.messages[0]["content"])
            self.assertEqual(completed, [("inside.txt", None)])

    def test_workspace_turn_stops_repeated_outside_paths(self) -> None:
        with TemporaryDirectory() as folder:
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)
            agent.messages = [
                {"role": "system", "content": "System prompt."},
                {"role": "user", "content": "List the workspace."},
            ]
            agent.root = Mock()
            agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
            completed = []
            agent._finish = lambda answer, error: completed.append((answer, error))
            agent._track_step = Mock()
            agent._chat = Mock(return_value={
                "message": {"role": "assistant", "tool_calls": [
                    {"function": {"name": "list_files", "arguments": {"path": "/"}}}
                ]}
            })

            agent._run_turn("http://localhost:11434", "llama3.1:8b", "Workspace files")

            self.assertEqual(agent._chat.call_count, 2)
            self.assertIn("Stopped repeating a blocked list_files", completed[0][0])

    def test_rejects_tool_calls_outside_selected_mode(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Write a file."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            return_value={
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "write_file",
                                "arguments": {"path": "HelloWorld.txt", "content": "Hello"},
                            }
                        }
                    ],
                }
            }
        )
        agent._execute_tool = Mock()

        agent._run_turn("http://localhost:11434", "llama3.1:8b", "Questions only")

        self.assertIn("not available in Questions only mode", completed[0][1])
        agent._execute_tool.assert_not_called()


class DesktopSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(DesktopAgent, "face", Mock(), create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_and_prompt_remain_visible_while_working_in_short_window(self) -> None:
        try:
            root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(root.destroy)
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_begin_model_load"
        ):
            with patch("app.read_system_status", return_value=(40, 10)), patch(
                "app.read_cpu_counters", return_value=(800, 700)
            ):
                agent = DesktopAgent(root)
            def cancel_callbacks() -> None:
                for callback in root.tk.splitlist(root.tk.call("after", "info")):
                    root.after_cancel(callback)

            self.addCleanup(cancel_callbacks)
            status_label = next(
                child
                for row in root.winfo_children()
                for child in row.winfo_children()
                if isinstance(child, tk.Label)
                and str(child.cget("textvariable")) == str(agent.status)
            )
            metrics_label = next(
                child
                for row in root.winfo_children()
                for child in row.winfo_children()
                if isinstance(child, tk.Label)
                and str(child.cget("textvariable")) == str(agent.system_status)
            )
            root.geometry("820x650")
            self.assertIn("Elapsed Time - 00:00", agent.system_status.get())
            self.assertIn("GPU - 10% utilization", agent.system_status.get())
            scheduled = agent.system_status_after
            agent.workspace = Path(folder)
            agent.prompt.insert("1.0", "Test the status line")
            with patch("app.threading.Thread"), patch(
                "app.read_system_status", return_value=(55, 60)
            ), patch("app.read_cpu_counters", return_value=(1000, 800)), patch(
                "app.time.monotonic", return_value=100.0
            ):
                agent._send()
            self.assertTrue(agent.busy)
            with patch("app.read_system_status", return_value=(55, 60)), patch(
                "app.read_cpu_counters", return_value=(1200, 900)
            ), patch("app.time.monotonic", return_value=165.0):
                agent._refresh_system_status()
            root.update_idletasks()
            self.assertEqual(agent.status.get(), "Working…")
            self.assertIn("Elapsed Time - 01:05", agent.system_status.get())
            self.assertIn("GPU - 60% utilization", agent.system_status.get())
            for widget in (
                status_label, metrics_label, agent.prompt, agent.working_indicator
            ):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())
                self.assertLessEqual(
                    widget.winfo_rooty() + widget.winfo_height(),
                    root.winfo_rooty() + root.winfo_height(),
                )
            self.assertGreater(agent.transcript.winfo_height(), 1)
            self.assertGreaterEqual(
                metrics_label.winfo_width(), metrics_label.winfo_reqwidth()
            )
            agent.status.set("Another status message")
            self.assertIn("Elapsed Time - 01:05", agent.system_status.get())
            with patch("app.read_system_status", return_value=(56, 61)), patch(
                "app.read_cpu_counters", return_value=(1400, 1000)
            ), patch("app.time.monotonic", return_value=170.0):
                agent._finish("Finished.", None)
            root.update_idletasks()
            self.assertEqual(agent.status.get(), "Ready.")
            self.assertIn("Elapsed Time - 00:00", agent.system_status.get())
            self.assertIn("GPU - 61% utilization", agent.system_status.get())
            self.assertTrue(metrics_label.winfo_ismapped())
            self.assertEqual(agent.system_status_after, scheduled)
            self.assertIn(scheduled, root.tk.splitlist(root.tk.call("after", "info")))
            with patch("app.read_system_status", return_value=(57, 62)), patch(
                "app.read_cpu_counters", return_value=(1600, 1100)
            ), patch("app.time.monotonic", return_value=180.0):
                root.after_cancel(scheduled)
                agent._update_system_status()
            self.assertIn("Elapsed Time - 00:00", agent.system_status.get())
            self.assertIn("CPU - 50% utilization", agent.system_status.get())
            self.assertIn("GPU - 62% utilization", agent.system_status.get())

    def test_window_fits_requested_content_without_exceeding_screen(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.root = Mock()
        agent.root.winfo_reqwidth.return_value = 960
        agent.root.winfo_reqheight.return_value = 880
        agent.root.winfo_screenwidth.return_value = 1920
        agent.root.winfo_screenheight.return_value = 1080

        agent._fit_window_to_content()

        agent.root.update_idletasks.assert_called_once_with()
        agent.root.geometry.assert_called_once_with("960x880")

    def test_window_fit_is_clamped_to_available_screen_size(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.root = Mock()
        agent.root.winfo_reqwidth.return_value = 1600
        agent.root.winfo_reqheight.return_value = 1200
        agent.root.winfo_screenwidth.return_value = 1366
        agent.root.winfo_screenheight.return_value = 768

        agent._fit_window_to_content()

        agent.root.geometry.assert_called_once_with("1286x688")

    def test_system_prompt_dialog_fits_its_requested_content(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        dialog = Mock()
        dialog.winfo_reqwidth.return_value = 840
        dialog.winfo_reqheight.return_value = 530
        dialog.winfo_screenwidth.return_value = 1920
        dialog.winfo_screenheight.return_value = 1080

        agent._fit_window_to_content(dialog, minimum_size=(720, 480))

        dialog.update_idletasks.assert_called_once_with()
        dialog.geometry.assert_called_once_with("840x530")

    def test_remembered_desktop_approval_skips_click_and_typing_prompts(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.remember_desktop_approvals = True
        agent.root = Mock()

        self.assertTrue(agent._request_approval("click", {"x": 10, "y": 20}))
        self.assertTrue(agent._request_approval("type_text", {"text": "hello"}))

        agent.root.after.assert_not_called()

    def test_remembered_desktop_approval_does_not_skip_file_or_command_prompts(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.remember_desktop_approvals = True
        agent.root = Mock()
        agent.root.after.side_effect = (
            lambda _delay, callback, *args: callback(*args)
        )

        def approve(_name, _args, decision, completed) -> None:
            decision.append(True)
            completed.set()

        agent._show_approval = Mock(side_effect=approve)

        self.assertTrue(agent._request_approval("write_file", {"path": "file.txt"}))
        self.assertTrue(agent._request_approval("run_command", {"command": "ls"}))

        self.assertEqual(agent._show_approval.call_count, 2)

    def test_send_button_shows_red_stop_during_query(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.cancel_event = Event()
        agent.send_button = Mock()

        agent._update_send_button()

        agent.send_button.config.assert_called_once_with(
            text="Stop",
            state="normal",
            bg="#a32626",
            fg="#ffffff",
            activebackground="#c43c3c",
            activeforeground="#ffffff",
            disabledforeground="#183b24",
        )

    def test_stop_query_sets_cancel_event_and_closes_active_response(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.cancel_event = Event()
        agent.active_response = Mock()
        agent.active_response_lock = Lock()
        agent.send_button = Mock()
        agent.status = Mock()
        agent._update_send_button = Mock()

        agent._stop_query()

        self.assertTrue(agent.cancel_event.is_set())
        agent.active_response.fp.raw._sock.shutdown.assert_called_once_with(
            socket.SHUT_RDWR
        )
        agent.active_response.close.assert_called_once_with()
        agent._update_send_button.assert_called_once_with()

    def test_cancelled_turn_does_not_execute_returned_tool_call(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.cancel_event = Event()
        agent.messages = [{"role": "user", "content": "Run this action."}]
        agent.root = Mock()
        completed = []
        agent._finish = lambda *args: completed.append(args)
        agent._chat = Mock(
            side_effect=lambda *args, **kwargs: (
                agent.cancel_event.set()
                or {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "take_screenshot",
                                    "arguments": {},
                                }
                            }
                        ],
                    }
                }
            )
        )
        agent._execute_tool = Mock()

        agent._run_turn("http://localhost:11434", "llama3.1:8b", "Screenshot")

        agent._execute_tool.assert_not_called()
        agent.root.after.assert_called_once()
        self.assertEqual(agent.root.after.call_args.args[2:], ("", None, True))

    def test_finish_appends_elapsed_duration_after_answer(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.transcript = Mock()
        agent.turn_started_at = 10.0
        agent.busy = True
        agent.progress_after = None
        agent.root = Mock()
        agent.model_selector = Mock()
        agent.send_button = Mock()
        agent.new_chat_button = Mock()
        agent.save_transcript_button = Mock()
        agent.mode_buttons = []
        agent.prompt = Mock()
        agent.url_entry = Mock()
        agent.workspace_button = Mock()
        agent.voice_directory_button = Mock()
        agent.working_indicator = Mock()
        agent.attachment_status = Mock()
        agent.cancel_event = Event()
        agent.status = Mock()
        agent.system_status = Mock()
        agent.previous_cpu_counters = None
        agent._append = Mock()
        agent._update_send_button = Mock()

        with patch("app.time.monotonic", return_value=13.25):
            agent._finish("Here is the answer.", None)

        self.assertEqual(
            agent._append.call_args_list,
            [
                unittest.mock.call("Assistant", "Here is the answer."),
                unittest.mock.call("Query Duration", "3.2 seconds"),
            ],
        )
        self.assertIsNone(agent.turn_started_at)
        self.assertFalse(agent.busy)
        agent.prompt.config.assert_called_once_with(state="normal")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent.workspace_button.config.assert_called_once_with(state="normal")
        agent.voice_directory_button.config.assert_called_once_with(state="normal")
        agent.working_indicator.pack_forget.assert_called_once_with()
        self.assertIsNone(agent.cancel_event)
        agent.working_indicator.pack_forget.assert_called_once_with()
        agent.attachment_status.set.assert_called_once_with(IMAGE_DROP_HINT)

    def test_finish_resets_timer_on_success_error_and_cancellation(self) -> None:
        for error, cancelled in ((None, False), ("failed", False), (None, True)):
            with self.subTest(error=error, cancelled=cancelled):
                agent = DesktopAgent.__new__(DesktopAgent)
                agent.root = Mock()
                agent.face = Mock()
                agent.status = Mock()
                agent.system_status = Mock()
                agent.previous_cpu_counters = (1000, 800)
                agent.turn_started_at = 10.0
                agent.busy = True
                agent.cancel_event = Event()
                if cancelled:
                    agent.cancel_event.set()
                agent.attachment_status = Mock()
                agent._stop_progress_animation = Mock()
                agent._clear_step_highlight = Mock()
                agent._append = Mock()
                agent.model_selector = Mock()
                agent.url_entry = Mock()
                agent.prompt = Mock()
                agent.workspace_button = Mock()
                agent.voice_directory_button = Mock()
                agent.new_chat_button = Mock()
                agent.save_transcript_button = Mock()
                agent._update_send_button = Mock()
                agent._update_mode_buttons = Mock()
                with patch("app.read_system_status", return_value=(55, 60)), patch(
                    "app.read_cpu_counters", return_value=(1200, 900)
                ), patch("app.time.monotonic", return_value=15.0):
                    agent._finish("Finished", error)
                self.assertIn(
                    "Elapsed Time - 00:00", agent.system_status.set.call_args.args[0]
                )
                agent._append.assert_any_call("Query Duration", "5.0 seconds")

    def test_microphone_click_starts_offline_listening(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.is_listening = False
        agent.listening_event = None
        agent.root = Mock()
        agent.status = Mock()
        agent._draw_microphone_icon = Mock()
        agent._microphone_availability_error = Mock(return_value=None)

        with patch("app.threading.Thread") as thread:
            result = agent._on_microphone_click()

        self.assertEqual(result, "break")
        self.assertTrue(agent.is_listening)
        self.assertIsNotNone(agent.listening_event)
        agent.status.set.assert_called_once_with(
            "Listening… Click the microphone again to stop."
        )
        agent._draw_microphone_icon.assert_called_once_with()
        thread.assert_called_once()
        self.assertEqual(thread.call_args.kwargs["target"], agent._listen_for_speech)
        thread.return_value.start.assert_called_once_with()

    def test_microphone_click_stops_active_listening(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.is_listening = True
        agent.listening_event = Event()
        agent.status = Mock()
        agent.microphone_button = Mock()
        agent._draw_microphone_icon = Mock()

        result = agent._on_microphone_click()

        self.assertEqual(result, "break")
        self.assertFalse(agent.is_listening)
        self.assertTrue(agent.listening_event.is_set())
        agent.status.set.assert_called_once_with("Finishing dictation…")
        agent._draw_microphone_icon.assert_called_once_with()
        agent.microphone_button.config.assert_called_once_with(
            state="disabled", cursor=""
        )

    def test_microphone_transcription_is_appended_to_prompt(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.prompt = Mock()
        agent.prompt.get.return_value = "Existing message"
        agent.busy = False

        agent._insert_transcription("spoken words")

        agent.prompt.insert.assert_called_once_with("end-1c", " spoken words")
        agent.prompt.mark_set.assert_called_once_with("insert", "end-1c")
        agent.prompt.see.assert_called_once_with("insert")

    def test_microphone_setup_reports_missing_portaudio_library(self) -> None:
        with (
            patch("app.importlib.util.find_spec", return_value=object()),
            patch(
                "app.importlib.import_module",
                side_effect=OSError("PortAudio library not found"),
            ),
        ):
            error = DesktopAgent._microphone_availability_error()

        self.assertIsNotNone(error)
        self.assertIn("sudo apt install libportaudio2", error)
        self.assertIn("PortAudio library not found", error)

    def test_send_attaches_dropped_image_to_user_message(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.transcript = Mock()
        agent.request_history = []
        agent._refresh_history_view = Mock()
        agent.busy = False
        agent.workspace = Path(".")
        agent.prompt = Mock()
        agent.prompt.get.return_value = "What does this error mean?"
        agent.prompt.delete = Mock()
        agent.pending_image = ("error.png", "aGVsbG8=")
        agent.messages = []
        agent.screen_observed = False
        agent.send_button = Mock()
        agent.new_chat_button = Mock()
        agent.save_transcript_button = Mock()
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.workspace_button = Mock()
        agent.voice_directory_button = Mock()
        agent.working_indicator = Mock()
        agent.mode_buttons = []
        agent.status = Mock()
        agent.attachment_status = Mock()
        agent.url_entry = Mock()
        agent.url_entry.get.return_value = "http://127.0.0.1:11434"
        agent.active_model = "qwen3-vl:8b"
        agent.tool_mode = Mock()
        agent.tool_mode.get.return_value = "Questions only"
        agent._append = Mock()
        agent._clear_pending_image = Mock()
        agent._start_progress_animation = Mock()
        agent._refresh_system_status = Mock()

        with patch("app.threading.Thread") as thread:
            agent._send()

        self.assertEqual(
            agent.messages,
            [
                {
                    "role": "user",
                    "content": "What does this error mean?",
                    "images": ["aGVsbG8="],
                }
            ],
        )
        agent._append.assert_called_once_with(
            "You",
            "What does this error mean? [Image attached: error.png]",
        )
        agent.prompt.config.assert_called_once_with(state="disabled")
        agent.url_entry.config.assert_called_once_with(state="disabled")
        agent.workspace_button.config.assert_called_once_with(state="disabled")
        agent.voice_directory_button.config.assert_called_once_with(state="disabled")
        agent._start_progress_animation.assert_called_once_with()
        agent._clear_pending_image.assert_called_once_with()
        agent.attachment_status.set.assert_called_once_with("")
        thread.assert_called_once()

    def test_progress_segment_is_three_fifths_of_track(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.working_indicator = Mock()
        agent.working_indicator.winfo_width.return_value = 1000
        agent.working_indicator.winfo_height.return_value = 18
        agent.progress_segment = "segment"
        agent.progress_position = 0
        agent.progress_direction = 1
        agent.root = Mock()
        agent.root.after.return_value = "animation"

        agent._animate_progress()

        agent.working_indicator.coords.assert_called_once_with(
            "segment", 8, 0, 608, 18
        )
        agent.root.after.assert_called_once_with(30, agent._animate_progress)
        self.assertEqual(agent.progress_after, "animation")

    def test_prompt_keypresses_are_blocked_while_busy(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        self.assertEqual(agent._on_prompt_enter(Mock(keysym="Return")), "break")
        agent._on_prompt_other_key(Mock(keysym="a"))

        self.assertEqual(agent.last_prompt_enter, 10.0)
        agent._send.assert_not_called()

    def test_dropped_image_is_rejected_while_busy(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.status = Mock()
        agent.pending_image = None

        result = agent._on_image_drop(Mock(data="/tmp/image.png"))

        self.assertEqual(result, "refuse")
        self.assertIsNone(agent.pending_image)
        agent.status.set.assert_not_called()

    def test_working_status_includes_cpu_temperature_and_cpu_gpu_utilization(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.turn_started_at = 100.0
        agent.cancel_event = None
        agent.root = Mock()
        agent.root.after.return_value = "temperature-refresh"
        agent.status = Mock()
        agent.system_status = Mock()
        agent.previous_cpu_counters = (1000, 800)

        with (
            patch("app.read_system_status", return_value=(55, 60)),
            patch("app.read_cpu_counters", return_value=(1200, 900)),
            patch("app.time.monotonic", return_value=165.9),
        ):
            agent._update_system_status()

        agent.status.set.assert_not_called()
        agent.system_status.set.assert_called_once_with(
            "Elapsed Time - 01:05 / CPU - 55°C / "
            "CPU - 50% utilization / GPU - 60% utilization"
        )
        agent.root.after.assert_called_once_with(
            2000, agent._update_system_status
        )
        self.assertEqual(agent.system_status_after, "temperature-refresh")

    def test_stopping_status_keeps_elapsed_timer_visible(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.turn_started_at = 0.0
        agent.cancel_event = Event()
        agent.cancel_event.set()
        agent.root = Mock()
        agent.root.after.return_value = "refresh"
        agent.status = Mock()
        agent.system_status = Mock()
        agent.previous_cpu_counters = None

        with (
            patch("app.read_system_status", return_value=(None, None)),
            patch("app.read_cpu_counters", return_value=None),
            patch("app.time.monotonic", return_value=72.0),
        ):
            agent._update_system_status()

        agent.status.set.assert_not_called()
        self.assertIn("Elapsed Time - 01:12", agent.system_status.set.call_args.args[0])
        agent.root.after.assert_called_once_with(2000, agent._update_system_status)

    def test_double_enter_sends_and_prevents_second_newline(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = None
        agent._send = Mock()
        enter = Mock(keysym="Return")

        with patch("app.time.monotonic", side_effect=(10.0, 10.5)):
            self.assertIsNone(agent._on_prompt_enter(enter))
            self.assertEqual(agent._on_prompt_enter(enter), "break")

        agent._send.assert_called_once_with()
        self.assertIsNone(agent.last_prompt_enter)

    def test_keypad_enter_also_sends_on_second_press(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = None
        agent._send = Mock()

        with patch("app.time.monotonic", side_effect=(10.0, 10.5)):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="KP_Enter")))
            self.assertEqual(
                agent._on_prompt_enter(Mock(keysym="KP_Enter")), "break"
            )

        agent._send.assert_called_once_with()

    def test_non_enter_key_resets_double_enter_sequence(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        agent._on_prompt_other_key(Mock(keysym="a"))
        with patch("app.time.monotonic", return_value=10.2):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="Return")))

        agent._send.assert_not_called()
        self.assertEqual(agent.last_prompt_enter, 10.2)

    def test_double_enter_after_timeout_starts_a_new_sequence(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        with patch("app.time.monotonic", return_value=11.1):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="Return")))

        agent._send.assert_not_called()
        self.assertEqual(agent.last_prompt_enter, 11.1)

    def test_send_button_requires_existing_workspace_and_idle_app(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.send_button = Mock()
        agent.busy = False

        agent.workspace = None
        agent._update_send_button()
        self.assertEqual(
            agent.send_button.config.call_args.kwargs["state"], "disabled"
        )
        self.assertEqual(agent.send_button.config.call_args.kwargs["text"], "Send")
        self.assertEqual(agent.send_button.config.call_args.kwargs["fg"], "#183b24")

        with TemporaryDirectory() as folder:
            agent.workspace = Path(folder)
            agent._update_send_button()
            self.assertEqual(
                agent.send_button.config.call_args.kwargs["state"], "normal"
            )
            self.assertEqual(agent.send_button.config.call_args.kwargs["text"], "Send")
            self.assertEqual(agent.send_button.config.call_args.kwargs["bg"], "#2f6b3f")

            agent.busy = True
            agent._update_send_button()
            self.assertEqual(
                agent.send_button.config.call_args.kwargs["state"], "disabled"
            )

    def test_successful_model_load_activates_model_and_starts_new_chat(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.speech = Mock()
        agent._speak = Mock()
        agent.busy = True
        agent._model_load_control_states = []
        agent.active_model = "llama3.1:8b"
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.model_choice = Mock()
        agent.new_chat_button = Mock()
        agent.save_transcript_button = Mock()
        agent.send_button = Mock()
        agent.status = Mock()
        agent.workspace = Path(".")
        agent.mode_buttons = []
        agent.messages = [{"role": "user", "content": "old conversation"}]
        agent.system_prompt = "Custom system prompt."
        agent.screen_observed = True
        agent.transcript = Mock()
        agent._save_preferences = Mock()
        agent.voice_enabled = Mock(get=Mock(return_value=True))

        agent._finish_model_load("qwen3-vl:8b", "llama3.1:8b", None)
        agent._speak.assert_called_once_with("Ready")

        self.assertEqual(agent.active_model, "qwen3-vl:8b")
        self.assertEqual(agent.messages[0]["role"], "system")
        self.assertEqual(
            agent.messages[0]["content"], "Custom system prompt."
        )
        self.assertFalse(agent.screen_observed)
        agent.transcript.delete.assert_called_once_with("1.0", "end")
        agent.status.set.assert_called_with("qwen3-vl:8b loaded. Ready for a new chat.")
        agent.model_selector.config.assert_called_with(state="readonly")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent.save_transcript_button.config.assert_called_once_with(state="normal")
        agent._save_preferences.assert_called_once_with()

    def test_failed_model_load_restores_previous_selection(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent._model_load_control_states = []
        agent.active_model = "llama3.1:8b"
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.model_choice = Mock()
        agent.new_chat_button = Mock()
        agent.save_transcript_button = Mock()
        agent.send_button = Mock()
        agent.status = Mock()
        agent.workspace = Path(".")
        agent._append = Mock()

        agent._finish_model_load(
            "qwen3-vl:8b", "llama3.1:8b", "model not found"
        )

        agent.model_choice.set.assert_called_once_with("llama3.1:8b")
        self.assertEqual(agent.active_model, "llama3.1:8b")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent._append.assert_called_once_with("Error", "model not found")

    def test_non_vision_model_disables_visual_modes(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.model_capabilities = frozenset({"completion", "tools"})
        agent.mode_buttons = [Mock() for _ in TOOL_MODES]
        agent.tool_mode = Mock()
        agent.tool_mode.get.return_value = "Screenshot"
        agent._save_preferences = Mock()

        agent._update_mode_buttons()

        states = [
            button.config.call_args.kwargs["state"]
            for button in agent.mode_buttons
        ]
        self.assertEqual(states, ["normal", "disabled", "disabled", "normal", "normal"])
        agent.tool_mode.set.assert_called_once_with("Questions only")
        agent._save_preferences.assert_called_once_with()

    def test_send_does_not_submit_without_valid_workspace(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.workspace = None
        agent.send_button = Mock()
        agent.status = Mock()
        agent._update_send_button = Mock()
        agent.prompt = Mock()
        agent._send = DesktopAgent._send.__get__(agent)

        agent._send()

        agent._update_send_button.assert_called_once_with()
        agent.status.set.assert_called_once_with(
            "Choose a valid workspace folder before sending a message."
        )
        agent.prompt.get.assert_not_called()

    def test_blocks_screen_interaction_until_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = False
        result, images = agent._execute_tool("click", {"x": 10, "y": 20})
        self.assertIn("take a fresh screenshot", result)
        self.assertIsNone(images)

    def test_close_window_requires_screenshot_and_user_approval(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = True
        agent.screenshot_image_size = (100, 50)
        agent.screenshot_source_size = (200, 100)
        agent.agent_window_bounds = (100, 70, 50, 20, 200, 100)
        agent._request_approval = Mock(return_value=True)
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "close_window", {"x": 25, "y": 10}
        )

        self.assertIn("Clicked approved close button at (50, 20)", result)
        self.assertIsNone(images)
        self.assertFalse(agent.screen_observed)
        agent._request_approval.assert_called_once_with(
            "close_window", {"x": 25, "y": 10}
        )
        agent.wayland_desktop.click.assert_called_once_with(50, 20)

    def test_focus_window_is_blocked_without_fresh_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = False
        agent._request_approval = Mock()
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool("focus_window", {"x": 10, "y": 10})

        self.assertIn("take a fresh screenshot", result)
        self.assertIsNone(images)
        agent._request_approval.assert_not_called()
        agent.wayland_desktop.click.assert_not_called()

    def test_focus_window_blocks_click_inside_green_man_window(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = True
        agent.window_focus_ready = False
        agent.screenshot_image_size = (1024, 576)
        agent.screenshot_source_size = (1368, 768)
        agent.agent_window_bounds = (617, 112, 587, 642, 1368, 768)
        agent._request_approval = Mock()
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "focus_window", {"x": 500, "y": 500}
        )

        self.assertIn("inside or too close to the Green Man window", result)
        self.assertIn("No input was sent", result)
        self.assertIsNone(images)
        self.assertTrue(agent.screen_observed)
        self.assertFalse(agent.window_focus_ready)
        agent._request_approval.assert_not_called()
        agent.wayland_desktop.click.assert_not_called()

    def test_focus_window_rejects_out_of_bounds_before_approval(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = True
        agent.window_focus_ready = False
        agent.screenshot_image_size = (1024, 576)
        agent.screenshot_source_size = (1920, 1080)
        agent._request_approval = Mock()
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "focus_window", {"x": 1024, "y": 576}
        )

        self.assertIn("x=0..1023 and y=0..575", result)
        self.assertIn("No input was sent", result)
        self.assertIsNone(images)
        self.assertTrue(agent.screen_observed)
        self.assertFalse(agent.window_focus_ready)
        agent._request_approval.assert_not_called()
        agent.wayland_desktop.click.assert_not_called()

    def test_close_window_clicks_approved_close_control(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = True
        agent.screenshot_image_size = (100, 50)
        agent.screenshot_source_size = (200, 100)
        agent.agent_window_bounds = (100, 70, 50, 20, 200, 100)
        agent._request_approval = Mock(return_value=True)
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "close_window", {"x": 25, "y": 10}
        )

        self.assertIn("Clicked approved close button", result)
        self.assertIsNone(images)
        agent._request_approval.assert_called_once_with(
            "close_window", {"x": 25, "y": 10}
        )
        agent.wayland_desktop.click.assert_called_once_with(50, 20)

    def test_close_window_blocks_close_control_inside_green_man(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = True
        agent.screenshot_image_size = (100, 50)
        agent.screenshot_source_size = (200, 100)
        agent.agent_window_bounds = (100, 70, 50, 20, 200, 100)
        agent._request_approval = Mock()
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "close_window", {"x": 50, "y": 40}
        )

        self.assertIn("inside or too close to the Green Man window", result)
        self.assertIn("No input was sent", result)
        self.assertIsNone(images)
        agent._request_approval.assert_not_called()
        agent.wayland_desktop.click.assert_not_called()

    def test_list_windows_returns_accessible_titles_without_approval(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.window_controller = Mock()
        agent.window_controller.list_windows.return_value = [
            Mock(application="Google Chrome", title="Example - Google Chrome")
        ]
        agent._request_approval = Mock()

        result, images = agent._execute_tool("list_windows", {})

        self.assertEqual(
            json.loads(result),
            [{"application": "Google Chrome", "title": "Example - Google Chrome"}],
        )
        self.assertIsNone(images)
        agent._request_approval.assert_not_called()

    def test_close_named_window_requires_approval_and_activates_exact_window(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        target = Mock(
            application="Google Chrome",
            title="Example - Google Chrome",
            bus_name=":1.10",
            object_path="/org/a11y/atspi/window/1",
        )
        agent.root = Mock()
        agent.root.title.return_value = "Local Green Man Assistant"
        agent.window_controller = Mock()
        agent.window_controller.list_windows.return_value = [target]
        agent.window_controller.select_window.return_value = target
        agent.window_controller.focus_window.return_value = target
        agent.wayland_desktop = Mock()
        agent.shell_windows = Mock()
        agent.shell_windows.is_available.return_value = False
        agent._request_approval = Mock(return_value=True)

        result, images = agent._execute_tool(
            "close_named_window", {"title_or_app": "Google Chrome"}
        )

        self.assertIn("Sent the close-window shortcut", result)
        self.assertIn("Example - Google Chrome", result)
        self.assertIsNone(images)
        agent._request_approval.assert_called_once_with(
            "close_named_window",
            {
                "application": "Google Chrome",
                "title": "Example - Google Chrome",
            },
        )
        agent.window_controller.focus_window.assert_called_once_with(
            "Example - Google Chrome", "Local Green Man Assistant"
        )
        agent.wayland_desktop.close_focused_window.assert_called_once_with()

    def test_close_named_window_does_not_focus_after_denial(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        target = Mock(
            application="Google Chrome",
            title="Example - Google Chrome",
            bus_name=":1.10",
            object_path="/org/a11y/atspi/window/1",
        )
        agent.root = Mock()
        agent.root.title.return_value = "Local Green Man Assistant"
        agent.window_controller = Mock()
        agent.window_controller.list_windows.return_value = [target]
        agent.window_controller.select_window.return_value = target
        agent._request_approval = Mock(return_value=False)
        agent.wayland_desktop = Mock()

        result, images = agent._execute_tool(
            "close_named_window", {"title_or_app": "Google Chrome"}
        )

        self.assertEqual(result, "Action denied by the user.")
        self.assertIsNone(images)
        agent.window_controller.focus_window.assert_not_called()
        agent.wayland_desktop.close_focused_window.assert_not_called()

    def test_launch_application_requires_approval(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        application = Mock()
        application.name = "Google Chrome"
        application.desktop_id = "google-chrome.desktop"
        agent.application_launcher = Mock()
        agent.application_launcher.list_applications.return_value = [application]
        agent.application_launcher.resolve_application.return_value = application
        agent.application_launcher.launch.return_value = None
        agent._request_approval = Mock(return_value=True)

        result, images = agent._execute_tool(
            "launch_application", {"title_or_app": "Google Chrome"}
        )

        self.assertIn("Launched", result)
        self.assertIsNone(images)
        agent._request_approval.assert_called_once_with(
            "launch_application",
            {
                "application": "Google Chrome",
                "desktop_id": "google-chrome.desktop",
            },
        )
        agent.application_launcher.launch.assert_called_once_with(application)

    def test_rejects_outside_write_path_before_approval(self) -> None:
        with TemporaryDirectory() as folder:
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)
            agent._request_approval = Mock()

            with self.assertRaisesRegex(ValueError, "Path must stay inside"):
                agent._execute_tool(
                    "write_file",
                    {"path": "../HelloWorld.txt", "content": "Hello, world!"},
                )

            agent._request_approval.assert_not_called()

    def test_write_approval_shows_resolved_workspace_path(self) -> None:
        with TemporaryDirectory() as folder:
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)
            agent._request_approval = Mock(return_value=False)

            result, _ = agent._execute_tool(
                "write_file",
                {"path": "HelloWorld.txt", "content": "Hello, world!"},
            )

            self.assertEqual(result, "Action denied by the user.")
            approval_args = agent._request_approval.call_args.args[1]
            self.assertEqual(approval_args["resolved_path"], str(Path(folder) / "HelloWorld.txt"))
            self.assertFalse((Path(folder) / "HelloWorld.txt").exists())

    def test_view_image_attaches_supported_image_from_workspace(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nsample-image"
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "test-image-1.png"
            image_path.write_bytes(image_bytes)
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            result, images = agent._execute_tool(
                "view_image", {"path": "test-image-1.png"}
            )

        self.assertEqual(result, "Attached image test-image-1.png for visual inspection.")
        self.assertEqual(images, [base64.b64encode(image_bytes).decode("ascii")])

    def test_view_image_rejects_unsupported_file_extension(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "image.svg"
            image_path.write_text("<svg/>", encoding="utf-8")
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            with self.assertRaisesRegex(ValueError, "Image must use"):
                agent._execute_tool("view_image", {"path": image_path.name})

    def test_view_image_rejects_images_over_size_limit(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "large.png"
            image_path.write_bytes(b"x" * (MAX_IMAGE_BYTES + 1))
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            with self.assertRaisesRegex(ValueError, "10 MB view limit"):
                agent._execute_tool("view_image", {"path": image_path.name})

    def test_view_image_rejects_workspace_escape(self) -> None:
        with TemporaryDirectory() as folder:
            workspace = Path(folder) / "workspace"
            outside = Path(folder) / "outside.png"
            workspace.mkdir()
            outside.write_bytes(b"image")
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = workspace

            with self.assertRaisesRegex(ValueError, "stay inside"):
                agent._execute_tool("view_image", {"path": "../outside.png"})


if __name__ == "__main__":
    unittest.main()


class StepTrackingTests(unittest.TestCase):
    NOTES = (
        "Launch google chrome.\n"
        "Send the Enter key\n"
        "\n"
        'Enter text "Hello, world."\n'
        "Send the Ctrl+ENTER key to send email."
    )

    def test_split_request_steps_skips_blank_lines(self) -> None:
        spans = split_request_steps(self.NOTES)
        self.assertEqual(
            [self.NOTES[start:end] for start, end in spans],
            [
                "Launch google chrome.",
                "Send the Enter key",
                'Enter text "Hello, world."',
                "Send the Ctrl+ENTER key to send email.",
            ],
        )

    def test_tool_calls_advance_the_current_step(self) -> None:
        steps = [self.NOTES[s:e] for s, e in split_request_steps(self.NOTES)]
        index = current_step_index(steps, 0, "launch_application", {"title_or_app": "chrome"})
        self.assertEqual(index, 0)
        index = current_step_index(steps, index, "press_key", {"keys": "Enter"})
        self.assertEqual(index, 1)
        index = current_step_index(steps, index, "type_text", {"text": "Hello, world."})
        self.assertEqual(index, 2)
        index = current_step_index(steps, index, "press_key", {"keys": "ctrl+enter"})
        self.assertEqual(index, 3)

    def test_step_never_moves_backwards(self) -> None:
        steps = ["Launch chrome", "Press Enter"]
        self.assertEqual(current_step_index(steps, 1, "launch_application", {"title_or_app": "chrome"}), 1)
