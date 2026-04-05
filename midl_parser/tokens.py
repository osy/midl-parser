"""Token types and Token dataclass for the MIDL lexer."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class TokenType(enum.Enum):
    # Literals
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"

    # Identifier
    IDENT = "IDENT"

    # Keywords
    IMPORT = "import"
    CPP_QUOTE = "cpp_quote"
    TYPEDEF = "typedef"
    STRUCT = "struct"
    UNION = "union"
    ENUM = "enum"
    INTERFACE = "interface"
    LIBRARY = "library"
    COCLASS = "coclass"
    DISPINTERFACE = "dispinterface"
    MODULE = "module"
    CONST = "const"
    SIGNED = "signed"
    UNSIGNED = "unsigned"
    VOLATILE = "volatile"
    VOID = "void"
    PIPE = "pipe"
    SWITCH = "switch"
    CASE = "case"
    DEFAULT = "default"
    SIZEOF = "sizeof"
    IMPORTLIB = "importlib"
    PROPERTIES = "properties"
    METHODS = "methods"

    # Punctuation
    LBRACE = "{"
    RBRACE = "}"
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    SEMICOLON = ";"
    COMMA = ","
    COLON = ":"
    STAR = "*"
    DOT = "."
    PIPE_OP = "|"
    PLUS = "+"
    MINUS = "-"
    TILDE = "~"
    LSHIFT = "<<"
    RSHIFT = ">>"
    AMPERSAND = "&"
    CARET = "^"
    EQUALS = "="
    SLASH = "/"
    PERCENT = "%"
    BANG = "!"
    QUESTION = "?"
    ELLIPSIS = "..."

    # Special
    HASH = "#"
    NEWLINE = "NEWLINE"
    EOF = "EOF"


# Map keyword strings to token types
KEYWORDS: dict[str, TokenType] = {
    "import": TokenType.IMPORT,
    "cpp_quote": TokenType.CPP_QUOTE,
    "typedef": TokenType.TYPEDEF,
    "struct": TokenType.STRUCT,
    "union": TokenType.UNION,
    "enum": TokenType.ENUM,
    "interface": TokenType.INTERFACE,
    "library": TokenType.LIBRARY,
    "coclass": TokenType.COCLASS,
    "dispinterface": TokenType.DISPINTERFACE,
    "module": TokenType.MODULE,
    "const": TokenType.CONST,
    "signed": TokenType.SIGNED,
    "unsigned": TokenType.UNSIGNED,
    "volatile": TokenType.VOLATILE,
    "void": TokenType.VOID,
    "pipe": TokenType.PIPE,
    "switch": TokenType.SWITCH,
    "case": TokenType.CASE,
    "default": TokenType.DEFAULT,
    "sizeof": TokenType.SIZEOF,
    "importlib": TokenType.IMPORTLIB,
    "properties": TokenType.PROPERTIES,
    "methods": TokenType.METHODS,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int
    int_value: int | None = field(default=None, repr=False)
    float_value: float | None = field(default=None, repr=False)
    suffix: str = field(default="", repr=False)
