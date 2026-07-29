#!/usr/bin/env python3
"""
Test de integración de FASE 1 contra el mock server.
Valida el handshake completo del protocolo ps4debug:
  - get_console_debug_version
  - get_process_list
  - get_process_info
  - get_process_maps
  - read_memory  (debe devolver 0xCAFEBABE en la data section)
  - write_memory (escribe y relee)

Requiere que el mock server esté corriendo:
    python3 tests/mock_server_min.py &
"""
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import PS4DBG, PS4DBGError

HOST = "127.0.0.1"
PORT = 1744


def wait_for_server(timeout: float = 5.0):
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((HOST, PORT))
            s.close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    # Lanzar mock server en background si no está corriendo
    mock_proc = None
    if not wait_for_server(timeout=0.5):
        print("[test] lanzando mock server…")
        mock_path = os.path.join(os.path.dirname(__file__), "mock_server_min.py")
        mock_proc = subprocess.Popen([sys.executable, mock_path],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not wait_for_server(timeout=5.0):
            print("❌ No se pudo iniciar el mock server")
            if mock_proc:
                mock_proc.terminate()
            sys.exit(1)

    try:
        client = PS4DBG(HOST, PORT, timeout=5.0)
        if not client.connect():
            print("❌ No se pudo conectar al mock server")
            return 1
        print(f"[OK] connect -> {client.ip}:{client.port}")

        # version
        ver = client.get_console_debug_version()
        print(f"[OK] get_console_debug_version -> {ver!r}")
        assert ver == "ps4d-1.0.0", f"version wrong: {ver}"

        # process list
        procs = client.get_process_list()
        print(f"[OK] get_process_list -> {len(procs)} proceso(s)")
        for p in procs:
            print(f"     {p}")
        assert len(procs) == 1
        assert procs[0].pid == 100
        assert procs[0].name == "eboot.bin"

        # process info
        info = client.get_process_info(100)
        print(f"[OK] get_process_info -> pid={info.pid} titleid={info.titleid}")
        assert info.pid == 100
        assert info.titleid == "CUSA00001"

        # process maps
        pmap = client.get_process_maps(100)
        print(f"[OK] get_process_maps -> {len(pmap.entries)} entradas")
        for e in pmap.entries:
            print(f"     {e}")
        assert len(pmap.entries) == 2

        # read memory (debe devolver 0xCAFEBABE)
        data = client.read_memory(100, 0x10000000, 4)
        import struct
        val = struct.unpack("<I", data)[0]
        print(f"[OK] read_memory(0x10000000, 4) -> 0x{val:08X}")
        assert val == 0xCAFEBABE, f"expected 0xCAFEBABE, got 0x{val:08X}"

        # read más grande
        data = client.read_memory(100, 0x10000000, 16)
        vals = struct.unpack("<4I", data)
        print(f"[OK] read_memory(0x10000000, 16) -> {[f'0x{v:08X}' for v in vals]}")
        assert all(v == 0xCAFEBABE for v in vals)

        # write memory: cambiar los primeros 4 bytes a 0xDEADBEEF
        new_data = struct.pack("<I", 0xDEADBEEF)
        client.write_memory(100, 0x10000000, new_data)
        print(f"[OK] write_memory(0x10000000, 0xDEADBEEF)")

        # releer
        data = client.read_memory(100, 0x10000000, 4)
        val = struct.unpack("<I", data)[0]
        print(f"[OK] read_memory(0x10000000, 4) -> 0x{val:08X}")
        assert val == 0xDEADBEEF, f"expected 0xDEADBEEF after write, got 0x{val:08X}"

        # notify
        client.notify(0, "Hello from Python")
        print(f"[OK] notify(0, 'Hello from Python')")

        client.disconnect()
        print(f"[OK] disconnect")
        print("\n✅ Todos los tests de integración de FASE 1 pasan.")
        return 0
    except AssertionError as e:
        print(f"\n❌ Assertion failed: {e}")
        return 1
    finally:
        if mock_proc is not None:
            mock_proc.terminate()
            mock_proc.wait(timeout=2.0)


if __name__ == "__main__":
    sys.exit(main())
