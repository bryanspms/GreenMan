"""Markdown text widget for displaying formatted text in Tkinter."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import scrolledtext, font as tkfont


def strip_markdown(text: str) -> str:
    """Remove Markdown syntax from text, leaving only plain text content.
    
    Removes: **bold**, __bold__, *italic*, _italic_, `code`, # headers, > blockquotes
    
    Args:
        text: Text containing Markdown syntax
        
    Returns:
        Plain text with all Markdown syntax removed
    """
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Remove blockquotes
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Remove bold (**text** and __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    
    # Remove italic (*text* and _text_)
    text = re.sub(r'\*(?!\*)([^\*]+?)\*(?!\*)', r'\1', text)
    text = re.sub(r'_(?!_)([^_]+?)_(?!_)', r'\1', text)
    
    # Remove code (`text`)
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    
    return text


class MarkdownText(scrolledtext.ScrolledText):
    """A ScrolledText widget that renders basic Markdown formatting."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get base font info
        try:
            base_font = tkfont.nametofont(self.cget("font"))
            font_family = base_font.actual("family")
            font_size = base_font.actual("size")
        except Exception as e:
            print(f"Warning: Failed to get font info: {e}")
            # Use defaults
            font_family = "TkFixedFont"
            font_size = 10
        
        # Configure Markdown tags
        self.tag_configure(
            "bold",
            font=(font_family, font_size, "bold"),
        )
        self.tag_configure(
            "italic",
            font=(font_family, font_size, "italic"),
        )
        self.tag_configure(
            "code",
            background="#f5f5f5",
            foreground="#d63384",
            font=(font_family, font_size, "normal"),
        )
        self.tag_configure(
            "header1",
            font=(font_family, font_size + 6, "bold"),
            foreground="#1a1a1a",
            spacing3=6,
        )
        self.tag_configure(
            "header2",
            font=(font_family, font_size + 4, "bold"),
            foreground="#2c2c2c",
            spacing3=4,
        )
        self.tag_configure(
            "header3",
            font=(font_family, font_size + 2, "bold"),
            foreground="#4a4a4a",
            spacing3=2,
        )
        self.tag_configure(
            "blockquote",
            foreground="#666666",
            lmargin1=20,
            lmargin2=20,
            font=(font_family, font_size, "italic"),
        )

    def insert_markdown(self, text: str) -> None:
        """Replace all content with text with Markdown formatting applied."""
        was_disabled = self.cget("state") == tk.DISABLED
        self.config(state=tk.NORMAL)
        
        # Clear existing content
        self.delete("1.0", tk.END)
        
        # Parse and insert the markdown text
        self._parse_and_insert_markdown(text)
        
        if was_disabled:
            self.config(state=tk.DISABLED)

    def append_markdown(self, text: str) -> None:
        """Append text with Markdown formatting applied to existing content."""
        print(f"DEBUG append_markdown: was_disabled={self.cget('state')}", flush=True)
        was_disabled = self.cget("state") == tk.DISABLED
        self.config(state=tk.NORMAL)
        print(f"DEBUG append_markdown: after setNORMAL, state={self.cget('state')}", flush=True)
        
        # Parse and append the markdown text (don't clear)
        self._parse_and_insert_markdown(text)
        
        print(f"DEBUG append_markdown: after parse, state={self.cget('state')}", flush=True)
        if was_disabled:
            self.config(state=tk.DISABLED)
            print(f"DEBUG append_markdown: set back to DISABLED", flush=True)

    def _parse_and_insert_markdown(self, text: str) -> None:
        """Parse Markdown and insert formatted text with tags."""
        lines = text.split('\n')
        
        for line_idx, line in enumerate(lines):
            if line_idx > 0:
                self.insert(tk.END, '\n')
            
            # Skip empty lines
            if not line.strip():
                continue
            
            # Check for headers (# Header, ## Header, etc.)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                hashes = header_match.group(1)
                header_text = header_match.group(2)
                level = min(len(hashes), 3)
                tag = f"header{level}"
                start_index = self.index(tk.END)
                self.insert(tk.END, header_text)
                end_index = self.index(tk.END)
                self.tag_add(tag, start_index, end_index)
                continue
            
            # Check for blockquotes (> Quote)
            if line.startswith('>'):
                quote_text = line[1:].strip()
                start_index = self.index(tk.END)
                self.insert(tk.END, quote_text)
                end_index = self.index(tk.END)
                self.tag_add("blockquote", start_index, end_index)
                continue
            
            # Format inline Markdown in the line
            self._format_inline_markdown(line)

    def _format_inline_markdown(self, text: str) -> None:
        """Format inline Markdown elements (bold, italic, code) using regex substitution."""
        # Use a list to track replacements and their positions
        # We'll process the text and rebuild it with tags
        pos = 0
        
        # Process patterns in order of priority: bold, code, italic
        # We need to handle overlapping patterns carefully
        
        while pos < len(text):
            # Try to find the nearest Markdown pattern
            patterns = [
                (r'\*\*(.+?)\*\*', 'bold'),      # **bold**
                (r'__(.+?)__', 'bold'),           # __bold__
                (r'`([^`]+?)`', 'code'),          # `code`
                (r'\*(?!\*)([^\*]+?)\*(?!\*)', 'italic'),  # *italic* (not **)
                (r'_(?!_)([^_]+?)_(?!_)', 'italic'),       # _italic_ (not __)
            ]
            
            nearest_match = None
            nearest_pos = len(text)
            nearest_tag = None
            nearest_pattern = None
            
            # Find the nearest matching pattern
            for pattern, tag in patterns:
                match = re.search(pattern, text[pos:])
                if match and match.start() < nearest_pos:
                    nearest_match = match
                    nearest_pos = pos + match.start()
                    nearest_tag = tag
                    nearest_pattern = pattern
            
            if nearest_match is None:
                # No more patterns found, insert the rest of the text
                self.insert(tk.END, text[pos:])
                break
            
            # Insert text before the match
            text_before = text[pos:pos + nearest_match.start()]
            if text_before:
                self.insert(tk.END, text_before)
            
            # Insert the matched content with tag
            content = nearest_match.group(1)
            
            # Get the position BEFORE inserting the content
            start_index = self.index(tk.END)
            current_state = self.cget("state")
            print(f"DEBUG: Before insert, state={repr(current_state)}, tk.END={start_index}, content={repr(content)}", flush=True)
            
            # Verify widget is NORMAL before insert
            if current_state != "normal":
                print(f"ERROR: Widget is not NORMAL! State is: {repr(current_state)}", flush=True)
                # Force it to normal
                self.config(state=tk.NORMAL)
            
            self.insert(tk.END, content)
            
            # Verify the insert actually happened
            widget_content_after = self.get(start_index, tk.END)
            print(f"DEBUG: After insert, widget content from {start_index}: {repr(widget_content_after)}", flush=True)
            
            end_index = self.index(tk.END)
            print(f"DEBUG: After insert, tk.END={end_index}, length={len(content)}", flush=True)
            
            self.tag_add(nearest_tag, start_index, end_index)
            
            # Debug output
            print(f"DEBUG: Applied tag '{nearest_tag}' from {start_index} to {end_index}: {repr(content)}", flush=True)
            
            # Move position forward
            pos += nearest_match.start() + len(nearest_match.group(0))



