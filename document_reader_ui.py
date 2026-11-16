"""Green Man Document Reader UI - Integrated reading experience."""

from __future__ import annotations

import json
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
        on_reading_started: Optional[Callable[[], None]] = None,
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
        self.on_reading_started = on_reading_started
        
        print(f"DEBUG: After assignment: self.on_word_highlight={bool(self.on_word_highlight)}", flush=True)
        
        self.reading_session: Optional[ReadingSession] = None
        self.is_reading = False
        self.is_paused = False  # Track if reading is currently paused
        self.current_cancel_event: Optional[Event] = None
        self._reading_after: Optional[str] = None
        self._highlighted = False
        self._chunk_text = ""
        self.speech_actually_started: Event = Event()  # Signals when audio playback actually begins
        self.current_envelope: Optional[list[float]] = None  # Audio envelope for current speech
        self.current_window_seconds: float = 0.04  # Time duration per envelope sample
        
        # Load last selected folder from config
        self.last_folder_path = self._load_last_folder()
        
        # Collapse state
        self.is_collapsed = self._load_collapse_state()
        self.collapsible_widgets: list[tk.Widget] = []
        
        # Create the document reader frame
        self.frame = tk.LabelFrame(parent, text="📚 Document Reader", padx=10, pady=10)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the document reader UI components."""
        
        # Header row with collapse button
        header_row = tk.Frame(self.frame)
        header_row.pack(fill=tk.X, pady=(0, 10))
        
        self.collapse_button = tk.Button(
            header_row,
            text="▼" if not self.is_collapsed else "▶",
            command=self._toggle_collapse,
            width=3,
            relief=tk.FLAT,
        )
        self.collapse_button.pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Label(header_row, text="Contents:").pack(side=tk.LEFT)
        
        # File selection row
        file_row = tk.Frame(self.frame)
        file_row.pack(fill=tk.X, pady=(0, 10))
        self.collapsible_widgets.append(file_row)

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
        self.collapsible_widgets.append(control_row)

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

        self.previous_chunk_button = tk.Button(
            control_row,
            text="Previous Chunk",
            command=self._previous_chunk,
            state=tk.DISABLED,
        )
        self.previous_chunk_button.pack(side=tk.LEFT, padx=(0, 5))

        self.next_chunk_button = tk.Button(
            control_row,
            text="Next Chunk",
            command=self._next_chunk,
            state=tk.DISABLED,
        )
        self.next_chunk_button.pack(side=tk.LEFT, padx=(0, 5))

        # Progress row
        progress_row = tk.Frame(self.frame)
        progress_row.pack(fill=tk.X, pady=(0, 10))
        self.collapsible_widgets.append(progress_row)

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
        self.collapsible_widgets.append(settings_row)

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
        self.collapsible_widgets.append(self.status_label)
        
        # Apply initial collapse state
        self._update_collapse_state()

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

    def _load_collapse_state(self) -> bool:
        """Load the collapse state from config file."""
        config_file = Path.home() / ".greenman_document_collapsed"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return f.read().strip().lower() == 'true'
            except Exception as e:
                print(f"DEBUG: Error loading collapse state: {e}", flush=True)
        return False

    def _save_collapse_state(self, collapsed: bool) -> None:
        """Save the collapse state to config file."""
        try:
            config_file = Path.home() / ".greenman_document_collapsed"
            with open(config_file, 'w') as f:
                f.write('true' if collapsed else 'false')
        except Exception as e:
            print(f"DEBUG: Error saving collapse state: {e}", flush=True)

    def _toggle_collapse(self) -> None:
        """Toggle the collapse state of the document reader."""
        self.is_collapsed = not self.is_collapsed
        self._save_collapse_state(self.is_collapsed)
        self._update_collapse_state()

    def _update_collapse_state(self) -> None:
        """Update the visibility of collapsible widgets based on collapse state."""
        if self.is_collapsed:
            # Hide all collapsible widgets
            for widget in self.collapsible_widgets:
                widget.pack_forget()
            self.collapse_button.config(text="▶")
        else:
            # Show all collapsible widgets
            for widget in self.collapsible_widgets:
                widget.pack(fill=tk.X, pady=(0, 10))
            self.collapse_button.config(text="▼")

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

            self.start_button.config(
                state=tk.NORMAL if self.reading_session.total_chunks else tk.DISABLED
            )
            self._update_progress()

        except Exception as e:
            messagebox.showerror("Error Loading Document", f"Failed to load document:\n{e}")
            self.status_label.config(text=f"Error: {e}", fg="red")

    def _start_reading(self) -> None:
        """Start reading from the current position."""
        if not self.reading_session or not self.reading_session.get_current_chunk() or self.is_reading:
            return

        self.is_reading = True
        self.is_paused = False
        if self.on_reading_started:
            self.on_reading_started()
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)
        self.resume_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        if self.on_waiting_changed:
            self.on_waiting_changed(True)
        self._process_current_chunk()

    def _process_current_chunk(self) -> None:
        if not self.is_reading or not self.reading_session:
            return
        try:
            chunk = self.reading_session.get_current_chunk()
            if chunk is None:
                self._on_reading_complete()
                return
            cleaned_text = prepare_text_for_speech(chunk)
            self._update_progress()
            if not cleaned_text:
                self._advance_reading()
                return

            status = self.reading_session.get_status()
            self.status_label.config(
                text=f"Reading: {status['file']} - Chunk {status['current_chunk']}/{status['total_chunks']}",
                fg="green",
            )
            if self.on_text_ready:
                self.on_text_ready(cleaned_text)
            self.speech_actually_started.clear()
            self.current_envelope = None
            self._chunk_text = cleaned_text
            self._highlighted = False
            event = self.speech_player.speak_async(cleaned_text)
            self.current_cancel_event = event
            if self.on_speech_started:
                self.on_speech_started(event)
            self._reading_after = self.parent.after(50, self._wait_for_chunk, event)
        except Exception as error:
            self._stop_reading()
            messagebox.showerror("Reading Error", f"Error during reading:\n{error}")

    def _wait_for_chunk(self, event: Event) -> None:
        if not self.is_reading or event is not self.current_cancel_event:
            return
        self._reading_after = None
        if event.is_set():
            if self.on_word_highlight and self._highlighted:
                self.on_word_highlight("", 0, 0)
                self._highlighted = False
            self._advance_reading()
        else:
            should_highlight = self.speech_actually_started.is_set() and not self.is_paused
            if self.on_word_highlight and should_highlight != self._highlighted:
                if should_highlight:
                    self.on_word_highlight(self._chunk_text, 0, len(self._chunk_text))
                else:
                    self.on_word_highlight("", 0, 0)
                self._highlighted = should_highlight
            self._reading_after = self.parent.after(50, self._wait_for_chunk, event)

    def _advance_reading(self) -> None:
        if self.reading_session and self.reading_session.advance() is not None:
            self._reading_after = self.parent.after(0, self._process_current_chunk)
        else:
            self._on_reading_complete()

    def _previous_chunk(self) -> None:
        self._navigate_chunk(-1)

    def _next_chunk(self) -> None:
        self._navigate_chunk(1)

    def _navigate_chunk(self, offset: int) -> None:
        session = self.reading_session
        if not session or not 0 <= session.current_index + offset < session.total_chunks:
            return
        self._stop_reading()
        session.jump_to_position(session.current_index + offset)
        session.save_progress()
        self._update_progress()
        self._start_reading()

    def _pause_reading(self) -> None:
        """Pause the current reading session."""
        if self.current_cancel_event and hasattr(self.speech_player, 'set_paused'):
            if self.speech_player.set_paused(True, self.current_cancel_event):
                self.is_paused = True
                self.pause_button.config(state=tk.DISABLED)
                self.resume_button.config(state=tk.NORMAL)
                self.status_label.config(text="Reading paused", fg="blue")
                self.reading_session.save_progress()

    def _resume_reading(self) -> None:
        """Resume the paused reading session."""
        if self.current_cancel_event and hasattr(self.speech_player, 'set_paused'):
            if self.speech_player.set_paused(False, self.current_cancel_event):
                self.is_paused = False
                self.resume_button.config(state=tk.DISABLED)
                self.pause_button.config(state=tk.NORMAL)
                self.status_label.config(text="Resuming reading...", fg="blue")

    def _stop_reading(self) -> None:
        """Stop the reading session completely."""
        self.is_reading = False
        self.is_paused = False

        if self._reading_after is not None:
            self.parent.after_cancel(self._reading_after)
            self._reading_after = None
        if self.current_cancel_event:
            self.current_cancel_event.set()
            self.current_cancel_event = None

        self.speech_player.stop()
        if self.on_word_highlight:
            self.on_word_highlight("", 0, 0)
        if self.on_reading_finished:
            self.on_reading_finished()

        self.start_button.config(
            state=tk.NORMAL
            if self.reading_session and self.reading_session.total_chunks
            else tk.DISABLED
        )
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
        self.previous_chunk_button.config(
            state=tk.NORMAL if self.reading_session.current_index > 0 else tk.DISABLED
        )
        self.next_chunk_button.config(
            state=tk.NORMAL
            if self.reading_session.current_index < self.reading_session.total_chunks - 1
            else tk.DISABLED
        )
        self.status_label.config(
            text=f"Chunk {status_info['current_chunk']} of {status_info['total_chunks']} "
                 f"({status_info['progress_percent']:.0f}%)",
            fg="black",
        )

    def _on_reading_complete(self) -> None:
        """Handle completion of reading."""
        self.is_reading = False
        self.is_paused = False
        self.current_cancel_event = None
        if self.on_word_highlight:
            self.on_word_highlight("", 0, 0)
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
