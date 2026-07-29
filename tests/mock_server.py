"""
tests/mock_server.py — Mock server TCP que simula el protocolo ps4debug.

Versión mejorada para FASE 6: soporta:
  - CMD_VERSION, CMD_PROC_LIST, CMD_PROC_INFO, CMD_PROC_MAPS
  - CMD_PROC_READ, CMD_PROC_WRITE
  - CMD_PROC_ALLOC, CMD_PROC_FREE, CMD_PROC_PROTECT
  - CMD_PROC_INSTALL (RPC stub)
  - CMD_CONSOLE_NOTIFY, CMD_CONSOLE_END, CMD_CONSOLE_REBOOT
  - CMD_CONSOLE_PRINT

Memoria simulada:
  - 2 procesos: eboot.bin (pid=100), SceShellUI (pid=200)
  - Proceso 100 tiene:
    - executable: 0x400000-0x401000 (r-x, 4KB) — código falso
    - data: 0x10000000-0x10001000 (rw-, 4KB) — lleno de 0xCAFEBABE
    - heap: 0x20000000-0x20010000 (rw-, 64KB) — punteros interconectados
  - Proceso 200 tiene:
    - main: 0x300000-0x301000 (rwx, 4KB)

Uso:
    python3 tests/mock_server.py [--port 1744]
"""
from __future__ import annotations

import argparse
import os
import socket
import struct
import sys
import threading
import time

# Add project root to path
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

from lib import protocol as P
from lib import CMD, CMD_STATUS, VMProtection


# ---------------------------------------------------------------------------
# Simulated processes & memory
# ---------------------------------------------------------------------------

SIM_PROCS = [
    P.Process(name="eboot.bin", pid=100),
    P.Process(name="SceShellUI", pid=200),
    P.Process(name="SceCdlgApp", pid=300),
]

SIM_PROC_INFOS = {
    100: P.ProcessInfo(pid=100, name="eboot.bin", path="/system/vsh/app", titleid="CUSA00001", contentid="UP0001-CUSA00001"),
    200: P.ProcessInfo(pid=200, name="SceShellUI", path="/system/vsh", titleid="CUSA00000", contentid="UP0000-CUSA00000"),
    300: P.ProcessInfo(pid=300, name="SceCdlgApp", path="/system/vsh", titleid="CUSA00002", contentid="UP0002-CUSA00002"),
}

SIM_PROC_MAPS = {
    100: P.ProcessMap(pid=100, entries=[
        P.MemoryEntry(name="executable", start=0x400000, end=0x401000, offset=0, prot=0x5),  # r-x
        P.MemoryEntry(name="data",       start=0x10000000, end=0x10001000, offset=0, prot=0x3),  # rw-
        P.MemoryEntry(name="heap",       start=0x20000000, end=0x20010000, offset=0, prot=0x3),  # rw-, 64KB
    ]),
    200: P.ProcessMap(pid=200, entries=[
        P.MemoryEntry(name="main", start=0x300000, end=0x301000, offset=0, prot=0x7),  # rwx
    ]),
    300: P.ProcessMap(pid=300, entries=[
        P.MemoryEntry(name="libSceCdlgUtilServer.sprx", start=0x500000, end=0x501000, offset=0, prot=0x3),
    ]),
}

# Memoria simulada por proceso: {pid: bytearray(start_addr, length)}
# La memoria se modela como un dict {address: bytearray} por simplicidad
class SimMemory:
    """Memoria simulada de un proceso."""
    def __init__(self):
        self.regions: list[tuple[int, bytearray]] = []  # [(start, data), ...]

    def add_region(self, start: int, data: bytes):
        self.regions.append((start, bytearray(data)))

    def read(self, address: int, length: int) -> bytes:
        out = bytearray(length)
        for start, data in self.regions:
            if address + length > start and address < start + len(data):
                src_start = max(0, address - start)
                dst_start = max(0, start - address)
                n = min(len(data) - src_start, length - dst_start)
                if n > 0:
                    out[dst_start:dst_start + n] = data[src_start:src_start + n]
        return bytes(out)

    def write(self, address: int, data: bytes) -> int:
        n_written = 0
        for start, region in self.regions:
            if address + len(data) > start and address < start + len(region):
                src_start = max(0, address - start)
                dst_start = max(0, start - address)
                n = min(len(region) - src_start, len(data) - dst_start)
                if n > 0:
                    region[src_start:src_start + n] = data[dst_start:dst_start + n]
                    n_written += n
        return n_written


def make_sim_memory(pid: int) -> SimMemory:
    """Crea memoria simulada para un proceso."""
    mem = SimMemory()
    if pid == 100:
        # executable: código falso (NOP sled)
        mem.add_region(0x400000, b"\x90" * 4096)
        # data: 4096 bytes llenos de 0xCAFEBABE (1024 uint32)
        mem.add_region(0x10000000, b"\xBE\xBA\xFE\xCA" * 1024)
        # heap: 64KB con algunos punteros interconectados
        heap = bytearray(65536)
        # Punteros en heap[0..32]: forman cadena 0x20000000 -> 0x20000008 -> 0x20000010 -> 0x10000000 (target)
        struct.pack_into("<Q", heap, 0,  0x20000008)  # 0x20000000 -> 0x20000008
        struct.pack_into("<Q", heap, 8,  0x20000010)  # 0x20000008 -> 0x20000010
        struct.pack_into("<Q", heap, 16, 0x10000000)  # 0x20000010 -> 0x10000000 (data section!)
        # Otros punteros inválidos
        struct.pack_into("<Q", heap, 24, 0xDEADDEAD)
        # Resto lleno de ceros (ya está)
        mem.add_region(0x20000000, bytes(heap))
    elif pid == 200:
        # main: 4KB de ceros
        mem.add_region(0x300000, b"\x00" * 4096)
    elif pid == 300:
        # libSceCdlgUtilServer.sprx con GameID y Version
        data = bytearray(4096)
        # GameID en offset 0xA0
        gid = b"CUSA00001\x00"
        data[0xA0:0xA0 + len(gid)] = gid
        # Version en offset 0xC8
        ver = b"01.00\x00"
        data[0xC8:0xC8 + len(ver)] = ver
        mem.add_region(0x500000, bytes(data))
    return mem


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class MockServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 1744):
        self.host = host
        self.port = port
        self.memories: dict[int, SimMemory] = {}
        self.notify_count = 0
        self.last_notify: tuple[int, str] | None = None
        self.reboot_count = 0
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._sock.accept()
                t = threading.Thread(target=self._handle_conn, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_conn(self, conn: socket.socket, addr):
        try:
            while self._running:
                header = self._recv_exact(conn, P.CMD_PACKET_SIZE)
                if not header:
                    break
                magic, cmd, datalen = struct.unpack("<III", header)
                if magic != P.CMD_PACKET_MAGIC:
                    break
                payload = b""
                if datalen > 0:
                    payload = self._recv_exact(conn, datalen)

                cmd_e = CMD(cmd)
                self._dispatch(conn, cmd_e, payload)
        except (OSError, ConnectionError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _recv_exact(self, conn: socket.socket, length: int) -> bytes:
        buf = bytearray()
        while len(buf) < length:
            chunk = conn.recv(length - len(buf))
            if not chunk:
                return b""
            buf.extend(chunk)
        return bytes(buf)

    def _send_status(self, conn: socket.socket, status: CMD_STATUS):
        conn.sendall(struct.pack("<I", int(status)))

    def _dispatch(self, conn: socket.socket, cmd: CMD, payload: bytes):
        with self._lock:
            try:
                self._dispatch_inner(conn, cmd, payload)
            except Exception as e:
                # Log pero no matar el thread; intentar responder error
                import sys
                print(f"[mock] dispatch error on cmd={cmd.name}: {e}", file=sys.stderr)
                try:
                    self._send_status(conn, CMD_STATUS.CMD_ERROR)
                except OSError:
                    pass

    def _dispatch_inner(self, conn: socket.socket, cmd: CMD, payload: bytes):
        if cmd == CMD.CMD_VERSION:
            ver = b"ps4d-1.0.0\x00"
            conn.sendall(struct.pack("<i", len(ver)) + ver)
        elif cmd == CMD.CMD_PROC_LIST:
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            count = struct.pack("<i", len(SIM_PROCS))
            entries = b""
            for p in SIM_PROCS:
                entries += p.name.encode().ljust(32, b"\x00") + struct.pack("<i", p.pid)
            conn.sendall(count + entries)
        elif cmd == CMD.CMD_PROC_INFO:
            pid = struct.unpack("<i", payload)[0]
            if pid not in SIM_PROC_INFOS:
                self._send_status(conn, CMD_STATUS.CMD_INVALID_INDEX)
                return
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            info = SIM_PROC_INFOS[pid]
            data = struct.pack("<i", info.pid)
            data += info.name.encode().ljust(40, b"\x00")
            data += info.path.encode().ljust(64, b"\x00")
            data += info.titleid.encode().ljust(16, b"\x00")
            data += info.contentid.encode().ljust(64, b"\x00")
            conn.sendall(data[:P.PROC_PROC_INFO_SIZE])
        elif cmd == CMD.CMD_PROC_MAPS:
            pid = struct.unpack("<i", payload)[0]
            if pid not in SIM_PROC_MAPS:
                self._send_status(conn, CMD_STATUS.CMD_INVALID_INDEX)
                return
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            pmap = SIM_PROC_MAPS[pid]
            count = struct.pack("<i", len(pmap.entries))
            data = b""
            for e in pmap.entries:
                data += e.name.encode().ljust(32, b"\x00")
                data += struct.pack("<QQQH", e.start, e.end, e.offset, e.prot)
            conn.sendall(count + data)
        elif cmd == CMD.CMD_PROC_READ:
            pid, address, length = struct.unpack("<IQI", payload)
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            mem = self.memories.setdefault(pid, make_sim_memory(pid))
            conn.sendall(mem.read(address, length))
        elif cmd == CMD.CMD_PROC_WRITE:
            pid, address, length = struct.unpack("<IQI", payload)
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            wdata = self._recv_exact(conn, length)
            mem = self.memories.setdefault(pid, make_sim_memory(pid))
            mem.write(address, wdata)
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
        elif cmd == CMD.CMD_PROC_INTALL:  # ojo: typo del protocolo original
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            conn.sendall(struct.pack("<Q", 0xDEADBEEF))  # fake stub
        elif cmd == CMD.CMD_PROC_ALLOC:
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
            conn.sendall(struct.pack("<Q", 0x70000000))  # fake address
        elif cmd == CMD.CMD_PROC_FREE:
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
        elif cmd == CMD.CMD_PROC_PROTECT:
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
        elif cmd == CMD.CMD_CONSOLE_NOTIFY:
            # payload = type(4) + length(4) + message_bytes
            notice_type, msg_len = struct.unpack_from("<II", payload, 0)
            msg = payload[8:8 + msg_len].decode("utf-8", errors="replace")
            self.notify_count += 1
            self.last_notify = (notice_type, msg)
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
        elif cmd == CMD.CMD_CONSOLE_REBOOT:
            self.reboot_count += 1
            # No status: la consola se reinicia
        elif cmd == CMD.CMD_CONSOLE_PRINT:
            self._send_status(conn, CMD_STATUS.CMD_SUCCESS)
        elif cmd == CMD.CMD_CONSOLE_END:
            # Cerrar conexión limpiamente
            return
        else:
            self._send_status(conn, CMD_STATUS.CMD_ERROR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=1744, type=int)
    args = parser.parse_args()
    srv = MockServer(args.host, args.port)
    srv.start()
    print(f"[mock] escuchando en {args.host}:{args.port} (Ctrl+C para parar)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[mock] cerrando")
        srv.stop()


if __name__ == "__main__":
    main()
