"""Markdown text widget for displaying formatted text in Tkinter."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import scrolledtext, font as tkfont


class MarkdownText(scrolledtext.ScrolledText):
    """A ScrolledText widget that renders basic Markdown formatting."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get base font info
        base_font_name = tkfont.nametofont(self.cget("font"))
        base_size = base_font_name.actual("size")
        
        # Configure Markdown tags
        self.tag_configure(
            "bold",
            font=(base_font_name.actual("family"), base_size, "bold"),
        )
        self.tag_configure(
            "italic",
            font=(base_font_name.actual("family"), base_size, "italic"),
        )
        self.tag_configure(
            "code",
            background="#f5f5f5",
            foreground="#d63384",
        )
        self.tag_configure(
            "header1",
            font=(base_font_name.actual("family"), base_size + 6, "bold"),
            foreground="#1a1a1a",
            spacing3=6,
        )
        self.tag_configure(
            "header2",
            font=(base_font_name.actual("family"), base_size + 4, "bold"),
            foreground="#2c2c2c",
            spacing3=4,
        )
        self.tag_configure(
            "header3",
            font=(base_font_name.actual("family"), base_size + 2, "bold"),
            foreground="#4a4a4a",
            spacing3=2,
        )
        self.tag_configure(
            "blockquote",
            foreground="#666666",
            lmargin1=20,
            lmargin2=20,
            font=(base_font_name.actual("family"), base_size, "italic"),
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
        was_disabled = self.cget("state") == tk.DISABLED
        self.config(state=tk.NORMAL)
        
        # Parse and append the markdown text (don't clear)
        self._parse_and_insert_markdown(text)
        
        if was_disabled:
            self.config(state=tk.DISABLED)

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
                start_pos = tk.END
                self.insert(tk.END, header_text)
                self.tag_add(tag, start_pos, tk.END)
                continue
            
            # Check for blockquotes (> Quote)
            if line.startswith('>'):
                quote_text = line[1:].strip()
                start_pos = tk.END
                self.insert(tk.END, quote_text)
                self.tag_add("blockquote", start_pos, tk.END)
                continue
            
            # Format inline Markdown in the line
            self._format_inline_markdown(line)

    def _format_inline_markdown(self, text: str) -> None:
        """Format inline Markdown elements (bold, italic, code)."""
        # Process the line character by character, looking for patterns
        pos = 0
        
        while pos < len(text):
            # Look for patterns starting at current position
            # Order matters: check longer patterns first
            
            # Check for **bold** (must be at least one character between)
            bold_match = re.match(r'\*\*(.+?)\*\*', text[pos:])
            if bold_match:
                content = bold_match.group(1)
                start_pos = tk.END
                self.insert(tk.END, content)
                self.tag_add("bold", start_pos, tk.END)
                pos += len(bold_match.group(0))
                continue
            
            # Check for __bold__ (must be at least one character between)
            bold_match = re.match(r'__(.+?)__', text[pos:])
            if bold_match:
                content = bold_match.group(1)
                start_pos = tk.END
                self.insert(tk.END, content)
                self.tag_add("bold", start_pos, tk.END)
                pos += len(bold_match.group(0))
                continue
            
            # Check for `code`
            code_match = re.match(r'`([^`]+?)`', text[pos:])
            if code_match:
                content = code_match.group(1)
                start_pos = tk.END
                self.insert(tk.END, content)
                self.tag_add("code", start_pos, tk.END)
                pos += len(code_match.group(0))
                continue
            
            # Check for *italic* (but not **)
            # Use negative lookahead/lookbehind to avoid matching ** patterns
            italic_match = re.match(r'\*(?!\*)([^\*]+?)\*(?!\*)', text[pos:])
            if italic_match:
                content = italic_match.group(1)
                start_pos = tk.END
                self.insert(tk.END, content)
                self.tag_add("italic", start_pos, tk.END)
                pos += len(italic_match.group(0))
                continue
            
            # Check for _italic_ (but not __)
            italic_match = re.match(r'_(?!_)([^_]+?)_(?!_)', text[pos:])
            if italic_match:
                content = italic_match.group(1)
                start_pos = tk.END
                self.insert(tk.END, content)
                self.tag_add("italic", start_pos, tk.END)
                pos += len(italic_match.group(0))
                continue
            
            # No pattern found, insert plain character
            self.insert(tk.END, text[pos])
            pos += 1
