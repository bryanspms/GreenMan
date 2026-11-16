import json
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

from tkinterdnd2 import TkinterDnD

from app import DesktopAgent
from document_reader_ui import DocumentReaderUI


class DocumentReaderNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(self.root.destroy)
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = patch.dict("os.environ", {"HOME": self.folder.name})
        self.home.start()
        self.addCleanup(self.home.stop)
        self.path = Path(self.folder.name) / "document.txt"
        self.path.write_text(
            "The first paragraph contains enough text.\n\n"
            "The second paragraph contains enough text.\n\n"
            "The third paragraph contains enough text.",
            encoding="utf-8",
        )
        self.speech = Mock()
        self.speech.speak_async.side_effect = lambda text: Event()
        self.speech.set_paused.return_value = True
        self.finished = Mock()
        self.text_ready = Mock()
        self.highlight = Mock()
        with patch.object(DocumentReaderUI, "_load_collapse_state", return_value=False):
            self.reader = DocumentReaderUI(
                self.root, self.speech, on_text_ready=self.text_ready,
                on_reading_finished=self.finished,
                on_word_highlight=self.highlight,
            )
        self.reader.chunk_strategy.set("paragraphs")
        with patch("document_reader_ui.filedialog.askopenfilename", return_value=str(self.path)):
            self.reader._open_document()

    def tearDown(self) -> None:
        if hasattr(self, "reader"):
            self.reader._stop_reading()

    def test_navigation_stops_speech_and_respects_boundaries(self) -> None:
        reader = self.reader
        self.assertEqual(str(reader.previous_chunk_button.cget("state")), "disabled")
        self.assertEqual(str(reader.next_chunk_button.cget("state")), "normal")
        reader._start_reading()
        first_event = reader.current_cancel_event
        reader._next_chunk()
        self.assertTrue(first_event.is_set())
        self.assertEqual(reader.reading_session.current_index, 1)
        self.assertIn("second paragraph", self.speech.speak_async.call_args.args[0])
        self.assertEqual(str(reader.previous_chunk_button.cget("state")), "normal")
        self.assertEqual(str(reader.next_chunk_button.cget("state")), "normal")
        current_event = reader.current_cancel_event
        current_timer = reader._reading_after
        reader._wait_for_chunk(first_event)
        self.assertIs(reader.current_cancel_event, current_event)
        self.assertEqual(reader._reading_after, current_timer)
        self.assertEqual(reader.reading_session.current_index, 1)

        reader._pause_reading()
        self.assertTrue(reader.is_paused)
        reader._next_chunk()
        self.assertTrue(current_event.is_set())
        self.assertFalse(reader.is_paused)
        self.assertEqual(reader.reading_session.current_index, 2)
        self.assertIn("third paragraph", self.speech.speak_async.call_args.args[0])
        self.assertEqual(str(reader.next_chunk_button.cget("state")), "disabled")
        calls = self.speech.speak_async.call_count
        reader._next_chunk()
        self.assertEqual(self.speech.speak_async.call_count, calls)

        reader._previous_chunk()
        self.assertEqual(reader.reading_session.current_index, 1)
        reader._previous_chunk()
        self.assertEqual(reader.reading_session.current_index, 0)
        self.assertEqual(str(reader.previous_chunk_button.cget("state")), "disabled")
        calls = self.speech.speak_async.call_count
        reader._previous_chunk()
        self.assertEqual(self.speech.speak_async.call_count, calls)

    def test_navigation_from_stopped_starts_and_saves_target(self) -> None:
        self.reader._next_chunk()
        self.assertTrue(self.reader.is_reading)
        self.assertEqual(self.reader.reading_session.current_index, 1)
        self.assertIn("second paragraph", self.text_ready.call_args.args[0])
        self.assertEqual(
            json.loads(self.reader.reading_session._session_file.read_text())["current_index"],
            1,
        )

    def test_normal_completion_advances_and_updates_buttons(self) -> None:
        self.reader._start_reading()
        first_event = self.reader.current_cancel_event
        self.root.after_cancel(self.reader._reading_after)
        first_event.set()
        self.reader._wait_for_chunk(first_event)
        self.root.update()
        self.assertEqual(self.reader.reading_session.current_index, 1)
        self.assertIn("second paragraph", self.speech.speak_async.call_args.args[0])
        self.assertEqual(str(self.reader.previous_chunk_button.cget("state")), "normal")

    def test_scheduled_playback_progresses_after_speech_finishes(self) -> None:
        self.reader._start_reading()
        self.reader.current_cancel_event.set()
        self.root.after(150, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.reader.reading_session.current_index, 1)
        self.assertEqual(self.speech.speak_async.call_count, 2)

    def test_single_chunk_disables_both_navigation_buttons(self) -> None:
        session = self.reader.reading_session
        session.chunks = session.chunks[:1]
        session.total_chunks = 1
        self.reader._update_progress()
        self.assertEqual(str(self.reader.previous_chunk_button.cget("state")), "disabled")
        self.assertEqual(str(self.reader.next_chunk_button.cget("state")), "disabled")
        self.reader._start_reading()
        event = self.reader.current_cancel_event
        self.reader._previous_chunk()
        self.reader._next_chunk()
        self.assertIs(self.reader.current_cancel_event, event)
        self.assertFalse(event.is_set())

    def test_highlight_tracks_playback_pause_and_navigation(self) -> None:
        self.reader._start_reading()
        event = self.reader.current_cancel_event
        self.reader.speech_actually_started.set()
        self.root.after_cancel(self.reader._reading_after)
        self.reader._wait_for_chunk(event)
        text = self.text_ready.call_args.args[0]
        self.highlight.assert_called_with(text, 0, len(text))
        self.reader._pause_reading()
        self.root.after_cancel(self.reader._reading_after)
        self.reader._wait_for_chunk(event)
        self.highlight.assert_called_with("", 0, 0)
        self.reader._resume_reading()
        self.root.after_cancel(self.reader._reading_after)
        self.reader._wait_for_chunk(event)
        self.highlight.assert_called_with(text, 0, len(text))
        self.reader._next_chunk()
        self.highlight.assert_called_with("", 0, 0)

    def test_last_chunk_completes_once_without_repeating(self) -> None:
        self.reader.reading_session.jump_to_position(2)
        self.reader._start_reading()
        event = self.reader.current_cancel_event
        self.root.after_cancel(self.reader._reading_after)
        event.set()
        with patch("document_reader_ui.messagebox.showinfo") as showinfo:
            self.reader._wait_for_chunk(event)
        self.assertFalse(self.reader.is_reading)
        self.assertEqual(self.speech.speak_async.call_count, 1)
        showinfo.assert_called_once()


class DocumentReaderSendIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(self.root.destroy)
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = patch.dict("os.environ", {"HOME": self.folder.name})
        self.home.start()
        self.addCleanup(self.home.stop)
        with patch("app.preferences_path", return_value=Path(self.folder.name) / "prefs.json"), \
             patch("app.piper_voice_directory", return_value=Path(self.folder.name)), \
             patch.object(DesktopAgent, "_refresh_ollama_models"), \
             patch.object(DesktopAgent, "_begin_model_load"), \
             patch.object(DocumentReaderUI, "_load_collapse_state", return_value=False):
            self.agent = DesktopAgent(self.root)
        self.agent.workspace = Path(self.folder.name)
        self.agent._update_send_button()
        self.agent.speech.speak_async = Mock(side_effect=lambda text: Event())
        self.agent.speech.set_paused = Mock(return_value=True)
        self.path = Path(self.folder.name) / "document.txt"
        self.path.write_text(
            "The first paragraph contains enough text.\n\n"
            "The second paragraph contains enough text.",
            encoding="utf-8",
        )
        self.reader = self.agent.document_reader_ui
        self.reader.chunk_strategy.set("paragraphs")
        with patch("document_reader_ui.filedialog.askopenfilename", return_value=str(self.path)):
            self.reader._open_document()

    def tearDown(self) -> None:
        if hasattr(self, "reader"):
            self.reader._stop_reading()
        if hasattr(self, "root"):
            for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(callback)

    def test_send_disabled_until_reading_stops_even_when_paused_or_skipping(self) -> None:
        self.assertEqual(str(self.agent.send_button.cget("state")), "normal")
        self.reader._start_reading()
        self.assertEqual(str(self.agent.send_button.cget("state")), "disabled")
        self.reader._pause_reading()
        self.assertEqual(str(self.agent.send_button.cget("state")), "disabled")
        self.reader._next_chunk()
        self.assertEqual(str(self.agent.send_button.cget("state")), "disabled")
        self.reader._stop_reading()
        self.assertEqual(str(self.agent.send_button.cget("state")), "normal")

    def test_send_disabled_for_keyboard_and_restored_after_completion(self) -> None:
        self.reader._start_reading()
        self.agent.prompt.insert("1.0", "Do not send")
        self.agent.last_prompt_enter = 10.0
        with patch("app.time.monotonic", return_value=10.1):
            self.assertEqual(self.agent._on_prompt_enter(Mock(keysym="Return")), "break")
        self.assertIn("Do not send", self.agent.prompt.get("1.0", tk.END))
        self.assertIn("Stop document reading", self.agent.status.get())
        self.reader.reading_session.jump_to_position(1)
        event = self.reader.current_cancel_event
        self.root.after_cancel(self.reader._reading_after)
        event.set()
        with patch("document_reader_ui.messagebox.showinfo"):
            self.reader._wait_for_chunk(event)
        self.assertEqual(str(self.agent.send_button.cget("state")), "normal")

    def test_send_remains_disabled_after_stop_if_workspace_or_app_unavailable(self) -> None:
        self.reader._start_reading()
        self.agent.workspace = None
        self.reader._stop_reading()
        self.assertEqual(str(self.agent.send_button.cget("state")), "disabled")
        self.agent.workspace = Path(self.folder.name)
        self.reader._start_reading()
        self.agent.busy = True
        self.reader._stop_reading()
        self.assertEqual(str(self.agent.send_button.cget("state")), "disabled")

    def test_send_restored_if_starting_speech_fails(self) -> None:
        self.agent.speech.speak_async.side_effect = RuntimeError("speech failed")
        with patch("document_reader_ui.messagebox.showerror") as error:
            self.reader._start_reading()
        error.assert_called_once()
        self.assertFalse(self.reader.is_reading)
        self.assertEqual(str(self.agent.send_button.cget("state")), "normal")

    def test_stop_query_remains_available_during_reading(self) -> None:
        self.agent.cancel_event = Event()
        self.agent._update_send_button()
        self.reader._start_reading()
        self.assertEqual(self.agent.send_button.cget("text"), "Stop")
        self.assertEqual(str(self.agent.send_button.cget("state")), "normal")
        self.reader._stop_reading()
        self.assertEqual(self.agent.send_button.cget("text"), "Stop")


if __name__ == "__main__":
    unittest.main()
