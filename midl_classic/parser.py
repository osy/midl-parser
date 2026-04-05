"""Recursive descent parser for MIDL source files."""

from __future__ import annotations

from .tokens import Token, TokenType
from .errors import ParseError
from .ast_nodes import (
    Attribute, AttributeName, PointerLevel, TypeSpec,
    IntegerLiteral, FloatLiteral, StringLiteral, IdentifierRef,
    BinaryOp, UnaryOp, ParenExpr, Expression, ArrayDimension,
    ImportStatement, CppQuote, PreprocessorDirective, Constant,
    EnumMember, EnumDef, StructField, AnonymousUnion, AnonymousStruct,
    StructDef, UnionCase, UnionDef, TypeAlias, FuncPointerParam,
    FuncPointerTypedef, MethodParam, Method, InterfaceTypedef,
    InterfaceDef, ForwardDecl, ImportLib, CoclassInterface,
    CoclassDef, LibraryDef, MidlFile,
)

# Type modifier keywords
_TYPE_MODIFIERS = {"const", "signed", "unsigned", "volatile"}

# Calling convention keywords
_CALLING_CONVENTIONS = {
    "__stdcall", "__cdecl", "__fastcall", "__pascal",
    "cdecl", "stdcall", "pascal", "WINAPI", "APIENTRY", "CALLBACK",
}

# Base types that can appear in multi-word combinations
_MULTI_WORD_TYPES = {"long", "short", "int", "char", "double"}

# Keywords that start a type in a struct field context
_TYPE_START_KEYWORDS = {
    TokenType.CONST, TokenType.SIGNED, TokenType.UNSIGNED,
    TokenType.VOLATILE, TokenType.VOID, TokenType.STRUCT,
    TokenType.UNION, TokenType.ENUM,
}


class Parser:
    """Recursive descent MIDL parser."""

    def __init__(self, tokens: list[Token], filename: str = "<string>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0

    def _error(self, msg: str) -> ParseError:
        tok = self._peek()
        return ParseError(msg, self.filename, tok.line, tok.column)

    # -- Navigation --

    def _peek(self, offset: int = 0) -> Token:
        p = self.pos + offset
        if p < len(self.tokens):
            return self.tokens[p]
        return self.tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _expect(self, tt: TokenType) -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise self._error(f"Expected {tt.value!r}, got {tok.type.value!r} ({tok.value!r})")
        return self._advance()

    def _match(self, *types: TokenType) -> Token | None:
        if self._peek().type in types:
            return self._advance()
        return None

    def _at(self, *types: TokenType) -> bool:
        return self._peek().type in types

    def _skip_newlines(self) -> None:
        while self._at(TokenType.NEWLINE):
            self._advance()

    def _skip_to_semicolon(self) -> None:
        """Error recovery: skip tokens until we find a semicolon."""
        depth = 0
        while not self._at(TokenType.EOF):
            if self._at(TokenType.LBRACE):
                depth += 1
            elif self._at(TokenType.RBRACE):
                if depth > 0:
                    depth -= 1
                else:
                    break
            elif self._at(TokenType.SEMICOLON) and depth == 0:
                self._advance()
                return
            self._advance()

    def _skip_to_rbrace(self) -> None:
        """Error recovery: skip to matching closing brace."""
        depth = 1
        while not self._at(TokenType.EOF):
            if self._at(TokenType.LBRACE):
                depth += 1
            elif self._at(TokenType.RBRACE):
                depth -= 1
                if depth == 0:
                    self._advance()
                    return
            self._advance()

    # -- Attribute parsing --

    def _parse_attribute_block(self) -> list[Attribute]:
        """Parse [...] attribute block. Returns empty list if no [ is present."""
        if not self._at(TokenType.LBRACKET):
            return []
        self._advance()  # [
        attrs: list[Attribute] = []

        while not self._at(TokenType.RBRACKET, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACKET):
                break

            # Read attribute name - can be a keyword or identifier
            tok = self._peek()
            if tok.type in (TokenType.IDENT, TokenType.CASE, TokenType.DEFAULT,
                            TokenType.CONST, TokenType.VOID, TokenType.INTERFACE,
                            TokenType.STRUCT, TokenType.UNION, TokenType.STRING):
                # STRING token type won't match here - it's the actual string
                raw_name = self._advance().value
            elif tok.type == TokenType.STRING:
                # Quoted attribute value without name (shouldn't happen normally)
                raw_name = self._advance().value
            else:
                # Try any keyword token as attribute name
                raw_name = self._advance().value

            attr_name = AttributeName.lookup(raw_name)

            # Check for parenthesized value
            value: str | None = None
            if self._at(TokenType.LPAREN):
                value = self._read_balanced_parens()

            attrs.append(Attribute(name=attr_name, raw_name=raw_name, value=value))

            # Comma separates attributes
            if self._at(TokenType.COMMA):
                self._advance()
            self._skip_newlines()

        self._expect(TokenType.RBRACKET)
        return attrs

    def _read_balanced_parens(self) -> str:
        """Read content between ( and ), handling nesting and strings. Returns the inner content.

        Reconstructs the content from tokens, using source line/column info
        to determine whether whitespace existed between tokens.
        """
        self._expect(TokenType.LPAREN)
        depth = 1
        parts: list[str] = []
        prev_tok: Token | None = None

        while not self._at(TokenType.EOF):
            tok = self._peek()
            if tok.type == TokenType.NEWLINE:
                self._advance()
                continue

            # Determine if we need a space separator
            if parts and prev_tok is not None:
                # On the same line, check column gap
                if tok.line == prev_tok.line:
                    expected_col = prev_tok.column + len(prev_tok.value)
                    needs_space = tok.column > expected_col
                else:
                    # Different line - use space
                    needs_space = True
                if needs_space:
                    parts.append(" ")

            if tok.type == TokenType.LPAREN:
                depth += 1
                parts.append("(")
                prev_tok = tok
                self._advance()
            elif tok.type == TokenType.RPAREN:
                depth -= 1
                if depth == 0:
                    self._advance()
                    break
                parts.append(")")
                prev_tok = tok
                self._advance()
            elif tok.type == TokenType.STRING:
                parts.append(f'"{tok.value}"')
                prev_tok = tok
                # Adjust prev_tok length to include quotes
                self._advance()
            elif tok.type == TokenType.COMMA:
                parts.append(", ")
                prev_tok = tok
                self._advance()
            else:
                parts.append(tok.value)
                prev_tok = tok
                self._advance()

        return "".join(parts).strip()

    # -- Type parsing --

    def _parse_type_spec(self) -> TypeSpec:
        """Parse a type specification: [modifiers] base_type [calling_conv] [pointers]"""
        is_const = False
        is_signed: bool | None = None
        is_unsigned = False
        is_volatile = False
        calling_convention: str | None = None

        # Collect leading modifiers
        while True:
            tok = self._peek()
            if tok.type == TokenType.CONST:
                is_const = True
                self._advance()
            elif tok.type == TokenType.SIGNED:
                is_signed = True
                self._advance()
            elif tok.type == TokenType.UNSIGNED:
                is_unsigned = True
                self._advance()
            elif tok.type == TokenType.VOLATILE:
                is_volatile = True
                self._advance()
            elif tok.type == TokenType.IDENT and tok.value in _CALLING_CONVENTIONS:
                calling_convention = tok.value
                self._advance()
            else:
                break

        # Parse base type name
        base_name = self._parse_base_type_name()

        # Check for calling convention after type name
        if calling_convention is None:
            tok = self._peek()
            if tok.type == TokenType.IDENT and tok.value in _CALLING_CONVENTIONS:
                calling_convention = tok.value
                self._advance()

        # Parse pointer levels
        pointer_levels = self._parse_pointer_levels()

        return TypeSpec(
            base_name=base_name,
            is_const=is_const,
            is_signed=is_signed,
            is_unsigned=is_unsigned,
            is_volatile=is_volatile,
            pointer_levels=pointer_levels,
            calling_convention=calling_convention,
        )

    def _parse_base_type_name(self) -> str:
        """Parse the base type name, handling multi-word types."""
        tok = self._peek()

        # Handle void
        if tok.type == TokenType.VOID:
            self._advance()
            return "void"

        # Handle struct/union/enum TYPE
        if tok.type in (TokenType.STRUCT, TokenType.UNION, TokenType.ENUM):
            keyword = self._advance().value
            if self._at(TokenType.IDENT):
                name = self._advance().value
                return f"{keyword} {name}"
            return keyword

        # Must be an identifier
        if tok.type != TokenType.IDENT:
            raise self._error(f"Expected type name, got {tok.value!r}")

        name = self._advance().value

        # Handle multi-word types: long long, unsigned long long, etc.
        if name in _MULTI_WORD_TYPES:
            while self._peek().type == TokenType.IDENT and self._peek().value in _MULTI_WORD_TYPES:
                name += " " + self._advance().value

        return name

    def _parse_pointer_levels(self) -> list[PointerLevel]:
        """Parse pointer indirection: *, *const*, **, etc."""
        levels: list[PointerLevel] = []
        while self._at(TokenType.STAR):
            self._advance()
            # Check for *const pattern
            is_const = False
            if self._at(TokenType.CONST):
                is_const = True
                self._advance()
            levels.append(PointerLevel(is_const=is_const))
        return levels

    # -- Expression parsing --

    def _parse_expression(self) -> Expression:
        """Parse a value expression (for enum values, constants, array sizes)."""
        return self._parse_ternary()

    def _parse_ternary(self) -> Expression:
        expr = self._parse_bitwise_or()
        if self._at(TokenType.QUESTION):
            self._advance()
            true_expr = self._parse_expression()
            self._expect(TokenType.COLON)
            false_expr = self._parse_expression()
            return BinaryOp("?:", true_expr, false_expr)
        return expr

    def _parse_bitwise_or(self) -> Expression:
        left = self._parse_bitwise_xor()
        while self._at(TokenType.PIPE_OP):
            self._advance()
            right = self._parse_bitwise_xor()
            left = BinaryOp("|", left, right)
        return left

    def _parse_bitwise_xor(self) -> Expression:
        left = self._parse_bitwise_and()
        while self._at(TokenType.CARET):
            self._advance()
            right = self._parse_bitwise_and()
            left = BinaryOp("^", left, right)
        return left

    def _parse_bitwise_and(self) -> Expression:
        left = self._parse_shift()
        while self._at(TokenType.AMPERSAND):
            self._advance()
            right = self._parse_shift()
            left = BinaryOp("&", left, right)
        return left

    def _parse_shift(self) -> Expression:
        left = self._parse_additive()
        while self._at(TokenType.LSHIFT, TokenType.RSHIFT):
            op = self._advance().value
            right = self._parse_additive()
            left = BinaryOp(op, left, right)
        return left

    def _parse_additive(self) -> Expression:
        left = self._parse_multiplicative()
        while self._at(TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def _parse_multiplicative(self) -> Expression:
        left = self._parse_unary()
        while self._at(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance().value
            right = self._parse_unary()
            left = BinaryOp(op, left, right)
        return left

    def _parse_unary(self) -> Expression:
        if self._at(TokenType.MINUS):
            self._advance()
            operand = self._parse_unary()
            # Fold negative integer literals
            if isinstance(operand, IntegerLiteral):
                return IntegerLiteral(
                    value=-operand.value, base=operand.base,
                    suffix=operand.suffix, raw="-" + operand.raw
                )
            return UnaryOp("-", operand)
        if self._at(TokenType.TILDE):
            self._advance()
            return UnaryOp("~", self._parse_unary())
        if self._at(TokenType.BANG):
            self._advance()
            return UnaryOp("!", self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Expression:
        tok = self._peek()

        if tok.type == TokenType.INTEGER:
            self._advance()
            return IntegerLiteral(
                value=tok.int_value if tok.int_value is not None else 0,
                base=16 if tok.value.lower().startswith("0x") else (8 if tok.value.startswith("0") and len(tok.value) > 1 and tok.value[1:].isdigit() else 10),
                suffix=tok.suffix,
                raw=tok.value,
            )

        if tok.type == TokenType.FLOAT:
            self._advance()
            return FloatLiteral(value=tok.float_value or 0.0, raw=tok.value)

        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(value=tok.value)

        if tok.type == TokenType.IDENT:
            self._advance()
            return IdentifierRef(name=tok.value)

        # Handle keyword tokens used as enum member references (e.g. TRUE, FALSE, NULL)
        if tok.type in (TokenType.DEFAULT, TokenType.VOID):
            self._advance()
            return IdentifierRef(name=tok.value)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return ParenExpr(inner=expr)

        raise self._error(f"Expected expression, got {tok.value!r}")

    # -- Import/CppQuote/Preprocessor --

    def _parse_import(self) -> ImportStatement:
        line = self._peek().line
        self._expect(TokenType.IMPORT)
        path_tok = self._expect(TokenType.STRING)
        # Import can have multiple comma-separated paths
        paths = [path_tok.value]
        while self._at(TokenType.COMMA):
            self._advance()
            paths.append(self._expect(TokenType.STRING).value)
        self._expect(TokenType.SEMICOLON)
        # Return first path; if multiple, emit separate ImportStatements
        stmts = [ImportStatement(path=p, line=line) for p in paths]
        return stmts  # type: ignore

    def _parse_cpp_quote(self) -> CppQuote:
        line = self._peek().line
        self._expect(TokenType.CPP_QUOTE)
        self._expect(TokenType.LPAREN)
        text = self._expect(TokenType.STRING).value
        self._expect(TokenType.RPAREN)
        self._match(TokenType.SEMICOLON)  # optional
        return CppQuote(text=text, line=line)

    def _parse_preprocessor(self) -> PreprocessorDirective:
        line = self._peek().line
        self._expect(TokenType.HASH)
        self._skip_newlines()
        directive_tok = self._peek()
        if directive_tok.type in (TokenType.IDENT, TokenType.IMPORT):
            directive = self._advance().value
        else:
            directive = self._advance().value
        # Read content (already captured as STRING by lexer)
        content = ""
        if self._at(TokenType.STRING):
            content = self._advance().value
        self._skip_newlines()
        return PreprocessorDirective(directive=directive, content=content, line=line)

    # -- Constants --

    def _parse_constant(self) -> Constant:
        line = self._peek().line
        self._expect(TokenType.CONST)
        type_spec = self._parse_type_spec()
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.EQUALS)
        value = self._parse_expression()
        self._expect(TokenType.SEMICOLON)
        return Constant(type_spec=type_spec, name=name, value=value, line=line)

    # -- Enum --

    def _parse_typedef_enum(self, attrs: list[Attribute] | None = None) -> EnumDef:
        line = self._peek().line
        self._expect(TokenType.ENUM)
        tag = ""
        if self._at(TokenType.IDENT):
            tag = self._advance().value
        self._expect(TokenType.LBRACE)

        members: list[EnumMember] = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            # Member name - handle keyword names too
            mem_tok = self._peek()
            if mem_tok.type == TokenType.IDENT:
                mem_name = self._advance().value
            else:
                # Some enum members might clash with keywords
                mem_name = self._advance().value

            mem_line = mem_tok.line
            value: Expression | None = None
            if self._at(TokenType.EQUALS):
                self._advance()
                value = self._parse_expression()

            members.append(EnumMember(name=mem_name, value=value, line=mem_line))

            if self._at(TokenType.COMMA):
                self._advance()
            self._skip_newlines()

        self._expect(TokenType.RBRACE)

        # Parse typedef name(s)
        name = ""
        if self._at(TokenType.IDENT):
            name = self._advance().value
        if not name:
            name = tag

        self._match(TokenType.SEMICOLON)
        return EnumDef(name=name, tag=tag, members=members,
                       attributes=attrs or [], line=line)

    # -- Struct --

    def _parse_typedef_struct(self, attrs: list[Attribute] | None = None) -> StructDef:
        line = self._peek().line
        self._expect(TokenType.STRUCT)
        tag = ""
        if self._at(TokenType.IDENT):
            tag = self._advance().value

        self._expect(TokenType.LBRACE)
        members = self._parse_struct_body()
        self._expect(TokenType.RBRACE)

        # Parse typedef name and aliases: NAME [, *ALIAS1, *ALIAS2]
        name, aliases = self._parse_typedef_aliases()
        if not name:
            name = tag

        self._match(TokenType.SEMICOLON)
        return StructDef(name=name, tag=tag, members=members,
                         aliases=aliases, attributes=attrs or [], line=line)

    def _parse_bare_struct(self) -> StructDef:
        """Parse a struct without typedef: struct NAME { ... };"""
        line = self._peek().line
        self._expect(TokenType.STRUCT)
        tag = ""
        if self._at(TokenType.IDENT):
            tag = self._advance().value

        self._expect(TokenType.LBRACE)
        members = self._parse_struct_body()
        self._expect(TokenType.RBRACE)
        self._match(TokenType.SEMICOLON)
        return StructDef(name=tag, tag=tag, members=members, line=line)

    def _parse_struct_body(self) -> list:
        """Parse struct body contents between { and }."""
        members = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break
            member = self._parse_struct_member()
            if member is not None:
                members.append(member)
        return members

    def _parse_struct_member(self):
        """Parse a single struct member: field, anonymous union, or anonymous struct."""
        # Check for anonymous union
        if self._at(TokenType.UNION):
            return self._parse_anonymous_union()

        # Check for anonymous struct
        if self._at(TokenType.STRUCT):
            return self._parse_anonymous_struct()

        # Check for attribute block on field
        attrs = self._parse_attribute_block()

        # Check if this is a union/struct with switch_is or similar
        if self._at(TokenType.UNION):
            return self._parse_anonymous_union(attrs)
        if self._at(TokenType.STRUCT):
            return self._parse_anonymous_struct()

        # Regular field
        return self._parse_struct_field(attrs)

    def _parse_struct_field(self, attrs: list[Attribute] | None = None) -> StructField:
        """Parse a struct field: [attrs] TYPE name [: bitwidth] [dimensions] ;"""
        line = self._peek().line
        type_spec = self._parse_type_spec()

        # Name
        name = ""
        if self._at(TokenType.IDENT):
            name = self._advance().value

        # Array dimensions
        array_dims = self._parse_array_dimensions()

        # Bitfield
        bitfield_width: int | None = None
        if self._at(TokenType.COLON):
            self._advance()
            bw_tok = self._expect(TokenType.INTEGER)
            bitfield_width = bw_tok.int_value

        self._expect(TokenType.SEMICOLON)
        return StructField(
            type_spec=type_spec, name=name, attributes=attrs or [],
            array_dimensions=array_dims, bitfield_width=bitfield_width,
            line=line,
        )

    def _parse_anonymous_union(self, attrs: list[Attribute] | None = None) -> AnonymousUnion:
        """Parse an anonymous union inside a struct."""
        line = self._peek().line
        self._expect(TokenType.UNION)
        # Optional tag name (skip it)
        if self._at(TokenType.IDENT) and self._peek(1).type == TokenType.LBRACE:
            self._advance()
        self._expect(TokenType.LBRACE)

        members = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            # Check for [case(n)] or [default] in discriminated unions
            field_attrs = self._parse_attribute_block()

            if self._at(TokenType.RBRACE):
                break

            if self._at(TokenType.SEMICOLON):
                # Empty case: [default] ;
                self._advance()
                continue

            if self._at(TokenType.STRUCT):
                members.append(self._parse_anonymous_struct())
                continue

            if self._at(TokenType.UNION):
                members.append(self._parse_anonymous_union())
                continue

            # Regular field
            member = self._parse_struct_field(field_attrs)
            members.append(member)

        self._expect(TokenType.RBRACE)

        # Optional member name
        name: str | None = None
        if self._at(TokenType.IDENT):
            name = self._advance().value
        self._match(TokenType.SEMICOLON)

        return AnonymousUnion(members=members, attributes=attrs or [],
                              name=name, line=line)

    def _parse_anonymous_struct(self) -> AnonymousStruct:
        """Parse an anonymous struct inside a union."""
        line = self._peek().line
        self._expect(TokenType.STRUCT)
        # Optional tag
        if self._at(TokenType.IDENT) and self._peek(1).type == TokenType.LBRACE:
            self._advance()
        self._expect(TokenType.LBRACE)

        members: list[StructField] = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break
            attrs = self._parse_attribute_block()
            members.append(self._parse_struct_field(attrs))

        self._expect(TokenType.RBRACE)

        name: str | None = None
        if self._at(TokenType.IDENT):
            name = self._advance().value
        self._match(TokenType.SEMICOLON)

        return AnonymousStruct(members=members, name=name, line=line)

    def _parse_array_dimensions(self) -> list[ArrayDimension]:
        """Parse array dimensions: [expr], [expr][expr], [], etc."""
        dims: list[ArrayDimension] = []
        while self._at(TokenType.LBRACKET):
            self._advance()
            if self._at(TokenType.RBRACKET):
                dims.append(ArrayDimension(size=None))
            elif self._at(TokenType.STAR):
                self._advance()
                dims.append(ArrayDimension(size=None))
            else:
                size = self._parse_expression()
                dims.append(ArrayDimension(size=size))
            self._expect(TokenType.RBRACKET)
        return dims

    # -- Union --

    def _parse_typedef_union(self, attrs: list[Attribute] | None = None) -> UnionDef:
        line = self._peek().line
        self._expect(TokenType.UNION)
        tag = ""
        if self._at(TokenType.IDENT):
            tag = self._advance().value

        # Check for encapsulated union: switch (type name) { ... }
        switch_type: TypeSpec | None = None
        switch_name: str | None = None
        if self._at(TokenType.SWITCH):
            self._advance()
            self._expect(TokenType.LPAREN)
            switch_type = self._parse_type_spec()
            if self._at(TokenType.IDENT):
                switch_name = self._advance().value
            self._expect(TokenType.RPAREN)
            # Optional union name after switch
            if self._at(TokenType.IDENT) and self._peek(1).type == TokenType.LBRACE:
                self._advance()

        self._expect(TokenType.LBRACE)

        # Parse union body
        members = []
        cases: list[UnionCase] = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            field_attrs = self._parse_attribute_block()

            # Check if this is a case/default union
            has_case = any(a.name == AttributeName.CASE for a in field_attrs)
            has_default = any(a.name == AttributeName.DEFAULT for a in field_attrs)

            if has_case or has_default:
                # Discriminated union case
                case_values: list[Expression] = []
                for a in field_attrs:
                    if a.name == AttributeName.CASE and a.value:
                        # Parse the case value(s)
                        for v in a.value.split(","):
                            v = v.strip()
                            if v:
                                # Quick parse of a single expression
                                from .lexer import Lexer
                                case_toks = Lexer(v, self.filename).tokenize()
                                case_parser = Parser(case_toks, self.filename)
                                case_values.append(case_parser._parse_expression())

                field = None
                if self._at(TokenType.SEMICOLON):
                    # Empty case
                    self._advance()
                elif self._at(TokenType.STRUCT):
                    field = self._parse_anonymous_struct()
                elif not self._at(TokenType.LBRACKET, TokenType.RBRACE):
                    field = self._parse_struct_field()

                cases.append(UnionCase(
                    case_values=case_values, is_default=has_default,
                    member=field, attributes=field_attrs, line=line,
                ))
            else:
                if self._at(TokenType.STRUCT):
                    members.append(self._parse_anonymous_struct())
                elif self._at(TokenType.SEMICOLON):
                    self._advance()
                else:
                    members.append(self._parse_struct_field(field_attrs))

        self._expect(TokenType.RBRACE)

        name, aliases = self._parse_typedef_aliases()
        if not name:
            name = tag

        self._match(TokenType.SEMICOLON)
        return UnionDef(
            name=name, tag=tag, members=members, cases=cases,
            aliases=aliases, attributes=attrs or [],
            switch_type=switch_type, switch_name=switch_name, line=line,
        )

    # -- Typedef aliases --

    def _parse_typedef_aliases(self) -> tuple[str, list[str]]:
        """Parse the name and optional pointer aliases after a closing brace.

        E.g.: `NAME, *PNAME, *LPNAME` -> ("NAME", ["PNAME", "LPNAME"])
        """
        name = ""
        aliases: list[str] = []

        if self._at(TokenType.IDENT):
            name = self._advance().value

        while self._at(TokenType.COMMA):
            self._advance()
            # Skip stars
            while self._at(TokenType.STAR):
                self._advance()
            if self._at(TokenType.IDENT):
                aliases.append(self._advance().value)

        return name, aliases

    # -- Type alias --

    def _parse_typedef_alias(self, attrs: list[Attribute] | None = None) -> TypeAlias:
        """Parse typedef TYPE NAME [, *ALIAS ...];"""
        line = self._peek().line
        type_spec = self._parse_type_spec()
        name = ""
        if self._at(TokenType.IDENT):
            name = self._advance().value

        aliases: list[str] = []
        while self._at(TokenType.COMMA):
            self._advance()
            while self._at(TokenType.STAR):
                self._advance()
            if self._at(TokenType.IDENT):
                aliases.append(self._advance().value)

        self._expect(TokenType.SEMICOLON)
        return TypeAlias(type_spec=type_spec, name=name,
                         attributes=attrs or [], aliases=aliases, line=line)

    # -- Function pointer typedef --

    def _parse_typedef_funcptr(self, return_type: TypeSpec) -> FuncPointerTypedef:
        """Parse typedef RET (CONV *NAME)(PARAMS);"""
        line = self._peek().line
        self._expect(TokenType.LPAREN)

        calling_convention: str | None = None
        if self._at(TokenType.IDENT) and self._peek().value in _CALLING_CONVENTIONS:
            calling_convention = self._advance().value

        self._expect(TokenType.STAR)
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.RPAREN)

        # Parse parameter list
        self._expect(TokenType.LPAREN)
        params: list[FuncPointerParam] = []
        while not self._at(TokenType.RPAREN, TokenType.EOF):
            if self._at(TokenType.VOID) and self._peek(1).type == TokenType.RPAREN:
                self._advance()  # skip void
                break
            ptype = self._parse_type_spec()
            pname: str | None = None
            if self._at(TokenType.IDENT):
                pname = self._advance().value
            params.append(FuncPointerParam(type_spec=ptype, name=pname))
            if not self._at(TokenType.RPAREN):
                self._expect(TokenType.COMMA)
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.SEMICOLON)

        return FuncPointerTypedef(
            return_type=return_type, name=name,
            calling_convention=calling_convention,
            params=params, line=line,
        )

    # -- Interface --

    def _parse_interface(self, attrs: list[Attribute] | None = None) -> InterfaceDef:
        line = self._peek().line
        self._expect(TokenType.INTERFACE)
        name = self._expect(TokenType.IDENT).value

        # Check for forward declaration
        if self._at(TokenType.SEMICOLON):
            self._advance()
            return ForwardDecl(kind="interface", name=name, line=line)  # type: ignore

        # Inheritance
        parent: str | None = None
        if self._at(TokenType.COLON):
            self._advance()
            parent = self._expect(TokenType.IDENT).value

        self._expect(TokenType.LBRACE)

        methods: list[Method] = []
        typedefs: list[InterfaceTypedef] = []

        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            # Check for typedef inside interface
            if self._at(TokenType.TYPEDEF):
                td = self._parse_typedef()
                if td is not None:
                    typedefs.append(InterfaceTypedef(typedef=td, line=td.line))
                continue

            # Method or method with attributes
            method_attrs = self._parse_attribute_block()

            if self._at(TokenType.RBRACE):
                break

            # Check for typedef with attrs (e.g. [context_handle])
            if self._at(TokenType.TYPEDEF):
                td = self._parse_typedef()
                if td is not None:
                    typedefs.append(InterfaceTypedef(typedef=td, line=td.line))
                continue

            method = self._parse_method(method_attrs)
            if method is not None:
                methods.append(method)

        self._expect(TokenType.RBRACE)
        self._match(TokenType.SEMICOLON)

        return InterfaceDef(
            name=name, attributes=attrs or [], parent=parent,
            methods=methods, typedefs=typedefs, line=line,
        )

    def _parse_method(self, attrs: list[Attribute] | None = None) -> Method | None:
        """Parse a method declaration inside an interface."""
        line = self._peek().line

        # Return type
        return_type = self._parse_type_spec()

        # Method name
        if not self._at(TokenType.IDENT):
            # Could be a malformed line, try to recover
            self._skip_to_semicolon()
            return None
        name = self._advance().value

        # Parameter list
        self._expect(TokenType.LPAREN)
        params: list[MethodParam] = []

        while not self._at(TokenType.RPAREN, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RPAREN):
                break

            # Check for (void) - no parameters
            if self._at(TokenType.VOID) and self._peek(1).type == TokenType.RPAREN:
                self._advance()
                break

            param = self._parse_method_param()
            params.append(param)

            if self._at(TokenType.COMMA):
                self._advance()
            self._skip_newlines()

        self._expect(TokenType.RPAREN)
        self._expect(TokenType.SEMICOLON)

        return Method(return_type=return_type, name=name,
                      params=params, attributes=attrs or [], line=line)

    def _parse_method_param(self) -> MethodParam:
        """Parse a single method parameter."""
        line = self._peek().line
        param_attrs = self._parse_attribute_block()
        type_spec = self._parse_type_spec()

        name: str | None = None
        # The name is optional (could be followed by , or ) or [ directly)
        if self._at(TokenType.IDENT):
            # Make sure it's actually a name, not the start of the next param
            name = self._advance().value

        array_dims = self._parse_array_dimensions()

        return MethodParam(
            type_spec=type_spec, name=name, attributes=param_attrs,
            array_dimensions=array_dims, line=line,
        )

    # -- Library --

    def _parse_library(self, attrs: list[Attribute] | None = None) -> LibraryDef:
        line = self._peek().line
        self._expect(TokenType.LIBRARY)
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.LBRACE)

        elements = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            elem = self._parse_library_element()
            if elem is not None:
                elements.append(elem)

        self._expect(TokenType.RBRACE)
        self._match(TokenType.SEMICOLON)
        return LibraryDef(name=name, attributes=attrs or [],
                          elements=elements, line=line)

    def _parse_library_element(self):
        """Parse a single element inside a library body."""
        # importlib
        if self._at(TokenType.IMPORTLIB):
            return self._parse_importlib()

        # typedef
        if self._at(TokenType.TYPEDEF):
            return self._parse_typedef()

        # Attribute block -> coclass, interface, dispinterface
        if self._at(TokenType.LBRACKET):
            attrs = self._parse_attribute_block()
            if self._at(TokenType.COCLASS):
                return self._parse_coclass(attrs)
            elif self._at(TokenType.INTERFACE):
                return self._parse_interface(attrs)
            elif self._at(TokenType.LIBRARY):
                return self._parse_library(attrs)
            else:
                # Could be attributed typedef or unknown
                self._skip_to_semicolon()
                return None

        # Bare interface (forward decl in library)
        if self._at(TokenType.INTERFACE):
            self._advance()
            iname = self._expect(TokenType.IDENT).value
            self._expect(TokenType.SEMICOLON)
            return ForwardDecl(kind="interface", name=iname, line=self._peek().line)

        # Bare coclass
        if self._at(TokenType.COCLASS):
            return self._parse_coclass()

        # Skip unknown
        self._skip_to_semicolon()
        return None

    def _parse_importlib(self) -> ImportLib:
        line = self._peek().line
        self._expect(TokenType.IMPORTLIB)
        self._expect(TokenType.LPAREN)
        path = self._expect(TokenType.STRING).value
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.SEMICOLON)
        return ImportLib(path=path, line=line)

    def _parse_coclass(self, attrs: list[Attribute] | None = None) -> CoclassDef:
        line = self._peek().line
        self._expect(TokenType.COCLASS)
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.LBRACE)

        interfaces: list[CoclassInterface] = []
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break

            iface_attrs = self._parse_attribute_block()

            # interface keyword
            if self._at(TokenType.INTERFACE) or self._at(TokenType.DISPINTERFACE):
                self._advance()

            if self._at(TokenType.IDENT):
                iname = self._advance().value
                interfaces.append(CoclassInterface(
                    name=iname, attributes=iface_attrs, line=self._peek().line
                ))

            self._match(TokenType.SEMICOLON)

        self._expect(TokenType.RBRACE)
        self._match(TokenType.SEMICOLON)
        return CoclassDef(name=name, attributes=attrs or [],
                          interfaces=interfaces, line=line)

    # -- Typedef dispatcher --

    def _parse_typedef(self):
        """Parse a typedef statement, dispatching to the appropriate handler."""
        line = self._peek().line
        self._expect(TokenType.TYPEDEF)

        # Check for attributes on typedef: typedef [attrs] ...
        attrs = self._parse_attribute_block()

        # Dispatch based on what follows
        if self._at(TokenType.STRUCT):
            return self._parse_typedef_struct(attrs)
        elif self._at(TokenType.ENUM):
            return self._parse_typedef_enum(attrs)
        elif self._at(TokenType.UNION):
            return self._parse_typedef_union(attrs)
        elif self._at(TokenType.PIPE):
            # typedef pipe TYPE NAME;
            self._advance()
            return self._parse_typedef_alias(attrs)
        else:
            # Could be: simple alias, or function pointer typedef
            # Need to parse the return type first, then check for funcptr pattern
            type_spec = self._parse_type_spec()

            # Check for function pointer: typedef RET (CONV *NAME)(...)
            if self._at(TokenType.LPAREN):
                # Peek ahead to see if this is a function pointer
                saved_pos = self.pos
                try:
                    return self._parse_typedef_funcptr(type_spec)
                except ParseError:
                    self.pos = saved_pos
                    # Fall through to simple alias

            # Simple alias
            name = ""
            if self._at(TokenType.IDENT):
                name = self._advance().value

            aliases: list[str] = []
            while self._at(TokenType.COMMA):
                self._advance()
                while self._at(TokenType.STAR):
                    self._advance()
                if self._at(TokenType.IDENT):
                    aliases.append(self._advance().value)

            self._expect(TokenType.SEMICOLON)
            return TypeAlias(type_spec=type_spec, name=name,
                             attributes=attrs, aliases=aliases, line=line)

    # -- Forward declaration --

    def _parse_forward_decl(self) -> ForwardDecl:
        line = self._peek().line
        kind = self._advance().value  # interface, struct, etc.
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.SEMICOLON)
        return ForwardDecl(kind=kind, name=name, line=line)

    # -- Top-level parse --

    def parse(self) -> MidlFile:
        """Parse the token stream into a MidlFile AST."""
        elements = []

        while not self._at(TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.EOF):
                break

            try:
                elem = self._parse_top_level()
                if elem is not None:
                    if isinstance(elem, list):
                        elements.extend(elem)
                    else:
                        elements.append(elem)
            except ParseError:
                # Recovery: skip to next statement
                self._skip_to_semicolon()

        return MidlFile(filename=self.filename, elements=elements)

    def _parse_top_level(self):
        """Parse a single top-level element."""
        tok = self._peek()

        # Preprocessor directive
        if tok.type == TokenType.HASH:
            return self._parse_preprocessor()

        # Import
        if tok.type == TokenType.IMPORT:
            return self._parse_import()

        # cpp_quote
        if tok.type == TokenType.CPP_QUOTE:
            return self._parse_cpp_quote()

        # Constant
        if tok.type == TokenType.CONST:
            # Distinguish const declaration from const in type spec
            # Look ahead: const TYPE NAME = VALUE;
            # Save position and try
            saved = self.pos
            try:
                return self._parse_constant()
            except ParseError:
                self.pos = saved
                # Fall through

        # Typedef
        if tok.type == TokenType.TYPEDEF:
            return self._parse_typedef()

        # Bare struct (no typedef)
        if tok.type == TokenType.STRUCT:
            return self._parse_bare_struct()

        # Attribute block -> interface, library, coclass
        if tok.type == TokenType.LBRACKET:
            attrs = self._parse_attribute_block()
            if self._at(TokenType.INTERFACE):
                return self._parse_interface(attrs)
            elif self._at(TokenType.LIBRARY):
                return self._parse_library(attrs)
            elif self._at(TokenType.COCLASS):
                return self._parse_coclass(attrs)
            elif self._at(TokenType.TYPEDEF):
                return self._parse_typedef()
            else:
                # Unknown attributed construct
                self._skip_to_semicolon()
                return None

        # Bare interface (forward decl or definition)
        if tok.type == TokenType.INTERFACE:
            # Check if forward declaration
            if self._peek(1).type == TokenType.IDENT:
                next_after = self._peek(2)
                if next_after.type == TokenType.SEMICOLON:
                    return self._parse_forward_decl()
            return self._parse_interface()

        # Bare library
        if tok.type == TokenType.LIBRARY:
            return self._parse_library()

        # Bare coclass
        if tok.type == TokenType.COCLASS:
            return self._parse_coclass()

        # Skip unknown tokens
        self._advance()
        return None
