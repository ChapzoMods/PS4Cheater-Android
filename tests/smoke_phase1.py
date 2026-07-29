#!/usr/bin/env python3
"""
Smoke test rápido para FASE 1: verifica que la serialización del protocolo
funciona sin necesidad de PS4 real.

Uso:
    python3 /home/z/my-project/ps4cheater-android/tests/smoke_phase1.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import protocol as P
from lib import PS4DBG, PS4DBGPool, connect_ps4debug, connect_goldhen

def test_header():
    h = P.build_header(int(P.CMD.CMD_PROC_LIST), 0)
    assert len(h) == 12, f"header must be 12 bytes, got {len(h)}"
    magic, cmd, datalen = P.unpack = __import__("struct").unpack("<III", h)
    assert magic == P.CMD_PACKET_MAGIC, f"magic wrong: 0x{magic:X}"
    assert cmd == int(P.CMD.CMD_PROC_LIST), f"cmd wrong: 0x{cmd:X}"
    assert datalen == 0, f"datalen wrong: {datalen}"
    print("[OK] header serialization")

def test_payloads():
    # CMD_PROC_READ
    p = P.payload_proc_read(pid=100, address=0x7FFFF0000, length=4096)
    assert len(p) == 16, f"proc_read payload must be 16 bytes, got {len(p)}"
    pid, addr, length = __import__("struct").unpack("<IQI", p)
    assert pid == 100 and addr == 0x7FFFF0000 and length == 4096
    print("[OK] payload_proc_read")

    # CMD_PROC_WRITE
    p = P.payload_proc_write(pid=100, address=0x7FFFF0000, length=4)
    assert len(p) == 16
    print("[OK] payload_proc_write")

    # CMD_PROC_INFO / MAPS / INSTALL
    assert len(P.payload_proc_info(5)) == 4
    assert len(P.payload_proc_maps(5)) == 4
    assert len(P.payload_proc_install(5)) == 4
    print("[OK] simple pid payloads")

    # CMD_PROC_ALLOC / FREE / PROTECT
    assert len(P.payload_proc_alloc(5, 0x1000)) == 8
    assert len(P.payload_proc_free(5, 0x1000, 0x1000)) == 16
    assert len(P.payload_proc_protect(5, 0x1000, 0x1000, 0x3)) == 20
    print("[OK] alloc/free/protect payloads")

    # CMD_CONSOLE_NOTIFY
    p = P.payload_console_notify(0, "Hello PS4")
    assert len(p) == 8 + 9  # type + length + msg
    print("[OK] console_notify payload")

def test_parse_process_list():
    # 2 procesos fake
    p1_name = b"eboot.bin\x00" + b"\x00" * 22  # 32 bytes
    p1_pid = (1234).to_bytes(4, "little")
    p2_name = b"SceShellUI\x00" + b"\x00" * 21
    p2_pid = (5678).to_bytes(4, "little")
    data = p1_name + p1_pid + p2_name + p2_pid
    procs = P.parse_process_list(data)
    assert len(procs) == 2
    assert procs[0].name == "eboot.bin" and procs[0].pid == 1234
    assert procs[1].name == "SceShellUI" and procs[1].pid == 5678
    print(f"[OK] parse_process_list -> {procs[0]} / {procs[1]}")

def test_parse_process_info():
    import struct
    data = struct.pack("<i", 100)                       # pid (4)
    data += b"eboot.bin\x00" + b"\x00" * 30             # name[40]  (9+1+30=40)
    data += b"/system/vsh/app\x00" + b"\x00" * 48       # path[64]  (15+1+48=64)
    data += b"CUSA00001\x00" + b"\x00" * 6              # titleid[16] (9+1+6=16)
    data += b"UP0001-CUSA00001\x00" + b"\x00" * 47      # contentid[64] (16+1+47=64)
    assert len(data) == P.PROC_PROC_INFO_SIZE, f"len={len(data)}"
    info = P.parse_process_info(data)
    assert info.pid == 100
    assert info.name == "eboot.bin"
    assert info.path == "/system/vsh/app"
    assert info.titleid == "CUSA00001"
    assert info.contentid == "UP0001-CUSA00001"
    print(f"[OK] parse_process_info -> pid={info.pid} titleid={info.titleid}")

def test_parse_process_maps():
    import struct
    e1 = b"executable\x00" + b"\x00" * 21               # name[32]
    e1 += struct.pack("<QQQH", 0x400000, 0x500000, 0, 0x5)
    e2 = b"data\x00" + b"\x00" * 27
    e2 += struct.pack("<QQQH", 0x10000000, 0x10010000, 0, 0x3)
    data = e1 + e2
    assert len(data) == 2 * P.PROC_MAP_ENTRY_SIZE
    entries = P.parse_process_maps(data)
    assert len(entries) == 2
    assert entries[0].name == "executable"
    assert entries[0].start == 0x400000
    assert entries[0].end == 0x500000
    assert entries[0].prot == 0x5
    assert entries[0].readable and entries[0].executable and not entries[0].writable
    assert entries[1].readable and entries[1].writable and not entries[1].executable
    print(f"[OK] parse_process_maps -> {entries[0].name} {entries[0]} / {entries[1].name} {entries[1]}")

def test_ps4dbg_class():
    # Verifica que la clase se construye correctamente sin conectar
    c = PS4DBG(ip="192.168.1.100", port=744)
    assert not c.is_connected
    assert c.ip == "192.168.1.100"
    assert c.port == 744
    print(f"[OK] PS4DBG constructor (no connect): {c.ip}:{c.port}")

    pool = PS4DBGPool(ip="192.168.1.100", port=744, size=3)
    assert len(pool._connections) == 3
    assert all(not c.is_connected for c in pool._connections)
    print(f"[OK] PS4DBGPool size=3")

    g = connect_goldhen("192.168.1.100")
    assert g.port == 9090
    print(f"[OK] connect_goldhen port={g.port}")

    p = connect_ps4debug("192.168.1.100")
    assert p.port == 744
    print(f"[OK] connect_ps4debug port={p.port}")

if __name__ == "__main__":
    print("=== FASE 1 Smoke Tests ===")
    test_header()
    test_payloads()
    test_parse_process_list()
    test_parse_process_info()
    test_parse_process_maps()
    test_ps4dbg_class()
    print("\n✅ Todos los smoke tests de FASE 1 pasan.")
