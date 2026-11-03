"""Spoken responses: Piper or system speech engines, plus lip-sync analysis."""

from __future__ import annotations

import importlib.util
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from array import array
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock

NO_SPEECH_ENGINE_MESSAGE = (
    "Install espeak-ng or speech-dispatcher to enable spoken responses."
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
        on_start: Callable[[list[float] | None, float], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_error: Callable[[str, Event], None] | None = None,
    ) -> None:
        self._voice_model_provider = voice_model_provider
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_error = on_error
        self.process: subprocess.Popen | None = None
        self.process_lock = Lock()
        self.cancel_event: Event | None = None

    def speak_async(self, text: str) -> None:
        cancel_event = Event()
        self.cancel_event = cancel_event
        threading.Thread(
            target=self.speak, args=(text, cancel_event), daemon=True
        ).start()

    def stop(self) -> None:
        cancel_event = self.cancel_event
        if cancel_event is not None:
            cancel_event.set()
        with self.process_lock:
            process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

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
        if cancel_event.is_set():
            return
        try:
            if self._voice_model_provider() is not None:
                self._speak_with_piper(text, cancel_event)
                return
            speech_engine = self.speech_engine()
            if speech_engine is None:
                raise FileNotFoundError(NO_SPEECH_ENGINE_MESSAGE)
            executable, arguments = speech_engine
            self._notify_start(None, 0.04)
            result = self._run_process(
                [executable, *arguments],
                cancel_event,
                input_text=text,
                discard_stdout=executable.endswith("spd-say"),
            )
            if result and not cancel_event.is_set():
                self._notify_error(
                    f"Speech engine exited with status {result}.", cancel_event
                )
        except (OSError, RuntimeError) as error:
            if not cancel_event.is_set():
                self._notify_error(str(error), cancel_event)
        finally:
            if self._on_stop is not None:
                self._on_stop()
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
        self, envelope: list[float] | None, window_seconds: float
    ) -> None:
        if self._on_start is not None:
            self._on_start(envelope, window_seconds)

    def _notify_error(self, message: str, cancel_event: Event) -> None:
        if self._on_error is not None:
            self._on_error(message, cancel_event)

    def _run_process(
        self,
        command: list[str],
        cancel_event: Event,
        *,
        input_text: str | None = None,
        discard_stdout: bool = False,
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
            if cancel_event.is_set():
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
        try:
            process.communicate(input=input_text)
            return process.returncode
        finally:
            with self.process_lock:
                if self.process is process:
                    self.process = None

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
            self._notify_start(envelope, window_seconds)
            result = self._run_process(
                [player_executable, *player_arguments, temporary_path],
                cancel_event,
                discard_stdout=True,
            )
            if result and not cancel_event.is_set():
                raise RuntimeError(f"Audio player exited with status {result}.")
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)
