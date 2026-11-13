"""Spoken responses: Piper or system speech engines, plus lip-sync analysis."""

from __future__ import annotations

import importlib.util
import math
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from array import array
from array import array
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock

NO_SPEECH_ENGINE_MESSAGE = (
    "Install espeak-ng or speech-dispatcher to enable spoken responses."
)

_EMOJI_SEQUENCE = re.compile(
    r"(?:[0-9#*]\ufe0f?\u20e3|[\u00a9\u00ae\u203c\u2049\u2122\u2139]\ufe0f|"
    r"[\U0001f1e6-\U0001f1ff]{1,2}|"
    r"[\U0001f000-\U0001faff\u2600-\u27bf]"
    r"(?:[\ufe0e\ufe0f\U0001f3fb-\U0001f3ff]"
    r"|[\U000e0020-\U000e007f]|\u200d"
    r"|[\U0001f000-\U0001faff\u2600-\u27bf])*)"
)


def prepare_text_for_speech(text: str) -> str:
    """Remove common Markdown decoration and emoji from spoken text."""
    text = _EMOJI_SEQUENCE.sub(" ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|>\s*)", "", text)
    text = re.sub(r"(?m)^\s*```[^\n]*$", "", text)
    text = re.sub(r"`+([^`\n]+)`+", r"\1", text)
    text = re.sub(r"(\*{2,3})(?=\S)(.+?\S|\S)\1", r"\2", text)
    text = re.sub(r"(?<!\w)(\*)(?=\S)(.+?\S|\S)\1(?!\w)", r"\2", text)
    text = re.sub(r"(?<!\w)(_{1,3})(?=\S)(.+?\S|\S)\1(?!\w)", r"\2", text)
    return "\n".join(
        line for raw_line in text.splitlines()
        if (line := re.sub(r"[^\S\n]+", " ", raw_line).strip())
    )


def compute_speech_envelope(
    wav_path: Path, window_seconds: float = 0.04
) -> tuple[list[float], float]:
    """Return per-window loudness levels (0-1) for a 16-bit PCM WAV file."""
    with wave.open(str(wav_path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM audio is supported.")
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
    samples = array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    samples = samples[::channels]
    window_size = max(1, int(sample_rate * window_seconds))
    levels: list[float] = []
    for start in range(0, len(samples), window_size):
        chunk = samples[start : start + window_size]
        levels.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)))
    peak = max(levels, default=0.0)
    if peak <= 0:
        return [0.0] * len(levels), window_seconds
    reference = peak * 0.6
    return [min(1.0, level / reference) for level in levels], window_seconds


class SpeechPlayer:
    """Speaks text aloud and reports progress through callbacks.

    Callbacks run on the speech worker thread, so GUI code must marshal them
    onto its own thread.
    """

    def __init__(
        self,
        voice_model_provider: Callable[[], Path | None],
        on_start: Callable[[list[float] | None, float, Event], None] | None = None,
        on_stop: Callable[[Event], None] | None = None,
        on_error: Callable[[str, Event], None] | None = None,
        on_pause: Callable[[Event], None] | None = None,
        on_resume: Callable[[Event], None] | None = None,
        volume_provider: Callable[[], int] | None = None,
    ) -> None:
        self._voice_model_provider = voice_model_provider
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_error = on_error
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._volume_provider = volume_provider or (lambda: 100)
        self.process: subprocess.Popen | None = None
        self.process_lock = Lock()
        self._playback_lock = Lock()
        self.cancel_event: Event | None = None
        self._pausable = False
        self._dispatcher = False
        self._paused = False

    def speak_async(self, text: str) -> Event:
        self.stop()
        cancel_event = Event()
        with self.process_lock:
            self.cancel_event = cancel_event
        threading.Thread(
            target=self._speak_serially, args=(text, cancel_event), daemon=True
        ).start()
        return cancel_event

    def _speak_serially(self, text: str, cancel_event: Event) -> None:
        with self._playback_lock:
            self.speak(text, cancel_event)

    def stop(self) -> None:
        with self.process_lock:
            cancel_event = self.cancel_event
            if cancel_event is not None:
                cancel_event.set()
            process = self.process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    if self._paused and not self._dispatcher:
                        process.send_signal(signal.SIGCONT)
                except ProcessLookupError:
                    pass
            self._paused = False

    def set_paused(self, paused: bool, cancel_event: Event) -> bool:
        """Request pause or resume for the current playback."""
        with self.process_lock:
            process = self.process
            if (
                self.cancel_event is not cancel_event or cancel_event.is_set()
                or not self._pausable or process is None or process.poll() is not None
            ):
                return False
            if self._dispatcher:
                process.send_signal(signal.SIGUSR1 if paused else signal.SIGUSR2)
            else:
                process.send_signal(signal.SIGSTOP if paused else signal.SIGCONT)
                self._paused = paused
                callback = self._on_pause if paused else self._on_resume
                if callback is not None:
                    callback(cancel_event)
            return True

    def availability_error(self) -> str | None:
        voice_model = self._voice_model_provider()
        if voice_model is not None:
            if not voice_model.is_file():
                return f"The selected Piper voice model was not found:\n{voice_model}"
            config_path = Path(f"{voice_model}.json")
            if not config_path.is_file():
                return f"The Piper voice configuration was not found:\n{config_path}"
            if importlib.util.find_spec("piper") is None:
                return (
                    "Install Piper in this Python environment with "
                    "`python -m pip install piper-tts`."
                )
            if not self.audio_player():
                return (
                    "Piper needs an audio player. Install pw-play, paplay, "
                    "aplay, or ffplay."
                )
            return None
        if not self.speech_engine():
            return NO_SPEECH_ENGINE_MESSAGE
        return None

    def speak(self, text: str, cancel_event: Event) -> None:
        try:
            if cancel_event.is_set():
                return
            text = prepare_text_for_speech(text)
            if not text:
                return
            if self._voice_model_provider() is not None:
                self._speak_with_piper(text, cancel_event)
                return
            speech_engine = self.speech_engine()
            if speech_engine is None:
                raise FileNotFoundError(NO_SPEECH_ENGINE_MESSAGE)
            executable, arguments = speech_engine
            if executable.endswith("spd-say"):
                self._speak_with_dispatcher(text, cancel_event)
                return
            arguments = [*arguments, "-a", str(self._speech_volume())]
            result = self._run_process(
                [executable, *arguments],
                cancel_event,
                input_text=text,
                on_started=lambda: self._notify_start(None, 0.04, cancel_event),
            )
            if result and not cancel_event.is_set():
                self._notify_error(
                    f"Speech engine exited with status {result}.", cancel_event
                )
        except (OSError, RuntimeError, wave.Error) as error:
            if not cancel_event.is_set():
                self._notify_error(str(error), cancel_event)
        finally:
            if self._on_stop is not None:
                self._on_stop(cancel_event)
            # Signal that this speech chunk has completed
            cancel_event.set()
            with self.process_lock:
                if self.cancel_event is cancel_event:
                    self.cancel_event = None

    @staticmethod
    def speech_engine() -> tuple[str, list[str]] | None:
        for name in ("espeak-ng", "espeak"):
            executable = shutil.which(name)
            if executable:
                return executable, ["--stdin"]
        executable = shutil.which("spd-say")
        if executable:
            return executable, ["--pipe-mode", "--wait"]
        return None

    @staticmethod
    def audio_player() -> tuple[str, list[str]] | None:
        for name in ("pw-play", "paplay", "aplay"):
            executable = shutil.which(name)
            if executable:
                return executable, []
        executable = shutil.which("ffplay")
        if executable:
            return executable, ["-nodisp", "-autoexit", "-loglevel", "error"]
        return None

    def _notify_start(
        self, envelope: list[float] | None, window_seconds: float, cancel_event: Event
    ) -> None:
        if self._on_start is not None:
            self._on_start(envelope, window_seconds, cancel_event)

    def _notify_error(self, message: str, cancel_event: Event) -> None:
        if self._on_error is not None:
            self._on_error(message, cancel_event)

    def _speech_volume(self) -> int:
        return max(0, min(100, self._volume_provider()))

    def _play_piper_audio(
        self,
        command: list[str],
        wav_path: Path,
        cancel_event: Event,
        on_started: Callable[[], None],
    ) -> int | None:
        if cancel_event.is_set():
            return None
        with wave.open(str(wav_path), "rb") as source:
            if source.getsampwidth() != 2:
                raise wave.Error("Volume control requires 16-bit PCM Piper audio.")
            channels = source.getnchannels()
            rate = source.getframerate()
            data_size = source.getnframes() * channels * 2
            header = struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF", 36 + data_size, b"WAVE", b"fmt ", 16, 1,
                channels, rate, rate * channels * 2, channels * 2, 16,
                b"data", data_size,
            )
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                bufsize=0,
            )
            with self.process_lock:
                self.process = process
                self._pausable = True
                self._dispatcher = False
                self._paused = False
                if cancel_event.is_set():
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                else:
                    on_started()
            try:
                stdin = process.stdin
                assert stdin is not None
                def write_all(data: bytes) -> None:
                    remaining = memoryview(data)
                    while remaining:
                        written = stdin.write(remaining)
                        if not written:
                            raise BrokenPipeError("Audio player stopped accepting audio.")
                        remaining = remaining[written:]

                write_all(header)
                next_chunk_time = time.monotonic() - 0.1
                while not cancel_event.is_set():
                    while not cancel_event.is_set():
                        with self.process_lock:
                            paused = self._paused
                        if paused:
                            next_chunk_time = time.monotonic() - 0.1
                            cancel_event.wait(0.05)
                            continue
                        delay = next_chunk_time - time.monotonic()
                        if delay <= 0:
                            break
                        cancel_event.wait(min(delay, 0.05))
                    if cancel_event.is_set():
                        break
                    frames = source.readframes(1024)
                    if not frames:
                        break
                    samples = array("h")
                    samples.frombytes(frames)
                    if sys.byteorder == "big":
                        samples.byteswap()
                    volume = self._speech_volume()
                    if volume != 100:
                        for index, sample in enumerate(samples):
                            samples[index] = round(sample * volume / 100)
                    if sys.byteorder == "big":
                        samples.byteswap()
                    write_all(samples.tobytes())
                    next_chunk_time = max(
                        next_chunk_time, time.monotonic() - 0.1
                    ) + len(frames) / (rate * channels * 2)
            finally:
                try:
                    if process.stdin is not None:
                        process.stdin.close()
                finally:
                    process.wait()
                    with self.process_lock:
                        if self.process is process:
                            self.process = None
                            self._pausable = False
                            self._paused = False
            return process.returncode

    def _run_process(
        self,
        command: list[str],
        cancel_event: Event,
        *,
        input_text: str | None = None,
        discard_stdout: bool = False,
        on_started: Callable[[], None] | None = None,
    ) -> int | None:
        if cancel_event.is_set():
            return None
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL if discard_stdout else None,
            text=input_text is not None,
        )
        with self.process_lock:
            self.process = process
            self._pausable = on_started is not None
            self._dispatcher = False
            self._paused = False
            if cancel_event.is_set():
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
            elif on_started is not None:
                on_started()
        try:
            process.communicate(input=input_text)
            return process.returncode
        finally:
            with self.process_lock:
                if self.process is process:
                    self.process = None
                    self._pausable = False
                    self._paused = False

    def _speak_with_dispatcher(self, text: str, cancel_event: Event) -> None:
        interpreter = (
            Path(sys.executable)
            if importlib.util.find_spec("speechd") is not None
            else Path("/usr/bin/python3")
        )
        if not interpreter.is_file():
            raise FileNotFoundError(
                "Speech Dispatcher requires /usr/bin/python3 and python3-speechd."
            )
        if cancel_event.is_set():
            return
        process = subprocess.Popen(
            [
                str(interpreter),
                str(Path(__file__).with_name("speech_dispatcher_helper.py")),
                str(self._speech_volume()),
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        with self.process_lock:
            self.process = process
            self._pausable = False
            self._dispatcher = True
            self._paused = False
            if cancel_event.is_set():
                process.terminate()
        try:
            assert process.stdin is not None and process.stdout is not None
            try:
                process.stdin.write(text)
                process.stdin.close()
            except BrokenPipeError:
                pass
            reported_error = False
            for line in process.stdout:
                message = line.rstrip("\n")
                if message == "begin":
                    with self.process_lock:
                        if not cancel_event.is_set():
                            self._pausable = True
                            self._notify_start(None, 0.04, cancel_event)
                elif message in ("pause", "resume"):
                    with self.process_lock:
                        self._paused = message == "pause"
                        callback = self._on_pause if self._paused else self._on_resume
                        if callback is not None and not cancel_event.is_set():
                            callback(cancel_event)
                elif message.startswith("error:") and not cancel_event.is_set():
                    reported_error = True
                    self._notify_error(message[6:], cancel_event)
            result = process.wait()
            if result and not reported_error and not cancel_event.is_set():
                self._notify_error(
                    f"Speech Dispatcher exited with status {result}.", cancel_event
                )
        finally:
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            if process.stdout is not None:
                process.stdout.close()
            with self.process_lock:
                if self.process is process:
                    self.process = None
                    self._pausable = False
                    self._dispatcher = False
                    self._paused = False
            # Signal that this speech chunk has completed
            if self._on_stop is not None:
                self._on_stop(cancel_event)
            cancel_event.set()

    def _speak_with_piper(self, text: str, cancel_event: Event) -> None:
        voice_model = self._voice_model_provider()
        assert voice_model is not None
        player = self.audio_player()
        if importlib.util.find_spec("piper") is None or player is None:
            raise FileNotFoundError(
                self.availability_error()
                or "Piper speech dependencies are unavailable."
            )
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output:
                temporary_path = output.name
            result = self._run_process(
                [
                    sys.executable,
                    "-m",
                    "piper",
                    "--model",
                    str(voice_model),
                    "--output-file",
                    temporary_path,
                ],
                cancel_event,
                input_text=text,
                discard_stdout=True,
            )
            if cancel_event.is_set():
                return
            if result:
                raise RuntimeError(f"Piper exited with status {result}.")
            player_executable, player_arguments = player
            try:
                envelope, window_seconds = compute_speech_envelope(
                    Path(temporary_path)
                )
            except (OSError, ValueError, EOFError, wave.Error):
                envelope, window_seconds = None, 0.04
            input_name = "pipe:0" if Path(player_executable).name == "ffplay" else "-"
            result = self._play_piper_audio(
                [player_executable, *player_arguments, input_name],
                Path(temporary_path),
                cancel_event,
                on_started=lambda: self._notify_start(
                    envelope, window_seconds, cancel_event
                ),
            )
            if result and not cancel_event.is_set():
                raise RuntimeError(f"Audio player exited with status {result}.")
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)
            # Signal that this speech chunk has completed
            if self._on_stop is not None:
                self._on_stop(cancel_event)
            cancel_event.set()
