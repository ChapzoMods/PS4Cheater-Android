"""
Tests de cli/main.py — helpers puros, estado de Session, y comandos Click.

El módulo cli.main mantiene un objeto global `session` y persiste estado en
archivos ~/.ps4cheater_*.json. Los tests aíslan ese estado redirigiendo las
constantes de ruta a un tmp_path y reemplazando el `session` global por una
instancia fresca.
"""
import json
import struct

import pytest
from click.testing import CliRunner

from cli import main as cli_main
from cli.main import (
    Session, cli,
    parse_address, parse_hex_bytes, hexdump, format_value,
)
from core import ValueType, CompareType, make_handler, ScanEngine
from lib import ProcessMap, MemoryEntry, Process


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirige los archivos de estado a tmp_path y resetea el session global."""
    session_file = str(tmp_path / "session.json")
    scan_file = str(tmp_path / "scan.json")
    cheats_file = str(tmp_path / "cheats.json")
    monkeypatch.setattr(cli_main, "SESSION_FILE", session_file)
    monkeypatch.setattr(cli_main, "SCAN_STATE_FILE", scan_file)
    monkeypatch.setattr(cli_main, "CHEATS_FILE", cheats_file)
    fresh = Session()
    monkeypatch.setattr(cli_main, "session", fresh)
    return {
        "session": fresh,
        "session_file": session_file,
        "scan_file": scan_file,
        "cheats_file": cheats_file,
    }


class FakePS4:
    """Cliente PS4DBG falso para comandos que requieren conexión."""
    def __init__(self, procs=None, maps=None):
        self._procs = procs or []
        self._maps = maps
        self.notifications = []
        self.reboots = 0
        self.reads = []
        self.writes = []
        self.disconnected = False
        self.is_connected = True

    def get_console_debug_version(self):
        return "1.0.0-fake"

    def get_process_list(self):
        return list(self._procs)

    def get_process_maps(self, pid):
        return self._maps or ProcessMap(pid=pid, entries=[])

    def read_memory(self, pid, addr, length):
        self.reads.append((pid, addr, length))
        return b"\xAA" * length

    def write_memory(self, pid, addr, data):
        self.writes.append((pid, addr, bytes(data)))

    def notify(self, notice_type, message):
        self.notifications.append((notice_type, message))

    def reboot(self):
        self.reboots += 1

    def disconnect(self):
        self.disconnected = True


def _sample_map(pid=100):
    return ProcessMap(pid=pid, entries=[
        MemoryEntry(name="data", start=0x10000000, end=0x10001000, offset=0, prot=0x3),
        MemoryEntry(name="code", start=0x20000000, end=0x20001000, offset=0, prot=0x5),
    ])


class FakePool:
    """Pool que devuelve memoria generada proceduralmente (igual que test_scanner)."""
    def __init__(self, memory):
        self.memory = memory

    def get(self, idx=0):
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


# ---------------------------------------------------------------------------
# parse_address
# ---------------------------------------------------------------------------

class TestParseAddress:
    def test_hex_prefixed(self):
        assert parse_address("0x10000000") == 0x10000000
        assert parse_address("0X1A") == 0x1A

    def test_hex_with_letters(self):
        assert parse_address("DEADBEEF") == 0xDEADBEEF
        assert parse_address("1a2b") == 0x1A2B

    def test_small_decimal(self):
        assert parse_address("100") == 100
        assert parse_address("0") == 0

    def test_large_decimal_treated_as_hex(self):
        # > 0x10000 y ambiguo → se interpreta como hex
        assert parse_address("1000000") == 0x1000000

    def test_boundary_at_0x10000(self):
        # 65536 == 0x10000, no es > 0x10000 → se mantiene decimal
        assert parse_address("65536") == 65536
        # 65537 > 0x10000 y ambiguo → se interpreta como hex
        assert parse_address("65537") == 0x65537

    def test_whitespace_stripped(self):
        assert parse_address("  0x40  ") == 0x40


# ---------------------------------------------------------------------------
# parse_hex_bytes
# ---------------------------------------------------------------------------

class TestParseHexBytes:
    def test_plain(self):
        assert parse_hex_bytes("AABBCCDD") == b"\xAA\xBB\xCC\xDD"

    def test_with_spaces(self):
        assert parse_hex_bytes("AA BB CC DD") == b"\xAA\xBB\xCC\xDD"

    def test_with_0x_prefix(self):
        assert parse_hex_bytes("0xAABB") == b"\xAA\xBB"

    def test_with_tabs(self):
        assert parse_hex_bytes("AA\tBB") == b"\xAA\xBB"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_hex_bytes("ZZ")


# ---------------------------------------------------------------------------
# hexdump
# ---------------------------------------------------------------------------

class TestHexdump:
    def test_single_line(self):
        out = hexdump(b"\x41\x42\x43", base_addr=0x1000)
        assert out.startswith("0000000000001000")
        assert "41 42 43" in out
        assert "|ABC|" in out

    def test_non_printable_shown_as_dot(self):
        out = hexdump(b"\x00\x01\x02")
        assert "|...|" in out

    def test_multi_line(self):
        data = bytes(range(32))
        out = hexdump(data, base_addr=0)
        lines = out.split("\n")
        assert len(lines) == 2

    def test_empty(self):
        assert hexdump(b"") == ""


# ---------------------------------------------------------------------------
# format_value
# ---------------------------------------------------------------------------

class TestFormatValue:
    def test_uint32(self):
        assert format_value(struct.pack("<I", 1337), ValueType.UINT_TYPE) == "1337"

    def test_byte(self):
        assert format_value(struct.pack("<B", 42), ValueType.BYTE_TYPE) == "42"


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

class TestSessionPersistence:
    def test_save_and_load_roundtrip(self, isolated_state):
        s = isolated_state["session"]
        s.ip = "192.168.1.50"
        s.port = 9090
        s.pid = 1234
        s.proc_name = "eboot.bin"
        s.section_checks = [True, False, True]
        s.save()

        s2 = Session()
        s2.load()
        assert s2.ip == "192.168.1.50"
        assert s2.port == 9090
        assert s2.pid == 1234
        assert s2.proc_name == "eboot.bin"
        assert s2.section_checks == [True, False, True]

    def test_load_missing_file_is_noop(self, isolated_state):
        s = Session()
        s.load()  # no debe lanzar
        assert s.ip == ""

    def test_load_corrupt_file_is_noop(self, isolated_state):
        with open(isolated_state["session_file"], "w") as f:
            f.write("{not valid json")
        s = Session()
        s.load()
        assert s.ip == ""

    def test_attach_persists(self, isolated_state):
        s = isolated_state["session"]
        s.attach(777, "game.bin")
        assert s.pid == 777
        assert s.proc_name == "game.bin"
        assert s.cheats.pid == 777
        s2 = Session()
        s2.load()
        assert s2.pid == 777

    def test_disconnect_without_connection(self, isolated_state):
        s = isolated_state["session"]
        s.disconnect()  # no debe lanzar aunque no haya conexión
        assert not s.connected


# ---------------------------------------------------------------------------
# Section checks sync/capture
# ---------------------------------------------------------------------------

class TestSectionChecks:
    def test_capture_and_sync(self, isolated_state):
        s = isolated_state["session"]
        s.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        assert s.pm.section_count == 2
        s.pm.mapped_section_list.section_check(0, True)
        s.capture_section_checks()
        assert s.section_checks == [True, False]

        # Nuevo session con los mismos checks debe re-aplicarlos
        s2 = Session()
        s2.section_checks = [True, False]
        s2.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s2.sync_section_checks_to_pm()
        assert s2.pm.mapped_section_list[0].check is True
        assert s2.pm.mapped_section_list[1].check is False

    def test_sync_empty_is_noop(self, isolated_state):
        s = isolated_state["session"]
        s.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s.section_checks = []
        s.sync_section_checks_to_pm()  # no debe lanzar


# ---------------------------------------------------------------------------
# Scan state persistence
# ---------------------------------------------------------------------------

class TestScanStatePersistence:
    def test_save_scan_state_no_handler_noop(self, isolated_state):
        s = isolated_state["session"]
        s.save_scan_state()  # handler None → no escribe
        assert not __import__("os").path.exists(isolated_state["scan_file"])

    def test_load_scan_state_missing(self, isolated_state):
        s = isolated_state["session"]
        assert s.load_scan_state() is False

    def test_save_and_load_scan_state_roundtrip(self, isolated_state):
        s = isolated_state["session"]
        s.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s.pm.mapped_section_list.check_all(True)
        # poblar un ResultList en la sección 0
        from core import ResultList
        section = s.pm.mapped_section_list[0]
        section.result_list = ResultList(4, 4)
        section.result_list.add(0, struct.pack("<I", 1337))
        section.result_list.add(4, struct.pack("<I", 42))
        s.handler = make_handler(ValueType.UINT_TYPE, CompareType.EXACT_VALUE, is_aligned=True)

        s.save_scan_state()

        s2 = Session()
        s2.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s2.pm.mapped_section_list.check_all(True)
        assert s2.load_scan_state() is True
        assert s2.handler is not None
        assert s2.handler.value_type == ValueType.UINT_TYPE
        total = s2.pm.mapped_section_list.total_result_count()
        assert total == 2

    def test_clear_scan_state(self, isolated_state):
        s = isolated_state["session"]
        with open(isolated_state["scan_file"], "w") as f:
            f.write("{}")
        s.clear_scan_state()
        import os
        assert not os.path.exists(isolated_state["scan_file"])

    def test_load_corrupt_scan_state(self, isolated_state):
        s = isolated_state["session"]
        with open(isolated_state["scan_file"], "w") as f:
            f.write("garbage")
        assert s.load_scan_state() is False


# ---------------------------------------------------------------------------
# Cheats persistence
# ---------------------------------------------------------------------------

class TestCheatsPersistence:
    def test_save_and_load_cheats(self, isolated_state):
        s = isolated_state["session"]
        s.cheats.add(address=0x10000000, value_type=ValueType.UINT_TYPE,
                     value="9999", description="HP")
        s.save_cheats()

        s.cheats.clear()
        assert len(s.cheats) == 0
        s.load_cheats()
        assert len(s.cheats) == 1
        assert s.cheats.entries[0].description == "HP"

    def test_load_cheats_missing_noop(self, isolated_state):
        s = isolated_state["session"]
        s.load_cheats()  # no debe lanzar
        assert len(s.cheats) == 0


# ---------------------------------------------------------------------------
# Click commands (CliRunner)
# ---------------------------------------------------------------------------

class TestCliMeta:
    def test_version(self):
        result = CliRunner().invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.5.2" in result.output

    def test_help(self):
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "connect" in result.output


class TestStatusCommand:
    def test_status_disconnected(self, isolated_state):
        result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Estado" in result.output


class TestConnectCommand:
    def test_connect_success(self, isolated_state, monkeypatch):
        fake = FakePS4()

        class FakePool:
            def __init__(self, *a, **k):
                pass

            def connect_all(self):
                return True

            def disconnect_all(self):
                pass

        monkeypatch.setattr(cli_main, "PS4DBGPool", FakePool)
        monkeypatch.setattr(cli_main, "PS4DBG", lambda ip, port, timeout=30.0: _ConnectableFake(fake))

        result = CliRunner().invoke(cli, ["connect", "192.168.1.10"])
        assert result.exit_code == 0
        assert "Conectado" in result.output
        assert isolated_state["session"].connected

    def test_connect_failure(self, isolated_state, monkeypatch):
        class FailingClient:
            def connect(self):
                return False

        monkeypatch.setattr(cli_main, "PS4DBG", lambda *a, **k: FailingClient())
        result = CliRunner().invoke(cli, ["connect", "10.0.0.1"])
        assert result.exit_code == 1
        assert "No se pudo conectar" in result.output


class _ConnectableFake:
    """Envuelve un FakePS4 añadiendo connect() -> True."""
    def __init__(self, inner):
        self._inner = inner

    def connect(self):
        return True

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestCommandsRequireConnection:
    def test_procs_not_connected(self, isolated_state):
        result = CliRunner().invoke(cli, ["procs"])
        assert result.exit_code == 1
        assert "No conectado" in result.output

    def test_read_not_connected(self, isolated_state):
        result = CliRunner().invoke(cli, ["read", "0x10000000", "16"])
        assert result.exit_code == 1
        assert "No conectado" in result.output

    def test_notify_not_connected(self, isolated_state):
        result = CliRunner().invoke(cli, ["notify", "hola"])
        assert result.exit_code == 1


class TestCommandsWithFakeConnection:
    def _prime(self, isolated_state, monkeypatch, maps=None, procs=None):
        s = isolated_state["session"]
        fake = FakePS4(procs=procs, maps=maps)
        s.ps4 = fake
        s.connected = True
        s.pid = 100
        s.proc_name = "eboot.bin"
        return fake

    def test_procs(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch,
                           procs=[Process(name="eboot.bin", pid=100),
                                  Process(name="SceShellCore", pid=42)])
        result = CliRunner().invoke(cli, ["procs"])
        assert result.exit_code == 0
        assert "eboot.bin" in result.output
        assert "100" in result.output

    def test_attach_by_pid(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch,
                           procs=[Process(name="eboot.bin", pid=100)],
                           maps=_sample_map())
        s = isolated_state["session"]
        s.pid = 0
        result = CliRunner().invoke(cli, ["attach", "100"])
        assert result.exit_code == 0
        assert "Attacheado" in result.output
        assert s.pid == 100

    def test_attach_by_name(self, isolated_state, monkeypatch):
        self._prime(isolated_state, monkeypatch,
                    procs=[Process(name="eboot.bin", pid=100)],
                    maps=_sample_map())
        s = isolated_state["session"]
        s.pid = 0
        result = CliRunner().invoke(cli, ["attach", "eboot"])
        assert result.exit_code == 0
        assert s.pid == 100

    def test_attach_not_found(self, isolated_state, monkeypatch):
        self._prime(isolated_state, monkeypatch,
                    procs=[Process(name="eboot.bin", pid=100)])
        s = isolated_state["session"]
        s.pid = 0
        result = CliRunner().invoke(cli, ["attach", "nope"])
        assert result.exit_code == 1
        assert "no encontrado" in result.output

    def test_read(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch, maps=_sample_map())
        result = CliRunner().invoke(cli, ["read", "0x10000000", "8"])
        assert result.exit_code == 0
        assert fake.reads[-1] == (100, 0x10000000, 8)

    def test_write(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch, maps=_sample_map())
        result = CliRunner().invoke(cli, ["write", "0x10000000", "DEADBEEF"])
        assert result.exit_code == 0
        assert fake.writes[-1] == (100, 0x10000000, b"\xDE\xAD\xBE\xEF")

    def test_write_invalid_hex(self, isolated_state, monkeypatch):
        self._prime(isolated_state, monkeypatch, maps=_sample_map())
        result = CliRunner().invoke(cli, ["write", "0x10000000", "ZZZ"])
        assert result.exit_code == 1
        assert "hex inválido" in result.output

    def test_notify(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch)
        result = CliRunner().invoke(cli, ["notify", "hola", "--type", "2"])
        assert result.exit_code == 0
        assert fake.notifications[-1] == (2, "hola")

    def test_reboot_confirmed(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch)
        result = CliRunner().invoke(cli, ["reboot"], input="y\n")
        assert result.exit_code == 0
        assert fake.reboots == 1

    def test_reboot_declined(self, isolated_state, monkeypatch):
        fake = self._prime(isolated_state, monkeypatch)
        result = CliRunner().invoke(cli, ["reboot"], input="n\n")
        assert result.exit_code == 0
        assert fake.reboots == 0

    def test_disconnect(self, isolated_state, monkeypatch):
        self._prime(isolated_state, monkeypatch)
        result = CliRunner().invoke(cli, ["disconnect"])
        assert result.exit_code == 0
        assert "Desconectado" in result.output
        assert not isolated_state["session"].connected


class TestCheatCommands:
    def test_cheat_list_empty(self, isolated_state):
        result = CliRunner().invoke(cli, ["cheat", "list"])
        assert result.exit_code == 0
        assert "No hay cheats" in result.output

    def test_cheat_list_populated(self, isolated_state):
        s = isolated_state["session"]
        s.cheats.add(address=0x10000000, value_type=ValueType.UINT_TYPE,
                     value="9999", description="HP")
        result = CliRunner().invoke(cli, ["cheat", "list"])
        assert result.exit_code == 0
        assert "HP" in result.output

    def test_cheat_remove_found(self, isolated_state):
        s = isolated_state["session"]
        e = s.cheats.add(address=0x1, value_type=ValueType.UINT_TYPE, value="1")
        result = CliRunner().invoke(cli, ["cheat", "remove", str(e.id)])
        assert result.exit_code == 0
        assert "eliminado" in result.output
        assert len(s.cheats) == 0

    def test_cheat_remove_not_found(self, isolated_state):
        result = CliRunner().invoke(cli, ["cheat", "remove", "999"])
        assert result.exit_code == 0
        assert "no encontrado" in result.output


class TestExportImport:
    def test_export_empty(self, isolated_state):
        result = CliRunner().invoke(cli, ["export", "/tmp/none.json"])
        assert result.exit_code == 0
        assert "No hay cheats" in result.output

    def test_export_and_import_json(self, isolated_state, tmp_path):
        s = isolated_state["session"]
        s.cheats.add(address=0x10000000, value_type=ValueType.UINT_TYPE,
                     value="1234", description="gold")
        out = str(tmp_path / "table.json")
        r1 = CliRunner().invoke(cli, ["export", out])
        assert r1.exit_code == 0
        assert "exportados" in r1.output

        # limpiar e importar
        s.cheats.clear()
        r2 = CliRunner().invoke(cli, ["import", out])
        assert r2.exit_code == 0
        assert "importados" in r2.output
        assert len(s.cheats) == 1
        assert s.cheats.entries[0].description == "gold"

    def test_import_merge(self, isolated_state, tmp_path):
        s = isolated_state["session"]
        s.cheats.add(address=0x1, value_type=ValueType.UINT_TYPE, value="1")
        out = str(tmp_path / "t.json")
        CliRunner().invoke(cli, ["export", out])
        # con --merge se agregan al existente
        r = CliRunner().invoke(cli, ["import", out, "--merge"])
        assert r.exit_code == 0
        assert len(s.cheats) == 2

    def test_import_missing_file(self, isolated_state):
        r = CliRunner().invoke(cli, ["import", "/nonexistent/x.json"])
        assert r.exit_code == 0
        assert "❌" in r.output


class TestScanCommands:
    def _prime_scan(self, isolated_state):
        """Prepara una sesión attacheada con ScanEngine sobre memoria falsa."""
        s = isolated_state["session"]
        mem = bytearray(256)
        for off in (4, 16, 32, 60):
            struct.pack_into("<I", mem, off, 1337)
        pool = FakePool({0x10000000: bytes(mem)})
        s.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s.pm.mapped_section_list.check_all(True)
        s.capture_section_checks()
        s.scan_engine = ScanEngine(pool, s.pm, peek_buffer_length=1024 * 1024,
                                   num_comparers=1)
        s.ps4 = FakePS4(maps=_sample_map())
        s.connected = True
        s.pid = 100
        s.proc_name = "eboot.bin"
        return s, pool, mem

    def test_scan_new_exact(self, isolated_state):
        s, _pool, _mem = self._prime_scan(isolated_state)
        result = CliRunner().invoke(cli, ["scan", "new", "uint32", "exact", "1337"])
        assert result.exit_code == 0
        assert "4 resultado" in result.output
        assert s.pm.mapped_section_list.total_result_count() == 4

    def test_scan_new_bad_type(self, isolated_state):
        self._prime_scan(isolated_state)
        result = CliRunner().invoke(cli, ["scan", "new", "notatype", "exact", "1"])
        assert result.exit_code == 1

    def test_scan_results(self, isolated_state):
        self._prime_scan(isolated_state)
        CliRunner().invoke(cli, ["scan", "new", "uint32", "exact", "1337"])
        result = CliRunner().invoke(cli, ["scan", "results"])
        assert result.exit_code == 0
        assert "Resultados" in result.output
        assert "1337" in result.output

    def test_scan_next_changed(self, isolated_state):
        s, pool, mem = self._prime_scan(isolated_state)
        CliRunner().invoke(cli, ["scan", "new", "uint32", "exact", "1337"])
        # modificar 2 de los 4
        struct.pack_into("<I", mem, 16, 9999)
        struct.pack_into("<I", mem, 60, 8888)
        pool.memory[0x10000000] = bytes(mem)
        result = CliRunner().invoke(cli, ["scan", "next", "changed"])
        assert result.exit_code == 0
        assert "2 resultado" in result.output

    def test_scan_next_without_prior(self, isolated_state):
        self._prime_scan(isolated_state)
        result = CliRunner().invoke(cli, ["scan", "next", "changed"])
        assert result.exit_code == 1
        assert "No hay scan previo" in result.output


class TestPointerScanCommand:
    def test_pointer_scan(self, isolated_state):
        s = isolated_state["session"]
        mem = bytearray(64)
        struct.pack_into("<Q", mem, 0, 0x10000008)
        struct.pack_into("<Q", mem, 8, 0x10000000)
        pool = FakePool({0x10000000: bytes(mem)})
        s.pm.init_sections(
            ProcessMap(pid=100, entries=[
                MemoryEntry(name="data", start=0x10000000, end=0x10000040, offset=0, prot=0x3),
            ]),
            buffer_length=1024 * 1024)
        s.pm.mapped_section_list.check_all(True)
        s.scan_engine = ScanEngine(pool, s.pm, peek_buffer_length=1024 * 1024,
                                   num_comparers=1)
        s.ps4 = FakePS4()
        s.connected = True
        s.pid = 100
        s.proc_name = "eboot.bin"
        result = CliRunner().invoke(cli, ["pointer", "scan", "0x10000000"])
        assert result.exit_code == 0
        assert "punteros encontrados" in result.output

    def test_pointer_scan_bad_depth(self, isolated_state):
        s = isolated_state["session"]
        s.pm.init_sections(_sample_map(), buffer_length=1024 * 1024)
        s.scan_engine = ScanEngine(FakePool({}), s.pm, num_comparers=1)
        s.ps4 = FakePS4()
        s.connected = True
        s.pid = 100
        s.proc_name = "eboot.bin"
        result = CliRunner().invoke(cli, ["pointer", "scan", "0x10000000", "--depth", "9"])
        assert result.exit_code == 1
        assert "depth" in result.output


class TestCheatApplyFreeze:
    def _prime(self, isolated_state):
        s = isolated_state["session"]
        fake = FakePS4(maps=_sample_map())
        s.ps4 = fake
        s.connected = True
        s.pid = 100
        s.proc_name = "eboot.bin"
        s.cheats.ps4 = fake
        s.cheats.pid = 100
        return s, fake

    def test_cheat_add_no_freeze(self, isolated_state):
        s, fake = self._prime(isolated_state)
        result = CliRunner().invoke(
            cli, ["cheat", "add", "0x10000000", "uint32", "9999", "--desc", "HP"])
        assert result.exit_code == 0
        assert len(s.cheats) == 1
        assert fake.writes  # se aplicó (write_memory)

    def test_cheat_apply(self, isolated_state):
        s, fake = self._prime(isolated_state)
        e = s.cheats.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="42")
        result = CliRunner().invoke(cli, ["cheat", "apply", str(e.id)])
        assert result.exit_code == 0
        assert "aplicado" in result.output

    def test_cheat_apply_not_found(self, isolated_state):
        self._prime(isolated_state)
        result = CliRunner().invoke(cli, ["cheat", "apply", "999"])
        assert result.exit_code == 1
        assert "no encontrado" in result.output

    def test_cheat_freeze_toggle(self, isolated_state):
        s, fake = self._prime(isolated_state)
        e = s.cheats.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="42")
        try:
            result = CliRunner().invoke(cli, ["cheat", "freeze", str(e.id), "on"])
            assert result.exit_code == 0
            assert "freeze=on" in result.output
        finally:
            if s.cheats.freeze_running:
                s.cheats.stop_freeze_loop()

    def test_cheat_freeze_not_found(self, isolated_state):
        self._prime(isolated_state)
        result = CliRunner().invoke(cli, ["cheat", "freeze", "999", "off"])
        assert result.exit_code == 0
        assert "no encontrado" in result.output
