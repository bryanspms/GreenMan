"""Markdown text widget - simplified version that actually works."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import scrolledtext, font as tkfont


def strip_markdown(text: str) -> str:
    """Remove Markdown syntax from text."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(?!\*)([^\*]+?)\*(?!\*)', r'\1', text)
    text = re.sub(r'_(?!_)([^_]+?)_(?!_)', r'\1', text)
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    return text


class MarkdownText(scrolledtext.ScrolledText):
    """Simple Markdown text widget."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        try:
            base_font = tkfont.nametofont(self.cget("font"))
            font_family = base_font.actual("family")
            font_size = base_font.actual("size")
        except:
            font_family = "TkFixedFont"
            font_size = 10
        
        # Configure tags
        self.tag_config("bold", font=(font_family, font_size, "bold"))
        self.tag_config("italic", font=(font_family, font_size, "italic"))
        self.tag_config("code", background="#f5f5f5", foreground="#d63384")
        self.tag_config("header1", font=(font_family, font_size + 6, "bold"), foreground="#1a1a1a")
        self.tag_config("header2", font=(font_family, font_size + 4, "bold"), foreground="#2c2c2c")
        self.tag_config("header3", font=(font_family, font_size + 2, "bold"), foreground="#4a4a4a")
        self.tag_config("blockquote", font=(font_family, font_size, "italic"), foreground="#666666")

    def insert_markdown(self, text: str) -> None:
        """Insert text with Markdown formatting."""
        was_disabled = self.cget("state") == "disabled"
        self.config(state="normal")
        self.delete("1.0", tk.END)
        self._insert_formatted(text)
        if was_disabled:
            self.config(state="disabled")

    def append_markdown(self, text: str) -> None:
        """Append text with Markdown formatting."""
        was_disabled = self.cget("state") == "disabled"
        self.config(state="normal")
        self._insert_formatted(text)
        if was_disabled:
            self.config(state="disabled")

    def _insert_formatted(self, text: str) -> None:
        """Insert text with formatting."""
        lines = text.split('\n')
        
        for line_idx, line in enumerate(lines):
            if line_idx > 0:
                self.insert(tk.END, '\n')
            
            if not line.strip():
                continue
            
            # Headers
            if match := re.match(r'^(#{1,6})\s+(.+)$', line):
                level = min(len(match.group(1)), 3)
                content = match.group(2)
                self.insert_with_tag(content, f"header{level}")
                continue
            
            # Blockquotes
            if line.startswith('>'):
                content = line[1:].strip()
                self.insert_with_tag(content, "blockquote")
                continue
            
            # Inline formatting
            self._insert_inline(line)

    def _insert_inline(self, line: str) -> None:
        """Insert line with inline Markdown."""
        pos = 0
        while pos < len(line):
            patterns = [
                (r'\*\*(.+?)\*\*', 'bold'),
                (r'__(.+?)__', 'bold'),
                (r'`([^`]+?)`', 'code'),
                (r'\*(?!\*)([^\*]+?)\*(?!\*)', 'italic'),
                (r'_(?!_)([^_]+?)_(?!_)', 'italic'),
            ]
            
            best_match = None
            best_pos = len(line) - pos
            best_tag = None
            
            for pattern, tag in patterns:
                if m := re.search(pattern, line[pos:]):
                    if m.start() < best_pos:
                        best_match = m
                        best_pos = m.start()
                        best_tag = tag
            
            if not best_match:
                self.insert(tk.END, line[pos:])
                break
            
            # Insert before match
            if best_pos > 0:
                self.insert(tk.END, line[pos:pos + best_pos])
            
            # Insert with formatting
            content = best_match.group(1)
            self.insert_with_tag(content, best_tag)
            
            pos += best_pos + len(best_match.group(0))

    def insert_with_tag(self, text: str, tag: str) -> None:
        """Helper to insert text with a tag."""
        # Get the position right before inserting
        # We need to know where content currently ends
        current = self.get("1.0", "end-1c")  # Don't include final newline
        
        # Count lines up to current position
        lines_before = current.count('\n')
        if lines_before == 0:
            # We're on line 1
            line_num = 1
            col_num = len(current)
        else:
            # We're past line 1
            line_num = lines_before + 1
            # Get the last line's content
            last_line = current.split('\n')[-1]
            col_num = len(last_line)
        
        start_index = f"{line_num}.{col_num}"
        
        # Insert the text
        self.insert(tk.END, text)
        
        # Calculate end index
        text_lines = text.split('\n')
        if len(text_lines) == 1:
            # Single line insertion
            end_col = col_num + len(text)
            end_index = f"{line_num}.{end_col}"
        else:
            # Multi-line insertion
            end_line = line_num + len(text_lines) - 1
            end_col = len(text_lines[-1])
            end_index = f"{end_line}.{end_col}"
        
        self.tag_add(tag, start_index, end_index)
