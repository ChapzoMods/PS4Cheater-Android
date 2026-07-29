"""Tests del protocolo: serialización, parsing, payloads."""
import struct
import pytest

from lib import protocol as P
from lib import CMD, CMD_STATUS, VMProtection, PS4DBG_PORT, GOLDHEN_PORT


class TestConstants:
    def test_magic(self):
        assert P.CMD_PACKET_MAGIC == 0xFFAABBCC

    def test_packet_size(self):
        assert P.CMD_PACKET_SIZE == 12

    def test_net_max_length(self):
        assert P.NET_MAX_LENGTH == 0x20000

    def test_ports(self):
        assert PS4DBG_PORT == 744
        assert GOLDHEN_PORT == 9090
        assert P.BROADCAST_PORT == 1010
        assert P.BROADCAST_MAGIC == 0xFFFFAAAA

    def test_cmd_codes(self):
        assert int(CMD.CMD_VERSION) == 0xBD000001
        assert int(CMD.CMD_PROC_LIST) == 0xBDAA0001
        assert int(CMD.CMD_PROC_READ) == 0xBDAA0002
        assert int(CMD.CMD_PROC_WRITE) == 0xBDAA0003
        assert int(CMD.CMD_PROC_MAPS) == 0xBDAA0004
        assert int(CMD.CMD_PROC_INFO) == 0xBDAA000A
        assert int(CMD.CMD_CONSOLE_END) == 0xBDDD0002

    def test_status_codes(self):
        assert int(CMD_STATUS.CMD_SUCCESS) == 0x80000000
        assert int(CMD_STATUS.CMD_ERROR) == 0xF0000001
        assert int(CMD_STATUS.CMD_INVALID_INDEX) == 0xF0000005

    def test_vm_protection_flags(self):
        assert int(VMProtection.VM_PROT_READ) == 0x1
        assert int(VMProtection.VM_PROT_WRITE) == 0x2
        assert int(VMProtection.VM_PROT_EXECUTE) == 0x4
        assert int(VMProtection.VM_PROT_ALL) == 0x7

    def test_struct_sizes(self):
        assert P.PROC_LIST_ENTRY_SIZE == 36
        assert P.PROC_MAP_ENTRY_SIZE == 58
        assert P.PROC_PROC_INFO_SIZE == 188


class TestSerialization:
    def test_build_header(self):
        h = P.build_header(int(CMD.CMD_PROC_LIST), 0)
        assert len(h) == 12
        magic, cmd, datalen = struct.unpack("<III", h)
        assert magic == P.CMD_PACKET_MAGIC
        assert cmd == int(CMD.CMD_PROC_LIST)
        assert datalen == 0

    def test_build_packet(self):
        p = P.build_packet(int(CMD.CMD_PROC_READ), b"\x00" * 16)
        assert len(p) == 12 + 16
        magic, cmd, datalen = struct.unpack("<III", p[:12])
        assert magic == P.CMD_PACKET_MAGIC
        assert cmd == int(CMD.CMD_PROC_READ)
        assert datalen == 16

    def test_parse_status(self):
        assert P.parse_status(b"\x00\x00\x00\x80") == CMD_STATUS.CMD_SUCCESS
        assert P.parse_status(b"\x01\x00\x00\xF0") == CMD_STATUS.CMD_ERROR
        assert P.parse_status(b"\x05\x00\x00\xF0") == CMD_STATUS.CMD_INVALID_INDEX

    def test_cstr(self):
        assert P.cstr(b"hello\x00world") == "hello"
        assert P.cstr(b"hello\x00world", 6) == "world"
        assert P.cstr(b"no null here") == "no null here"
        assert P.cstr(b"", 0) == ""


class TestPayloads:
    def test_payload_proc_read(self):
        p = P.payload_proc_read(100, 0x10000000, 4096)
        assert len(p) == 16
        pid, addr, length = struct.unpack("<IQI", p)
        assert pid == 100
        assert addr == 0x10000000
        assert length == 4096

    def test_payload_proc_write(self):
        p = P.payload_proc_write(100, 0x10000000, 4)
        assert len(p) == 16

    def test_payload_proc_info(self):
        p = P.payload_proc_info(100)
        assert len(p) == 4
        assert struct.unpack("<i", p)[0] == 100

    def test_payload_proc_maps(self):
        p = P.payload_proc_maps(100)
        assert len(p) == 4

    def test_payload_proc_alloc(self):
        p = P.payload_proc_alloc(100, 4096)
        assert len(p) == 8
        pid, length = struct.unpack("<ii", p)
        assert pid == 100 and length == 4096

    def test_payload_proc_free(self):
        p = P.payload_proc_free(100, 0x10000000, 4096)
        assert len(p) == 16

    def test_payload_proc_protect(self):
        p = P.payload_proc_protect(100, 0x10000000, 4096, 0x3)
        assert len(p) == 20

    def test_payload_proc_scan(self):
        p = P.payload_proc_scan(100, 4, 0, 4)  # uint32, exact, length=4
        assert len(p) == 10

    def test_payload_console_notify(self):
        p = P.payload_console_notify(0, "Hello PS4")
        assert len(p) == 8 + 9  # type + length + msg
        ntype, mlen = struct.unpack("<II", p[:8])
        assert ntype == 0 and mlen == 9
        assert p[8:] == b"Hello PS4"


class TestParseProcessList:
    def test_empty(self):
        assert P.parse_process_list(b"") == []

    def test_single(self):
        data = b"eboot.bin\x00" + b"\x00" * 22 + struct.pack("<i", 100)
        procs = P.parse_process_list(data)
        assert len(procs) == 1
        assert procs[0].name == "eboot.bin"
        assert procs[0].pid == 100

    def test_multiple(self):
        data = (
            b"eboot.bin\x00" + b"\x00" * 22 + struct.pack("<i", 100) +
            b"SceShellUI\x00" + b"\x00" * 21 + struct.pack("<i", 200)
        )
        procs = P.parse_process_list(data)
        assert len(procs) == 2
        assert procs[0].name == "eboot.bin"
        assert procs[0].pid == 100
        assert procs[1].name == "SceShellUI"
        assert procs[1].pid == 200


class TestParseProcessInfo:
    def test_full(self):
        # Layout: pid(4) + name[40] + path[64] + titleid[16] + contentid[64] = 188 bytes
        data = struct.pack("<i", 100)  # pid (4)
        data += b"eboot.bin\x00" + b"\x00" * 30  # name[40] = 9 + 1 + 30
        data += b"/system/vsh/app\x00" + b"\x00" * 48  # path[64] = 15 + 1 + 48
        data += b"CUSA00001\x00" + b"\x00" * 6  # titleid[16] = 9 + 1 + 6
        data += b"UP0001-CUSA00001\x00" + b"\x00" * 47  # contentid[64] = 16 + 1 + 47
        assert len(data) == P.PROC_PROC_INFO_SIZE
        info = P.parse_process_info(data)
        assert info.pid == 100
        assert info.name == "eboot.bin"
        assert info.path == "/system/vsh/app"
        assert info.titleid == "CUSA00001"
        assert info.contentid == "UP0001-CUSA00001"

    def test_short_buffer_raises(self):
        with pytest.raises(ValueError):
            P.parse_process_info(b"short")


class TestParseProcessMaps:
    def test_single_entry(self):
        data = b"executable\x00" + b"\x00" * 21
        data += struct.pack("<QQQH", 0x400000, 0x401000, 0, 0x5)
        entries = P.parse_process_maps(data)
        assert len(entries) == 1
        e = entries[0]
        assert e.name == "executable"
        assert e.start == 0x400000
        assert e.end == 0x401000
        assert e.prot == 0x5
        assert e.readable
        assert e.executable
        assert not e.writable
        assert e.length == 0x1000

    def test_multiple_entries(self):
        data = (
            b"executable\x00" + b"\x00" * 21 + struct.pack("<QQQH", 0x400000, 0x401000, 0, 0x5) +
            b"data\x00" + b"\x00" * 27 + struct.pack("<QQQH", 0x10000000, 0x10001000, 0, 0x3)
        )
        entries = P.parse_process_maps(data)
        assert len(entries) == 2
        assert entries[0].executable
        assert entries[1].writable and not entries[1].executable


class TestMemoryEntry:
    def test_protection_helpers(self):
        e = P.MemoryEntry(name="x", start=0, end=0x1000, offset=0, prot=0x7)
        assert e.readable and e.writable and e.executable

        e = P.MemoryEntry(name="x", start=0, end=0x1000, offset=0, prot=0x0)
        assert not e.readable and not e.writable and not e.executable

    def test_length(self):
        e = P.MemoryEntry(name="x", start=0x1000, end=0x2000, offset=0, prot=0x3)
        assert e.length == 0x1000

    def test_str(self):
        e = P.MemoryEntry(name="data", start=0x10000000, end=0x10001000, offset=0, prot=0x3)
        s = str(e)
        assert "data" in s
        assert "rw-" in s
        assert "0x0000000010000000" in s
