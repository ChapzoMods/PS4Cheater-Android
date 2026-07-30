"""Tests de propagación de errores (lecturas fallidas, conexión caída, estado corrupto)."""
import socket
import struct
import threading

import pytest

from core import CheatList, ProcessManager, ScanEngine, ValueType
from lib import CMD, CMD_STATUS, PS4DBG, PS4DBGError, PS4DBGPool, ProcessMap, MemoryEntry
from lib import protocol as P


class FailingReadServer:
    """Mock mínimo que responde CMD_ERROR a todo CMD_PROC_READ."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            while self._running:
                header = conn.recv(P.CMD_PACKET_SIZE)
                if len(header) < P.CMD_PACKET_SIZE:
                    return
                _, cmd, datalen = struct.unpack("<III", header)
                if datalen:
                    conn.recv(datalen)
                if cmd == int(CMD.CMD_PROC_READ):
                    conn.sendall(struct.pack("<I", int(CMD_STATUS.CMD_ERROR)))
                elif cmd == int(CMD.CMD_CONSOLE_END):
                    return
                else:
                    conn.sendall(struct.pack("<I", int(CMD_STATUS.CMD_SUCCESS)))
        except OSError:
            return
        finally:
            conn.close()

    def stop(self):
        self._running = False
        self._sock.close()


@pytest.fixture
def failing_server():
    srv = FailingReadServer()
    yield srv
    srv.stop()


class TestReadMemoryErrors:
    def test_read_memory_raises_on_error_status(self, failing_server):
        c = PS4DBG("127.0.0.1", failing_server.port, timeout=5.0)
        assert c.connect()
        try:
            with pytest.raises(PS4DBGError):
                c.read_memory(100, 0x10000000, 16)
        finally:
            c.disconnect()

    def test_read_memory_zero_fill_is_opt_in(self, failing_server):
        c = PS4DBG("127.0.0.1", failing_server.port, timeout=5.0)
        assert c.connect()
        try:
            data = c.read_memory(100, 0x10000000, 16, zero_fill_on_error=True)
            assert data == b"\x00" * 16
        finally:
            c.disconnect()


class TestConnectErrors:
    def test_connect_failure_records_last_error(self):
        # Puerto cerrado: connect() sigue devolviendo False pero deja el motivo.
        c = PS4DBG("127.0.0.1", 1, timeout=0.5)
        assert c.connect() is False
        assert isinstance(c.last_error, OSError)


class TestScanReportsFailedReads:
    def _process_manager(self):
        pm = ProcessManager()
        pmap = ProcessMap(pid=100, entries=[
            MemoryEntry(name="data", start=0x10000000, end=0x10001000, offset=0, prot=0x3),
        ])
        pm.attach(100, "eboot.bin")
        pm.init_sections(pmap)
        pm.mapped_section_list.check_all(True)
        return pm

    def test_failed_chunks_are_skipped_not_zero_filled(self, failing_server):
        from core import CompareType, make_handler

        pool = PS4DBGPool("127.0.0.1", failing_server.port, size=1, timeout=5.0)
        assert pool.connect_all()
        try:
            pm = self._process_manager()
            engine = ScanEngine(pool, pm)
            handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE)
            # 0 es el valor que un zero-fill silencioso hubiese "encontrado" por todas partes.
            count = engine.new_scan(handler, struct.pack("<I", 0))
            assert count == 0
            assert engine.failed_reads == 1
            assert engine.failed_bytes == 0x1000
        finally:
            pool.disconnect_all()


class TestCheatListErrors:
    def test_apply_without_connection_reports_reason(self):
        cl = CheatList(ps4=None, pid=100)
        entry = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337")
        assert cl.apply(entry) is False
        assert cl.last_error is not None

    def test_apply_with_failing_console_reports_reason(self, failing_server):
        c = PS4DBG("127.0.0.1", failing_server.port, timeout=5.0)
        assert c.connect()
        try:
            cl = CheatList(ps4=c, pid=100)
            entry = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="no-es-un-numero")
            assert cl.apply(entry) is False
            assert isinstance(cl.last_error, ValueError)
        finally:
            c.disconnect()

    def test_from_dict_rejects_incomplete_entry(self):
        with pytest.raises(ValueError, match="missing required field"):
            CheatList.from_dict({"pid": 1, "entries": [{"address": 0x100, "value": "1"}]})


class TestProtocolErrors:
    def test_parse_status_rejects_unknown_code(self):
        with pytest.raises(ValueError, match="unknown ps4debug status"):
            P.parse_status(struct.pack("<I", 0x12345678))

    def test_parse_status_rejects_short_buffer(self):
        with pytest.raises(ValueError, match="too short"):
            P.parse_status(b"\x00\x00")
