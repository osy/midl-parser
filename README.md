# MIDL Parser

A complete Python parser for Microsoft Interface Definition Language (MIDL/IDL) files. Parses IDL files into rich, structured Python objects suitable for code generation, analysis, and documentation.

## Installation

No external dependencies required. Python 3.10+ (uses `X | Y` union syntax).

```bash
# Just copy or symlink midl_parser/ into your project, or:
pip install -e .
```

## Quick Start

```python
from midl_parser import parse_file, parse_string

# Parse an IDL file
midl = parse_file("path/to/file.idl")

# Or parse from a string
midl = parse_string('''
    typedef enum Color { RED = 0, GREEN = 1, BLUE = 2 } COLOR;
''')

# Access parsed elements by type
for iface in midl.interfaces:
    print(f"Interface: {iface.name} (UUID: {iface.uuid})")
    for method in iface.methods:
        print(f"  {method.return_type.format()} {method.name}()")
        for param in method.params:
            print(f"    [{param.direction_str()}] {param.type_spec.format()} {param.name}")

for enum in midl.enums:
    print(f"Enum: {enum.name} ({len(enum.members)} values)")

for struct in midl.structs:
    print(f"Struct: {struct.name} ({len(struct.members)} fields)")
```

## API Reference

### Top-Level Functions

#### `parse_file(path: str) -> MidlFile`
Parse an IDL file from disk. Handles UTF-8 with BOM.

#### `parse_string(source: str, filename: str = "<string>") -> MidlFile`
Parse MIDL source text from a string.

### MidlFile

The root node returned by both parse functions. Contains all parsed elements.

| Property | Type | Description |
|----------|------|-------------|
| `filename` | `str` | Source filename |
| `elements` | `list[MidlElement]` | All parsed elements in order |
| `imports` | `list[ImportStatement]` | `import` statements |
| `constants` | `list[Constant]` | `const` declarations |
| `enums` | `list[EnumDef]` | Enum definitions |
| `structs` | `list[StructDef]` | Struct definitions |
| `unions` | `list[UnionDef]` | Union definitions |
| `interfaces` | `list[InterfaceDef]` | Interface definitions |
| `typedefs` | `list[TypeAlias]` | Simple type aliases |
| `libraries` | `list[LibraryDef]` | Type library definitions |
| `coclasses` | `list[CoclassDef]` | Coclass definitions |
| `forward_decls` | `list[ForwardDecl]` | Forward declarations |
| `cpp_quotes` | `list[CppQuote]` | `cpp_quote()` directives |

### TypeSpec — Structured Type Representation

Types are **not stored as strings**. Each type is a `TypeSpec` with:

```python
@dataclass
class TypeSpec:
    base_name: str              # "UINT", "void", "ID3D11Device"
    is_const: bool              # leading 'const'
    is_signed: bool | None      # 'signed' modifier
    is_unsigned: bool           # 'unsigned' modifier
    is_volatile: bool           # 'volatile' modifier
    pointer_levels: list[PointerLevel]  # each * indirection
    calling_convention: str | None      # __stdcall, __cdecl, etc.
```

Each `PointerLevel` tracks whether it's a const pointer (`*const`):

```python
# const void*         -> is_const=True, base="void", ptrs=[PL(False)]
# IUnknown*const*     -> base="IUnknown", ptrs=[PL(is_const=True), PL(False)]
# unsigned long       -> is_unsigned=True, base="long"
```

Use `ts.format()` to get a readable string, or inspect fields directly:
```python
if param.type_spec.is_pointer:
    print(f"Pointer depth: {param.type_spec.pointer_depth}")
```

### Attributes

MIDL attributes (`[in]`, `[out]`, `[uuid(...)]`, etc.) are parsed into `Attribute` objects:

```python
@dataclass
class Attribute:
    name: AttributeName   # Enum value (IN, OUT, UUID, SIZE_IS, ...)
    raw_name: str         # Original text
    value: str | None     # Parenthesized content if any
```

Over 100 well-known attributes are recognized via the `AttributeName` enum. Unknown attributes get `AttributeName.CUSTOM`.

### Expressions

Enum values, constants, and array sizes are parsed into expression trees:

```python
IntegerLiteral(value=255, base=16, suffix="", raw="0xff")
IdentifierRef(name="D3D_PRIMITIVE_TOPOLOGY_UNDEFINED")
BinaryOp(op="|", left=IdentifierRef("A"), right=IdentifierRef("B"))
UnaryOp(op="-", operand=IntegerLiteral(value=10))
```

### Method Parameters — Rich Annotations

`MethodParam` provides convenience properties:

```python
param.is_in          # True if [in]
param.is_out         # True if [out]
param.is_retval      # True if [retval]
param.is_optional    # True if [optional] or annotation contains "_opt_"
param.is_string      # True if [string]
param.size_is        # "count" from [size_is(count)]
param.max_is         # value from [max_is(...)]
param.length_is      # value from [length_is(...)]
param.iid_is         # "riid" from [iid_is(riid)]
param.annotation     # SAL annotation string
param.direction_str() # "in", "out", "in, out", "out, retval", etc.
```

### Struct Members

Struct fields support:
- **Attributes**: `[annotation("_Field_size_(n)")]`
- **Array dimensions**: `WCHAR Name[128]`, `FLOAT Transform[3][4]`
- **Bitfields**: `UINT Flags : 8`
- **Anonymous unions/structs**: Nested unnamed aggregates

```python
for member in struct_def.members:
    if isinstance(member, StructField):
        print(f"{member.type_spec.format()} {member.name}")
        if member.bitfield_width:
            print(f"  bitfield: {member.bitfield_width} bits")
        for dim in member.array_dimensions:
            print(f"  array dim: {dim.size}")
    elif isinstance(member, AnonymousUnion):
        print("  anonymous union { ... }")
    elif isinstance(member, AnonymousStruct):
        print("  anonymous struct { ... }")
```

### Enum Members

```python
for member in enum_def.members:
    if member.value is None:
        print(f"{member.name} (auto)")
    elif isinstance(member.value, IntegerLiteral):
        print(f"{member.name} = {member.value.value}")
    elif isinstance(member.value, IdentifierRef):
        print(f"{member.name} = {member.value.name}")
    elif isinstance(member.value, BinaryOp):
        print(f"{member.name} = (expression)")
```

### Discriminated Unions

Discriminated unions with `[case()]` / `[default]` arms:

```python
for union_def in midl.unions:
    for case in union_def.cases:
        if case.is_default:
            print("default:")
        else:
            values = [str(v.value) for v in case.case_values
                      if isinstance(v, IntegerLiteral)]
            print(f"case({', '.join(values)}):")
        if case.member:
            print(f"  {case.member.type_spec.format()} {case.member.name}")
```

## Supported Constructs

| Construct | Example |
|-----------|---------|
| Import | `import "oaidl.idl";` |
| cpp_quote | `cpp_quote("#include <windows.h>")` |
| Preprocessor | `#define`, `#pragma`, `#ifdef`/`#endif` |
| Constants | `const UINT VAL = 0xff;` with hex/decimal/suffixed integers |
| Enums | `typedef enum { A=0, B=1 } E;` with expressions, cross-refs |
| Structs | Nested unions, bitfields, arrays, multi-dim, annotations |
| Unions | Simple and discriminated (`[case]`/`[default]`) |
| Typedefs | Simple aliases, attributed, pipe types |
| Function pointers | `typedef void(__stdcall *PFN)(void*);` |
| Interfaces | With inheritance, UUID, methods, inline typedefs |
| Methods | With `[in]`/`[out]`/`[retval]`, `[size_is]`, `[annotation]` |
| Forward decls | `interface IFoo;` |
| Libraries | `library Name { importlib; coclass; }` |
| Coclasses | `coclass Name { [default] interface IFoo; }` |
| Property methods | `[propget]`, `[propput]` |
| RPC attributes | `[idempotent]`, `[maybe]`, `[broadcast]`, `[callback]` |
| Context handles | `[context_handle]` |

## CLI Tool

The included `midl_dump.py` prints all elements with rich annotations:

```bash
# Dump everything
python midl_dump.py examples/dxgi.idl

# Filter by type
python midl_dump.py examples/d3d11.idl --filter interfaces

# Verbose mode (enum values, struct fields, etc.)
python midl_dump.py examples/d3d12.idl --filter enums --verbose

# Available filters: all, imports, constants, enums, structs, unions,
#   typedefs, interfaces, forward_decls, libraries, coclasses, cpp_quotes
```

Sample output:
```
=== examples/dxgi.idl ===
Total elements: 106

--- Interfaces (14) ---
  interface IDXGIObject : IUnknown
    uuid: aec22fb8-76f3-4639-9be0-28eb43a67a2e  [object, local, pointer_default(unique)]
    methods: 4
      HRESULT SetPrivateData(3 params)
        [in] REFGUID Name  {annotation("_In_")}
        [in] UINT DataSize
        [in] const void* pData  {annotation("_In_reads_bytes_(DataSize)")}
      HRESULT GetParent(2 params)
        [in] REFIID riid  {annotation("_In_")}
        [out, retval] void** ppParent  {annotation("_COM_Outptr_")}
```

## Tested On

Successfully parses all DirectX IDL headers:
- `d3d11.idl` (5,480 lines, 41 interfaces, 133 structs, 72 enums)
- `d3d12.idl` (6,528 lines, 73 interfaces, 266 structs, 156 enums)
- `dxgi.idl` through `dxgi1_6.idl`
- `d3dcommon.idl`, `d3d11_1.idl` through `d3d11_4.idl`
- COM type library examples with `library`/`coclass`
- RPC examples with discriminated unions, pipes, context handles
