#!/usr/bin/env python3
"""Debug script to test document reading and chunk extraction."""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from document_reader import DocumentReader, ReadingSession


def debug_document(file_path: str) -> None:
    """Debug a specific document to see what's being extracted."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return
    
    print(f"\n{'='*70}")
    print(f"Debugging: {file_path.name}")
    print(f"{'='*70}\n")
    
    # Detect format
    fmt = DocumentReader.detect_format(file_path)
    print(f"Format detected: {fmt.value if fmt else 'UNKNOWN'}")
    
    try:
        # Extract text
        print("\n📖 Extracting text...")
        full_text = DocumentReader.read_text(file_path)
        text_length = len(full_text)
        print(f"✓ Text extracted: {text_length:,} characters")
        
        # Show preview
        preview = full_text[:500].replace('\n', ' ')
        print(f"\n📝 Preview (first 500 chars):")
        print(f"   {preview}...")
        
        # Create reading session
        print(f"\n📚 Creating reading session...")
        session = ReadingSession(file_path, chunk_strategy="paragraphs")
        
        print(f"✓ Total chunks: {session.total_chunks}")
        print(f"✓ Chunk strategy: {session.chunk_strategy}")
        
        if session.total_chunks == 0:
            print("\n⚠️  WARNING: No chunks created! The text may be too short or fragmented.")
            print("\nTrying with 'sentences' strategy...")
            session = ReadingSession(file_path, chunk_strategy="sentences")
            print(f"✓ Total chunks with sentences: {session.total_chunks}")
            
            if session.total_chunks == 0:
                print("\nTrying with 'words' strategy...")
                session = ReadingSession(file_path, chunk_strategy="words")
                print(f"✓ Total chunks with words: {session.total_chunks}")
        
        # Show first few chunks
        if session.total_chunks > 0:
            print(f"\n🔍 First 3 chunks:\n")
            for i in range(min(3, session.total_chunks)):
                chunk = session.chunks[i]
                chunk_preview = chunk[:100].replace('\n', ' ')
                print(f"   Chunk {i+1}: {chunk_preview}...")
                if len(chunk) > 100:
                    print(f"            (Length: {len(chunk)} characters)\n")
                else:
                    print()
        
        # Test speech preparation
        print(f"🔊 Testing speech preparation...")
        from speech import prepare_text_for_speech
        
        if session.total_chunks > 0:
            first_chunk = session.chunks[0]
            prepared = prepare_text_for_speech(first_chunk)
            print(f"✓ Original length: {len(first_chunk)} chars")
            print(f"✓ After prep: {len(prepared)} chars")
            if prepared:
                preview = prepared[:100].replace('\n', ' ')
                print(f"✓ Preview: {preview}...")
            else:
                print("⚠️  WARNING: Text is empty after speech preparation!")
        
        print(f"\n✅ Document debugging complete!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 debug_document.py <path_to_document>")
        print("\nExample:")
        print("  python3 debug_document.py book.epub")
        print("  python3 debug_document.py document.pdf")
        sys.exit(1)
    
    debug_document(sys.argv[1])
