"""Tests de ResultList (bitmap compacto), MappedSectionList, ProcessManager."""
import struct
import pytest
import random

from core import ResultList, MappedSection, MappedSectionList, ProcessManager
from lib import ProcessMap, MemoryEntry


class TestResultListBasic:
    def test_single_add(self):
        rl = ResultList(element_size=4, element_alignment=4)
        rl.add(0, struct.pack("<I", 100))
        assert rl.count == 1
        items = list(rl)
        assert len(items) == 1
        assert items[0][0] == 0
        assert struct.unpack("<I", items[0][1])[0] == 100

    def test_contiguous_adds(self):
        rl = ResultList(element_size=4, element_alignment=4)
        for i in range(5):
            rl.add(i * 4, struct.pack("<I", i))
        assert rl.count == 5
        addrs = [a for a, _ in rl]
        assert addrs == [0, 4, 8, 12, 16]
        vals = [struct.unpack("<I", v)[0] for _, v in rl]
        assert vals == [0, 1, 2, 3, 4]

    def test_empty_iter(self):
        rl = ResultList(element_size=4, element_alignment=4)
        assert list(rl) == []
        assert rl.count == 0
        assert len(rl) == 0

    def test_clear(self):
        rl = ResultList(element_size=4, element_alignment=4)
        rl.add(0, struct.pack("<I", 100))
        rl.add(4, struct.pack("<I", 200))
        rl.clear()
        assert rl.count == 0
        assert list(rl) == []


class TestResultListSparse:
    def test_sparse_adds(self):
        rl = ResultList(element_size=4, element_alignment=4)
        rl.add(0,    struct.pack("<I", 10))
        rl.add(64,   struct.pack("<I", 20))  # offset 64/4=16, still in tag (< 64)
        rl.add(1000, struct.pack("<I", 30))  # needs new tag
        assert rl.count == 3
        items = list(rl)
        addrs = [a for a, _ in items]
        vals = [struct.unpack("<I", v)[0] for _, v in items]
        assert addrs == [0, 64, 1000]
        assert vals == [10, 20, 30]

    def test_value_size_mismatch_raises(self):
        rl = ResultList(element_size=4, element_alignment=4)
        with pytest.raises(ValueError):
            rl.add(0, b"\x00\x00")  # too short


class TestResultListMany:
    def test_1000_random(self):
        random.seed(42)
        rl = ResultList(element_size=4, element_alignment=4)
        addrs_set = sorted(random.sample(range(0, 100000, 4), 1000))
        for a in addrs_set:
            rl.add(a, struct.pack("<I", a))
        assert rl.count == 1000
        # Round-trip
        out_addrs = [a for a, _ in rl]
        assert out_addrs == addrs_set
        out_vals = [struct.unpack("<I", v)[0] for _, v in rl]
        assert out_vals == addrs_set

    def test_100_contiguous_then_sparse(self):
        rl = ResultList(element_size=2, element_alignment=2)
        for i in range(100):
            rl.add(i * 2, struct.pack("<H", i))
        rl.add(10000, struct.pack("<H", 999))
        rl.add(20000, struct.pack("<H", 888))
        assert rl.count == 102
        items = list(rl)
        assert items[0][0] == 0
        assert items[99][0] == 198
        assert items[100][0] == 10000
        assert items[101][0] == 20000


class TestResultListDifferentSizes:
    def test_uint8(self):
        rl = ResultList(element_size=1, element_alignment=1)
        for i in range(10):
            rl.add(i, bytes([i]))
        assert rl.count == 10
        items = list(rl)
        assert [a for a, _ in items] == list(range(10))
        assert [v[0] for _, v in items] == list(range(10))

    def test_uint64(self):
        rl = ResultList(element_size=8, element_alignment=8)
        for i in range(5):
            rl.add(i * 8, struct.pack("<Q", i * 1000))
        assert rl.count == 5
        items = list(rl)
        vals = [struct.unpack("<Q", v)[0] for _, v in items]
        assert vals == [0, 1000, 2000, 3000, 4000]

    def test_float(self):
        rl = ResultList(element_size=4, element_alignment=4)
        for i in range(5):
            rl.add(i * 4, struct.pack("<f", i * 1.5))
        items = list(rl)
        vals = [struct.unpack("<f", v)[0] for _, v in items]
        assert vals == [0.0, 1.5, 3.0, 4.5, 6.0]


class TestMappedSection:
    def test_properties(self):
        s = MappedSection(start=0x1000, length=0x1000, name="data", prot=0x3, check=False)
        assert s.start == 0x1000
        assert s.end == 0x2000
        assert s.length == 0x1000
        assert s.readable
        assert s.writable
        assert not s.executable

    def test_contains(self):
        s = MappedSection(start=0x1000, length=0x1000, name="data", prot=0x3)
        assert s.contains(0x1000)
        assert s.contains(0x1FFF)
        assert not s.contains(0x2000)
        assert not s.contains(0xFFF)


class TestMappedSectionList:
    def _make_pmap(self):
        return ProcessMap(pid=100, entries=[
            MemoryEntry(name="executable", start=0x400000, end=0x401000, offset=0, prot=0x5),
            MemoryEntry(name="data",       start=0x10000000, end=0x10010000, offset=0, prot=0x3),
            MemoryEntry(name="non-readable", start=0x20000000, end=0x20010000, offset=0, prot=0x0),
        ])

    def test_init_filters_non_readable(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        # non-readable (prot=0x0) debe ser filtrada
        # exec (prot=0x5) en bloque único (1)
        # data (prot=0x3, 64KB) con buffer_length=4096 → 16 chunks
        assert sl.count == 1 + 16

    def test_executable_single_chunk(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        # La primera sección es executable y debe tener length = 0x1000 (4KB, completo)
        assert sl[0].length == 0x1000
        assert sl[0].name == "executable[0]"

    def test_data_chunked(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        # Las secciones 1-16 son chunks de data, cada uno de 4KB
        for i in range(1, 17):
            assert sl[i].length == 4096
            assert sl[i].name.startswith("data[")

    def test_binary_search(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        assert sl.get_mapped_section_id(0x400000) == 0
        assert sl.get_mapped_section_id(0x10000000) == 1
        assert sl.get_mapped_section_id(0x10005000) == 6  # 5 chunks * 4096 = 0x5000
        assert sl.get_mapped_section_id(0x99999999) == -1  # fuera de rango

    def test_section_check(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        assert sl.total_memory_size == 0
        sl.section_check(0, True)
        assert sl.total_memory_size == 0x1000
        sl.section_check(1, True)
        assert sl.total_memory_size == 0x1000 + 4096
        sl.section_check(1, False)
        assert sl.total_memory_size == 0x1000
        # Re-marcar no debe duplicar
        sl.section_check(0, True)
        assert sl.total_memory_size == 0x1000

    def test_check_all(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        sl.check_all(True)
        assert sl.total_memory_size == 0x1000 + 0x10000  # exec + data
        sl.check_all(False)
        assert sl.total_memory_size == 0

    def test_get_sections_by_name_prot(self):
        sl = MappedSectionList()
        sl.init_from_process_map(self._make_pmap(), buffer_length=4096)
        rw_sections = sl.get_sections_by_name_prot("data", 0x3)
        assert len(rw_sections) == 16
        exec_sections = sl.get_sections_by_name_prot("executable", 0x5)
        assert len(exec_sections) == 1


class TestProcessManager:
    def test_init_sections(self):
        pm = ProcessManager()
        pmap = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x1000, end=0x2000, offset=0, prot=0x3),
        ])
        pm.init_sections(pmap, buffer_length=4096)
        assert pm.section_count == 1
        assert pm.mapped_section_list[0].name == "data[0]"

    def test_attach(self):
        pm = ProcessManager()
        pm.attach(pid=100, name="eboot.bin")
        assert pm.pid == 100
        assert pm.name == "eboot.bin"

    def test_total_memory_size(self):
        pm = ProcessManager()
        pmap = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x1000, end=0x2000, offset=0, prot=0x3),
        ])
        pm.init_sections(pmap, buffer_length=4096)
        pm.mapped_section_list.check_all(True)
        assert pm.total_memory_size == 0x1000
