import math
import io
import json
import signal
import struct
import subprocess
import sys
import threading
import unittest
import wave
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

from speech import SpeechPlayer, compute_speech_envelope, prepare_text_for_speech
import speech_dispatcher_helper


class SpeechTextTests(unittest.TestCase):
    def test_strips_formatting_and_emoji_but_preserves_text(self) -> None:
        cases = {
            "**Hello**, *world*! 😊": "Hello, world!",
            "## Heading\n- **First** item\n* Second item": "Heading\nFirst item\nSecond item",
            "Use `example.py` and [the guide](https://example.com).": (
                "Use example.py and the guide."
            ),
            "Done✅Next 👨‍👩‍👧‍👦 👍🏽 🇺🇸 1️⃣": "Done Next",
            "©️ ™️ Hello ✈️": "Hello",
            "Café 中文 and العربية; 2 * 3 = 6; file_name; a_b_c.": (
                "Café 中文 and العربية; 2 * 3 = 6; file_name; a_b_c."
            ),
            "x*y*z and 2*3*4": "x*y*z and 2*3*4",
            "👩🏽‍💻✨": "",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(prepare_text_for_speech(source), expected)

    def test_all_engines_receive_prepared_text(self) -> None:
        for engine in ("piper", "espeak", "dispatcher"):
            with self.subTest(engine=engine):
                player = SpeechPlayer(lambda: Path("voice") if engine == "piper" else None)
                event = Event()
                with patch.object(player, "_speak_with_piper") as piper, patch.object(
                    player, "_speak_with_dispatcher"
                ) as dispatcher, patch.object(
                    player, "speech_engine",
                    return_value=("/usr/bin/spd-say" if engine == "dispatcher"
                                  else "/usr/bin/espeak", []),
                ), patch.object(player, "_run_process", return_value=0) as run:
                    player.speak("**Hello** 😊", event)
                if engine == "piper":
                    piper.assert_called_once_with("Hello", event)
                elif engine == "dispatcher":
                    dispatcher.assert_called_once_with("Hello", event)
                else:
                    self.assertEqual(run.call_args.kwargs["input_text"], "Hello")

    def test_emoji_only_skips_engines_but_completes(self) -> None:
        stopped = Mock()
        player = SpeechPlayer(lambda: None, on_stop=stopped)
        event = Event()
        with patch.object(player, "speech_engine") as engine:
            player.speak("😊✨", event)
        engine.assert_not_called()
        stopped.assert_called_once_with(event)


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
            ["/usr/bin/espeak-ng", "--stdin", "-a", "100"],
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
        on_start, on_pause, on_resume = Mock(), Mock(), Mock()
        player = SpeechPlayer(
            lambda: None, on_start=on_start, on_pause=on_pause, on_resume=on_resume
        )
        cancel_event = Event()
        player.cancel_event = cancel_event
        process = Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO("begin\npause\nresume\n")
        process.wait.return_value = 0

        def find_engine(name: str) -> str | None:
            return "/usr/bin/spd-say" if name == "spd-say" else None

        with (
            patch("speech.shutil.which", side_effect=find_engine),
            patch("speech.subprocess.Popen", return_value=process) as popen,
        ):
            player.speak("Hello there.", cancel_event)

        popen.assert_called_once_with(
            [
                "/usr/bin/python3",
                str(Path(__file__).with_name("speech_dispatcher_helper.py")),
                "100",
                "100",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        on_start.assert_called_once_with(None, 0.04, cancel_event)
        on_pause.assert_called_once_with(cancel_event)
        on_resume.assert_called_once_with(cancel_event)
        self.assertIsNone(player.process)
        self.assertIsNone(player.cancel_event)

    def test_speech_volume_is_passed_to_espeak(self) -> None:
        player = SpeechPlayer(lambda: None, volume_provider=lambda: 37)
        event = Event()
        with (
            patch.object(
                player, "speech_engine", return_value=("/usr/bin/espeak-ng", ["--stdin"])
            ),
            patch.object(player, "_run_process", return_value=0) as run_process,
        ):
            player.speak("Hello", event)

        self.assertEqual(
            run_process.call_args.args[0],
            ["/usr/bin/espeak-ng", "--stdin", "-a", "37"],
        )

    def test_speech_speed_is_passed_to_espeak(self) -> None:
        for speed, expected in ((50, "88"), (150, "262"), (200, "350")):
            with self.subTest(speed=speed):
                player = SpeechPlayer(lambda: None, speed_provider=lambda: speed)
                with patch.object(
                    player, "speech_engine", return_value=("/usr/bin/espeak-ng", ["--stdin"])
                ), patch.object(player, "_run_process", return_value=0) as run:
                    player.speak("Hello", Event())
                self.assertEqual(run.call_args.args[0][-2:], ["-s", expected])

    def test_piper_speed_respects_voice_default_length_scale(self) -> None:
        with TemporaryDirectory() as folder:
            voice = Path(folder) / "voice.onnx"
            Path(f"{voice}.json").write_text(json.dumps({
                "inference": {"length_scale": 1.2}
            }))
            for speed, expected in ((50, 2.4), (100, None), (200, 0.6)):
                with self.subTest(speed=speed):
                    player = SpeechPlayer(lambda: voice, speed_provider=lambda: speed)
                    player.audio_player = Mock(return_value=("/usr/bin/aplay", []))
                    player._run_process = Mock(return_value=0)
                    player._play_piper_audio = Mock(return_value=0)
                    with patch("speech.importlib.util.find_spec", return_value=object()):
                        player.speak("Hello", Event())
                    command = player._run_process.call_args.args[0]
                    if expected is None:
                        self.assertNotIn("--length-scale", command)
                    else:
                        self.assertAlmostEqual(
                            float(command[command.index("--length-scale") + 1]), expected
                        )

    def test_speech_speed_is_passed_to_dispatcher(self) -> None:
        player = SpeechPlayer(lambda: None, speed_provider=lambda: 150)
        process = Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO("")
        process.wait.return_value = 0
        with patch("speech.subprocess.Popen", return_value=process) as popen:
            player._speak_with_dispatcher("Hello", Event())
        self.assertEqual(popen.call_args.args[0][-1], "150")

    def test_dispatcher_maps_speed_to_valid_rate(self) -> None:
        for speed, expected in ((50, -100), (100, 0), (200, 100)):
            with self.subTest(speed=speed):
                client = Mock()
                client.speak.side_effect = lambda text, callback: callback("end")
                speechd = SimpleNamespace(
                    SSIPClient=Mock(return_value=client),
                    SSIPError=type("SSIPError", (Exception,), {}),
                    SSIPResponseError=type("SSIPResponseError", (Exception,), {}),
                )
                with patch.dict(sys.modules, {"speechd": speechd}), patch.object(
                    sys, "argv", ["speech_dispatcher_helper.py", "100", str(speed)]
                ), patch.object(sys, "stdin", io.StringIO("Hello")), patch(
                    "speech_dispatcher_helper.signal.signal"
                ):
                    self.assertEqual(speech_dispatcher_helper.main(), 0)
                client.set_rate.assert_called_once_with(expected)

    def test_piper_volume_changes_while_audio_is_streamed(self) -> None:
        with TemporaryDirectory() as folder:
            source = Path(folder) / "source.wav"
            with wave.open(str(source), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(struct.pack("<h", 10000) * 2048)

            volume = [100]
            audio = bytearray()
            pipe = Mock()

            def write(data: bytes) -> int:
                audio.extend(data)
                if len(audio) == 44 + 2048:
                    volume[0] = 0
                return len(data)

            pipe.write.side_effect = write
            process = Mock(stdin=pipe, returncode=0)
            player = SpeechPlayer(lambda: None, volume_provider=lambda: volume[0])
            with patch("speech.subprocess.Popen", return_value=process):
                result = player._play_piper_audio(
                    ["player", "-"], source, Event(), Mock()
                )
            self.assertEqual(result, 0)
            with wave.open(io.BytesIO(audio), "rb") as actual:
                samples = struct.unpack("<2048h", actual.readframes(2048))
            self.assertEqual(samples[:1024], (10000,) * 1024)
            self.assertEqual(samples[1024:], (0,) * 1024)

    def test_piper_player_backends_receive_stream_input(self) -> None:
        cases = (
            ("/usr/bin/pw-play", [], "-"),
            ("/usr/bin/paplay", [], "-"),
            ("/usr/bin/aplay", [], "-"),
            ("/usr/bin/ffplay", ["-nodisp"], "pipe:0"),
        )
        for executable, initial_arguments, input_name in cases:
            with self.subTest(player=executable):
                player = SpeechPlayer(
                    lambda: Path("voice.onnx"), volume_provider=lambda: 40
                )
                player.audio_player = Mock(
                    return_value=(executable, initial_arguments)
                )
                player._run_process = Mock(return_value=0)
                player._play_piper_audio = Mock(return_value=0)
                with patch("speech.importlib.util.find_spec", return_value=object()):
                    player.speak("Hello", Event())

                playback_command = player._play_piper_audio.call_args.args[0]
                self.assertEqual(
                    playback_command, [executable, *initial_arguments, input_name]
                )

    def test_piper_stream_can_be_paused_and_stopped(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "long.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\0\0" * 16000 * 10)
            player = SpeechPlayer(lambda: None)
            event = Event()
            player.cancel_event = event
            started = Event()
            errors: list[Exception] = []

            def playback() -> None:
                try:
                    player._play_piper_audio(
                        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
                        path, event, started.set,
                    )
                except BrokenPipeError as error:
                    errors.append(error)

            worker = threading.Thread(target=playback)
            worker.start()
            try:
                self.assertTrue(started.wait(5))
                self.assertTrue(player.set_paused(True, event))
                self.assertTrue(player.set_paused(False, event))
                self.assertTrue(player.set_paused(True, event))
                player.stop()
                worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertTrue(event.is_set())
                self.assertIsNone(player.process)
            finally:
                player.stop()
                worker.join(5)

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
                on_started: object = None,
            ) -> int:
                commands.append((command, input_text))
                return 0

            player._run_process = Mock(side_effect=run_process)
            player._play_piper_audio = Mock(return_value=0)
            with patch("speech.importlib.util.find_spec", return_value=object()):
                player.speak("A natural sounding reply.", cancel_event)

        self.assertEqual(len(commands), 1)
        model_command, input_text = commands[0]
        self.assertEqual(
            model_command[:4],
            [sys.executable, "-m", "piper", "--model"],
        )
        self.assertEqual(model_command[4], str(voice_model))
        self.assertEqual(model_command[5], "--output-file")
        self.assertEqual(input_text, "A natural sounding reply.")
        self.assertEqual(player._play_piper_audio.call_args.args[0], ["/usr/bin/aplay", "-"])
        self.assertEqual(player._play_piper_audio.call_args.args[1], Path(commands[0][0][6]))
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

    def test_pause_resume_and_stop_a_real_process(self) -> None:
        player = SpeechPlayer(lambda: None)
        event = Event()
        player.cancel_event = event
        started = Event()
        worker = threading.Thread(
            target=player._run_process,
            args=([sys.executable, "-c", "import time; time.sleep(30)"], event),
            kwargs={"on_started": started.set},
        )
        worker.start()
        try:
            self.assertTrue(started.wait(5))
            self.assertTrue(player.set_paused(True, event))
            assert player.process is not None
            process_status = Path(f"/proc/{player.process.pid}/status")
            for _ in range(100):
                if "\nState:\tT" in process_status.read_text():
                    break
                threading.Event().wait(0.01)
            self.assertIn("\nState:\tT", process_status.read_text())
            self.assertTrue(player.set_paused(False, event))
            self.assertTrue(player.set_paused(True, event))
            player.stop()
            worker.join(5)
            self.assertFalse(worker.is_alive())
        finally:
            player.stop()
            worker.join(5)

    def test_dispatcher_pause_is_scoped_to_its_helper_process(self) -> None:
        player = SpeechPlayer(lambda: None)
        event = Event()
        player.cancel_event = event
        process = Mock()
        process.poll.return_value = None
        player.process = process
        player._pausable = True
        player._dispatcher = True
        self.assertTrue(player.set_paused(True, event))
        process.send_signal.assert_called_with(signal.SIGUSR1)
        self.assertTrue(player.set_paused(False, event))
        process.send_signal.assert_called_with(signal.SIGUSR2)
        self.assertFalse(player.set_paused(True, Event()))

    def test_dispatcher_missing_bindings_reports_actionable_error(self) -> None:
        on_error = Mock()
        player = SpeechPlayer(lambda: None, on_error=on_error)
        event = Event()
        player.cancel_event = event
        process = Mock()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO(
            "error:Speech Dispatcher requires the system python3-speechd package.\n"
        )
        process.wait.return_value = 1
        with patch("speech.subprocess.Popen", return_value=process):
            player._speak_with_dispatcher("hello", event)
        on_error.assert_called_once_with(
            "Speech Dispatcher requires the system python3-speechd package.", event
        )


if __name__ == "__main__":
    unittest.main()
