"""Document reader: Extract and read text from various document formats."""

from __future__ import annotations

import json
import re
import shlex
import sys
from enum import Enum
from pathlib import Path
from typing import Optional


def _missing_dependency_message(package: str, format_name: str) -> str:
    requirements = Path(__file__).with_name("requirements.txt")
    command = (
        f"{shlex.quote(sys.executable)} -m pip install -r "
        f"{shlex.quote(str(requirements))}"
    )
    return f"{package} is required for {format_name} support. Install it with:\n{command}"


class DocumentFormat(Enum):
    """Supported document formats."""
    PDF = "pdf"
    EPUB = "epub"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    HTML = "html"
    ODT = "odt"


class DocumentReader:
    """Extract text from various document formats."""

    @staticmethod
    def detect_format(file_path: Path | str) -> DocumentFormat | None:
        """Detect document format from file extension."""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        
        format_map = {
            ".pdf": DocumentFormat.PDF,
            ".epub": DocumentFormat.EPUB,
            ".docx": DocumentFormat.DOCX,
            ".doc": DocumentFormat.DOCX,
            ".txt": DocumentFormat.TXT,
            ".md": DocumentFormat.MD,
            ".markdown": DocumentFormat.MD,
            ".html": DocumentFormat.HTML,
            ".htm": DocumentFormat.HTML,
            ".odt": DocumentFormat.ODT,
        }
        return format_map.get(suffix)

    @staticmethod
    def read_text(file_path: Path | str) -> str:
        """Read and extract text from a document file."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        fmt = DocumentReader.detect_format(file_path)
        
        if fmt is None:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        if fmt == DocumentFormat.TXT:
            return DocumentReader._read_txt(file_path)
        elif fmt == DocumentFormat.MD:
            return DocumentReader._read_markdown(file_path)
        elif fmt == DocumentFormat.PDF:
            return DocumentReader._read_pdf(file_path)
        elif fmt == DocumentFormat.EPUB:
            return DocumentReader._read_epub(file_path)
        elif fmt == DocumentFormat.DOCX:
            return DocumentReader._read_docx(file_path)
        elif fmt == DocumentFormat.HTML:
            return DocumentReader._read_html(file_path)
        elif fmt == DocumentFormat.ODT:
            return DocumentReader._read_odt(file_path)
        else:
            raise ValueError(f"Unsupported document format: {fmt}")

    @staticmethod
    def _read_txt(file_path: Path) -> str:
        """Read plain text file."""
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="latin-1")

    @staticmethod
    def _read_markdown(file_path: Path) -> str:
        """Read Markdown file."""
        return DocumentReader._read_txt(file_path)

    @staticmethod
    def _read_pdf(file_path: Path) -> str:
        """Read PDF file using PyPDF2."""
        try:
            import PyPDF2
        except ModuleNotFoundError as error:
            if error.name != "PyPDF2":
                raise
            raise ImportError(_missing_dependency_message("PyPDF2", "PDF")) from error
        
        text = []
        with open(file_path, "rb") as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            for page in reader.pages:
                text.append(page.extract_text())
        
        return "\n".join(text)

    @staticmethod
    def _read_epub(file_path: Path) -> str:
        """Read EPUB file."""
        try:
            import ebooklib
            from ebooklib import epub
        except ModuleNotFoundError as error:
            if error.name != "ebooklib":
                raise
            raise ImportError(_missing_dependency_message("ebooklib", "EPUB")) from error
        
        text = []
        try:
            book = epub.read_epub(str(file_path))
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    try:
                        content = item.get_content()
                        converted = DocumentReader._html_to_text(content)
                        if converted.strip():
                            text.append(converted)
                    except Exception:
                        # Skip items that can't be processed
                        continue
        except Exception as e:
            raise ValueError(f"Failed to read EPUB file: {e}")
        
        if not text:
            raise ValueError("No readable content found in EPUB file")
        
        return "\n".join(text)

    @staticmethod
    def _read_docx(file_path: Path) -> str:
        """Read DOCX (Word) file."""
        try:
            from docx import Document
        except ModuleNotFoundError as error:
            if error.name != "docx":
                raise
            raise ImportError(_missing_dependency_message("python-docx", "DOCX")) from error
        
        doc = Document(file_path)
        text = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                text.append(para.text)
        
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    row_text.append(cell.text.strip())
                if any(row_text):
                    text.append(" | ".join(row_text))
        
        return "\n".join(text)

    @staticmethod
    def _read_html(file_path: Path) -> str:
        """Read HTML file."""
        try:
            from html.parser import HTMLParser
        except ImportError:
            html_content = file_path.read_text(encoding="utf-8")
            return DocumentReader._html_to_text(html_content)
        
        html_content = file_path.read_text(encoding="utf-8")
        return DocumentReader._html_to_text(html_content)

    @staticmethod
    def _read_odt(file_path: Path) -> str:
        """Read ODT (OpenDocument Text) file."""
        try:
            from odf import text
            from odf.opendocument import load
        except ModuleNotFoundError as error:
            if error.name != "odf":
                raise
            raise ImportError(_missing_dependency_message("odfpy", "ODT")) from error
        
        doc = load(str(file_path))
        text_content = []
        
        for element in doc.getElementsByType(text.P):
            text_element = ""
            for node in element.childNodes:
                if hasattr(node, "data"):
                    text_element += node.data
            if text_element.strip():
                text_content.append(text_element)
        
        return "\n".join(text_content)

    @staticmethod
    def _html_to_text(html_content: str | bytes) -> str:
        """Convert HTML to plain text, removing tags and scripts."""
        if isinstance(html_content, bytes):
            try:
                html_content = html_content.decode("utf-8")
            except UnicodeDecodeError:
                html_content = html_content.decode("latin-1", errors="ignore")
        
        # Remove script and style tags with their content
        html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Replace common block elements with newlines for readability
        html_content = re.sub(r"</?(p|div|br|h[1-6]|li|blockquote)[^>]*>", "\n", html_content, flags=re.IGNORECASE)
        
        # Remove all remaining HTML tags
        html_content = re.sub(r"<[^>]+>", " ", html_content)
        
        # Decode HTML entities
        try:
            from html import unescape
            html_content = unescape(html_content)
        except (ImportError, AttributeError):
            # Fallback for basic entities
            html_content = html_content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
        
        # Replace multiple whitespace with single space, but preserve line breaks
        lines = html_content.split("\n")
        lines = [" ".join(line.split()) for line in lines]
        html_content = "\n".join(line for line in lines if line.strip())
        
        return html_content.strip()


class TextChunker:
    """Split text into readable chunks for document reading."""

    @staticmethod
    def chunk_by_paragraphs(text: str, min_length: int = 20) -> list[str]:
        """Split text into paragraphs, filtering small ones."""
        paragraphs = text.split("\n\n")
        chunks = []
        
        for para in paragraphs:
            para = para.strip()
            if len(para) >= min_length:
                chunks.append(para)
        
        return chunks

    @staticmethod
    def chunk_by_sentences(text: str, max_chars: int = 500) -> list[str]:
        """Split text into sentences, grouping to stay under max_chars."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    @staticmethod
    def chunk_by_words(text: str, words_per_chunk: int = 100) -> list[str]:
        """Split text into chunks by word count."""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), words_per_chunk):
            chunk = " ".join(words[i:i + words_per_chunk])
            if chunk.strip():
                chunks.append(chunk)
        
        return chunks


class ReadingSession:
    """Track reading progress for document reading."""

    def __init__(self, file_path: Path | str, chunk_strategy: str = "paragraphs") -> None:
        self.file_path = Path(file_path)
        self.chunk_strategy = chunk_strategy
        self.full_text = DocumentReader.read_text(self.file_path)
        self.chunks = self._create_chunks()
        self.current_index = 0
        self.total_chunks = len(self.chunks)
        self._session_file = self._get_session_file()

    def _create_chunks(self) -> list[str]:
        """Create text chunks based on strategy."""
        if self.chunk_strategy == "paragraphs":
            return TextChunker.chunk_by_paragraphs(self.full_text)
        elif self.chunk_strategy == "sentences":
            return TextChunker.chunk_by_sentences(self.full_text)
        elif self.chunk_strategy == "words":
            return TextChunker.chunk_by_words(self.full_text)
        else:
            return TextChunker.chunk_by_paragraphs(self.full_text)

    def _get_session_file(self) -> Path:
        """Get the path to save session progress."""
        cache_dir = Path.home() / ".greenman" / "reading_sessions"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{self.file_path.stem}.json"

    def save_progress(self) -> None:
        """Save current reading position to file."""
        data = {
            "file_path": str(self.file_path),
            "current_index": self.current_index,
            "total_chunks": self.total_chunks,
            "chunk_strategy": self.chunk_strategy,
        }
        self._session_file.write_text(json.dumps(data, indent=2))

    def load_progress(self) -> bool:
        """Load reading position from file. Returns True if loaded, False if not found."""
        if not self._session_file.exists():
            return False
        
        try:
            data = json.loads(self._session_file.read_text())
            if (
                data.get("file_path") == str(self.file_path)
                and data.get("total_chunks") == self.total_chunks
            ):
                self.current_index = data.get("current_index", 0)
                return True
        except (json.JSONDecodeError, KeyError):
            pass
        
        return False

    def get_current_chunk(self) -> str | None:
        """Get the current chunk without advancing."""
        if 0 <= self.current_index < self.total_chunks:
            return self.chunks[self.current_index]
        return None

    def get_next_chunk(self) -> str | None:
        """Get the next chunk and advance the pointer."""
        chunk = self.get_current_chunk()
        if chunk is not None and self.current_index < self.total_chunks - 1:
            self.current_index += 1
        return chunk

    def advance(self) -> str | None:
        """Move to the next chunk."""
        if self.current_index < self.total_chunks - 1:
            self.current_index += 1
            return self.get_current_chunk()
        return None

    def go_back(self) -> str | None:
        """Move to the previous chunk."""
        if self.current_index > 0:
            self.current_index -= 1
            return self.get_current_chunk()
        return None

    def jump_to_position(self, chunk_index: int) -> str | None:
        """Jump to a specific chunk position."""
        if 0 <= chunk_index < self.total_chunks:
            self.current_index = chunk_index
            return self.get_current_chunk()
        return None

    def get_progress_percentage(self) -> float:
        """Get reading progress as a percentage."""
        if self.total_chunks == 0:
            return 0.0
        return (self.current_index / (self.total_chunks - 1)) * 100 if self.total_chunks > 1 else 100.0

    def get_status(self) -> dict:
        """Get current reading status."""
        return {
            "file": self.file_path.name,
            "current_chunk": self.current_index + 1,
            "total_chunks": self.total_chunks,
            "progress_percent": self.get_progress_percentage(),
            "chunk_strategy": self.chunk_strategy,
        }

    def clear_session(self) -> None:
        """Clear saved progress."""
        if self._session_file.exists():
            self._session_file.unlink()
