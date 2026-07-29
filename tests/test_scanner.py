"""Tests del ScanEngine: new_scan, next_scan, pointer_scan."""
import struct
import pytest

from core import (
    ScanEngine, ValueType, CompareType,
    make_handler, ProcessManager, PointerList,
)
from lib import ProcessMap, MemoryEntry


class FakePool:
    """Pool fake que devuelve memoria generada proceduralmente."""
    def __init__(self, memory: dict):
        self.memory = memory

    def get(self, idx: int = 0):
        return self

    def read_memory(self, pid, address, length):
        out = bytearray(length)
        for addr, data in self.memory.items():
            if addr + len(data) > address and addr < address + length:
                src_start = max(0, address - addr)
                dst_start = max(0, addr - address)
                n = min(len(data) - src_start, length - dst_start)
                if n > 0:
                    out[dst_start:dst_start + n] = data[src_start:src_start + n]
        return bytes(out)


class TestNewScan:
    def test_uint32_exact(self):
        """Crea 64 uint32, escanea buscando 1337 — debe encontrar 4."""
        mem = bytearray(256)
        targets = [4, 16, 32, 60]
        for off in targets:
            struct.pack_into("<I", mem, off, 1337)
        for off in [0, 8, 12, 20, 24, 28, 36, 40, 44, 48, 52, 56]:
            if off not in targets:
                struct.pack_into("<I", mem, off, 999)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000100, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        count = engine.new_scan(handler, struct.pack("<I", 1337), None)

        assert count == 4
        results = engine.get_all_results()
        found_addrs = sorted([a for a, _ in results])
        expected_addrs = sorted([0x10000000 + t for t in targets])
        assert found_addrs == expected_addrs

    def test_uint32_exact_no_matches(self):
        mem = bytearray(64)
        for i in range(0, 64, 4):
            struct.pack_into("<I", mem, i, 999)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        count = engine.new_scan(handler, struct.pack("<I", 1337), None)
        assert count == 0

    def test_uint32_bigger_than(self):
        mem = bytearray(40)
        struct.pack_into("<I", mem, 0, 50)
        struct.pack_into("<I", mem, 4, 100)
        struct.pack_into("<I", mem, 8, 200)
        struct.pack_into("<I", mem, 12, 30)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000028, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        handler = make_handler(ValueType.UINT_TYPE, CompareType.BIGGER_THAN_VALUE, is_aligned=True)
        count = engine.new_scan(handler, struct.pack("<I", 60), None)
        # > 60: 100 y 200
        assert count == 2

    def test_unknown_initial_value(self):
        """UNKNOWN_INITIAL_VALUE matches cualquier valor != 0."""
        mem = bytearray(20)
        struct.pack_into("<I", mem, 0, 100)
        struct.pack_into("<I", mem, 4, 0)   # no match
        struct.pack_into("<I", mem, 8, 200)
        struct.pack_into("<I", mem, 12, 0)  # no match
        struct.pack_into("<I", mem, 16, 1)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000014, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        handler = make_handler(ValueType.UINT_TYPE, CompareType.UNKNOWN_INITIAL_VALUE, is_aligned=True)
        count = engine.new_scan(handler, None, None)
        assert count == 3  # 100, 200, 1


class TestNextScan:
    def test_changed(self):
        """New scan encuentra 4, modificamos 2, next scan changed encuentra 2."""
        mem = bytearray(64)
        for off in [4, 16, 32, 60]:
            struct.pack_into("<I", mem, off, 1337)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        engine.new_scan(handler, struct.pack("<I", 1337), None)
        assert proc_mgr.mapped_section_list.total_result_count() == 4

        # Modify memory: change 2 of the 4
        struct.pack_into("<I", mem, 16, 9999)
        struct.pack_into("<I", mem, 60, 8888)
        pool.memory[0x10000000] = bytes(mem)

        # Next scan changed
        handler2 = make_handler(ValueType.UINT_TYPE, CompareType.CHANGED_VALUE, is_aligned=True)
        count = engine.next_scan(handler2, None, None)
        assert count == 2
        results = engine.get_all_results()
        addrs = sorted([a for a, _ in results])
        assert addrs == [0x10000010, 0x1000003C]

    def test_unchanged(self):
        """Modify some values, next scan unchanged finds the ones that stayed."""
        mem = bytearray(32)
        for off in [0, 4, 8, 12]:
            struct.pack_into("<I", mem, off, 100)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000020, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        engine.new_scan(
            make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True),
            struct.pack("<I", 100), None)
        assert proc_mgr.mapped_section_list.total_result_count() == 4

        # Modify 2 of 4
        struct.pack_into("<I", mem, 4, 200)
        struct.pack_into("<I", mem, 12, 300)
        pool.memory[0x10000000] = bytes(mem)

        handler2 = make_handler(ValueType.UINT_TYPE, CompareType.UNCHANGED_VALUE, is_aligned=True)
        count = engine.next_scan(handler2, None, None)
        assert count == 2
        addrs = sorted([a for a, _ in engine.get_all_results()])
        assert addrs == [0x10000000, 0x10000008]

    def test_next_scan_exact(self):
        """New scan finds values > 0, next scan narrows by exact value."""
        mem = bytearray(20)
        struct.pack_into("<I", mem, 0, 100)
        struct.pack_into("<I", mem, 4, 200)
        struct.pack_into("<I", mem, 8, 100)
        struct.pack_into("<I", mem, 12, 300)
        struct.pack_into("<I", mem, 16, 100)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000014, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        # First scan: unknown initial (any != 0)
        h1 = make_handler(ValueType.UINT_TYPE, CompareType.UNKNOWN_INITIAL_VALUE, is_aligned=True)
        count1 = engine.new_scan(h1, None, None)
        assert count1 == 5

        # Next scan: exact = 100 → 3 results
        h2 = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        count2 = engine.next_scan(h2, struct.pack("<I", 100), None)
        assert count2 == 3
        addrs = sorted([a for a, _ in engine.get_all_results()])
        assert addrs == [0x10000000, 0x10000008, 0x10000010]


class TestPointerScan:
    def test_pointer_scan_basic(self):
        """Memoria con punteros que apuntan a la propia sección."""
        mem = bytearray(64)
        struct.pack_into("<Q", mem, 0,  0x10000008)   # pointer to next
        struct.pack_into("<Q", mem, 8,  0xDEAD)        # invalid (not in section)
        struct.pack_into("<Q", mem, 16, 0x10000000)   # back to start
        struct.pack_into("<Q", mem, 24, 0x10000018)   # pointer to byte 24 (self)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        pl = PointerList()
        count = engine.pointer_scan(pl)
        # Punteros válidos: 0x10000008 (en sección), 0x10000000 (en sección), 0x10000018 (en sección)
        # 0xDEAD no está en sección → no
        assert count == 3

    def test_pointer_scan_with_mock_server(self, ps4_client):
        """Pointer scan usando memoria real del mock server."""
        # El mock server tiene un heap en 0x20000000 con punteros:
        # 0x20000000 -> 0x20000008 -> 0x20000010 -> 0x10000000 (data section!)
        # 0x20000018 -> 0xDEADDEAD (no válido)
        from lib import PS4DBGPool

        pool = PS4DBGPool("127.0.0.1", 1744, size=1, timeout=5.0)
        pool.connect_all()
        try:
            pmap = ps4_client.get_process_maps(100)
            proc_mgr = ProcessManager(pid=100)
            proc_mgr.init_sections(pmap, buffer_length=32 * 1024 * 1024)
            proc_mgr.mapped_section_list.check_all(True)

            engine = ScanEngine(pool, proc_mgr, peek_buffer_length=32 * 1024 * 1024, num_comparers=1)
            pl = PointerList()
            count = engine.pointer_scan(pl)
            # Debe encontrar al menos los 3 punteros válidos del heap
            # (0x20000000->0x20000008, 0x20000008->0x20000010, 0x20000010->0x10000000)
            assert count >= 3
            # Verificar que están los esperados
            addrs = sorted(p.address for p in pl._by_address)
            assert 0x20000000 in addrs
            assert 0x20000008 in addrs
            assert 0x20000010 in addrs
        finally:
            pool.disconnect_all()


class TestScanProgress:
    def test_progress_callback(self):
        """Verifica que el callback de progreso es invocado."""
        mem = bytearray(64)
        for i in range(0, 64, 4):
            struct.pack_into("<I", mem, i, 100)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        progress_calls = []

        def cb(p):
            progress_calls.append(p.percent)

        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        engine.new_scan(handler, struct.pack("<I", 100), None, progress_cb=cb)

        assert len(progress_calls) > 0
        # El último call debe ser 100%
        assert progress_calls[-1] == 100.0


class TestScanCancellation:
    def test_cancel_during_scan(self):
        """Cancela un scan: el flag is_cancelled se respeta."""
        mem = bytearray(64)
        for i in range(0, 64, 4):
            struct.pack_into("<I", mem, i, 100)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        # El engine._reset_cancel() se llama al inicio de new_scan, así que
        # cancelar antes no sirve. En su lugar, cancelamos DENTRO del scan
        # vía callback.
        def kill_cb(p):
            engine.cancel()
        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        # Cancelar en el primer callback de progreso
        engine.new_scan(handler, struct.pack("<I", 100), None, progress_cb=kill_cb)
        # Después de cancelar, el flag debe estar activo
        assert engine.is_cancelled
        engine._reset_cancel()

    def test_cancel_before_scan_resets(self):
        """El flag de cancelación se resetea al empezar un scan nuevo."""
        mem = bytearray(64)
        for i in range(0, 64, 4):
            struct.pack_into("<I", mem, i, 100)

        pool = FakePool({0x10000000: bytes(mem)})
        pm = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
        ])
        proc_mgr = ProcessManager(pid=100)
        proc_mgr.init_sections(pm, buffer_length=1024 * 1024)
        proc_mgr.mapped_section_list.check_all(True)

        engine = ScanEngine(pool, proc_mgr, peek_buffer_length=1024 * 1024, num_comparers=1)
        engine.cancel()
        assert engine.is_cancelled
        handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
        # Al empezar un scan nuevo, _reset_cancel() debe limpiar el flag
        engine.new_scan(handler, struct.pack("<I", 100), None)
        assert not engine.is_cancelled
