"""Error types for the MIDL parser."""

from __future__ import annotations


class MidlError(Exception):
    """Base error for MIDL parsing."""

    def __init__(self, message: str, filename: str = "", line: int = 0, column: int = 0):
        self.filename = filename
        self.line = line
        self.column = column
        loc = ""
        if filename or line:
            parts = []
            if filename:
                parts.append(filename)
            if line:
                parts.append(str(line))
                if column:
                    parts.append(str(column))
            loc = ":".join(parts) + ": "
        super().__init__(f"{loc}{message}")


class LexError(MidlError):
    """Error during tokenization."""


class ParseError(MidlError):
    """Error during parsing."""
