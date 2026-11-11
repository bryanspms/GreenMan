# Document Reader - Bug Fixes and Improvements

## Issues Fixed

### 1. **Speech Not Playing (Critical)**
**Problem:** When clicking "Start Reading", the UI would show "Starting to read..." and chunks would be created, but no audio would be output.

**Root Cause:** The reading loop was waiting for the `cancel_event` to be set, but this event is only set when the user explicitly stops speech - it's never set when speech naturally completes. The loop would become stuck waiting indefinitely for an event that never triggers.

**Solution:** 
- Implemented a proper `chunk_done_event` that gets cleared before each chunk
- Wrapped the `SpeechPlayer._on_stop` callback to set this event when a chunk finishes
- Modified the reading loop to wait for this event with proper timeouts
- Now each chunk completes properly before moving to the next one

### 2. **EPUB Processing Issues**
**Problem:** EPUB files would load but extract minimal or no text, resulting in 0-1 chunks.

**Root Cause:** 
- EPUB content is HTML-based, and the HTML-to-text conversion was too aggressive
- No handling for encoding errors
- No validation that content was actually extracted

**Solutions:**
- Improved `_html_to_text()` to preserve block structure with newlines
- Added HTML entity decoding (e.g., `&amp;` → `&`)
- Added better error handling for malformed HTML
- Added validation to ensure text was actually extracted
- Better line break handling to preserve document structure

### 3. **UI Thread Safety Improvements**
**Problem:** Potential race conditions in the reading loop when updating UI.

**Solutions:**
- Used `Event` objects instead of bare threading operations
- Proper event initialization and clearing
- All UI updates via `parent.after()` to ensure thread safety
- Better exception handling with proper lambda closures

## Code Changes

### `document_reader_ui.py`

**Before:**
```python
# Waiting for cancel event that never completes
while (
    self.is_reading
    and self.current_cancel_event
    and not self.current_cancel_event.is_set()
):
    threading.Event().wait(0.1)  # ❌ Wrong! Creates new event each time
```

**After:**
```python
# Wrap callback to signal completion
original_on_stop = self.speech_player._on_stop
def wrapped_on_stop(event: Event) -> None:
    if original_on_stop:
        original_on_stop(event)
    self.chunk_done_event.set()  # ✅ Signal completion

# Wait for actual completion
while self.is_reading and not self.chunk_done_event.is_set():
    self.chunk_done_event.wait(timeout=0.1)  # ✅ Wait for real event
```

### `document_reader.py`

**Improved EPUB handling:**
```python
@staticmethod
def _read_epub(file_path: Path) -> str:
    """Read EPUB file with better error handling."""
    text = []
    book = epub.read_epub(str(file_path))
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            try:
                content = item.get_content()
                converted = DocumentReader._html_to_text(content)
                if converted.strip():  # ✅ Only add non-empty content
                    text.append(converted)
            except Exception:
                continue  # ✅ Skip problematic items
    
    if not text:
        raise ValueError("No readable content found in EPUB file")
    
    return "\n".join(text)
```

**Improved HTML parsing:**
```python
# Preserve block structure with newlines
html_content = re.sub(r"</?(p|div|br|h[1-6]|li|blockquote)[^>]*>", "\n", html_content)

# Handle HTML entities
from html import unescape
html_content = unescape(html_content)  # Decodes &amp; &lt; &quot; etc.

# Preserve line breaks while cleaning whitespace
lines = html_content.split("\n")
lines = [" ".join(line.split()) for line in lines]
```

## Testing

All existing tests pass:
```
✅ Text file reading works
✅ Format detection works
✅ Markdown file reading works
✅ All chunking strategies work
✅ Reading session management works
✅ HTML to text conversion works
✅ Progress tracking works
```

## New Debug Tool

A new debugging script `debug_document.py` has been created to help troubleshoot document reading:

```bash
python3 debug_document.py /path/to/document.epub
```

Output includes:
- Format detection
- Text extraction with character count
- Preview of extracted text
- Number of chunks created
- First 3 chunks preview
- Speech preparation testing
- Detailed error messages

This can be used to diagnose any remaining issues with specific documents.

## How to Test the Fixes

1. **Start Green Man** - The updates are now active

2. **Try reading an EPUB:**
   - Click "📁 Open Document"
   - Select any EPUB file
   - Should now show multiple chunks (typically 10-50+)
   - Click "▶ Start Reading"
   - **Audio should now play!** 🎉

3. **Test pause/resume:**
   - While reading, click "⏸ Pause"
   - Verify audio stops
   - Click "▶ Resume"
   - Verify audio continues

4. **Try other formats:**
   - PDF files
   - Word documents
   - Text files
   - Web pages (HTML)

## Remaining Considerations

### If audio still doesn't play:

1. **Verify TTS is working:**
   - Green Man's "Read responses aloud" checkbox must be enabled ✓
   - A valid voice must be selected ✓

2. **Use the debug tool:**
   ```bash
   python3 debug_document.py your_book.epub
   ```
   This will show you exactly what text is being extracted.

3. **Try a different chunk strategy:**
   - If "Paragraphs" doesn't work, try "Sentences" or "Words"
   - Different documents may need different strategies

### For EPUBs specifically:

- Some EPUB files have complex formatting that may not extract perfectly
- Scanned EPUBs (image-based) won't work (would need OCR)
- Very large EPUBs might take a few seconds to load

## Performance Notes

- **First load**: Documents are processed once and cached in the session
- **Resume**: Session file (~1KB) is saved on pause/stop
- **Memory**: Entire document text must fit in RAM
- **Threading**: All heavy lifting happens in background thread

## Migration Notes

This fix is fully backward compatible:
- Existing saved sessions will still work
- The same session format is used
- Just drop in the new files and it works

---

## Summary

The document reader should now work correctly for all supported formats. The main issue was the speech completion detection, which has been completely rearchitected. EPUB handling has also been significantly improved for better text extraction.

If you still experience issues with specific documents, use `debug_document.py` to see what's being extracted, or let me know which format/file is problematic!
