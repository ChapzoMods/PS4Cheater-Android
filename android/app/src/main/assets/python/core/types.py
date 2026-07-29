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
# Conversiones string -> bytes
# ---------------------------------------------------------------------------

def string_to_byte(value: str) -> bytes:
    return struct.pack("<B", int(value))

def string_to_2_bytes(value: str) -> bytes:
    return struct.pack("<H", int(value))

def string_to_4_bytes(value: str) -> bytes:
    return struct.pack("<I", int(value))

def string_to_8_bytes(value: str) -> bytes:
    return struct.pack("<Q", int(value))

def string_to_float(value: str) -> bytes:
    return struct.pack("<f", float(value))

def string_to_double(value: str) -> bytes:
    return struct.pack("<d", float(value))

def string_to_string_bytes(value: str) -> bytes:
    return value.encode("latin-1", errors="replace")

def string_to_hex_bytes(hex_str: str) -> bytes:
    """Convierte 'AABBCC' -> b'\xAA\xBB\xCC'."""
    if len(hex_str) % 2 != 0:
        raise ValueError("hex string must have even length")
    return bytes.fromhex(hex_str)

def hex_string_to_byte(value: str) -> bytes:
    return struct.pack("<B", int(value, 16))

def hex_string_to_2_bytes(value: str) -> bytes:
    return struct.pack("<H", int(value, 16))

def hex_string_to_4_bytes(value: str) -> bytes:
    return struct.pack("<I", int(value, 16))

def hex_string_to_8_bytes(value: str) -> bytes:
    return struct.pack("<Q", int(value, 16))

def hex_string_to_float(value: str) -> bytes:
    # C#: BitConverter.GetBytes(float.Parse(value, NumberStyles.HexNumber))
    # En .NET float.Parse(hex) no es válido; el código original aparentemente lo usa
    # como uint -> reinterpreta. Hacemos lo mismo: int hex -> struct pack como uint -> reinterpret float.
    u = int(value, 16)
    return struct.pack("<I", u)

def hex_string_to_double(value: str) -> bytes:
    u = int(value, 16)
    return struct.pack("<Q", u)


# ---------------------------------------------------------------------------
# Conversiones bytes -> string
# ---------------------------------------------------------------------------

def uchar_to_string(value: bytes) -> str:
    return str(value[0])

def uint16_to_string(value: bytes) -> str:
    return str(struct.unpack("<H", value[:2])[0])

def uint_to_string(value: bytes) -> str:
    return str(struct.unpack("<I", value[:4])[0])

def ulong_to_string(value: bytes) -> str:
    return str(struct.unpack("<Q", value[:8])[0])

def float_to_string(value: bytes) -> str:
    return repr(struct.unpack("<f", value[:4])[0])

def double_to_string(value: bytes) -> str:
    return repr(struct.unpack("<d", value[:8])[0])

def string_to_string(value: bytes) -> str:
    # C#: Encoding.Default.GetString(value) — latin-1-ish
    return value.decode("latin-1", errors="replace")

def hex_to_string(value: bytes) -> str:
    return value.hex().upper()

def uchar_to_hex_string(value: bytes) -> str:
    return f"{value[0]:02X}"

def uint16_to_hex_string(value: bytes) -> str:
    return f"{struct.unpack('<H', value[:2])[0]:04X}"

def uint_to_hex_string(value: bytes) -> str:
    return f"{struct.unpack('<I', value[:4])[0]:08X}"

def ulong_to_hex_string(value: bytes) -> str:
    return f"{struct.unpack('<Q', value[:8])[0]:016X}"

def float_to_hex_string(value: bytes) -> str:
    return f"{struct.unpack('<I', value[:4])[0]:08X}"

def double_to_hex_string(value: bytes) -> str:
    return f"{struct.unpack('<Q', value[:8])[0]:016X}"

def string_to_hex_string(value: bytes) -> str:
    return value.hex().upper()


# ---------------------------------------------------------------------------
# Comparadores
# Signature: (default_value_0: bytes, default_value_1: bytes, old_value: Optional[bytes], new_value: bytes) -> bool
# ---------------------------------------------------------------------------

# --- helpers ---
def _u8(b: bytes, off: int = 0) -> int: return b[off]
def _u16(b: bytes, off: int = 0) -> int: return struct.unpack_from("<H", b, off)[0]
def _u32(b: bytes, off: int = 0) -> int: return struct.unpack_from("<I", b, off)[0]
def _u64(b: bytes, off: int = 0) -> int: return struct.unpack_from("<Q", b, off)[0]
def _f32(b: bytes, off: int = 0) -> float: return struct.unpack_from("<f", b, off)[0]
def _f64(b: bytes, off: int = 0) -> float: return struct.unpack_from("<d", b, off)[0]

# --- ANY (UnknownInitialValue) ---
def scan_type_any_uint8(d0, d1, old, new):   return new[0] != 0
def scan_type_any_uint16(d0, d1, old, new):  return _u16(new) != 0
def scan_type_any_uint(d0, d1, old, new):    return _u32(new) != 0
def scan_type_any_ulong(d0, d1, old, new):   return _u64(new) != 0
def scan_type_any_float(d0, d1, old, new):   return _f32(new) != 0
def scan_type_any_double(d0, d1, old, new):  return _f64(new) != 0

# --- EXACT ---
def scan_type_equal_uint8(d0, d1, old, new):  return d0[0] == new[0]
def scan_type_equal_uint16(d0, d1, old, new): return _u16(d0) == _u16(new)
def scan_type_equal_uint(d0, d1, old, new):   return _u32(d0) == _u32(new)
def scan_type_equal_ulong(d0, d1, old, new):  return _u64(d0) == _u64(new)
def scan_type_equal_float(d0, d1, old, new):  return abs(_f32(d0) - _f32(new)) < 0.0001
def scan_type_equal_double(d0, d1, old, new): return abs(_f64(d0) - _f64(new)) < 0.0001
def scan_type_equal_string(d0, d1, old, new):
    if len(d0) != len(new): raise ValueError("length mismatch")
    return d0 == new
def scan_type_equal_hex(d0, d1, old, new):
    if len(d0) != len(new): raise ValueError("length mismatch")
    return d0 == new

# --- NOT (inverso de EXACT) ---
def scan_type_not_uint8(d0, d1, old, new):  return d0[0] != new[0]
def scan_type_not_uint16(d0, d1, old, new): return _u16(d0) != _u16(new)
def scan_type_not_uint(d0, d1, old, new):   return _u32(d0) != _u32(new)
def scan_type_not_ulong(d0, d1, old, new):  return _u64(d0) != _u64(new)
def scan_type_not_float(d0, d1, old, new):  return not scan_type_equal_float(d0, d1, old, new)
def scan_type_not_double(d0, d1, old, new): return not scan_type_equal_double(d0, d1, old, new)

# --- BIGGER_THAN ---
def scan_type_bigger_uint8(d0, d1, old, new):  return new[0] > d0[0]
def scan_type_bigger_uint16(d0, d1, old, new): return _u16(new) > _u16(d0)
def scan_type_bigger_uint(d0, d1, old, new):   return _u32(new) > _u32(d0)
def scan_type_bigger_ulong(d0, d1, old, new):  return _u64(new) > _u64(d0)
def scan_type_bigger_float(d0, d1, old, new):  return _f32(new) > _f32(d0)
def scan_type_bigger_double(d0, d1, old, new): return _f64(new) > _f64(d0)

# --- SMALLER_THAN ---
def scan_type_less_uint8(d0, d1, old, new):  return new[0] < d0[0]
def scan_type_less_uint16(d0, d1, old, new): return _u16(new) < _u16(d0)
def scan_type_less_uint(d0, d1, old, new):   return _u32(new) < _u32(d0)
def scan_type_less_ulong(d0, d1, old, new):  return _u64(new) < _u64(d0)
def scan_type_less_float(d0, d1, old, new):  return _f32(new) < _f32(d0)
def scan_type_less_double(d0, d1, old, new): return _f64(new) < _f64(d0)

# --- BETWEEN ---
def scan_type_between_uint8(d0, d1, old, new):  return d0[0] <= new[0] <= d1[0]
def scan_type_between_uint16(d0, d1, old, new): return _u16(d0) <= _u16(new) <= _u16(d1)
def scan_type_between_uint(d0, d1, old, new):   return _u32(d0) <= _u32(new) <= _u32(d1)
def scan_type_between_ulong(d0, d1, old, new):  return _u64(d0) <= _u64(new) <= _u64(d1)
def scan_type_between_float(d0, d1, old, new):  return _f32(d0) <= _f32(new) <= _f32(d1)
def scan_type_between_double(d0, d1, old, new): return _f64(d0) <= _f64(new) <= _f64(d1)

# --- CHANGED ---
def scan_type_changed_uint8(d0, d1, old, new):  return old[0] != new[0]
def scan_type_changed_uint16(d0, d1, old, new): return _u16(old) != _u16(new)
def scan_type_changed_uint(d0, d1, old, new):   return _u32(old) != _u32(new)
def scan_type_changed_ulong(d0, d1, old, new):  return _u64(old) != _u64(new)
def scan_type_changed_float(d0, d1, old, new):  return not scan_type_unchanged_float(d0, d1, old, new)
def scan_type_changed_double(d0, d1, old, new): return not scan_type_unchanged_double(d0, d1, old, new)

# --- UNCHANGED ---
def scan_type_unchanged_uint8(d0, d1, old, new):  return old[0] == new[0]
def scan_type_unchanged_uint16(d0, d1, old, new): return _u16(old) == _u16(new)
def scan_type_unchanged_uint(d0, d1, old, new):   return _u32(old) == _u32(new)
def scan_type_unchanged_ulong(d0, d1, old, new):  return _u64(old) == _u64(new)
def scan_type_unchanged_float(d0, d1, old, new):  return abs(_f32(old) - _f32(new)) < 0.0001
def scan_type_unchanged_double(d0, d1, old, new): return abs(_f64(old) - _f64(new)) < 0.0001

# --- INCREASED ---
def scan_type_increased_uint8(d0, d1, old, new):  return new[0] > old[0]
def scan_type_increased_uint16(d0, d1, old, new): return _u16(new) > _u16(old)
def scan_type_increased_uint(d0, d1, old, new):   return _u32(new) > _u32(old)
def scan_type_increased_ulong(d0, d1, old, new):  return _u64(new) > _u64(old)
def scan_type_increased_float(d0, d1, old, new):  return _f32(new) > _f32(old)
def scan_type_increased_double(d0, d1, old, new): return _f64(new) > _f64(old)

# --- INCREASED_BY ---
def scan_type_increased_by_uint8(d0, d1, old, new):  return new[0] == old[0] + d0[0]
def scan_type_increased_by_uint16(d0, d1, old, new): return _u16(new) == _u16(old) + _u16(d0)
def scan_type_increased_by_uint(d0, d1, old, new):   return _u32(new) == (_u32(old) + _u32(d0)) & 0xFFFFFFFF
def scan_type_increased_by_ulong(d0, d1, old, new):  return _u64(new) == (_u64(old) + _u64(d0)) & 0xFFFFFFFFFFFFFFFF
def scan_type_increased_by_float(d0, d1, old, new):  return abs(_f32(new) - (_f32(d0) + _f32(old))) < 0.0001
def scan_type_increased_by_double(d0, d1, old, new): return abs(_f64(new) - (_f64(d0) + _f64(old))) < 0.0001

# --- DECREASED ---
def scan_type_decreased_uint8(d0, d1, old, new):  return new[0] < old[0]
def scan_type_decreased_uint16(d0, d1, old, new): return _u16(new) < _u16(old)
def scan_type_decreased_uint(d0, d1, old, new):   return _u32(new) < _u32(old)
def scan_type_decreased_ulong(d0, d1, old, new):  return _u64(new) < _u64(old)
def scan_type_decreased_float(d0, d1, old, new):  return _f32(new) < _f32(old)
def scan_type_decreased_double(d0, d1, old, new): return _f64(new) < _f64(old)

# --- DECREASED_BY ---
def scan_type_decreased_by_uint8(d0, d1, old, new):  return new[0] == old[0] - d0[0]
def scan_type_decreased_by_uint16(d0, d1, old, new): return _u16(new) == (_u16(old) - _u16(d0)) & 0xFFFF
def scan_type_decreased_by_uint(d0, d1, old, new):   return _u32(new) == (_u32(old) - _u32(d0)) & 0xFFFFFFFF
def scan_type_decreased_by_ulong(d0, d1, old, new):  return _u64(new) == (_u64(old) - _u64(d0)) & 0xFFFFFFFFFFFFFFFF
def scan_type_decreased_by_float(d0, d1, old, new):  return abs(_f32(new) - (_f32(old) - _f32(d0))) < 0.0001
def scan_type_decreased_by_double(d0, d1, old, new): return abs(_f64(new) - (_f64(old) - _f64(d0))) < 0.0001

# --- FUZZY_EQUAL (solo float/double, tolerancia 1.0) ---
def scan_type_fuzzy_equal_float(d0, d1, old, new):  return abs(_f32(d0) - _f32(new)) < 1
def scan_type_fuzzy_equal_double(d0, d1, old, new): return abs(_f64(d0) - _f64(new)) < 1


# ---------------------------------------------------------------------------
# Tabla de comparadores por (ValueType, CompareType)
# ---------------------------------------------------------------------------

ComparatorFn = Callable[[Optional[bytes], Optional[bytes], Optional[bytes], bytes], bool]

_COMPARATORS: dict[tuple[ValueType, CompareType], ComparatorFn] = {
    # ANY
    (ValueType.BYTE_TYPE,   CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_uint8,
    (ValueType.USHORT_TYPE, CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_uint16,
    (ValueType.UINT_TYPE,   CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_uint,
    (ValueType.ULONG_TYPE,  CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_float,
    (ValueType.DOUBLE_TYPE, CompareType.UNKNOWN_INITIAL_VALUE): scan_type_any_double,

    # EXACT
    (ValueType.BYTE_TYPE,   CompareType.EXACT_VALUE): scan_type_equal_uint8,
    (ValueType.USHORT_TYPE, CompareType.EXACT_VALUE): scan_type_equal_uint16,
    (ValueType.UINT_TYPE,   CompareType.EXACT_VALUE): scan_type_equal_uint,
    (ValueType.ULONG_TYPE,  CompareType.EXACT_VALUE): scan_type_equal_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.EXACT_VALUE): scan_type_equal_float,
    (ValueType.DOUBLE_TYPE, CompareType.EXACT_VALUE): scan_type_equal_double,
    (ValueType.STRING_TYPE, CompareType.EXACT_VALUE): scan_type_equal_string,
    (ValueType.HEX_TYPE,    CompareType.EXACT_VALUE): scan_type_equal_hex,

    # NOT (invertido)
    (ValueType.BYTE_TYPE,   CompareType.NONE): scan_type_not_uint8,  # NONE == NOT en este contexto
    (ValueType.USHORT_TYPE, CompareType.NONE): scan_type_not_uint16,
    (ValueType.UINT_TYPE,   CompareType.NONE): scan_type_not_uint,
    (ValueType.ULONG_TYPE,  CompareType.NONE): scan_type_not_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.NONE): scan_type_not_float,
    (ValueType.DOUBLE_TYPE, CompareType.NONE): scan_type_not_double,

    # BIGGER
    (ValueType.BYTE_TYPE,   CompareType.BIGGER_THAN_VALUE): scan_type_bigger_uint8,
    (ValueType.USHORT_TYPE, CompareType.BIGGER_THAN_VALUE): scan_type_bigger_uint16,
    (ValueType.UINT_TYPE,   CompareType.BIGGER_THAN_VALUE): scan_type_bigger_uint,
    (ValueType.ULONG_TYPE,  CompareType.BIGGER_THAN_VALUE): scan_type_bigger_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.BIGGER_THAN_VALUE): scan_type_bigger_float,
    (ValueType.DOUBLE_TYPE, CompareType.BIGGER_THAN_VALUE): scan_type_bigger_double,

    # SMALLER
    (ValueType.BYTE_TYPE,   CompareType.SMALLER_THAN_VALUE): scan_type_less_uint8,
    (ValueType.USHORT_TYPE, CompareType.SMALLER_THAN_VALUE): scan_type_less_uint16,
    (ValueType.UINT_TYPE,   CompareType.SMALLER_THAN_VALUE): scan_type_less_uint,
    (ValueType.ULONG_TYPE,  CompareType.SMALLER_THAN_VALUE): scan_type_less_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.SMALLER_THAN_VALUE): scan_type_less_float,
    (ValueType.DOUBLE_TYPE, CompareType.SMALLER_THAN_VALUE): scan_type_less_double,

    # BETWEEN
    (ValueType.BYTE_TYPE,   CompareType.BETWEEN_VALUE): scan_type_between_uint8,
    (ValueType.USHORT_TYPE, CompareType.BETWEEN_VALUE): scan_type_between_uint16,
    (ValueType.UINT_TYPE,   CompareType.BETWEEN_VALUE): scan_type_between_uint,
    (ValueType.ULONG_TYPE,  CompareType.BETWEEN_VALUE): scan_type_between_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.BETWEEN_VALUE): scan_type_between_float,
    (ValueType.DOUBLE_TYPE, CompareType.BETWEEN_VALUE): scan_type_between_double,

    # CHANGED
    (ValueType.BYTE_TYPE,   CompareType.CHANGED_VALUE): scan_type_changed_uint8,
    (ValueType.USHORT_TYPE, CompareType.CHANGED_VALUE): scan_type_changed_uint16,
    (ValueType.UINT_TYPE,   CompareType.CHANGED_VALUE): scan_type_changed_uint,
    (ValueType.ULONG_TYPE,  CompareType.CHANGED_VALUE): scan_type_changed_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.CHANGED_VALUE): scan_type_changed_float,
    (ValueType.DOUBLE_TYPE, CompareType.CHANGED_VALUE): scan_type_changed_double,

    # UNCHANGED
    (ValueType.BYTE_TYPE,   CompareType.UNCHANGED_VALUE): scan_type_unchanged_uint8,
    (ValueType.USHORT_TYPE, CompareType.UNCHANGED_VALUE): scan_type_unchanged_uint16,
    (ValueType.UINT_TYPE,   CompareType.UNCHANGED_VALUE): scan_type_unchanged_uint,
    (ValueType.ULONG_TYPE,  CompareType.UNCHANGED_VALUE): scan_type_unchanged_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.UNCHANGED_VALUE): scan_type_unchanged_float,
    (ValueType.DOUBLE_TYPE, CompareType.UNCHANGED_VALUE): scan_type_unchanged_double,

    # INCREASED
    (ValueType.BYTE_TYPE,   CompareType.INCREASED_VALUE): scan_type_increased_uint8,
    (ValueType.USHORT_TYPE, CompareType.INCREASED_VALUE): scan_type_increased_uint16,
    (ValueType.UINT_TYPE,   CompareType.INCREASED_VALUE): scan_type_increased_uint,
    (ValueType.ULONG_TYPE,  CompareType.INCREASED_VALUE): scan_type_increased_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.INCREASED_VALUE): scan_type_increased_float,
    (ValueType.DOUBLE_TYPE, CompareType.INCREASED_VALUE): scan_type_increased_double,

    # INCREASED_BY
    (ValueType.BYTE_TYPE,   CompareType.INCREASED_VALUE_BY): scan_type_increased_by_uint8,
    (ValueType.USHORT_TYPE, CompareType.INCREASED_VALUE_BY): scan_type_increased_by_uint16,
    (ValueType.UINT_TYPE,   CompareType.INCREASED_VALUE_BY): scan_type_increased_by_uint,
    (ValueType.ULONG_TYPE,  CompareType.INCREASED_VALUE_BY): scan_type_increased_by_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.INCREASED_VALUE_BY): scan_type_increased_by_float,
    (ValueType.DOUBLE_TYPE, CompareType.INCREASED_VALUE_BY): scan_type_increased_by_double,

    # DECREASED
    (ValueType.BYTE_TYPE,   CompareType.DECREASED_VALUE): scan_type_decreased_uint8,
    (ValueType.USHORT_TYPE, CompareType.DECREASED_VALUE): scan_type_decreased_uint16,
    (ValueType.UINT_TYPE,   CompareType.DECREASED_VALUE): scan_type_decreased_uint,
    (ValueType.ULONG_TYPE,  CompareType.DECREASED_VALUE): scan_type_decreased_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.DECREASED_VALUE): scan_type_decreased_float,
    (ValueType.DOUBLE_TYPE, CompareType.DECREASED_VALUE): scan_type_decreased_double,

    # DECREASED_BY
    (ValueType.BYTE_TYPE,   CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_uint8,
    (ValueType.USHORT_TYPE, CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_uint16,
    (ValueType.UINT_TYPE,   CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_uint,
    (ValueType.ULONG_TYPE,  CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_ulong,
    (ValueType.FLOAT_TYPE,  CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_float,
    (ValueType.DOUBLE_TYPE, CompareType.DECREASED_VALUE_BY): scan_type_decreased_by_double,

    # FUZZY (solo float/double)
    (ValueType.FLOAT_TYPE,  CompareType.FUZZY_VALUE): scan_type_fuzzy_equal_float,
    (ValueType.DOUBLE_TYPE, CompareType.FUZZY_VALUE): scan_type_fuzzy_equal_double,

    # POINTER (cualquier ulong no-cero — reusamos between_ulong)
    (ValueType.ULONG_TYPE, CompareType.POINTER_VALUE): scan_type_any_ulong,
}


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


def make_handler(value_type: ValueType, compare_type: CompareType,
                 is_aligned: bool = True, type_length: int = 0) -> MemoryTypeHandler:
    """
    Crea un MemoryTypeHandler configurado para el par (value_type, compare_type).
    Replica InitMemoryHandler() de MemoryHelper.cs.
    """
    # Defaults
    length = 0
    alignment = 1
    s2b = None
    b2s = None
    h2b = None
    b2h = None

    if value_type == ValueType.BYTE_TYPE:
        length = 1
        alignment = 1
        s2b = string_to_byte;  b2s = uchar_to_string
        h2b = hex_string_to_byte; b2h = uchar_to_hex_string
    elif value_type == ValueType.USHORT_TYPE:
        length = 2
        alignment = 2 if is_aligned else 1
        s2b = string_to_2_bytes; b2s = uint16_to_string
        h2b = hex_string_to_2_bytes; b2h = uint16_to_hex_string
    elif value_type == ValueType.UINT_TYPE:
        length = 4
        alignment = 4 if is_aligned else 1
        s2b = string_to_4_bytes; b2s = uint_to_string
        h2b = hex_string_to_4_bytes; b2h = uint_to_hex_string
    elif value_type == ValueType.ULONG_TYPE:
        length = 8
        alignment = 4 if is_aligned else 1
        s2b = string_to_8_bytes; b2s = ulong_to_string
        h2b = hex_string_to_8_bytes; b2h = ulong_to_hex_string
    elif value_type == ValueType.FLOAT_TYPE:
        length = 4
        alignment = 4 if is_aligned else 1
        s2b = string_to_float; b2s = float_to_string
        h2b = hex_string_to_float; b2h = float_to_hex_string
    elif value_type == ValueType.DOUBLE_TYPE:
        length = 8
        alignment = 4 if is_aligned else 1
        s2b = string_to_double; b2s = double_to_string
        h2b = hex_string_to_double; b2h = double_to_hex_string
    elif value_type == ValueType.HEX_TYPE:
        length = max(0, type_length // 2)
        alignment = 1
        s2b = string_to_hex_bytes; b2s = hex_to_string
        h2b = None; b2h = hex_to_string
    elif value_type == ValueType.STRING_TYPE:
        length = type_length
        alignment = 1
        s2b = string_to_string_bytes; b2s = string_to_string
        h2b = None; b2h = string_to_hex_string
    elif value_type == ValueType.POINTER_TYPE:
        length = 8
        alignment = 4 if is_aligned else 1
        s2b = string_to_8_bytes; b2s = ulong_to_string
        h2b = hex_string_to_8_bytes; b2h = ulong_to_hex_string
    else:
        raise ValueError(f"unsupported value_type: {value_type}")

    # Comparator lookup
    try:
        comparer = _COMPARATORS[(value_type, compare_type)]
    except KeyError:
        raise ValueError(f"unsupported (value_type={value_type.name}, compare_type={compare_type.name})")

    # Parse flags (copia de InitMemoryHandler switch compareType)
    if compare_type == CompareType.UNKNOWN_INITIAL_VALUE:
        parse_first, parse_second = False, False
    elif compare_type == CompareType.FUZZY_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.EXACT_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.CHANGED_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.UNCHANGED_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.INCREASED_VALUE:
        parse_first, parse_second = False, False
    elif compare_type == CompareType.INCREASED_VALUE_BY:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.DECREASED_VALUE:
        parse_first, parse_second = False, False
    elif compare_type == CompareType.DECREASED_VALUE_BY:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.BIGGER_THAN_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.SMALLER_THAN_VALUE:
        parse_first, parse_second = True, False
    elif compare_type == CompareType.BETWEEN_VALUE:
        parse_first, parse_second = True, True
    elif compare_type == CompareType.POINTER_VALUE:
        parse_first, parse_second = False, False
    else:
        parse_first, parse_second = True, False

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
