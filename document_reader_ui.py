"""Green Man Document Reader UI - Integrated reading experience."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from threading import Event

from document_reader import DocumentReader, DocumentFormat, ReadingSession, TextChunker
from speech import prepare_text_for_speech


class DocumentReaderUI:
    """UI for reading documents aloud with pause/resume controls."""
    
    # Version marker for debugging
    _VERSION = "20261111-event-driven-v2"

    SUPPORTED_FORMATS = {
        "All Documents": ("*.pdf", "*.epub", "*.docx", "*.doc", "*.txt", "*.md", "*.html", "*.htm", "*.odt"),
        "PDF Files": ("*.pdf",),
        "EPUB Books": ("*.epub",),
        "Word Documents": ("*.docx", "*.doc"),
        "Text Files": ("*.txt",),
        "Markdown Files": ("*.md",),
        "HTML Files": ("*.html", "*.htm"),
        "ODT Files": ("*.odt",),
    }

    def __init__(
        self,
        parent: tk.Widget,
        speech_player: object,
        on_text_ready: Optional[Callable[[str], None]] = None,
        on_waiting_changed: Optional[Callable[[bool], None]] = None,
        on_speech_started: Optional[Callable[[Event], None]] = None,
        on_word_highlight: Optional[Callable[[str, int, int], None]] = None,
        on_reading_finished: Optional[Callable[[], None]] = None,
        on_speech_actually_started: Optional[Callable[[Event, Optional[list[float]], float], None]] = None,
    ) -> None:
        print(f"DEBUG: DocumentReaderUI.__init__ ({self._VERSION})", flush=True)
        print(f"DEBUG: Callbacks passed: on_text_ready={bool(on_text_ready)}, on_word_highlight={bool(on_word_highlight)}, on_waiting_changed={bool(on_waiting_changed)}, on_speech_started={bool(on_speech_started)}, on_reading_finished={bool(on_reading_finished)}, on_speech_actually_started={bool(on_speech_actually_started)}", flush=True)
        self.parent = parent
        self.speech_player = speech_player
        self.on_text_ready = on_text_ready
        self.on_waiting_changed = on_waiting_changed
        self.on_speech_started = on_speech_started
        self.on_word_highlight = on_word_highlight
        self.on_reading_finished = on_reading_finished
        self.on_speech_actually_started = on_speech_actually_started
        
        print(f"DEBUG: After assignment: self.on_word_highlight={bool(self.on_word_highlight)}", flush=True)
        
        self.reading_session: Optional[ReadingSession] = None
        self.is_reading = False
        self.current_cancel_event: Optional[Event] = None
        self.speech_actually_started: Event = Event()  # Signals when audio playback actually begins
        self.current_envelope: Optional[list[float]] = None  # Audio envelope for current speech
        self.current_window_seconds: float = 0.04  # Time duration per envelope sample
        
        # Load last selected folder from config
        self.last_folder_path = self._load_last_folder()
        
        # Create the document reader frame
        self.frame = tk.LabelFrame(parent, text="📚 Document Reader", padx=10, pady=10)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the document reader UI components."""
        
        # File selection row
        file_row = tk.Frame(self.frame)
        file_row.pack(fill=tk.X, pady=(0, 10))

        self.file_label = tk.Label(file_row, text="No document selected", wraplength=300)
        self.file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        open_button = tk.Button(
            file_row,
            text="📁 Open Document",
            command=self._open_document,
            width=15,
        )
        open_button.pack(side=tk.RIGHT, padx=(5, 0))

        # Reading controls row
        control_row = tk.Frame(self.frame)
        control_row.pack(fill=tk.X, pady=(0, 10))

        self.start_button = tk.Button(
            control_row,
            text="▶ Start Reading",
            command=self._start_reading,
            state=tk.DISABLED,
            width=12,
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))

        self.pause_button = tk.Button(
            control_row,
            text="⏸ Pause",
            command=self._pause_reading,
            state=tk.DISABLED,
            width=12,
        )
        self.pause_button.pack(side=tk.LEFT, padx=(0, 5))

        self.resume_button = tk.Button(
            control_row,
            text="▶ Resume",
            command=self._resume_reading,
            state=tk.DISABLED,
            width=12,
        )
        self.resume_button.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_button = tk.Button(
            control_row,
            text="⏹ Stop",
            command=self._stop_reading,
            state=tk.DISABLED,
            width=12,
        )
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))

        # Progress row
        progress_row = tk.Frame(self.frame)
        progress_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(progress_row, text="Progress:").pack(side=tk.LEFT)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=300,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.progress_label = tk.Label(progress_row, text="0%", width=4)
        self.progress_label.pack(side=tk.LEFT)

        # Settings row
        settings_row = tk.Frame(self.frame)
        settings_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(settings_row, text="Chunk by:").pack(side=tk.LEFT)

        self.chunk_strategy = tk.StringVar(value="sentences")
        chunk_menu = ttk.Combobox(
            settings_row,
            textvariable=self.chunk_strategy,
            values=["paragraphs", "sentences", "words"],
            state="readonly",
            width=15,
        )
        chunk_menu.pack(side=tk.LEFT, padx=5)

        # Status row
        self.status_label = tk.Label(
            self.frame,
            text="Ready to open a document",
            fg="gray",
            wraplength=400,
        )
        self.status_label.pack(fill=tk.X, pady=(0, 5))

    def _load_last_folder(self) -> Optional[str]:
        """Load the last selected folder from config file."""
        config_file = Path.home() / ".greenman_document_folder"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    folder = f.read().strip()
                    if folder and Path(folder).exists():
                        return folder
            except Exception as e:
                print(f"DEBUG: Error loading folder config: {e}", flush=True)
        return None

    def _save_last_folder(self, folder_path: Path) -> None:
        """Save the last selected folder to config file."""
        try:
            config_file = Path.home() / ".greenman_document_folder"
            with open(config_file, 'w') as f:
                f.write(str(folder_path))
            self.last_folder_path = str(folder_path)
        except Exception as e:
            print(f"DEBUG: Error saving folder config: {e}", flush=True)

    def _open_document(self) -> None:
        """Open a file dialog to select a document."""
        file_types = [
            (name, " ".join(exts))
            for name, exts in self.SUPPORTED_FORMATS.items()
        ]
        
        # Use last folder if it exists and is valid, otherwise use None (default)
        initial_dir = None
        if self.last_folder_path and Path(self.last_folder_path).exists():
            initial_dir = self.last_folder_path
        
        file_path = filedialog.askopenfilename(
            parent=self.parent,
            title="Select a document to read",
            filetypes=file_types,
            initialdir=initial_dir,
        )
        
        if not file_path:
            return

        try:
            fmt = DocumentReader.detect_format(file_path)
            if fmt is None:
                messagebox.showerror("Unsupported Format", f"File type not supported: {Path(file_path).suffix}")
                return

            # Save the folder path for next time
            self._save_last_folder(Path(file_path).parent)

            self._stop_reading()

            chunk_strategy = self.chunk_strategy.get()
            self.reading_session = ReadingSession(file_path, chunk_strategy=chunk_strategy)

            if self.reading_session.load_progress():
                self.status_label.config(
                    text=f"Loaded saved position. Resume from chunk {self.reading_session.current_index + 1}?",
                    fg="blue",
                )
            else:
                self.status_label.config(
                    text="Document loaded successfully",
                    fg="green",
                )

            self.file_label.config(
                text=f"📄 {Path(file_path).name} ({self.reading_session.total_chunks} chunks)"
            )

            self.start_button.config(state=tk.NORMAL)
            self._update_progress()

        except Exception as e:
            messagebox.showerror("Error Loading Document", f"Failed to load document:\n{e}")
            self.status_label.config(text=f"Error: {e}", fg="red")

    def _start_reading(self) -> None:
        """Start reading the current document from the beginning."""
        if not self.reading_session:
            return

        print(f"DEBUG: _start_reading() called", flush=True)
        self.is_reading = True
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)

        # Set waiting state to show eyes are processing
        if self.on_waiting_changed:
            self.parent.after(0, lambda: self.on_waiting_changed(True))

        def read_worker() -> None:
            print(f"DEBUG: read_worker thread STARTED", flush=True)
            try:
                while self.is_reading and self.reading_session:
                    start_time = time.time()
                    print(f"DEBUG: Starting chunk processing at {start_time}", flush=True)
                    
                    chunk = self.reading_session.get_current_chunk()
                    if chunk is None:
                        self.is_reading = False
                        self.parent.after(0, self._on_reading_complete)
                        break

                    print(f"DEBUG: Chunk size = {len(chunk)} chars, {len(chunk.split())} words", flush=True)
                    cleaned_text = prepare_text_for_speech(chunk)
                    print(f"DEBUG: Text prep took {time.time() - start_time:.3f}s, cleaned = {len(cleaned_text)} chars", flush=True)
                    
                    if cleaned_text:
                        # Update status before starting speech
                        status = self.reading_session.get_status()
                        self.parent.after(
                            0,
                            lambda s=status: self.status_label.config(
                                text=f"Reading: {s['file']} - Chunk {s['current_chunk']}/{s['total_chunks']}",
                                fg="green"
                            ),
                        )
                        
                        # Display the text being read in the app's transcript
                        if self.on_text_ready:
                            self.parent.after(0, lambda text=cleaned_text: self.on_text_ready(text))
                        
                        # Start speech for this chunk
                        speech_start = time.time()
                        self.current_cancel_event = self.speech_player.speak_async(cleaned_text)
                        speech_init_time = time.time() - speech_start
                        print(f"DEBUG: speak_async() took {speech_init_time:.3f}s", flush=True)
                        
                        # Reset the "actually started" event for this chunk
                        self.speech_actually_started.clear()
                        
                        # Register this cancel_event BEFORE the speech event can fire
                        # This ensures _poll_speech_events knows this is document reading
                        if self.on_speech_started and self.current_cancel_event:
                            print(f"DEBUG: Registering document reading event", flush=True)
                            self.on_speech_started(self.current_cancel_event)
                        
                        # Start word highlighting thread if callback provided
                        # The thread will wait for speech to actually start before highlighting
                        print(f"DEBUG: Checking highlight conditions - on_word_highlight={bool(self.on_word_highlight)}, cancel_event={bool(self.current_cancel_event)}", flush=True)
                        if self.on_word_highlight and self.current_cancel_event:
                            print(f"DEBUG: ✓ Conditions met! Spawning highlighting thread for chunk {status['current_chunk']}", flush=True)
                            highlight_thread = threading.Thread(
                                target=self._highlight_words_during_playback,
                                args=(cleaned_text, self.current_cancel_event),
                                daemon=True,
                            )
                            highlight_thread.start()
                            print(f"DEBUG: ✓ Highlighting thread started", flush=True)
                        else:
                            print(f"DEBUG: ✗ NOT spawning thread - on_word_highlight={bool(self.on_word_highlight)}, cancel_event={bool(self.current_cancel_event)}", flush=True)
                        
                        # Wait for speech to complete by checking if the cancel_event is set
                        # The cancel_event is used internally by the speech player to signal completion
                        # We check periodically in case the user stops
                        wait_start = time.time()
                        while (
                            self.is_reading
                            and self.current_cancel_event is not None
                            and not self.current_cancel_event.is_set()
                        ):
                            # Sleep briefly to avoid busy-waiting
                            threading.Event().wait(0.05)
                        print(f"DEBUG: Speech completion wait took {time.time() - wait_start:.3f}s", flush=True)
                        
                        # Advance to next chunk only if still reading
                        if self.is_reading:
                            self.reading_session.advance()
                            self.parent.after(0, self._update_progress)
                    else:
                        # Skip empty chunks
                        self.reading_session.advance()

            except Exception as e:
                self.parent.after(
                    0,
                    lambda err=e: messagebox.showerror("Reading Error", f"Error during reading:\n{err}"),
                )
                self.is_reading = False
            finally:
                if self.is_reading:
                    self.is_reading = False
                    self.parent.after(0, self._on_reading_complete)
                # Ensure waiting state is cleared on exit
                if self.on_waiting_changed:
                    self.parent.after(0, lambda: self.on_waiting_changed(False))

        threading.Thread(target=read_worker, daemon=True).start()

    def _highlight_words_during_playback(self, text: str, cancel_event: Event) -> None:
        """Highlight the entire sentence/chunk while it's being spoken.
        
        STRATEGY: Simpler approach - highlight the whole chunk while Green Man
        speaks it. No need to sync individual words. Just highlight everything
        that's currently being read.
        """
        print(f"DEBUG: _highlight_words_during_playback THREAD STARTED with {len(text)} chars", flush=True)
        
        if not text or not self.on_word_highlight:
            print(f"DEBUG: Early return - text={bool(text)}, callback={bool(self.on_word_highlight)}", flush=True)
            return
        
        # WAIT FOR AUDIO TO ACTUALLY START
        print(f"DEBUG: Waiting for audio to actually start playback...", flush=True)
        self.speech_actually_started.wait()  # Wait indefinitely
        print(f"DEBUG: Audio playback started! Highlighting entire chunk.", flush=True)
        
        # Verify text is still being read after waiting
        if not self.is_reading or cancel_event.is_set():
            print(f"DEBUG: Reading cancelled while waiting for speech to start", flush=True)
            return
        
        # Highlight the entire text chunk from start to end
        text_start = 0
        text_end = len(text)
        
        print(f"DEBUG: Highlighting entire chunk {text_start}:{text_end}", flush=True)
        
        if self.on_word_highlight:
            # Highlight the full text chunk
            self.parent.after(0, lambda: self.on_word_highlight(text, text_start, text_end))
        
        # Wait for audio to finish playback
        # Use envelope duration if available, otherwise estimate from text
        if self.current_envelope and len(self.current_envelope) > 0:
            # Calculate actual audio duration
            audio_duration = len(self.current_envelope) * self.current_window_seconds
            print(f"DEBUG: Audio duration from envelope: {audio_duration:.1f}s", flush=True)
        else:
            # Fallback: estimate from word count at 140 WPM
            word_count = len(text.split())
            audio_duration = (word_count / 140) * 60
            print(f"DEBUG: Estimated audio duration: {audio_duration:.1f}s ({word_count} words @ 140 WPM)", flush=True)
        
        # Wait for the speech to complete
        # Keep highlighting until either:
        # 1. The audio duration has elapsed, OR
        # 2. The speech naturally completes (cancel_event is set)
        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            
            # Check if we've waited long enough based on duration
            if elapsed >= audio_duration:
                print(f"DEBUG: Speech complete (elapsed {elapsed:.1f}s >= duration {audio_duration:.1f}s)", flush=True)
                break
            
            # Check if speech actually finished (cancel_event was set)
            if cancel_event.is_set():
                print(f"DEBUG: Speech finished early (elapsed {elapsed:.1f}s < duration {audio_duration:.1f}s)", flush=True)
                break
            
            # Check if reading was stopped
            if not self.is_reading:
                print(f"DEBUG: Reading stopped (elapsed {elapsed:.1f}s)", flush=True)
                break
            
            time.sleep(0.05)  # Check every 50ms
        
        # Un-highlight at the end
        print(f"DEBUG: Chunk done, removing highlight", flush=True)

    def _pause_reading(self) -> None:
        """Pause the current reading session."""
        if self.current_cancel_event and hasattr(self.speech_player, 'set_paused'):
            if self.speech_player.set_paused(True, self.current_cancel_event):
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.NORMAL)
                self.status_label.config(text="Reading paused", fg="blue")
                self.reading_session.save_progress()

    def _resume_reading(self) -> None:
        """Resume the paused reading session."""
        if self.current_cancel_event and hasattr(self.speech_player, 'set_paused'):
            if self.speech_player.set_paused(False, self.current_cancel_event):
                self.resume_button.config(state=tk.DISABLED)
                self.pause_button.config(state=tk.NORMAL)
                self.status_label.config(text="Resuming reading...", fg="blue")

    def _stop_reading(self) -> None:
        """Stop the reading session completely."""
        self.is_reading = False

        if self.current_cancel_event:
            self.current_cancel_event.set()

        self.speech_player.stop()

        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

        # Clear waiting state when stopping
        if self.on_waiting_changed:
            self.on_waiting_changed(False)

        if self.reading_session:
            self.reading_session.save_progress()

        self.status_label.config(text="Reading stopped", fg="red")

    def _update_progress(self) -> None:
        """Update the progress bar and label."""
        if not self.reading_session:
            return

        progress = self.reading_session.get_progress_percentage()
        self.progress_var.set(progress)
        self.progress_label.config(
            text=f"{int(progress)}%"
        )

        status_info = self.reading_session.get_status()
        self.status_label.config(
            text=f"Chunk {status_info['current_chunk']} of {status_info['total_chunks']} "
                 f"({status_info['progress_percent']:.0f}%)",
            fg="black",
        )

    def _on_reading_complete(self) -> None:
        """Handle completion of reading."""
        self.is_reading = False
        self.start_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

        # Clear waiting state when reading completes
        if self.on_waiting_changed:
            self.on_waiting_changed(False)
        
        # Call reading finished callback (to stop face animations)
        if self.on_reading_finished:
            self.on_reading_finished()

        self.status_label.config(text="Finished reading document!", fg="green")
        messagebox.showinfo("Reading Complete", "The document has been read completely.")

        if self.reading_session:
            self.reading_session.clear_session()

    def pack(self, **kwargs) -> None:
        """Pack the frame."""
        self.frame.pack(**kwargs)

    def grid(self, **kwargs) -> None:
        """Grid the frame."""
        self.frame.grid(**kwargs)
