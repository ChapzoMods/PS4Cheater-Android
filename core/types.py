"""
core/types.py — Tipos de valor, comparadores y conversiones.

Port directo de MemoryHelper.cs:
  - Enums ValueType y CompareType (idénticos al C#)
  - Conversiones string<->bytes para cada tipo (string_to_bytes, bytes_to_string, etc.)
  - 80+ funciones comparadoras (scan_type_equal_uint32, scan_type_changed_float, …)
  - Clase MemoryTypeHandler que encapsula length/alignment/comparer para un par (ValueType, CompareType)
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ValueType(IntEnum):
    BYTE_TYPE    = 0   # uint8
    USHORT_TYPE  = 1   # uint16
    UINT_TYPE    = 2   # uint32
    ULONG_TYPE   = 3   # uint64
    FLOAT_TYPE   = 4
    DOUBLE_TYPE  = 5
    STRING_TYPE  = 6
    HEX_TYPE     = 7
    POINTER_TYPE = 8
    NONE_TYPE    = 9


class CompareType(IntEnum):
    EXACT_VALUE            = 0
    FUZZY_VALUE            = 1
    INCREASED_VALUE        = 2
    INCREASED_VALUE_BY     = 3
    DECREASED_VALUE        = 4
    DECREASED_VALUE_BY     = 5
    BIGGER_THAN_VALUE      = 6
    SMALLER_THAN_VALUE     = 7
    CHANGED_VALUE          = 8
    UNCHANGED_VALUE        = 9
    BETWEEN_VALUE          = 10
    UNKNOWN_INITIAL_VALUE  = 11
    POINTER_VALUE          = 12
    NONE                   = 13


# ---------------------------------------------------------------------------
# Mapeos string <-> enum (de Util.cs CONSTANT)
# ---------------------------------------------------------------------------

VALUE_TYPE_TO_STR = {
    ValueType.BYTE_TYPE:    "1 byte",
    ValueType.USHORT_TYPE:  "2 bytes",
    ValueType.UINT_TYPE:    "4 bytes",
    ValueType.ULONG_TYPE:   "8 bytes",
    ValueType.FLOAT_TYPE:   "float",
    ValueType.DOUBLE_TYPE:  "double",
    ValueType.STRING_TYPE:  "string",
    ValueType.HEX_TYPE:     "hex",
    ValueType.POINTER_TYPE: "pointer",
}

STR_TO_VALUE_TYPE = {
    "byte":      ValueType.BYTE_TYPE,
    "1 byte":    ValueType.BYTE_TYPE,
    "1 bytes":   ValueType.BYTE_TYPE,
    "2 bytes":   ValueType.USHORT_TYPE,
    "2 byte":    ValueType.USHORT_TYPE,
    "4 bytes":   ValueType.UINT_TYPE,
    "4 byte":    ValueType.UINT_TYPE,
    "8 bytes":   ValueType.ULONG_TYPE,
    "8 byte":    ValueType.ULONG_TYPE,
    "float":     ValueType.FLOAT_TYPE,
    "double":    ValueType.DOUBLE_TYPE,
    "string":    ValueType.STRING_TYPE,
    "hex":       ValueType.HEX_TYPE,
    "pointer":   ValueType.POINTER_TYPE,
}

COMPARE_TYPE_TO_STR = {
    CompareType.EXACT_VALUE:           "Exact Value",
    CompareType.FUZZY_VALUE:           "Fuzzy Value",
    CompareType.INCREASED_VALUE:       "Increased Value",
    CompareType.INCREASED_VALUE_BY:    "Increased Value By",
    CompareType.DECREASED_VALUE:       "Decreased Value",
    CompareType.DECREASED_VALUE_BY:    "Decreased Value By",
    CompareType.BIGGER_THAN_VALUE:     "Bigger Than",
    CompareType.SMALLER_THAN_VALUE:    "Smaller Than",
    CompareType.CHANGED_VALUE:         "Changed Value",
    CompareType.UNCHANGED_VALUE:       "Unchanged Value",
    CompareType.BETWEEN_VALUE:         "Between Value",
    CompareType.UNKNOWN_INITIAL_VALUE: "Unknown Initial Value",
    CompareType.POINTER_VALUE:         "Pointer Value",
}

STR_TO_COMPARE_TYPE = {
    "exact":            CompareType.EXACT_VALUE,
    "exact value":      CompareType.EXACT_VALUE,
    "fuzzy":            CompareType.FUZZY_VALUE,
    "fuzzy value":      CompareType.FUZZY_VALUE,
    "increased":        CompareType.INCREASED_VALUE,
    "increased value":  CompareType.INCREASED_VALUE,
    "increased by":     CompareType.INCREASED_VALUE_BY,
    "increased value by": CompareType.INCREASED_VALUE_BY,
    "decreased":        CompareType.DECREASED_VALUE,
    "decreased value":  CompareType.DECREASED_VALUE,
    "decreased by":     CompareType.DECREASED_VALUE_BY,
    "decreased value by": CompareType.DECREASED_VALUE_BY,
    "bigger":           CompareType.BIGGER_THAN_VALUE,
    "bigger than":      CompareType.BIGGER_THAN_VALUE,
    "smaller":          CompareType.SMALLER_THAN_VALUE,
    "smaller than":     CompareType.SMALLER_THAN_VALUE,
    "changed":          CompareType.CHANGED_VALUE,
    "changed value":    CompareType.CHANGED_VALUE,
    "unchanged":        CompareType.UNCHANGED_VALUE,
    "unchanged value":  CompareType.UNCHANGED_VALUE,
    "between":          CompareType.BETWEEN_VALUE,
    "between value":    CompareType.BETWEEN_VALUE,
    "unknown":          CompareType.UNKNOWN_INITIAL_VALUE,
    "unknown initial":  CompareType.UNKNOWN_INITIAL_VALUE,
    "unknown initial value": CompareType.UNKNOWN_INITIAL_VALUE,
    "any":              CompareType.UNKNOWN_INITIAL_VALUE,
    "pointer":          CompareType.POINTER_VALUE,
    "pointer value":    CompareType.POINTER_VALUE,
}


# ---------------------------------------------------------------------------
# Codecs numéricos — un único sitio donde vive el ancho/formato de cada tipo
# ---------------------------------------------------------------------------

EQUAL_TOLERANCE: float = 0.0001   # tolerancia de igualdad en float/double
FUZZY_TOLERANCE: float = 1.0      # tolerancia de FUZZY_VALUE


@dataclass(frozen=True)
class NumericCodec:
    """
    Conversiones string<->bytes de un tipo numérico de ancho fijo.

    `fmt` es el formato struct del valor y `uint_fmt` el del entero sin signo
    del mismo ancho, que es el usado en las representaciones hex (para
    float/double eso reinterpreta los bits, igual que el C# original).
    """
    fmt: str
    uint_fmt: str
    size: int
    parse: Callable[[str], object] = int
    tolerance: float = 0.0        # > 0 solo en tipos de coma flotante

    @property
    def hex_digits(self) -> int:
        return self.size * 2

    @property
    def mask(self) -> int:
        return (1 << (self.size * 8)) - 1

    def pack(self, value: str) -> bytes:
        return struct.pack(self.fmt, self.parse(value))

    def pack_hex(self, value: str) -> bytes:
        return struct.pack(self.uint_fmt, int(value, 16))

    def read(self, data: bytes, offset: int = 0):
        return struct.unpack_from(self.fmt, data, offset)[0]

    def to_string(self, data: bytes) -> str:
        return str(self.read(data))

    def to_hex_string(self, data: bytes) -> str:
        return f"{struct.unpack_from(self.uint_fmt, data)[0]:0{self.hex_digits}X}"


U8 = NumericCodec("<B", "<B", 1)
U16 = NumericCodec("<H", "<H", 2)
U32 = NumericCodec("<I", "<I", 4)
U64 = NumericCodec("<Q", "<Q", 8)
F32 = NumericCodec("<f", "<I", 4, parse=float, tolerance=EQUAL_TOLERANCE)
F64 = NumericCodec("<d", "<Q", 8, parse=float, tolerance=EQUAL_TOLERANCE)


# ---------------------------------------------------------------------------
# Conversiones string <-> bytes (nombres del port de MemoryHelper.cs)
# ---------------------------------------------------------------------------

string_to_byte = U8.pack
string_to_2_bytes = U16.pack
string_to_4_bytes = U32.pack
string_to_8_bytes = U64.pack
string_to_float = F32.pack
string_to_double = F64.pack

hex_string_to_byte = U8.pack_hex
hex_string_to_2_bytes = U16.pack_hex
hex_string_to_4_bytes = U32.pack_hex
hex_string_to_8_bytes = U64.pack_hex
hex_string_to_float = F32.pack_hex
hex_string_to_double = F64.pack_hex

uchar_to_string = U8.to_string
uint16_to_string = U16.to_string
uint_to_string = U32.to_string
ulong_to_string = U64.to_string
float_to_string = F32.to_string
double_to_string = F64.to_string

uchar_to_hex_string = U8.to_hex_string
uint16_to_hex_string = U16.to_hex_string
uint_to_hex_string = U32.to_hex_string
ulong_to_hex_string = U64.to_hex_string
float_to_hex_string = F32.to_hex_string
double_to_hex_string = F64.to_hex_string


def string_to_string_bytes(value: str) -> bytes:
    return value.encode("latin-1", errors="replace")


def string_to_hex_bytes(hex_str: str) -> bytes:
    """Convierte 'AABBCC' -> b'\xAA\xBB\xCC'."""
    if len(hex_str) % 2 != 0:
        raise ValueError("hex string must have even length")
    return bytes.fromhex(hex_str)


def string_to_string(value: bytes) -> str:
    # C#: Encoding.Default.GetString(value) — latin-1-ish
    return value.decode("latin-1", errors="replace")


def hex_to_string(value: bytes) -> str:
    return value.hex().upper()


string_to_hex_string = hex_to_string


# ---------------------------------------------------------------------------
# Comparadores
# Signature: (default_value_0, default_value_1, old_value, new_value) -> bool
#
# Cada familia de comparadores (exact, bigger, changed, …) se genera una única
# vez por codec en vez de escribirse a mano para los 6 tipos numéricos.
# ---------------------------------------------------------------------------

ComparatorFn = Callable[[Optional[bytes], Optional[bytes], Optional[bytes], bytes], bool]


def _make_comparators(codec: NumericCodec) -> dict[CompareType, ComparatorFn]:
    """Construye el mapa CompareType -> comparador para un codec numérico."""
    read = codec.read

    if codec.tolerance:
        def equal(a, b) -> bool:
            return abs(a - b) < codec.tolerance

        def add(a, b):
            return a + b

        def sub(a, b):
            return a - b
    else:
        def equal(a, b) -> bool:
            return a == b

        def add(a, b):
            return (a + b) & codec.mask

        def sub(a, b):
            return (a - b) & codec.mask

    def nonzero(d0, d1, old, new) -> bool:
        return read(new) != 0

    return {
        CompareType.UNKNOWN_INITIAL_VALUE: nonzero,
        CompareType.POINTER_VALUE: nonzero,
        CompareType.EXACT_VALUE: lambda d0, d1, old, new: equal(read(d0), read(new)),
        CompareType.NONE: lambda d0, d1, old, new: not equal(read(d0), read(new)),
        CompareType.BIGGER_THAN_VALUE: lambda d0, d1, old, new: read(new) > read(d0),
        CompareType.SMALLER_THAN_VALUE: lambda d0, d1, old, new: read(new) < read(d0),
        CompareType.BETWEEN_VALUE: lambda d0, d1, old, new: read(d0) <= read(new) <= read(d1),
        CompareType.CHANGED_VALUE: lambda d0, d1, old, new: not equal(read(old), read(new)),
        CompareType.UNCHANGED_VALUE: lambda d0, d1, old, new: equal(read(old), read(new)),
        CompareType.INCREASED_VALUE: lambda d0, d1, old, new: read(new) > read(old),
        CompareType.DECREASED_VALUE: lambda d0, d1, old, new: read(new) < read(old),
        CompareType.INCREASED_VALUE_BY:
            lambda d0, d1, old, new: equal(read(new), add(read(old), read(d0))),
        CompareType.DECREASED_VALUE_BY:
            lambda d0, d1, old, new: equal(read(new), sub(read(old), read(d0))),
        CompareType.FUZZY_VALUE:
            lambda d0, d1, old, new: abs(read(d0) - read(new)) < FUZZY_TOLERANCE,
    }


def _scan_type_equal_bytes(d0, d1, old, new) -> bool:
    """Comparación exacta de string/hex: los buffers deben medir lo mismo."""
    if len(d0) != len(new):
        raise ValueError("length mismatch")
    return d0 == new


# ---------------------------------------------------------------------------
# Tabla de comparadores por (ValueType, CompareType)
# ---------------------------------------------------------------------------

NUMERIC_CODECS: dict[ValueType, NumericCodec] = {
    ValueType.BYTE_TYPE:   U8,
    ValueType.USHORT_TYPE: U16,
    ValueType.UINT_TYPE:   U32,
    ValueType.ULONG_TYPE:  U64,
    ValueType.FLOAT_TYPE:  F32,
    ValueType.DOUBLE_TYPE: F64,
}

_COMPARATORS: dict[tuple[ValueType, CompareType], ComparatorFn] = {
    (value_type, compare_type): comparer
    for value_type, codec in NUMERIC_CODECS.items()
    for compare_type, comparer in _make_comparators(codec).items()
    # FUZZY solo aplica a float/double; POINTER_VALUE solo a uint64
    if (compare_type != CompareType.FUZZY_VALUE or codec.tolerance)
    and (compare_type != CompareType.POINTER_VALUE or value_type == ValueType.ULONG_TYPE)
}

_COMPARATORS[(ValueType.STRING_TYPE, CompareType.EXACT_VALUE)] = _scan_type_equal_bytes
_COMPARATORS[(ValueType.HEX_TYPE, CompareType.EXACT_VALUE)] = _scan_type_equal_bytes


# ---------------------------------------------------------------------------
# MemoryTypeHandler — encapsula el estado de un par (ValueType, CompareType)
# ---------------------------------------------------------------------------

@dataclass
class MemoryTypeHandler:
    """
    Equivalente al estado configurado de MemoryHelper en C#.
    Contiene: value_type, compare_type, length, alignment, comparador,
    conversiones, y flags de parseo.
    """
    value_type: ValueType
    compare_type: CompareType
    length: int                       # tamaño en bytes del valor
    alignment: int                    # stride para iterar
    comparer: ComparatorFn
    string_to_bytes: Callable[[str], bytes]
    bytes_to_string: Callable[[bytes], str]
    hex_string_to_bytes: Optional[Callable[[str], bytes]] = None
    bytes_to_hex_string: Optional[Callable[[bytes], str]] = None
    parse_first_value: bool = True
    parse_second_value: bool = False

    def parse_value(self, s: str, is_hex: bool = False) -> bytes:
        if is_hex and self.hex_string_to_bytes is not None:
            return self.hex_string_to_bytes(s)
        return self.string_to_bytes(s)

    def format_value(self, b: bytes, hex_fmt: bool = False) -> str:
        if hex_fmt and self.bytes_to_hex_string is not None:
            return self.bytes_to_hex_string(b)
        return self.bytes_to_string(b)


# Conversiones y alineación por tipo de valor: (codec, alineación cuando is_aligned)
_NUMERIC_TYPE_SPECS: dict[ValueType, tuple[NumericCodec, int]] = {
    ValueType.BYTE_TYPE:    (U8, 1),
    ValueType.USHORT_TYPE:  (U16, 2),
    ValueType.UINT_TYPE:    (U32, 4),
    ValueType.ULONG_TYPE:   (U64, 4),
    ValueType.FLOAT_TYPE:   (F32, 4),
    ValueType.DOUBLE_TYPE:  (F64, 4),
    ValueType.POINTER_TYPE: (U64, 4),
}

# Flags (parse_first_value, parse_second_value) de InitMemoryHandler; el resto
# de comparaciones solo necesita el primer valor.
_PARSE_FLAGS: dict[CompareType, tuple[bool, bool]] = {
    CompareType.UNKNOWN_INITIAL_VALUE: (False, False),
    CompareType.INCREASED_VALUE:       (False, False),
    CompareType.DECREASED_VALUE:       (False, False),
    CompareType.POINTER_VALUE:         (False, False),
    CompareType.BETWEEN_VALUE:         (True, True),
}


def make_handler(value_type: ValueType, compare_type: CompareType,
                 is_aligned: bool = True, type_length: int = 0) -> MemoryTypeHandler:
    """
    Crea un MemoryTypeHandler configurado para el par (value_type, compare_type).
    Replica InitMemoryHandler() de MemoryHelper.cs.
    """
    if value_type in _NUMERIC_TYPE_SPECS:
        codec, aligned_alignment = _NUMERIC_TYPE_SPECS[value_type]
        length = codec.size
        alignment = aligned_alignment if is_aligned else 1
        s2b, b2s = codec.pack, codec.to_string
        h2b, b2h = codec.pack_hex, codec.to_hex_string
    elif value_type == ValueType.HEX_TYPE:
        length = max(0, type_length // 2)
        alignment = 1
        s2b, b2s = string_to_hex_bytes, hex_to_string
        h2b, b2h = None, hex_to_string
    elif value_type == ValueType.STRING_TYPE:
        length = type_length
        alignment = 1
        s2b, b2s = string_to_string_bytes, string_to_string
        h2b, b2h = None, string_to_hex_string
    else:
        raise ValueError(f"unsupported value_type: {value_type}")

    try:
        comparer = _COMPARATORS[(value_type, compare_type)]
    except KeyError:
        raise ValueError(f"unsupported (value_type={value_type.name}, compare_type={compare_type.name})")

    parse_first, parse_second = _PARSE_FLAGS.get(compare_type, (True, False))

    return MemoryTypeHandler(
        value_type=value_type,
        compare_type=compare_type,
        length=length,
        alignment=alignment,
        comparer=comparer,
        string_to_bytes=s2b,
        bytes_to_string=b2s,
        hex_string_to_bytes=h2b,
        bytes_to_hex_string=b2h,
        parse_first_value=parse_first,
        parse_second_value=parse_second,
    )


def lookup_value_type(s: str) -> ValueType:
    """Lookup tolerante: acepta 'uint32', '4 bytes', '4bytes', etc."""
    s_norm = s.strip().lower()
    if s_norm in STR_TO_VALUE_TYPE:
        return STR_TO_VALUE_TYPE[s_norm]
    # Alias comunes
    aliases = {
        "uint8":   ValueType.BYTE_TYPE,
        "uint16":  ValueType.USHORT_TYPE,
        "uint32":  ValueType.UINT_TYPE,
        "uint64":  ValueType.ULONG_TYPE,
        "u8":      ValueType.BYTE_TYPE,
        "u16":     ValueType.USHORT_TYPE,
        "u32":     ValueType.UINT_TYPE,
        "u64":     ValueType.ULONG_TYPE,
        "int8":    ValueType.BYTE_TYPE,
        "int16":   ValueType.USHORT_TYPE,
        "int32":   ValueType.UINT_TYPE,
        "int64":   ValueType.ULONG_TYPE,
    }
    if s_norm in aliases:
        return aliases[s_norm]
    raise ValueError(f"unknown value type: {s!r}")


def lookup_compare_type(s: str) -> CompareType:
    """Lookup tolerante."""
    s_norm = s.strip().lower()
    if s_norm in STR_TO_COMPARE_TYPE:
        return STR_TO_COMPARE_TYPE[s_norm]
    raise ValueError(f"unknown compare type: {s!r}")
