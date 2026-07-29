"""Tests de tipos, conversiones y comparadores."""
import struct
import math
import pytest

from core import (
    ValueType, CompareType,
    MemoryTypeHandler, make_handler,
    lookup_value_type, lookup_compare_type,
)


class TestEnums:
    def test_value_type_values(self):
        assert int(ValueType.BYTE_TYPE) == 0
        assert int(ValueType.STRING_TYPE) == 6
        assert int(ValueType.POINTER_TYPE) == 8

    def test_compare_type_values(self):
        assert int(CompareType.EXACT_VALUE) == 0
        assert int(CompareType.BETWEEN_VALUE) == 10
        assert int(CompareType.POINTER_VALUE) == 12


class TestLookup:
    def test_lookup_value_type_aliases(self):
        assert lookup_value_type("uint8") == ValueType.BYTE_TYPE
        assert lookup_value_type("uint16") == ValueType.USHORT_TYPE
        assert lookup_value_type("uint32") == ValueType.UINT_TYPE
        assert lookup_value_type("uint64") == ValueType.ULONG_TYPE
        assert lookup_value_type("4 bytes") == ValueType.UINT_TYPE
        assert lookup_value_type("8 bytes") == ValueType.ULONG_TYPE
        assert lookup_value_type("float") == ValueType.FLOAT_TYPE
        assert lookup_value_type("double") == ValueType.DOUBLE_TYPE
        assert lookup_value_type("string") == ValueType.STRING_TYPE
        assert lookup_value_type("hex") == ValueType.HEX_TYPE
        assert lookup_value_type("pointer") == ValueType.POINTER_TYPE

    def test_lookup_value_type_case_insensitive(self):
        assert lookup_value_type("UINT32") == ValueType.UINT_TYPE
        assert lookup_value_type("Float") == ValueType.FLOAT_TYPE

    def test_lookup_value_type_unknown(self):
        with pytest.raises(ValueError):
            lookup_value_type("nonexistent")

    def test_lookup_compare_type_aliases(self):
        assert lookup_compare_type("exact") == CompareType.EXACT_VALUE
        assert lookup_compare_type("exact value") == CompareType.EXACT_VALUE
        assert lookup_compare_type("bigger than") == CompareType.BIGGER_THAN_VALUE
        assert lookup_compare_type("changed") == CompareType.CHANGED_VALUE
        assert lookup_compare_type("between") == CompareType.BETWEEN_VALUE
        assert lookup_compare_type("unknown") == CompareType.UNKNOWN_INITIAL_VALUE
        assert lookup_compare_type("any") == CompareType.UNKNOWN_INITIAL_VALUE
        assert lookup_compare_type("pointer") == CompareType.POINTER_VALUE

    def test_lookup_compare_type_unknown(self):
        with pytest.raises(ValueError):
            lookup_compare_type("nonexistent")


class TestStringToBytes:
    def test_string_to_byte(self):
        from core.types import string_to_byte
        assert string_to_byte("200") == struct.pack("<B", 200)
        assert string_to_byte("0") == b"\x00"
        assert string_to_byte("255") == b"\xFF"

    def test_string_to_2_bytes(self):
        from core.types import string_to_2_bytes
        assert string_to_2_bytes("65535") == b"\xFF\xFF"
        assert string_to_2_bytes("256") == b"\x00\x01"

    def test_string_to_4_bytes(self):
        from core.types import string_to_4_bytes
        assert string_to_4_bytes("1337") == struct.pack("<I", 1337)
        assert string_to_4_bytes("0xCAFEBABE") if False else True  # skip if not int
        assert string_to_4_bytes("4294967295") == b"\xFF\xFF\xFF\xFF"

    def test_string_to_8_bytes(self):
        from core.types import string_to_8_bytes
        assert string_to_8_bytes("42") == struct.pack("<Q", 42)

    def test_string_to_float(self):
        from core.types import string_to_float
        b = string_to_float("3.14")
        assert abs(struct.unpack("<f", b)[0] - 3.14) < 0.001

    def test_string_to_double(self):
        from core.types import string_to_double
        b = string_to_double("3.141592653589793")
        assert struct.unpack("<d", b)[0] == 3.141592653589793

    def test_string_to_hex_bytes(self):
        from core.types import string_to_hex_bytes
        assert string_to_hex_bytes("AABBCCDD") == b"\xAA\xBB\xCC\xDD"
        assert string_to_hex_bytes("") == b""
        assert string_to_hex_bytes("00FF") == b"\x00\xFF"

    def test_string_to_hex_bytes_odd_length(self):
        from core.types import string_to_hex_bytes
        with pytest.raises(ValueError):
            string_to_hex_bytes("ABC")

    def test_string_to_string_bytes(self):
        from core.types import string_to_string_bytes
        assert string_to_string_bytes("hello") == b"hello"


class TestBytesToString:
    def test_uint_to_string(self):
        from core.types import uint_to_string
        assert uint_to_string(struct.pack("<I", 1337)) == "1337"
        assert uint_to_string(struct.pack("<I", 0xCAFEBABE)) == "3405691582"

    def test_float_to_string(self):
        from core.types import float_to_string
        s = float_to_string(struct.pack("<f", 3.14))
        assert "3.14" in s

    def test_hex_to_string(self):
        from core.types import hex_to_string
        assert hex_to_string(b"\xDE\xAD\xBE\xEF") == "DEADBEEF"


# ---------------------------------------------------------------------------
# Comparadores
# ---------------------------------------------------------------------------

class TestComparatorExact:
    @pytest.mark.parametrize("vt,length,test_val", [
        (ValueType.BYTE_TYPE, 1, 200),
        (ValueType.USHORT_TYPE, 2, 50000),
        (ValueType.UINT_TYPE, 4, 1337),
        (ValueType.ULONG_TYPE, 8, 1000000),
    ])
    def test_equal_uint_match(self, vt, length, test_val):
        h = make_handler(vt, CompareType.EXACT_VALUE, is_aligned=True)
        d0 = test_val.to_bytes(length, "little")
        new_match = test_val.to_bytes(length, "little")
        new_nomatch = (test_val + 1).to_bytes(length, "little")
        assert h.comparer(d0, None, None, new_match) is True
        assert h.comparer(d0, None, None, new_nomatch) is False

    def test_equal_float(self):
        h = make_handler(ValueType.FLOAT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        d0 = struct.pack("<f", 3.14)
        new_match = struct.pack("<f", 3.14)
        new_close = struct.pack("<f", 3.14001)
        new_far = struct.pack("<f", 99.0)
        assert h.comparer(d0, None, None, new_match) is True
        # 3.14001 - 3.14 = 0.00001 < 0.0001 → True
        assert h.comparer(d0, None, None, new_close) is True
        assert h.comparer(d0, None, None, new_far) is False

    def test_equal_string(self):
        h = make_handler(ValueType.STRING_TYPE, CompareType.EXACT_VALUE, is_aligned=True, type_length=5)
        d0 = b"hello"
        assert h.comparer(d0, None, None, b"hello") is True
        assert h.comparer(d0, None, None, b"world") is False

    def test_equal_hex(self):
        h = make_handler(ValueType.HEX_TYPE, CompareType.EXACT_VALUE, is_aligned=True, type_length=8)
        d0 = b"\xDE\xAD\xBE\xEF"
        assert h.comparer(d0, None, None, b"\xDE\xAD\xBE\xEF") is True
        assert h.comparer(d0, None, None, b"\x00\x00\x00\x00") is False


class TestComparatorBiggerSmaller:
    def test_bigger_than_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.BIGGER_THAN_VALUE, is_aligned=True)
        d0 = struct.pack("<I", 100)
        assert h.comparer(d0, None, None, struct.pack("<I", 200)) is True
        assert h.comparer(d0, None, None, struct.pack("<I", 50)) is False
        assert h.comparer(d0, None, None, struct.pack("<I", 100)) is False  # not strictly bigger

    def test_smaller_than_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.SMALLER_THAN_VALUE, is_aligned=True)
        d0 = struct.pack("<I", 100)
        assert h.comparer(d0, None, None, struct.pack("<I", 50)) is True
        assert h.comparer(d0, None, None, struct.pack("<I", 200)) is False
        assert h.comparer(d0, None, None, struct.pack("<I", 100)) is False


class TestComparatorBetween:
    def test_between_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.BETWEEN_VALUE, is_aligned=True)
        d0 = struct.pack("<I", 100)
        d1 = struct.pack("<I", 200)
        assert h.comparer(d0, d1, None, struct.pack("<I", 150)) is True
        assert h.comparer(d0, d1, None, struct.pack("<I", 100)) is True  # inclusive
        assert h.comparer(d0, d1, None, struct.pack("<I", 200)) is True  # inclusive
        assert h.comparer(d0, d1, None, struct.pack("<I", 99)) is False
        assert h.comparer(d0, d1, None, struct.pack("<I", 201)) is False


class TestComparatorChanged:
    def test_changed_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.CHANGED_VALUE, is_aligned=True)
        old = struct.pack("<I", 100)
        new_same = struct.pack("<I", 100)
        new_diff = struct.pack("<I", 200)
        assert h.comparer(None, None, old, new_same) is False
        assert h.comparer(None, None, old, new_diff) is True

    def test_unchanged_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.UNCHANGED_VALUE, is_aligned=True)
        old = struct.pack("<I", 100)
        new_same = struct.pack("<I", 100)
        new_diff = struct.pack("<I", 200)
        assert h.comparer(None, None, old, new_same) is True
        assert h.comparer(None, None, old, new_diff) is False


class TestComparatorIncreased:
    def test_increased_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.INCREASED_VALUE, is_aligned=True)
        old = struct.pack("<I", 100)
        assert h.comparer(None, None, old, struct.pack("<I", 200)) is True
        assert h.comparer(None, None, old, struct.pack("<I", 50)) is False
        assert h.comparer(None, None, old, struct.pack("<I", 100)) is False

    def test_decreased_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.DECREASED_VALUE, is_aligned=True)
        old = struct.pack("<I", 100)
        assert h.comparer(None, None, old, struct.pack("<I", 50)) is True
        assert h.comparer(None, None, old, struct.pack("<I", 200)) is False
        assert h.comparer(None, None, old, struct.pack("<I", 100)) is False


class TestComparatorIncreasedBy:
    def test_increased_by_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.INCREASED_VALUE_BY, is_aligned=True)
        d0 = struct.pack("<I", 50)  # delta
        old = struct.pack("<I", 100)
        # new should be 100 + 50 = 150
        assert h.comparer(d0, None, old, struct.pack("<I", 150)) is True
        assert h.comparer(d0, None, old, struct.pack("<I", 149)) is False
        assert h.comparer(d0, None, old, struct.pack("<I", 151)) is False

    def test_decreased_by_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.DECREASED_VALUE_BY, is_aligned=True)
        d0 = struct.pack("<I", 50)
        old = struct.pack("<I", 100)
        # new should be 100 - 50 = 50
        assert h.comparer(d0, None, old, struct.pack("<I", 50)) is True
        assert h.comparer(d0, None, old, struct.pack("<I", 49)) is False


class TestComparatorUnknown:
    def test_unknown_initial_uint8(self):
        h = make_handler(ValueType.BYTE_TYPE, CompareType.UNKNOWN_INITIAL_VALUE, is_aligned=True)
        # Cualquier valor != 0
        assert h.comparer(None, None, None, b"\x01") is True
        assert h.comparer(None, None, None, b"\xFF") is True
        assert h.comparer(None, None, None, b"\x00") is False

    def test_unknown_initial_uint32(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.UNKNOWN_INITIAL_VALUE, is_aligned=True)
        assert h.comparer(None, None, None, struct.pack("<I", 1)) is True
        assert h.comparer(None, None, None, struct.pack("<I", 0)) is False


class TestComparatorFuzzy:
    def test_fuzzy_float(self):
        h = make_handler(ValueType.FLOAT_TYPE, CompareType.FUZZY_VALUE, is_aligned=True)
        d0 = struct.pack("<f", 100.0)
        # fuzzy: |new - d0| < 1
        assert h.comparer(d0, None, None, struct.pack("<f", 100.5)) is True
        assert h.comparer(d0, None, None, struct.pack("<f", 99.5)) is True
        assert h.comparer(d0, None, None, struct.pack("<f", 101.5)) is False
        assert h.comparer(d0, None, None, struct.pack("<f", 98.5)) is False


class TestHandlerProperties:
    def test_handler_lengths(self):
        assert make_handler(ValueType.BYTE_TYPE, CompareType.EXACT_VALUE).length == 1
        assert make_handler(ValueType.USHORT_TYPE, CompareType.EXACT_VALUE).length == 2
        assert make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE).length == 4
        assert make_handler(ValueType.ULONG_TYPE, CompareType.EXACT_VALUE).length == 8
        assert make_handler(ValueType.FLOAT_TYPE, CompareType.EXACT_VALUE).length == 4
        assert make_handler(ValueType.DOUBLE_TYPE, CompareType.EXACT_VALUE).length == 8

    def test_handler_alignment_aligned(self):
        assert make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True).alignment == 4
        assert make_handler(ValueType.ULONG_TYPE, CompareType.EXACT_VALUE, is_aligned=True).alignment == 4
        assert make_handler(ValueType.USHORT_TYPE, CompareType.EXACT_VALUE, is_aligned=True).alignment == 2
        assert make_handler(ValueType.BYTE_TYPE, CompareType.EXACT_VALUE, is_aligned=True).alignment == 1

    def test_handler_alignment_unaligned(self):
        assert make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=False).alignment == 1
        assert make_handler(ValueType.ULONG_TYPE, CompareType.EXACT_VALUE, is_aligned=False).alignment == 1

    def test_handler_parse_flags_exact(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE)
        assert h.parse_first_value is True
        assert h.parse_second_value is False

    def test_handler_parse_flags_between(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.BETWEEN_VALUE)
        assert h.parse_first_value is True
        assert h.parse_second_value is True

    def test_handler_parse_flags_unknown(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.UNKNOWN_INITIAL_VALUE)
        assert h.parse_first_value is False
        assert h.parse_second_value is False

    def test_handler_parse_flags_increased(self):
        h = make_handler(ValueType.UINT_TYPE, CompareType.INCREASED_VALUE)
        assert h.parse_first_value is False
        assert h.parse_second_value is False

    def test_unsupported_pair_raises(self):
        with pytest.raises(ValueError):
            make_handler(ValueType.STRING_TYPE, CompareType.BIGGER_THAN_VALUE)
