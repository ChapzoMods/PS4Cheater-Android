"""Tests del cliente TCP PS4DBG contra mock server."""
import struct
import pytest

from lib import (
    PS4DBG, PS4DBGError, PS4DBGPool,
    CMD_STATUS, Process, ProcessInfo, MemoryEntry, ProcessMap,
)


class TestConnection:
    def test_connect_disconnect(self, ps4_client):
        assert ps4_client.is_connected
        assert ps4_client.disconnect()
        assert not ps4_client.is_connected

    def test_double_connect(self, ps4_client):
        # Conectar de nuevo no debe fallar
        assert ps4_client.connect()
        assert ps4_client.is_connected

    def test_context_manager(self, mock_server):
        with PS4DBG("127.0.0.1", 1744, timeout=5.0) as c:
            assert c.is_connected
        assert not c.is_connected


class TestVersion:
    def test_get_version(self, ps4_client):
        v = ps4_client.get_console_debug_version()
        assert v == "ps4d-1.0.0"


class TestProcessList:
    def test_get_process_list(self, ps4_client):
        procs = ps4_client.get_process_list()
        assert len(procs) == 3
        # Verificar que están los esperados
        names = [p.name for p in procs]
        pids = [p.pid for p in procs]
        assert "eboot.bin" in names
        assert "SceShellUI" in names
        assert 100 in pids
        assert 200 in pids

    def test_process_str(self, ps4_client):
        procs = ps4_client.get_process_list()
        s = str(procs[0])
        assert "[" in s and "]" in s


class TestProcessInfo:
    def test_get_info_100(self, ps4_client):
        info = ps4_client.get_process_info(100)
        assert info.pid == 100
        assert info.name == "eboot.bin"
        assert info.titleid == "CUSA00001"
        assert "UP0001" in info.contentid

    def test_get_info_200(self, ps4_client):
        info = ps4_client.get_process_info(200)
        assert info.pid == 200
        assert info.name == "SceShellUI"


class TestProcessMaps:
    def test_get_maps_100(self, ps4_client):
        pmap = ps4_client.get_process_maps(100)
        assert pmap.pid == 100
        assert len(pmap.entries) == 3
        names = [e.name for e in pmap.entries]
        assert "executable" in names
        assert "data" in names
        assert "heap" in names

    def test_executable_section_prot(self, ps4_client):
        pmap = ps4_client.get_process_maps(100)
        exec_section = next(e for e in pmap.entries if e.name == "executable")
        assert exec_section.prot == 0x5
        assert exec_section.readable and exec_section.executable
        assert not exec_section.writable

    def test_data_section_prot(self, ps4_client):
        pmap = ps4_client.get_process_maps(100)
        data = next(e for e in pmap.entries if e.name == "data")
        assert data.prot == 0x3
        assert data.readable and data.writable and not data.executable
        assert data.length == 0x1000


class TestReadMemory:
    def test_read_cafebabe(self, ps4_client):
        data = ps4_client.read_memory(100, 0x10000000, 4)
        val = struct.unpack("<I", data)[0]
        assert val == 0xCAFEBABE

    def test_read_multiple(self, ps4_client):
        data = ps4_client.read_memory(100, 0x10000000, 16)
        vals = struct.unpack("<4I", data)
        assert all(v == 0xCAFEBABE for v in vals)

    def test_read_outside_region(self, ps4_client):
        # Leer de una address no mapeada devuelve zeros (no excepción)
        data = ps4_client.read_memory(100, 0x99999999, 4)
        assert data == b"\x00\x00\x00\x00"

    def test_read_zero_length(self, ps4_client):
        data = ps4_client.read_memory(100, 0x10000000, 0)
        assert data == b""

    def test_read_executable_section(self, ps4_client):
        data = ps4_client.read_memory(100, 0x400000, 16)
        # NOP sled
        assert data == b"\x90" * 16


class TestWriteMemory:
    def test_write_and_reread(self, ps4_client):
        # Escribir DEADBEEF en little-endian: EFBEADDE
        new_data = struct.pack("<I", 0xDEADBEEF)
        ps4_client.write_memory(100, 0x10000000, new_data)
        # Releer
        data = ps4_client.read_memory(100, 0x10000000, 4)
        val = struct.unpack("<I", data)[0]
        assert val == 0xDEADBEEF

    def test_write_multiple(self, ps4_client):
        data = struct.pack("<4I", 1, 2, 3, 4)
        ps4_client.write_memory(100, 0x10000000, data)
        reread = ps4_client.read_memory(100, 0x10000000, 16)
        assert reread == data

    def test_write_empty(self, ps4_client):
        # Escribir 0 bytes no debe fallar
        ps4_client.write_memory(100, 0x10000000, b"")


class TestNotify:
    def test_notify(self, ps4_client, mock_server):
        ps4_client.notify(0, "Test notification")
        assert mock_server.notify_count >= 1
        assert mock_server.last_notify is not None
        ntype, msg = mock_server.last_notify
        assert ntype == 0
        assert "Test" in msg


class TestPool:
    def test_pool_connect_disconnect(self, mock_server):
        pool = PS4DBGPool("127.0.0.1", 1744, size=3, timeout=5.0)
        assert pool.connect_all()
        assert pool.is_connected
        assert len(pool._connections) == 3
        pool.disconnect_all()

    def test_pool_read_memory(self, mock_server):
        with PS4DBGPool("127.0.0.1", 1744, size=2, timeout=5.0) as pool:
            data = pool.get(0).read_memory(100, 0x10000000, 4)
            val = struct.unpack("<I", data)[0]
            assert val == 0xCAFEBABE


class TestErrorHandling:
    def test_invalid_pid_process_info(self, ps4_client):
        # El mock devuelve CMD_INVALID_INDEX para pids no registrados
        with pytest.raises(PS4DBGError) as exc_info:
            ps4_client.get_process_info(9999)
        assert exc_info.value.status == CMD_STATUS.CMD_INVALID_INDEX

    def test_invalid_pid_process_maps(self, ps4_client):
        with pytest.raises(PS4DBGError):
            ps4_client.get_process_maps(9999)
