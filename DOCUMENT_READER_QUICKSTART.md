# Quick Start: Green Man Document Reader

## Installation

1. **Install dependencies** (if not already installed):
```bash
pip install PyPDF2 ebooklib python-docx odfpy
```

2. **Update Green Man**:
The document reader is now integrated into Green Man. No additional configuration needed!

## Using the Document Reader

### Step 1: Open Green Man
Launch the Green Man application as usual.

### Step 2: Locate the Document Reader Panel
Look for the **📚 Document Reader** section below the "Assistant mode" controls, above the conversation transcript.

### Step 3: Open a Document
Click the **📁 Open Document** button and select a document in any of these formats:
- PDF files (.pdf)
- E-books (.epub)
- Word documents (.docx, .doc)
- Text files (.txt)
- Markdown files (.md)
- Web pages (.html, .htm)
- OpenDocument files (.odt)

### Step 4: Configure Reading (Optional)
Select how you want the text chunked:
- **Paragraphs** (default) - Natural pause points
- **Sentences** - More frequent pauses
- **Words** - Fixed-size segments

### Step 5: Start Reading
Click **▶ Start Reading** to begin listening to your document.

### Step 6: Control Playback

| Button | Action |
|--------|--------|
| **▶ Start Reading** | Begin from the start or resume |
| **⏸ Pause** | Pause the current reading |
| **▶ Resume** | Continue after pausing |
| **⏹ Stop** | Stop reading completely |

The progress bar shows your position in the document.

## Advanced Features

### Automatic Resume
When you open a document you've previously read, Green Man remembers where you left off. You can resume from the same position or start over.

### Progress Saving
Your reading position is automatically saved:
- When you pause
- When you stop
- Located in: `~/.greenman/reading_sessions/`

### Different Reading Strategies
Experiment with different chunking strategies:
- **Paragraphs** - Best for books and articles (more natural pacing)
- **Sentences** - Good for technical documents or when you want more control
- **Words** - Useful for testing or very dense content

## Supported Formats

### PDF Files
- Standard PDFs are fully supported
- Scanned PDFs (image-based) require OCR (not currently automated)
- Note: Complex layouts may require sentence or word chunking

### EPUB Books
- Standard EPUB2 and EPUB3 formats
- Typically the best experience for books
- Preserves chapter structure in the document

### Word Documents
- .docx files (modern Word format)
- .doc files (legacy Word format)
- Includes text from tables

### Text Files
- Plain .txt files
- Markdown (.md) files with formatting removed
- Any UTF-8 encoded text

### HTML & Web Pages
- HTML files and web pages (.html, .htm)
- Scripts and styles automatically removed
- Plain text content extracted

### ODT Files
- OpenDocument Text format
- Used by LibreOffice and other open-source tools

## Tips & Tricks

### Reading Long Documents
- For very long documents (500+ pages), use **Paragraph** chunking
- This allows you to take natural breaks at paragraph boundaries
- Resume functionality makes it easy to continue later

### Technical Documents
- Use **Sentence** chunking for code documentation or technical content
- This gives you more control over where sentences end

### Listening While Working
- The reader runs in the background
- Use the pause button to answer messages or take a call
- Green Man's voice will resume exactly where it left off

### Checking Progress
- The progress bar and counter show exactly where you are
- Hover over the progress bar to see percentage complete

### Changing Your Mind
- Click **⏹ Stop** to stop reading at any time
- Use **📁 Open Document** to switch to a different document
- Your position is automatically saved when you stop

## Common Questions

**Q: Can I adjust the reading speed?**
A: Speed is controlled by your TTS engine settings in Green Man's preferences.

**Q: What if my document won't open?**
A: Make sure you have the required package for that format installed:
- PDF: `pip install PyPDF2`
- EPUB: `pip install ebooklib`
- Word: `pip install python-docx`
- ODT: `pip install odfpy`

**Q: Where are my reading positions saved?**
A: In `~/.greenman/reading_sessions/` as JSON files. You can delete them to start fresh.

**Q: Can I convert documents to audio files?**
A: Not yet, but this is planned for a future version.

**Q: Does it work with PDFs that are scanned images?**
A: No, OCR support is not yet implemented. Scanned PDFs won't be readable.

**Q: Can I skip ahead or rewind?**
A: Currently, the reader progresses sequentially through chunks. You can pause/resume or use stop/start.

## Voice Quality

The document reader uses Green Man's configured voice:
- **Piper TTS** (if configured) - High quality, multiple voices
- **espeak-ng** - System text-to-speech
- **speech-dispatcher** - Alternative system engine

See Green Man's voice settings to select your preferred voice and engine.

## Troubleshooting

### Panel doesn't appear
- Restart Green Man
- Ensure `document_reader.py` and `document_reader_ui.py` are in the same folder as `app.py`

### Document opens but won't read
- Check Green Man's voice settings (Voice enabled checkbox)
- Ensure a TTS engine is available
- Try selecting a different chunking strategy

### "Install X library" error
- Install the missing package as suggested
- Example: `pip install PyPDF2`

### Session not resuming
- Check if `~/.greenman/reading_sessions/` directory exists
- Ensure you're opening the same file
- Clear sessions manually if needed: `rm -rf ~/.greenman/reading_sessions/`

## Features Coming Soon

- Bookmark multiple positions in a document
- Search within documents
- Export to audio file format
- Chapter-by-chapter navigation for EPUBs
- Reading statistics (time, speed, etc.)

---

Enjoy reading with Green Man! 📚🎧
