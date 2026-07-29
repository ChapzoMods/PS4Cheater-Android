#!/usr/bin/env python3
"""
Smoke tests para FASE 2: ResultList, MappedSectionList, scanner básico.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import struct
from core import (
    ValueType, CompareType, make_handler, lookup_value_type, lookup_compare_type,
    MappedSection, MappedSectionList, ProcessManager, ResultList,
    ScanEngine, ScanProgress,
    Pointer, PointerList, PointerResult,
)
from lib import ProcessMap, MemoryEntry, PS4DBGPool


# ---------------------------------------------------------------------------
# ResultList
# ---------------------------------------------------------------------------

def test_resultlist_basic():
    """Añade 5 resultados (uint32, alignment 4) y verifica que se pueden iterar."""
    rl = ResultList(element_size=4, element_alignment=4)
    # 5 addresses contiguas
    for i in range(5):
        addr = i * 4
        val = struct.pack("<I", 100 + i)
        rl.add(addr, val)
    assert rl.count == 5, f"count={rl.count}"
    # Iterar
    addrs = [a for a, _ in rl]
    assert addrs == [0, 4, 8, 12, 16], f"addrs={addrs}"
    print(f"[OK] ResultList basic: 5 contiguos -> {addrs}")


def test_resultlist_sparse():
    """Añade 3 resultados dispersos (varios tags)."""
    rl = ResultList(element_size=4, element_alignment=4)
    rl.add(0,    struct.pack("<I", 10))
    rl.add(64,   struct.pack("<I", 20))  # fuera del rango del primer tag (>= 64*4=256 bytes offset)
    rl.add(1000, struct.pack("<I", 30))
    assert rl.count == 3, f"count={rl.count}"
    items = list(rl)
    addrs = [a for a, _ in items]
    vals = [struct.unpack("<I", v)[0] for _, v in items]
    assert addrs == [0, 64, 1000], f"addrs={addrs}"
    assert vals == [10, 20, 30], f"vals={vals}"
    print(f"[OK] ResultList sparse: {list(zip(addrs, vals))}")


def test_resultlist_many():
    """Añade 1000 resultados aleatorios ordenados (forzar múltiples tags/páginas)."""
    import random
    random.seed(42)
    rl = ResultList(element_size=4, element_alignment=4)
    addrs_set = sorted(random.sample(range(0, 100000, 4), 1000))
    for a in addrs_set:
        rl.add(a, struct.pack("<I", a))
    assert rl.count == 1000, f"count={rl.count}"
    # Verificar round-trip
    out_addrs = [a for a, _ in rl]
    assert out_addrs == addrs_set, f"mismatch: out={out_addrs[:5]}... expected={addrs_set[:5]}..."
    print(f"[OK] ResultList many: 1000 elementos en {len(rl._buffers)} páginas, round-trip OK")


# ---------------------------------------------------------------------------
# MappedSectionList
# ---------------------------------------------------------------------------

def test_mapped_section_list():
    """Crea un ProcessMap fake, inicializa section list, verifica búsqueda binaria."""
    pm = ProcessMap(pid=100, entries=[
        MemoryEntry(name="executable", start=0x400000, end=0x401000, offset=0, prot=0x5),
        MemoryEntry(name="data",       start=0x10000000, end=0x10010000, offset=0, prot=0x3),
        MemoryEntry(name="non-readable", start=0x20000000, end=0x20010000, offset=0, prot=0x0),  # filtrada
    ])
    sl = MappedSectionList()
    sl.init_from_process_map(pm, buffer_length=4096)  # chunks pequeños para forzar subdivisión

    # La sección non-readable (prot=0x0) debe ser filtrada
    # La sección executable (prot=0x5) se deja en un solo bloque (cur_buffer_length = length)
    # La sección data (prot=0x3, 64KB) con buffer_length=4096 se divide en 16 chunks
    assert sl.count == 1 + 16, f"expected 17 sections, got {sl.count}"
    print(f"[OK] MappedSectionList: {sl.count} secciones (1 exec + 16 data chunks)")

    # Búsqueda binaria
    sid = sl.get_mapped_section_id(0x10000000)
    assert sid == 1, f"expected section 1 for 0x10000000, got {sid}"
    sid = sl.get_mapped_section_id(0x10005000)
    assert sid == 6, f"expected section 6 for 0x10005000, got {sid}"
    sid = sl.get_mapped_section_id(0x400000)
    assert sid == 0, f"expected section 0 for 0x400000, got {sid}"
    sid = sl.get_mapped_section_id(0x99999999)
    assert sid == -1, f"expected -1 for out-of-range, got {sid}"
    print(f"[OK] MappedSectionList binary search OK")

    # section_check
    sl.section_check(0, True)
    sl.section_check(1, True)
    assert sl.total_memory_size == 4096 + 4096, f"total_memory_size={sl.total_memory_size}"
    sl.section_check(1, False)
    assert sl.total_memory_size == 4096
    print(f"[OK] MappedSectionList section_check / total_memory_size")


# ---------------------------------------------------------------------------
# Scanner con mock memory (sin TCP)
# ---------------------------------------------------------------------------

class FakePool:
    """Pool fake que devuelve memoria generada proceduralmente."""
    def __init__(self, memory: dict):
        # memory: {address: bytes}
        self.memory = memory

    def get(self, idx: int = 0):
        return self

    def read_memory(self, pid, address, length):
        # Ensamblar `length` bytes empezando en `address`
        out = bytearray(length)
        for addr, data in self.memory.items():
            # Si la región cae dentro de [address, address+length)
            if addr + len(data) > address and addr < address + length:
                # Copiar la parte que intersecta
                src_start = max(0, address - addr)
                dst_start = max(0, addr - address)
                n = min(len(data) - src_start, length - dst_start)
                out[dst_start:dst_start + n] = data[src_start:src_start + n]
        return bytes(out)


def test_new_scan_uint32_exact():
    """Crea memoria con varios uint32, escanea buscando un valor exacto."""
    # 64 uint32 (256 bytes), algunos son 1337
    mem_bytes = bytearray(256)
    targets = [4, 16, 32, 60]  # offsets donde pondremos 1337
    for off in targets:
        struct.pack_into("<I", mem_bytes, off, 1337)
    # Otros valores
    for off in [0, 8, 12, 20, 24, 28, 36, 40, 44, 48, 52, 56]:
        if off not in targets:
            struct.pack_into("<I", mem_bytes, off, 999)

    pool = FakePool({0x10000000: bytes(mem_bytes)})

    # ProcessManager
    pm = ProcessMap(pid=100, entries=[
        MemoryEntry(name="data", start=0x10000000, end=0x10000100, offset=0, prot=0x3),
    ])
    proc_mgr = ProcessManager(pid=100)
    proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
    proc_mgr.mapped_section_list.check_all(True)

    engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)

    handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
    val = struct.pack("<I", 1337)
    count = engine.new_scan(handler, val, None)

    assert count == len(targets), f"expected {len(targets)} matches, got {count}"
    results = engine.get_all_results()
    found_addrs = sorted([a for a, _ in results])
    expected_addrs = sorted([0x10000000 + t for t in targets])
    assert found_addrs == expected_addrs, f"found={found_addrs} expected={expected_addrs}"
    print(f"[OK] new_scan uint32 exact 1337 -> {count} matches en {found_addrs}")


def test_next_scan_changed():
    """Después de un new scan, modifica la memoria y hace next scan 'changed'."""
    mem_bytes = bytearray(256)
    # 4 valores 1337
    for off in [4, 16, 32, 60]:
        struct.pack_into("<I", mem_bytes, off, 1337)

    pool = FakePool({0x10000000: bytes(mem_bytes)})

    pm = ProcessMap(pid=100, entries=[
        MemoryEntry(name="data", start=0x10000000, end=0x10000100, offset=0, prot=0x3),
    ])
    proc_mgr = ProcessManager(pid=100)
    proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
    proc_mgr.mapped_section_list.check_all(True)

    engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)

    # First scan: exact 1337
    handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
    engine.new_scan(handler, struct.pack("<I", 1337), None)
    assert proc_mgr.mapped_section_list.total_result_count() == 4

    # Modify memory: cambiar 2 de los 4
    struct.pack_into("<I", mem_bytes, 16, 9999)
    struct.pack_into("<I", mem_bytes, 60, 8888)
    pool.memory[0x10000000] = bytes(mem_bytes)  # actualizar en el pool

    # Next scan: changed
    handler2 = make_handler(ValueType.UINT_TYPE, CompareType.CHANGED_VALUE, is_aligned=True)
    count = engine.next_scan(handler2, None, None)
    assert count == 2, f"expected 2 changed, got {count}"
    results = engine.get_all_results()
    addrs = sorted([a for a, _ in results])
    assert addrs == [0x10000010, 0x1000003C], f"addrs={addrs}"
    print(f"[OK] next_scan changed -> {count} matches en {addrs}")


def test_pointer_scan():
    """Crea memoria con punteros, escanea, verifica PointerList."""
    # Memory layout:
    # 0x10000000: [ptr=0x10000100, ptr=0x10000200, ptr=0xDEAD, ptr=0x10000000]
    # 0x10000100: [...]
    mem_bytes = bytearray(64)
    struct.pack_into("<Q", mem_bytes, 0,  0x10000100)
    struct.pack_into("<Q", mem_bytes, 8,  0x10000200)
    struct.pack_into("<Q", mem_bytes, 16, 0xDEAD)        # no apunta a sección mapeada
    struct.pack_into("<Q", mem_bytes, 24, 0x10000000)    # self-pointer

    pool = FakePool({0x10000000: bytes(mem_bytes)})

    pm = ProcessMap(pid=100, entries=[
        MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
    ])
    proc_mgr = ProcessManager(pid=100)
    proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
    proc_mgr.mapped_section_list.check_all(True)

    engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)

    pl = PointerList()
    count = engine.pointer_scan(pl)
    # Debe encontrar 3 punteros válidos (los que apuntan a [0x10000000, 0x10000040))
    # ptr=0x10000100 ✓, ptr=0x10000200 ✗ (fuera de rango), ptr=0xDEAD ✗, ptr=0x10000000 ✓
    # Wait: 0x10000200 está fuera del rango [0x10000000, 0x10000040), así que no.
    # 0x10000100 también está fuera! Hmm, mi sección termina en 0x10000040.
    # Voy a verificar:
    # 0x10000100 >= 0x10000040 → fuera de rango → no match
    # 0x10000200 → fuera → no match
    # 0xDEAD → fuera → no match
    # 0x10000000 → en rango → match
    # Entonces esperamos 1 match
    assert count == 1, f"expected 1 pointer match, got {count}: {[(p.address, p.pointer_value) for p in pl._by_address]}"
    print(f"[OK] pointer_scan -> {count} matches")


def test_type_handlers():
    """Verifica que los handlers se construyen correctamente para varios pares."""
    pairs = [
        (ValueType.BYTE_TYPE,   CompareType.EXACT_VALUE),
        (ValueType.USHORT_TYPE, CompareType.EXACT_VALUE),
        (ValueType.UINT_TYPE,   CompareType.EXACT_VALUE),
        (ValueType.ULONG_TYPE,  CompareType.EXACT_VALUE),
        (ValueType.FLOAT_TYPE,  CompareType.EXACT_VALUE),
        (ValueType.DOUBLE_TYPE, CompareType.EXACT_VALUE),
        (ValueType.UINT_TYPE,   CompareType.CHANGED_VALUE),
        (ValueType.UINT_TYPE,   CompareType.INCREASED_VALUE),
        (ValueType.UINT_TYPE,   CompareType.BETWEEN_VALUE),
        (ValueType.FLOAT_TYPE,  CompareType.FUZZY_VALUE),
        (ValueType.ULONG_TYPE,  CompareType.POINTER_VALUE),
    ]
    for vt, ct in pairs:
        h = make_handler(vt, ct, is_aligned=True)
        assert h.length > 0
        assert h.alignment > 0
        assert h.comparer is not None
    print(f"[OK] {len(pairs)} type handlers creados correctamente")

    # Lookup por string
    assert lookup_value_type("uint32") == ValueType.UINT_TYPE
    assert lookup_value_type("4 bytes") == ValueType.UINT_TYPE
    assert lookup_value_type("float") == ValueType.FLOAT_TYPE
    assert lookup_compare_type("exact") == CompareType.EXACT_VALUE
    assert lookup_compare_type("bigger than") == CompareType.BIGGER_THAN_VALUE
    print(f"[OK] lookup_value_type / lookup_compare_type")


def test_comparator_exact_uint32():
    """Verifica el comparador equal_uint32."""
    h = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE)
    d0 = struct.pack("<I", 1337)
    new_match = struct.pack("<I", 1337)
    new_nomatch = struct.pack("<I", 9999)
    assert h.comparer(d0, None, None, new_match) is True
    assert h.comparer(d0, None, None, new_nomatch) is False
    print(f"[OK] comparator equal_uint32")


def test_comparator_changed_uint32():
    h = make_handler(ValueType.UINT_TYPE, CompareType.CHANGED_VALUE)
    old = struct.pack("<I", 100)
    new_same = struct.pack("<I", 100)
    new_diff = struct.pack("<I", 200)
    assert h.comparer(None, None, old, new_same) is False
    assert h.comparer(None, None, old, new_diff) is True
    print(f"[OK] comparator changed_uint32")


if __name__ == "__main__":
    print("=== FASE 2 Smoke Tests ===")
    test_resultlist_basic()
    test_resultlist_sparse()
    test_resultlist_many()
    test_mapped_section_list()
    test_type_handlers()
    test_comparator_exact_uint32()
    test_comparator_changed_uint32()
    test_new_scan_uint32_exact()
    test_next_scan_changed()
    test_pointer_scan()
    print("\n✅ Todos los smoke tests de FASE 2 pasan.")
