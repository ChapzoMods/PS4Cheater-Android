"""Tests de integración end-to-end contra el mock server."""
import struct
import pytest

from lib import PS4DBG, PS4DBGPool, PS4DBGError
from core import (
    ScanEngine, ValueType, CompareType,
    make_handler, ProcessManager, PointerList,
    CheatList, CheatEntry,
)


class TestEndToEndConnection:
    def test_full_workflow(self, ps4_client):
        """Workflow completo: connect -> procs -> attach -> scan -> write -> cheat."""
        # 1. Listar procesos
        procs = ps4_client.get_process_list()
        assert len(procs) >= 1
        eboot = next(p for p in procs if p.name == "eboot.bin")
        assert eboot.pid == 100

        # 2. Obtener info del proceso
        info = ps4_client.get_process_info(100)
        assert info.titleid == "CUSA00001"

        # 3. Cargar sections
        pmap = ps4_client.get_process_maps(100)
        assert len(pmap.entries) == 3

        # 4. Setup ProcessManager + ScanEngine
        pm = ProcessManager(pid=100, name="eboot.bin")
        pm.init_sections(pmap, buffer_length=32 * 1024 * 1024)
        # Marcar solo la sección data (rw-)
        for i, s in enumerate(pm.mapped_section_list):
            if s.writable and not s.executable:
                pm.mapped_section_list.section_check(i, True)
        assert pm.total_memory_size > 0

        # 5. Pool + scan engine
        pool = PS4DBGPool("127.0.0.1", 1744, size=2, timeout=5.0)
        pool.connect_all()
        try:
            engine = ScanEngine(pool, pm, peek_buffer_length=32 * 1024 * 1024, num_comparers=1)

            # 6. New scan: buscar 0xCAFEBABE
            handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)
            count = engine.new_scan(handler, struct.pack("<I", 0xCAFEBABE), None)
            # 4096 bytes / 4 = 1024 resultados
            assert count == 1024

            # 7. Ver resultados
            results = engine.get_all_results(limit=5)
            assert len(results) == 5
            for addr, val in results:
                assert struct.unpack("<I", val)[0] == 0xCAFEBABE
                assert 0x10000000 <= addr < 0x10001000

            # 8. Escribir un valor nuevo
            ps4_client.write_memory(100, 0x10000000, struct.pack("<I", 0xDEADBEEF))

            # 9. Next scan: changed
            handler2 = make_handler(ValueType.UINT_TYPE, CompareType.CHANGED_VALUE, is_aligned=True)
            count2 = engine.next_scan(handler2, None, None)
            assert count2 == 1
            results2 = engine.get_all_results()
            assert len(results2) == 1
            assert results2[0][0] == 0x10000000

            # 10. Cheat
            cl = CheatList(ps4=ps4_client, pid=100)
            e = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337")
            assert cl.apply(e)
            # Verificar que se escribió
            data = ps4_client.read_memory(100, 0x10000000, 4)
            assert struct.unpack("<I", data)[0] == 1337
        finally:
            pool.disconnect_all()


class TestEndToEndMultiProcess:
    def test_two_processes(self, ps4_client):
        """Trabaja con dos procesos distintos."""
        # Proceso 100
        info100 = ps4_client.get_process_info(100)
        assert info100.name == "eboot.bin"

        # Proceso 200
        info200 = ps4_client.get_process_info(200)
        assert info200.name == "SceShellUI"

        # Proceso 300
        info300 = ps4_client.get_process_info(300)
        assert info300.name == "SceCdlgApp"

        # Maps de cada uno
        pmap100 = ps4_client.get_process_maps(100)
        pmap200 = ps4_client.get_process_maps(200)
        pmap300 = ps4_client.get_process_maps(300)

        assert len(pmap100.entries) == 3
        assert len(pmap200.entries) == 1
        assert len(pmap300.entries) == 1


class TestEndToEndHeap:
    def test_read_heap_pointers(self, ps4_client):
        """Lee los punteros del heap del proceso 100."""
        # El heap está en 0x20000000, los primeros 32 bytes son punteros:
        # 0x20000000: 0x20000008
        # 0x20000008: 0x20000010
        # 0x20000010: 0x10000000 (apunta a data section!)
        # 0x20000018: 0xDEADDEAD
        data = ps4_client.read_memory(100, 0x20000000, 32)
        ptrs = struct.unpack("<4Q", data)
        assert ptrs[0] == 0x20000008
        assert ptrs[1] == 0x20000010
        assert ptrs[2] == 0x10000000
        assert ptrs[3] == 0xDEADDEAD


class TestEndToEndWriteMultipleTimes:
    def test_write_then_overwrite(self, ps4_client):
        """Escribe un valor, luego lo sobreescribe."""
        # Escribir 0x11112222
        ps4_client.write_memory(100, 0x10000000, struct.pack("<I", 0x11112222))
        data = ps4_client.read_memory(100, 0x10000000, 4)
        assert struct.unpack("<I", data)[0] == 0x11112222

        # Sobreescribir con 0x33334444
        ps4_client.write_memory(100, 0x10000000, struct.pack("<I", 0x33334444))
        data = ps4_client.read_memory(100, 0x10000000, 4)
        assert struct.unpack("<I", data)[0] == 0x33334444


class TestEndToEndNotify:
    def test_notify(self, ps4_client, mock_server):
        initial_count = mock_server.notify_count
        ps4_client.notify(0, "Hello from test")
        assert mock_server.notify_count == initial_count + 1
        assert mock_server.last_notify[1] == "Hello from test"

    def test_notify_multiple(self, ps4_client, mock_server):
        initial = mock_server.notify_count
        for i in range(5):
            ps4_client.notify(1, f"msg {i}")
        assert mock_server.notify_count == initial + 5
