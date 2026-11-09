import math
import struct
import subprocess
import sys
import threading
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

from speech import SpeechPlayer, compute_speech_envelope


class SpeechEnvelopeTests(unittest.TestCase):
    def test_envelope_follows_loud_then_silent_audio(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "speech.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                loud = b"".join(
                    struct.pack("<h", int(12000 * math.sin(i * 0.3)))
                    for i in range(8000)
                )
                wav_file.writeframes(loud + b"\x00\x00" * 8000)
            levels, window = compute_speech_envelope(path)
        self.assertEqual(window, 0.04)
        self.assertEqual(len(levels), 25)
        self.assertEqual(levels[0], 1.0)
        self.assertEqual(levels[-1], 0.0)


class SpeechPlayerTests(unittest.TestCase):
    def test_speech_response_is_sent_to_local_speech_engine(self) -> None:
        on_start = Mock()
        on_stop = Mock()
        player = SpeechPlayer(lambda: None, on_start=on_start, on_stop=on_stop)
        cancel_event = Event()
        player.cancel_event = cancel_event
        process = Mock(returncode=0)

        with (
            patch("speech.shutil.which", return_value="/usr/bin/espeak-ng"),
            patch("speech.subprocess.Popen", return_value=process) as popen,
        ):
            player.speak("Hello there.", cancel_event)

        popen.assert_called_once_with(
            ["/usr/bin/espeak-ng", "--stdin"],
            stdin=subprocess.PIPE,
            stdout=None,
            text=True,
        )
        process.communicate.assert_called_once_with(input="Hello there.")
        on_start.assert_called_once_with(None, 0.04, cancel_event)
        on_stop.assert_called_once_with(cancel_event)
        self.assertIsNone(player.process)
        self.assertIsNone(player.cancel_event)

    def test_speech_response_supports_speech_dispatcher(self) -> None:
        player = SpeechPlayer(lambda: None)
        cancel_event = Event()
        player.cancel_event = cancel_event
        process = Mock(returncode=0)

        def find_engine(name: str) -> str | None:
            return "/usr/bin/spd-say" if name == "spd-say" else None

        with (
            patch("speech.shutil.which", side_effect=find_engine),
            patch("speech.subprocess.Popen", return_value=process) as popen,
        ):
            player.speak("Hello there.", cancel_event)

        popen.assert_called_once_with(
            ["/usr/bin/spd-say", "--pipe-mode", "--wait"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
        )
        process.communicate.assert_called_once_with(input="Hello there.")
        self.assertIsNone(player.process)
        self.assertIsNone(player.cancel_event)

    def test_speech_response_uses_selected_piper_voice_and_cleans_audio_file(
        self,
    ) -> None:
        with TemporaryDirectory() as folder:
            voice_model = Path(folder) / "natural.onnx"
            voice_model.write_bytes(b"model")
            player = SpeechPlayer(lambda: voice_model)
            cancel_event = Event()
            player.cancel_event = cancel_event
            player.audio_player = Mock(return_value=("/usr/bin/aplay", []))
            commands: list[tuple[list[str], str | None]] = []

            def run_process(
                command: list[str],
                event: Event,
                *,
                input_text: str | None = None,
                discard_stdout: bool = False,
            ) -> int:
                commands.append((command, input_text))
                if input_text is None:
                    self.assertTrue(Path(command[-1]).is_file())
                return 0

            player._run_process = Mock(side_effect=run_process)
            with patch("speech.importlib.util.find_spec", return_value=object()):
                player.speak("A natural sounding reply.", cancel_event)

        self.assertEqual(len(commands), 2)
        model_command, input_text = commands[0]
        self.assertEqual(
            model_command[:4],
            [sys.executable, "-m", "piper", "--model"],
        )
        self.assertEqual(model_command[4], str(voice_model))
        self.assertEqual(model_command[5], "--output-file")
        self.assertEqual(input_text, "A natural sounding reply.")
        self.assertEqual(
            commands[1][0][:2], ["/usr/bin/aplay", commands[0][0][6]]
        )
        self.assertIsNone(commands[1][1])
        self.assertFalse(Path(commands[0][0][6]).exists())
        self.assertIsNone(player.cancel_event)

    def test_errors_are_reported_unless_cancelled(self) -> None:
        on_error = Mock()
        player = SpeechPlayer(lambda: None, on_error=on_error)
        cancel_event = Event()
        with patch("speech.shutil.which", return_value=None):
            player.speak("Hello.", cancel_event)
        on_error.assert_called_once()
        self.assertEqual(on_error.call_args.args[1], cancel_event)

    def test_stop_cancels_and_terminates_running_process(self) -> None:
        player = SpeechPlayer(lambda: None)
        player.cancel_event = Event()
        player.process = Mock()
        player.process.poll.return_value = None
        player.stop()
        self.assertTrue(player.cancel_event.is_set())
        player.process.terminate.assert_called_once_with()

    def test_stop_terminates_a_real_running_process(self) -> None:
        player = SpeechPlayer(lambda: None)
        event = Event()
        player.cancel_event = event
        started = Event()
        actual_popen = subprocess.Popen

        def popen(*args: object, **kwargs: object) -> subprocess.Popen:
            process = actual_popen(*args, **kwargs)
            started.set()
            return process

        with patch("speech.subprocess.Popen", side_effect=popen):
            worker = threading.Thread(
                target=player._run_process,
                args=([sys.executable, "-c", "import time; time.sleep(30)"], event),
            )
            worker.start()
            self.assertTrue(started.wait(5))
            player.stop()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertTrue(event.is_set())
        self.assertIsNone(player.process)

    def test_replacement_speech_cancels_and_waits_for_previous_worker(self) -> None:
        player = SpeechPlayer(lambda: None)
        first_started = Event()
        release_first = Event()
        second_started = Event()

        def speak(text: str, event: Event) -> None:
            if text == "first":
                first_started.set()
                release_first.wait(5)
            else:
                second_started.set()

        with patch.object(player, "speak", side_effect=speak):
            first = player.speak_async("first")
            try:
                self.assertTrue(first_started.wait(5))
                second = player.speak_async("second")
                self.assertTrue(first.is_set())
                self.assertFalse(second.is_set())
                self.assertFalse(second_started.wait(0.1))
            finally:
                release_first.set()
            self.assertTrue(second_started.wait(5))

    def test_cancel_during_piper_synthesis_does_not_start_playback(self) -> None:
        with TemporaryDirectory() as folder:
            player = SpeechPlayer(lambda: Path(folder) / "voice.onnx")
            player.audio_player = Mock(return_value=("/usr/bin/aplay", []))
            event = Event()
            commands: list[list[str]] = []

            def cancel_synthesis(
                command: list[str], cancel_event: Event, **_kwargs: object
            ) -> int:
                commands.append(command)
                cancel_event.set()
                return 0

            player._run_process = Mock(side_effect=cancel_synthesis)
            with patch("speech.importlib.util.find_spec", return_value=object()):
                player.speak("hello", event)
            self.assertEqual(len(commands), 1)
            self.assertFalse(Path(commands[0][-1]).exists())


if __name__ == "__main__":
    unittest.main()
