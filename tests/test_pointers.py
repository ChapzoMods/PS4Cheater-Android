"""
Tests de core/pointers.py — PointerList, búsqueda binaria y DFS de cadenas.
"""
import pytest

from core.pointers import (
    Pointer, PointerResult, PointerList,
    _bisect_addr, _bisect_addr_right, _bisect_value, _bisect_value_right,
)


def _make_list(pairs):
    """pairs: lista de (address, pointer_value)."""
    pl = PointerList()
    for addr, val in pairs:
        pl.add(Pointer(address=addr, pointer_value=val))
    return pl


# ---------------------------------------------------------------------------
# PointerResult / Pointer básicos
# ---------------------------------------------------------------------------

class TestPointerResult:
    def test_str(self):
        r = PointerResult(base_address=0x1000, offsets=[0x10, 0x20])
        s = str(r)
        assert "0x1000" in s
        assert "+0x10" in s
        assert "+0x20" in s

    def test_str_empty_offsets(self):
        r = PointerResult(base_address=0x2000)
        assert "0x2000" in str(r)


# ---------------------------------------------------------------------------
# add / count / len / clear / init
# ---------------------------------------------------------------------------

class TestPointerListBasics:
    def test_add_and_count(self):
        pl = _make_list([(0x100, 0x200), (0x300, 0x400)])
        assert pl.count == 2
        assert len(pl) == 2

    def test_clear(self):
        pl = _make_list([(0x100, 0x200)])
        pl.stop = True
        pl.clear()
        assert len(pl) == 0
        assert pl.stop is False
        assert pl._sorted is False

    def test_init_sorts(self):
        pl = _make_list([(0x300, 0x30), (0x100, 0x10), (0x200, 0x20)])
        pl.init()
        assert pl._sorted is True
        addrs = [p.address for p in pl._by_address]
        assert addrs == [0x100, 0x200, 0x300]
        vals = [p.pointer_value for p in pl._by_value]
        assert vals == [0x10, 0x20, 0x30]


# ---------------------------------------------------------------------------
# Lookups internos
# ---------------------------------------------------------------------------

class TestLookups:
    def test_get_pointers_by_value(self):
        pl = _make_list([(0x100, 0xAAA), (0x200, 0xAAA), (0x300, 0xBBB)])
        # auto-init al no estar ordenado
        found = pl._get_pointers_by_value(0xAAA)
        assert len(found) == 2
        assert {p.address for p in found} == {0x100, 0x200}

    def test_get_pointers_by_value_none(self):
        pl = _make_list([(0x100, 0xAAA)])
        assert pl._get_pointers_by_value(0xFFFF) == []

    def test_get_pointer_by_address_exact(self):
        pl = _make_list([(0x100, 1), (0x200, 2), (0x300, 3)])
        p = pl._get_pointer_by_address(0x200)
        assert p is not None and p.address == 0x200

    def test_get_pointer_by_address_closest_lower(self):
        pl = _make_list([(0x100, 1), (0x300, 3)])
        p = pl._get_pointer_by_address(0x250)
        assert p is not None and p.address == 0x100

    def test_get_pointer_by_address_below_all(self):
        pl = _make_list([(0x100, 1)])
        assert pl._get_pointer_by_address(0x50) is None

    def test_get_pointers_in_range_by_address(self):
        pl = _make_list([(0x100, 1), (0x200, 2), (0x300, 3), (0x400, 4)])
        found = pl._get_pointers_in_range_by_address(0x200, 0x300)
        addrs = sorted(p.address for p in found)
        assert addrs == [0x200, 0x300]


# ---------------------------------------------------------------------------
# find_pointer_list (DFS)
# ---------------------------------------------------------------------------

class TestFindPointerList:
    def test_single_level(self):
        # target 0x5000, un puntero en 0x1000 apunta a 0x5000 (offset 0x4000)
        pl = _make_list([(0x1000, 0x5000)])
        results = pl.find_pointer_list(0x5000, ranges=[0x8000])
        assert len(results) == 1
        assert results[0].base_address == 0x1000
        assert results[0].offsets == [0x4000]

    def test_offset_out_of_range(self):
        pl = _make_list([(0x1000, 0x5000)])
        # offset 0x4000 > range 0x100 → sin resultados
        results = pl.find_pointer_list(0x5000, ranges=[0x100])
        assert results == []

    def test_no_pointer_to_target(self):
        pl = _make_list([(0x1000, 0x9999)])
        results = pl.find_pointer_list(0x5000, ranges=[0x10000])
        assert results == []

    def test_two_levels(self):
        # target 0x5000 <- 0x2000(apunta a 0x5000) <- 0x1000(apunta a 0x2000)
        pl = _make_list([
            (0x2000, 0x5000),
            (0x1000, 0x2000),
        ])
        results = pl.find_pointer_list(0x5000, ranges=[0x8000, 0x8000])
        assert len(results) == 1
        # base es el último puntero (más profundo)
        assert results[0].base_address == 0x1000

    def test_on_new_path_callback(self):
        pl = _make_list([(0x1000, 0x5000)])
        seen = []
        pl.find_pointer_list(0x5000, ranges=[0x8000], on_new_path=seen.append)
        assert len(seen) == 1
        assert isinstance(seen[0], PointerResult)

    def test_stop_flag_set_by_callback(self):
        # cadena de 2 niveles para que se emita un path e invoque el callback
        pl = _make_list([(0x2000, 0x5000), (0x1000, 0x2000)])

        def cb(r):
            pl.stop = True

        pl.find_pointer_list(0x5000, ranges=[0x8000, 0x8000], on_new_path=cb)
        assert pl.stop is True

    def test_stop_reset_on_new_search(self):
        pl = _make_list([(0x1000, 0x5000)])
        pl.stop = True
        # find_pointer_list debe resetear stop=False al iniciar
        pl.find_pointer_list(0x5000, ranges=[0x8000])
        assert pl.stop is False


# ---------------------------------------------------------------------------
# bisect helpers
# ---------------------------------------------------------------------------

class TestBisectHelpers:
    def _ptrs_by_addr(self, addrs):
        return sorted((Pointer(address=a, pointer_value=0) for a in addrs),
                      key=lambda p: p.address)

    def _ptrs_by_val(self, vals):
        return sorted((Pointer(address=0, pointer_value=v) for v in vals),
                      key=lambda p: (p.pointer_value, p.address))

    def test_bisect_addr(self):
        lst = self._ptrs_by_addr([10, 20, 30])
        assert _bisect_addr(lst, 20) == 1
        assert _bisect_addr(lst, 25) == 2
        assert _bisect_addr(lst, 5) == 0

    def test_bisect_addr_right(self):
        lst = self._ptrs_by_addr([10, 20, 20, 30])
        assert _bisect_addr_right(lst, 20) == 3
        assert _bisect_addr_right(lst, 30) == 4

    def test_bisect_value(self):
        lst = self._ptrs_by_val([1, 2, 3])
        assert _bisect_value(lst, 2) == 1
        assert _bisect_value(lst, 0) == 0

    def test_bisect_value_right(self):
        lst = self._ptrs_by_val([1, 2, 2, 3])
        assert _bisect_value_right(lst, 2) == 3
