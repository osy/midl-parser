"""AST node definitions for the MIDL parser.

All parsed MIDL constructs are represented as dataclasses here.
Types are structured (not plain strings) wherever meaningful.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Union


# ---------------------------------------------------------------------------
# Attribute name enum
# ---------------------------------------------------------------------------

class AttributeName(enum.Enum):
    """Well-known MIDL attribute names."""

    # Directional
    IN = "in"
    OUT = "out"
    RETVAL = "retval"

    # Pointer types
    PTR = "ptr"
    REF = "ref"
    UNIQUE = "unique"
    STRING = "string"
    IID_IS = "iid_is"

    # Array sizing
    SIZE_IS = "size_is"
    MAX_IS = "max_is"
    LENGTH_IS = "length_is"
    FIRST_IS = "first_is"
    LAST_IS = "last_is"
    MIN_IS = "min_is"
    RANGE = "range"

    # Interface header
    OBJECT = "object"
    LOCAL = "local"
    UUID = "uuid"
    VERSION = "version"
    POINTER_DEFAULT = "pointer_default"
    ENDPOINT = "endpoint"
    ASYNC_UUID = "async_uuid"
    MS_UNION = "ms_union"

    # Annotation (SAL)
    ANNOTATION = "annotation"

    # Type library / COM
    HELPSTRING = "helpstring"
    HELPCONTEXT = "helpcontext"
    HELPFILE = "helpfile"
    ID = "id"
    PROPGET = "propget"
    PROPPUT = "propput"
    PROPPUTREF = "propputref"
    DUAL = "dual"
    OLEAUTOMATION = "oleautomation"
    NONEXTENSIBLE = "nonextensible"
    HIDDEN = "hidden"
    RESTRICTED = "restricted"
    PUBLIC = "public"
    NONCREATABLE = "noncreatable"
    AGGREGATABLE = "aggregatable"
    CONTROL = "control"
    LICENSED = "licensed"
    SOURCE = "source"
    DEFAULT = "default"
    DEFAULTVALUE = "defaultvalue"
    OPTIONAL = "optional"
    VARARG = "vararg"
    LCID = "lcid"

    # Function call semantics
    CALLBACK = "callback"
    IDEMPOTENT = "idempotent"
    MAYBE = "maybe"
    BROADCAST = "broadcast"
    CALL_AS = "call_as"
    MESSAGE = "message"

    # Handle / context
    CONTEXT_HANDLE = "context_handle"
    CONTEXT_HANDLE_SERIALIZE = "context_handle_serialize"
    CONTEXT_HANDLE_NOSERIALIZE = "context_handle_noserialize"
    HANDLE = "handle"
    IMPLICIT_HANDLE = "implicit_handle"
    AUTO_HANDLE = "auto_handle"
    EXPLICIT_HANDLE = "explicit_handle"
    STRICT_CONTEXT_HANDLE = "strict_context_handle"

    # Union discriminant
    SWITCH_IS = "switch_is"
    SWITCH_TYPE = "switch_type"
    CASE = "case"

    # Marshaling
    TRANSMIT_AS = "transmit_as"
    WIRE_MARSHAL = "wire_marshal"
    USER_MARSHAL = "user_marshal"
    REPRESENT_AS = "represent_as"
    ENCODE = "encode"
    DECODE = "decode"
    BYTE_COUNT = "byte_count"
    IGNORE = "ignore"
    PARTIAL_IGNORE = "partial_ignore"

    # Versioning
    V1_ENUM = "v1_enum"
    V1_ARRAY = "v1_array"
    V1_STRING = "v1_string"
    V1_STRUCT = "v1_struct"

    # ACF-specific
    FAULT_STATUS = "fault_status"
    COMM_STATUS = "comm_status"
    ENABLE_ALLOCATE = "enable_allocate"
    ALLOCATE = "allocate"
    NOCODE = "nocode"
    CODE = "code"
    NOTIFY = "notify"
    NOTIFY_FLAG = "notify_flag"
    OPTIMIZE = "optimize"

    # System handle
    SYSTEM_HANDLE = "system_handle"

    # Custom / catch-all
    CUSTOM = "_custom"

    @classmethod
    def lookup(cls, name: str) -> "AttributeName":
        """Look up an attribute name, returning CUSTOM if unknown."""
        try:
            return cls(name.lower())
        except ValueError:
            return cls.CUSTOM


# ---------------------------------------------------------------------------
# Attribute
# ---------------------------------------------------------------------------

@dataclass
class Attribute:
    """A single parsed attribute from an [...] block."""
    name: AttributeName
    raw_name: str
    value: str | None = None  # parenthesized content, if any


# ---------------------------------------------------------------------------
# Type representation
# ---------------------------------------------------------------------------

@dataclass
class PointerLevel:
    """One level of pointer indirection (a single *)."""
    is_const: bool = False  # True for `*const` patterns


@dataclass
class TypeSpec:
    """A fully parsed type specification.

    Examples:
        const void*         -> is_const=True, base_name="void", pointer_levels=[PL(False)]
        IUnknown *const *   -> base_name="IUnknown", pointer_levels=[PL(True), PL(False)]
        unsigned long       -> is_unsigned=True, base_name="long"
        UINT                -> base_name="UINT"
    """
    base_name: str
    is_const: bool = False
    is_signed: bool | None = None
    is_unsigned: bool = False
    is_volatile: bool = False
    pointer_levels: list[PointerLevel] = field(default_factory=list)
    calling_convention: str | None = None

    @property
    def is_pointer(self) -> bool:
        return len(self.pointer_levels) > 0

    @property
    def pointer_depth(self) -> int:
        return len(self.pointer_levels)

    def format(self) -> str:
        """Format back to a readable type string."""
        parts: list[str] = []
        if self.is_const:
            parts.append("const")
        if self.is_volatile:
            parts.append("volatile")
        if self.is_signed is True:
            parts.append("signed")
        if self.is_unsigned:
            parts.append("unsigned")
        parts.append(self.base_name)
        if self.calling_convention:
            parts.append(self.calling_convention)
        for pl in self.pointer_levels:
            if pl.is_const:
                parts.append("*const")
            else:
                parts.append("*")
        return " ".join(parts).replace(" *", "*").replace("* const", "*const")


# ---------------------------------------------------------------------------
# Expressions (for enum values, constant values, array sizes)
# ---------------------------------------------------------------------------

@dataclass
class IntegerLiteral:
    """An integer constant like 0, 0xff, 42UL."""
    value: int
    base: int = 10  # 10, 16, or 8
    suffix: str = ""  # "", "L", "UL", "ULL", etc.
    raw: str = ""


@dataclass
class FloatLiteral:
    """A floating-point constant."""
    value: float
    raw: str = ""


@dataclass
class StringLiteral:
    """A string constant."""
    value: str


@dataclass
class IdentifierRef:
    """A reference to another named value (e.g. enum member or constant)."""
    name: str


@dataclass
class BinaryOp:
    """A binary operation like A | B or X + 1."""
    op: str
    left: "Expression"
    right: "Expression"


@dataclass
class UnaryOp:
    """A unary operation like -1 or ~0."""
    op: str
    operand: "Expression"


@dataclass
class ParenExpr:
    """A parenthesized expression."""
    inner: "Expression"


# Union type for all expression nodes
Expression = Union[
    IntegerLiteral, FloatLiteral, StringLiteral, IdentifierRef,
    BinaryOp, UnaryOp, ParenExpr
]


# ---------------------------------------------------------------------------
# Array dimension
# ---------------------------------------------------------------------------

@dataclass
class ArrayDimension:
    """One dimension of an array declaration.

    size is None for unsized arrays like `items[]` or `data[*]`.
    """
    size: Expression | None = None


# ---------------------------------------------------------------------------
# Parsed SAL annotation
# ---------------------------------------------------------------------------

class AnnotationDirection(enum.Enum):
    """Direction extracted from a SAL annotation."""
    IN = "in"
    OUT = "out"
    INOUT = "inout"
    NONE = ""


class AnnotationAccess(enum.Enum):
    """Buffer access pattern extracted from a SAL annotation."""
    NONE = ""
    READS = "reads"             # _In_reads_(n)
    READS_BYTES = "reads_bytes" # _In_reads_bytes_(n)
    WRITES = "writes"           # _Out_writes_(n)
    WRITES_BYTES = "writes_bytes"  # _Out_writes_bytes_(n)
    WRITES_TO = "writes_to"     # _Out_writes_to_(cap, count)
    WRITES_BYTES_TO = "writes_bytes_to"  # _Out_writes_bytes_to_(cap, count)
    UPDATES_BYTES = "updates_bytes"  # _Inout_updates_bytes_(n)
    FIELD_SIZE = "field_size"         # _Field_size_(n)
    FIELD_SIZE_BYTES = "field_size_bytes"  # _Field_size_bytes_full_(n)


class AnnotationKind(enum.Enum):
    """High-level category of a SAL annotation."""
    PARAM = "param"        # _In_, _Out_, _Inout_ and variants
    COM_OUTPTR = "com_outptr"  # _COM_Outptr_ and variants
    OUTPTR = "outptr"      # _Outptr_ and variants
    FIELD_SIZE = "field_size"  # _Field_size_ and variants
    RANGE = "range"        # _In_range_(min, max)
    NUL_TERMINATED = "z"   # _In_z_
    OTHER = "other"


@dataclass
class ParsedAnnotation:
    """A SAL (Source-code Annotation Language) annotation decomposed into
    structured fields.

    Example decompositions:
        "_In_"
            kind=PARAM, direction=IN
        "_Out_opt_"
            kind=PARAM, direction=OUT, optional=True
        "_In_reads_(count)"
            kind=PARAM, direction=IN, access=READS, size_expr="count"
        "_Out_writes_bytes_opt_(*pDataSize)"
            kind=PARAM, direction=OUT, access=WRITES_BYTES, optional=True,
            size_expr="*pDataSize"
        "_In_range_( 0, D3D11_COMMONSHADER_SAMPLER_SLOT_COUNT - 1 )"
            kind=RANGE, direction=IN, range_min="0",
            range_max="D3D11_COMMONSHADER_SAMPLER_SLOT_COUNT - 1"
        "_COM_Outptr_opt_result_maybenull_"
            kind=COM_OUTPTR, direction=OUT, optional=True, may_be_null=True
        "_Field_size_full_(NumEntries)"
            kind=FIELD_SIZE, access=FIELD_SIZE, size_expr="NumEntries",
            full=True
        "_In_z_"
            kind=NUL_TERMINATED, direction=IN
    """
    raw: str
    kind: AnnotationKind = AnnotationKind.OTHER
    direction: AnnotationDirection = AnnotationDirection.NONE
    optional: bool = False
    may_be_null: bool = False
    access: AnnotationAccess = AnnotationAccess.NONE
    size_expr: str | None = None      # buffer count/size expression
    capacity_expr: str | None = None  # for _writes_to_(capacity, count)
    range_min: str | None = None
    range_max: str | None = None
    full: bool = False                # _Field_size_full_ vs _Field_size_
    nul_terminated: bool = False      # _z_ suffix


# Regex to extract the outermost parenthesized argument of a SAL macro.
# Handles one level of nested parens (sufficient for _Inexpressible_(...)).
_SAL_ARGS_RE = re.compile(r'\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$')


def _extract_sal_args(s: str) -> str | None:
    """Return the content inside the outermost trailing (...) or None."""
    m = _SAL_ARGS_RE.search(s)
    return m.group(1).strip() if m else None


def parse_sal_annotation(raw: str) -> ParsedAnnotation:
    """Parse a SAL annotation string into a ParsedAnnotation.

    The input ``raw`` is the value from ``annotation("...")``, which is
    the SAL macro text including any surrounding quotes.
    """
    # Strip surrounding quotes that may be present in the attribute value
    s = raw.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1].strip()

    ann = ParsedAnnotation(raw=raw)

    # ---- _COM_Outptr_ family ----
    if s.startswith("_COM_Outptr_"):
        ann.kind = AnnotationKind.COM_OUTPTR
        ann.direction = AnnotationDirection.OUT
        if "_opt_" in s:
            ann.optional = True
        if "_maybenull_" in s:
            ann.may_be_null = True
        return ann

    # ---- _Outptr_ family ----
    if s.startswith("_Outptr_"):
        ann.kind = AnnotationKind.OUTPTR
        ann.direction = AnnotationDirection.OUT
        if "_opt_" in s:
            ann.optional = True
        if "_maybenull_" in s:
            ann.may_be_null = True
        # _Outptr_result_bytebuffer_(expr)
        args = _extract_sal_args(s)
        if args:
            if "_bytebuffer_" in s:
                ann.access = AnnotationAccess.WRITES_BYTES
            else:
                ann.access = AnnotationAccess.WRITES
            ann.size_expr = args
        return ann

    # ---- _Field_size_ family ----
    if s.startswith("_Field_size"):
        ann.kind = AnnotationKind.FIELD_SIZE
        if "_bytes_" in s:
            ann.access = AnnotationAccess.FIELD_SIZE_BYTES
        else:
            ann.access = AnnotationAccess.FIELD_SIZE
        if "_opt_" in s:
            ann.optional = True
        if "_full_" in s:
            ann.full = True
        args = _extract_sal_args(s)
        if args:
            ann.size_expr = args
        return ann

    # ---- _Always_ wrapper — unwrap and parse inner ----
    if s.startswith("_Always_"):
        args = _extract_sal_args(s)
        if args:
            inner = parse_sal_annotation(args)
            inner.raw = raw  # keep original
            return inner
        return ann

    # ---- _In_z_ (NUL-terminated) ----
    if s == "_In_z_":
        ann.kind = AnnotationKind.NUL_TERMINATED
        ann.direction = AnnotationDirection.IN
        ann.nul_terminated = True
        return ann

    # ---- _In_range_ ----
    m_range = re.match(r'^_In_range_\s*\((.+)\)\s*$', s)
    if m_range:
        ann.kind = AnnotationKind.RANGE
        ann.direction = AnnotationDirection.IN
        parts = m_range.group(1).split(",", 1)
        ann.range_min = parts[0].strip()
        if len(parts) > 1:
            ann.range_max = parts[1].strip()
        return ann

    # ---- Main _In_ / _Out_ / _Inout_ family ----
    ann.kind = AnnotationKind.PARAM

    # Determine direction
    if s.startswith("_Inout_"):
        ann.direction = AnnotationDirection.INOUT
        rest = s[7:]  # after "_Inout_"
    elif s.startswith("_In_"):
        ann.direction = AnnotationDirection.IN
        rest = s[4:]  # after "_In_"
    elif s.startswith("_Out_"):
        ann.direction = AnnotationDirection.OUT
        rest = s[5:]  # after "_Out_"
    else:
        # Unknown pattern
        ann.kind = AnnotationKind.OTHER
        return ann

    # Detect optional
    if "_opt_" in s:
        ann.optional = True

    # Detect buffer access pattern and extract size
    if rest.startswith("reads_bytes"):
        ann.access = AnnotationAccess.READS_BYTES
    elif rest.startswith("reads"):
        ann.access = AnnotationAccess.READS
    elif rest.startswith("writes_bytes_to"):
        ann.access = AnnotationAccess.WRITES_BYTES_TO
    elif rest.startswith("writes_to"):
        ann.access = AnnotationAccess.WRITES_TO
    elif rest.startswith("writes_bytes"):
        ann.access = AnnotationAccess.WRITES_BYTES
    elif rest.startswith("writes"):
        ann.access = AnnotationAccess.WRITES
    elif rest.startswith("updates_bytes"):
        ann.access = AnnotationAccess.UPDATES_BYTES

    # Extract parenthesized size/count expression
    args = _extract_sal_args(s)
    if args and ann.access != AnnotationAccess.NONE:
        if ann.access in (AnnotationAccess.WRITES_TO, AnnotationAccess.WRITES_BYTES_TO):
            parts = args.split(",", 1)
            ann.capacity_expr = parts[0].strip()
            if len(parts) > 1:
                ann.size_expr = parts[1].strip()
        else:
            ann.size_expr = args

    # _opt_bytecount_(n) is an older SAL form
    if "bytecount_" in rest:
        ann.access = AnnotationAccess.READS_BYTES
        args = _extract_sal_args(s)
        if args:
            ann.size_expr = args

    # _opt_count_(n) — older SAL form
    if "_opt_count_" in rest or rest.startswith("opt_count_"):
        ann.access = AnnotationAccess.READS
        args = _extract_sal_args(s)
        if args:
            ann.size_expr = args

    return ann


# ---------------------------------------------------------------------------
# Top-level AST nodes
# ---------------------------------------------------------------------------

@dataclass
class ImportStatement:
    """import "file.idl";"""
    path: str
    line: int = 0


@dataclass
class CppQuote:
    """cpp_quote("...");"""
    text: str
    line: int = 0


@dataclass
class PreprocessorDirective:
    """#define, #pragma, #ifdef, etc."""
    directive: str  # "define", "pragma", "ifdef", ...
    content: str  # rest of the line
    line: int = 0


@dataclass
class Constant:
    """const TYPE NAME = value;"""
    type_spec: TypeSpec
    name: str
    value: Expression
    line: int = 0


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

@dataclass
class EnumMember:
    """A single member of an enum."""
    name: str
    value: Expression | None = None  # None = auto-increment
    line: int = 0


@dataclass
class EnumDef:
    """typedef enum [TAG] { ... } NAME;"""
    name: str  # the typedef name
    tag: str  # the name after 'enum' keyword (may be empty for anonymous)
    members: list[EnumMember] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------------------
# Struct
# ---------------------------------------------------------------------------

@dataclass
class StructField:
    """A field in a struct or union."""
    type_spec: TypeSpec
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    array_dimensions: list[ArrayDimension] = field(default_factory=list)
    bitfield_width: int | None = None
    line: int = 0

    @property
    def parsed_annotation(self) -> ParsedAnnotation | None:
        """Parse the SAL annotation (if any) into structured fields."""
        for a in self.attributes:
            if a.name == AttributeName.ANNOTATION and a.value:
                return parse_sal_annotation(a.value)
        return None


@dataclass
class AnonymousUnion:
    """An anonymous union nested inside a struct."""
    members: list["StructMember"] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    name: str | None = None  # member name if any (e.g. `union { ... } u;`)
    line: int = 0


@dataclass
class AnonymousStruct:
    """An anonymous struct nested inside a union."""
    members: list[StructField] = field(default_factory=list)
    name: str | None = None  # member name if any (e.g. `struct { ... } Flags;`)
    line: int = 0


# A struct member can be a field, anonymous union, or anonymous struct
StructMember = Union[StructField, AnonymousUnion, AnonymousStruct]


@dataclass
class StructDef:
    """typedef struct [TAG] { ... } NAME [, *ALIAS ...];"""
    name: str  # primary typedef name
    tag: str  # tag name after 'struct' keyword
    members: list[StructMember] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)  # e.g. ["PLUID"] from `*PLUID`
    attributes: list[Attribute] = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------------------
# Union
# ---------------------------------------------------------------------------

@dataclass
class UnionCase:
    """A case arm in a discriminated union.

    case_values is a list of expressions for [case(v1, v2, ...)].
    is_default is True for [default].
    If the case is empty (e.g. `[default] ;`), member is None.
    """
    case_values: list[Expression] = field(default_factory=list)
    is_default: bool = False
    member: StructField | AnonymousStruct | None = None
    attributes: list[Attribute] = field(default_factory=list)
    line: int = 0


@dataclass
class UnionDef:
    """typedef union [TAG] { ... } NAME;

    For simple unions, `members` contains StructField entries.
    For discriminated unions (with case/default), `cases` is populated.
    """
    name: str
    tag: str
    members: list[StructMember] = field(default_factory=list)
    cases: list[UnionCase] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    # For encapsulated unions: the switch type and discriminant
    switch_type: TypeSpec | None = None
    switch_name: str | None = None
    line: int = 0


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

@dataclass
class TypeAlias:
    """typedef TYPE NAME [, *ALIAS ...];"""
    type_spec: TypeSpec
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------------------
# Function pointer typedef
# ---------------------------------------------------------------------------

@dataclass
class FuncPointerParam:
    """A parameter in a function pointer typedef."""
    type_spec: TypeSpec
    name: str | None = None


@dataclass
class FuncPointerTypedef:
    """typedef RETURN_TYPE (CONV *NAME)(PARAMS);"""
    return_type: TypeSpec
    name: str
    calling_convention: str | None = None
    params: list[FuncPointerParam] = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

@dataclass
class MethodParam:
    """A parameter in an interface method."""
    type_spec: TypeSpec
    name: str | None = None
    attributes: list[Attribute] = field(default_factory=list)
    array_dimensions: list[ArrayDimension] = field(default_factory=list)
    line: int = 0

    @property
    def is_in(self) -> bool:
        return any(a.name == AttributeName.IN for a in self.attributes)

    @property
    def is_out(self) -> bool:
        return any(a.name == AttributeName.OUT for a in self.attributes)

    @property
    def is_retval(self) -> bool:
        return any(a.name == AttributeName.RETVAL for a in self.attributes)

    @property
    def is_optional(self) -> bool:
        return any(
            a.name == AttributeName.OPTIONAL
            or (a.name == AttributeName.ANNOTATION and a.value and "_opt_" in a.value)
            for a in self.attributes
        )

    @property
    def size_is(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.SIZE_IS:
                return a.value
        return None

    @property
    def max_is(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.MAX_IS:
                return a.value
        return None

    @property
    def length_is(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.LENGTH_IS:
                return a.value
        return None

    @property
    def iid_is(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.IID_IS:
                return a.value
        return None

    @property
    def annotation(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.ANNOTATION:
                return a.value
        return None

    @property
    def parsed_annotation(self) -> ParsedAnnotation | None:
        """Parse the SAL annotation (if any) into structured fields."""
        for a in self.attributes:
            if a.name == AttributeName.ANNOTATION and a.value:
                return parse_sal_annotation(a.value)
        return None

    @property
    def is_string(self) -> bool:
        return any(a.name == AttributeName.STRING for a in self.attributes)

    def direction_str(self) -> str:
        parts = []
        if self.is_in:
            parts.append("in")
        if self.is_out:
            parts.append("out")
        if self.is_retval:
            parts.append("retval")
        return ", ".join(parts) if parts else ""


@dataclass
class Method:
    """A method in an interface."""
    return_type: TypeSpec
    name: str
    params: list[MethodParam] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    line: int = 0


# Top-level element that can appear inside an interface body
InterfaceBodyElement = Union["InterfaceTypedef", Method]


@dataclass
class InterfaceTypedef:
    """A typedef that appears inside an interface body."""
    typedef: Union[TypeAlias, EnumDef, StructDef, UnionDef, FuncPointerTypedef]
    line: int = 0


@dataclass
class InterfaceDef:
    """[attrs] interface NAME : PARENT { methods; };"""
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    parent: str | None = None
    methods: list[Method] = field(default_factory=list)
    typedefs: list[InterfaceTypedef] = field(default_factory=list)
    line: int = 0

    @property
    def uuid(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.UUID:
                return a.value
        return None

    @property
    def is_object(self) -> bool:
        return any(a.name == AttributeName.OBJECT for a in self.attributes)

    @property
    def is_local(self) -> bool:
        return any(a.name == AttributeName.LOCAL for a in self.attributes)

    @property
    def pointer_default(self) -> str | None:
        for a in self.attributes:
            if a.name == AttributeName.POINTER_DEFAULT:
                return a.value
        return None


# ---------------------------------------------------------------------------
# Forward declaration
# ---------------------------------------------------------------------------

@dataclass
class ForwardDecl:
    """interface IFoo; (forward declaration)"""
    kind: str  # "interface", "struct", "union", etc.
    name: str
    line: int = 0


# ---------------------------------------------------------------------------
# Library / Coclass / Dispinterface
# ---------------------------------------------------------------------------

@dataclass
class ImportLib:
    """importlib("filename.tlb");"""
    path: str
    line: int = 0


@dataclass
class CoclassInterface:
    """An interface reference inside a coclass."""
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    line: int = 0


@dataclass
class CoclassDef:
    """[attrs] coclass NAME { interfaces };"""
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    interfaces: list[CoclassInterface] = field(default_factory=list)
    line: int = 0


@dataclass
class LibraryDef:
    """[attrs] library NAME { elements };"""
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    elements: list = field(default_factory=list)  # mix of importlib, interface fwd, coclass, typedef, etc.
    line: int = 0


# ---------------------------------------------------------------------------
# Root node
# ---------------------------------------------------------------------------

# All possible top-level elements in a MIDL file
MidlElement = Union[
    ImportStatement, CppQuote, PreprocessorDirective, Constant,
    EnumDef, StructDef, UnionDef, TypeAlias, FuncPointerTypedef,
    InterfaceDef, ForwardDecl, LibraryDef, CoclassDef, ImportLib,
]


@dataclass
class MidlFile:
    """Root AST node representing an entire parsed MIDL file."""
    filename: str
    elements: list[MidlElement] = field(default_factory=list)

    @property
    def imports(self) -> list[ImportStatement]:
        return [e for e in self.elements if isinstance(e, ImportStatement)]

    @property
    def constants(self) -> list[Constant]:
        return [e for e in self.elements if isinstance(e, Constant)]

    @property
    def enums(self) -> list[EnumDef]:
        return [e for e in self.elements if isinstance(e, EnumDef)]

    @property
    def structs(self) -> list[StructDef]:
        return [e for e in self.elements if isinstance(e, StructDef)]

    @property
    def unions(self) -> list[UnionDef]:
        return [e for e in self.elements if isinstance(e, UnionDef)]

    @property
    def interfaces(self) -> list[InterfaceDef]:
        return [e for e in self.elements if isinstance(e, InterfaceDef)]

    @property
    def typedefs(self) -> list[TypeAlias]:
        return [e for e in self.elements if isinstance(e, TypeAlias)]

    @property
    def libraries(self) -> list[LibraryDef]:
        return [e for e in self.elements if isinstance(e, LibraryDef)]

    @property
    def coclasses(self) -> list[CoclassDef]:
        return [e for e in self.elements if isinstance(e, CoclassDef)]

    @property
    def cpp_quotes(self) -> list[CppQuote]:
        return [e for e in self.elements if isinstance(e, CppQuote)]

    @property
    def forward_decls(self) -> list[ForwardDecl]:
        return [e for e in self.elements if isinstance(e, ForwardDecl)]
