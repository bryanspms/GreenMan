"""Test the document reader functionality."""

import tempfile
from pathlib import Path
import sys

# Add the current directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from document_reader import DocumentReader, DocumentFormat, ReadingSession, TextChunker


def test_text_file():
    """Test reading a text file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is a test document.\nIt has multiple paragraphs.\n\n")
        f.write("This is the second paragraph.\nWith multiple lines.")
        f.flush()
        file_path = Path(f.name)
    
    try:
        text = DocumentReader.read_text(file_path)
        assert len(text) > 0, "Text file reading failed"
        assert "test document" in text, "Content not read correctly"
        print("✓ Text file reading works")
        
        fmt = DocumentReader.detect_format(file_path)
        assert fmt == DocumentFormat.TXT, "Format detection failed"
        print("✓ Format detection works")
        
    finally:
        file_path.unlink()


def test_markdown_file():
    """Test reading a markdown file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Heading\n\nSome **bold** text and *italic* text.\n\n")
        f.write("- Bullet point 1\n- Bullet point 2\n\n")
        f.write("Some more content.")
        f.flush()
        file_path = Path(f.name)
    
    try:
        text = DocumentReader.read_text(file_path)
        assert len(text) > 0, "Markdown file reading failed"
        assert "Heading" in text, "Content not read correctly"
        print("✓ Markdown file reading works")
    finally:
        file_path.unlink()


def test_text_chunking():
    """Test text chunking strategies."""
    text = (
        "First paragraph with some content here.\n\n"
        "Second paragraph with more content. And more sentences here.\n\n"
        "Third paragraph. Final content."
    )
    
    # Test paragraph chunking
    chunks = TextChunker.chunk_by_paragraphs(text)
    assert len(chunks) == 3, f"Expected 3 paragraphs, got {len(chunks)}"
    print("✓ Paragraph chunking works")
    
    # Test sentence chunking
    sentence_text = "First sentence. Second sentence. Third sentence."
    chunks = TextChunker.chunk_by_sentences(sentence_text, max_chars=30)
    assert len(chunks) > 1, "Sentence chunking failed"
    print("✓ Sentence chunking works")
    
    # Test word chunking
    word_text = " ".join(["word"] * 200)
    chunks = TextChunker.chunk_by_words(word_text, words_per_chunk=50)
    assert len(chunks) == 4, f"Expected 4 chunks, got {len(chunks)}"
    print("✓ Word chunking works")


def test_reading_session():
    """Test reading session tracking."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is paragraph one with enough content.\n\nThis is paragraph two with enough content.\n\nThis is paragraph three with enough content.\n\nThis is paragraph four with enough content.")
        f.flush()
        file_path = Path(f.name)
    
    try:
        session = ReadingSession(file_path, chunk_strategy="paragraphs")
        
        # Check initial state
        assert session.current_index == 0, "Initial index should be 0"
        assert session.total_chunks > 0, f"Should have chunks, got {session.total_chunks}"
        print(f"✓ Reading session created with {session.total_chunks} chunks")
        
        # Check current chunk
        chunk = session.get_current_chunk()
        assert chunk is not None, "Should have a current chunk"
        print("✓ Get current chunk works")
        
        # Test advancement
        session.advance()
        assert session.current_index == 1, "Should advance to next chunk"
        print("✓ Advancement works")
        
        # Test progress
        progress = session.get_progress_percentage()
        assert 0 <= progress <= 100, "Progress should be between 0-100"
        print(f"✓ Progress tracking works ({progress:.1f}%)")
        
        # Test go back
        session.go_back()
        assert session.current_index == 0, "Should go back to previous chunk"
        print("✓ Go back works")
        
        # Test status
        status = session.get_status()
        assert "file" in status and "progress_percent" in status, "Status should have required fields"
        print(f"✓ Status works: {status['file']} - {status['current_chunk']}/{status['total_chunks']}")
        
    finally:
        file_path.unlink()


def test_html_to_text():
    """Test HTML to text conversion."""
    html = """
    <html>
        <head><title>Test</title></head>
        <body>
            <h1>Heading</h1>
            <p>Some <strong>bold</strong> and <em>italic</em> text.</p>
            <script>console.log('hidden');</script>
            <p>Final paragraph.</p>
        </body>
    </html>
    """
    
    text = DocumentReader._html_to_text(html)
    assert "Heading" in text, "HTML should be converted"
    assert "bold" in text, "Content should be preserved"
    assert "hidden" not in text, "Script should be removed"
    print("✓ HTML to text conversion works")


if __name__ == "__main__":
    print("Testing Document Reader...\n")
    
    try:
        test_text_file()
        test_markdown_file()
        test_text_chunking()
        test_reading_session()
        test_html_to_text()
        
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
