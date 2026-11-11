# Document Reader Feature for Green Man

## Overview

The Document Reader feature allows Green Man to read documents and books aloud with full pause/resume support. It supports multiple document formats and provides an intuitive UI for document selection and playback control.

## Supported Document Formats

- **PDF** (.pdf) - Using PyPDF2 for text extraction
- **EPUB** (.epub) - E-books using ebooklib
- **Word Documents** (.docx, .doc) - Using python-docx
- **Text Files** (.txt) - Plain text documents
- **Markdown** (.md, .markdown) - Markdown formatted documents
- **HTML** (.html, .htm) - Web pages and HTML documents
- **ODT** (.odt) - OpenDocument Text files using odfpy

## Features

### 1. Document Selection
- Open any supported document format via a file browser dialog
- Automatic format detection based on file extension
- Clear display of currently selected document

### 2. Reading Controls
- **▶ Start Reading** - Begin reading from the start or resume from saved position
- **⏸ Pause** - Pause the current reading session
- **▶ Resume** - Resume reading after pause
- **⏹ Stop** - Stop reading completely

### 3. Progress Tracking
- Real-time progress bar showing reading progress
- Chunk counter showing current/total chunks
- Percentage indicator
- Automatic progress saving for resume functionality

### 4. Customizable Chunking Strategies
The reader can split documents into chunks using three strategies:

- **Paragraphs** (default) - Splits by paragraph breaks for natural reading flow
- **Sentences** - Splits by sentence boundaries for granular control
- **Words** - Fixed word count chunks for consistent segment sizes

### 5. Session Management
- Automatic saving of reading position to `~/.greenman/reading_sessions/`
- Resume from the last position when reopening a document
- Clear saved session when reading is complete

## Usage

### Basic Workflow

1. **Open Green Man** - Launch the application
2. **Locate Document Reader** - Find the "📚 Document Reader" section in the interface
3. **Select Document** - Click "📁 Open Document" and choose a file
4. **Configure Reading** - (Optional) Select a chunking strategy from the dropdown
5. **Start Reading** - Click "▶ Start Reading" to begin
6. **Control Playback**:
   - Use "⏸ Pause" to pause and "▶ Resume" to continue
   - Use "⏹ Stop" to stop reading completely
7. **Track Progress** - Watch the progress bar and chunk counter

### Keyboard Shortcuts

When a document is being read:
- The pause/resume functionality uses Green Man's built-in speech pause controls
- Speech can be paused through Green Man's main pause button as well

## Technical Architecture

### Module: `document_reader.py`

Core document reading functionality:

- **DocumentFormat** - Enum for supported document formats
- **DocumentReader** - Main class for extracting text from documents
  - `detect_format()` - Identify document type
  - `read_text()` - Extract text from any supported format
  - Format-specific methods: `_read_pdf()`, `_read_epub()`, etc.
  - HTML utility: `_html_to_text()` - Convert HTML to plain text

- **TextChunker** - Text segmentation utilities
  - `chunk_by_paragraphs()` - Split by paragraph breaks
  - `chunk_by_sentences()` - Split by sentence boundaries
  - `chunk_by_words()` - Split into fixed word counts

- **ReadingSession** - Tracks reading state and progress
  - Loads/saves reading position in JSON format
  - Provides navigation methods: `advance()`, `go_back()`, `jump_to_position()`
  - Progress tracking: `get_progress_percentage()`, `get_status()`
  - Session management: `save_progress()`, `load_progress()`, `clear_session()`

### Module: `document_reader_ui.py`

UI integration for document reading:

- **DocumentReaderUI** - Tkinter UI component
  - Integrates with Green Man's existing `SpeechPlayer`
  - Manages reading workflow and button states
  - Handles pause/resume through `SpeechPlayer.set_paused()`
  - Runs reading in background thread to prevent UI freezing
  - Provides real-time progress updates

### Integration with app.py

The document reader is integrated into the main Green Man application:
- Imported as `DocumentReaderUI`
- Instantiated in `DesktopAgent.__init__()` with access to speech player
- Packed into the main UI after the mode selection controls
- Shares the same theme colors as the rest of Green Man

## Dependencies

New dependencies added to `requirements.txt`:

```
PyPDF2>=3.0.0      # PDF text extraction
ebooklib>=0.18     # EPUB book reading
python-docx>=0.8.11  # Word document support
odfpy>=1.4.1       # OpenDocument format support
```

## Session Storage

Reading positions are automatically saved to:
```
~/.greenman/reading_sessions/{document_name}.json
```

Format:
```json
{
  "file_path": "/path/to/document.pdf",
  "current_index": 42,
  "total_chunks": 100,
  "chunk_strategy": "paragraphs"
}
```

When you reopen the same document, you'll be prompted to resume from the saved position.

## Speech Integration

The document reader uses Green Man's existing `SpeechPlayer` for audio output:

1. **Voice Engine** - Automatically uses configured Piper voice or system speech engine
2. **Text Preparation** - Removes markdown, emojis, and formatting before speech
3. **Pause/Resume** - Uses `SpeechPlayer.set_paused()` for seamless pause/resume
4. **Speed Control** - Inherits speech engine's speed settings
5. **Lip Sync** - Coordinates with facial animation if enabled

## Error Handling

The document reader gracefully handles:
- Unsupported file formats
- Missing document files
- Corrupted or invalid documents
- Missing Python dependencies for specific formats
- TTS engine unavailability

All errors are displayed in user-friendly error dialogs.

## Performance Considerations

- **Large Documents** - Documents are chunked in memory; very large files (>500MB) may require more RAM
- **First Load** - Initial text extraction may take time for large PDF files
- **Progress Saving** - Lightweight JSON saves happen on pause and stop
- **Threading** - Reading runs in background thread to keep UI responsive

## Future Enhancement Ideas

1. **Bookmark Support** - Create multiple bookmarks within a document
2. **Speed Control** - Adjust playback speed
3. **Chapter Navigation** - Detect and navigate chapters in ePUBs
4. **Statistics** - Display words per minute, estimated time remaining
5. **Search Function** - Find text within the document
6. **Audio Export** - Save read document as audio file
7. **Multiple Language Support** - Auto-detect and configure language for TTS

## Testing

Run the test suite:
```bash
python3 test_document_reader.py
```

Tests cover:
- Text file reading
- Format detection
- Markdown parsing
- Multiple chunking strategies
- Reading session management
- HTML to text conversion

## Troubleshooting

### "Install PyPDF2 for PDF support"
```bash
pip install PyPDF2
```

### "Install ebooklib for EPUB support"
```bash
pip install ebooklib
```

### "Install python-docx for DOCX support"
```bash
pip install python-docx
```

### "Install odfpy for ODT support"
```bash
pip install odfpy
```

### Document not showing chunks
- Ensure the document has content longer than the minimum chunk length (default 20 characters)
- Try a different chunking strategy (Sentences or Words)
- Check that the file is not corrupted

### Pause not working
- Ensure a TTS engine is available (espeak-ng, speech-dispatcher, or Piper)
- Check Green Man's voice settings
- Verify the pause button is enabled (should be blue when reading)

## Related Code

- `speech.py` - Core text-to-speech functionality
- `app.py` - Main Green Man application
- `test_document_reader.py` - Test suite
- `requirements.txt` - Python dependencies
