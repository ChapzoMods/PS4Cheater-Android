#!/usr/bin/env python3
"""
Mock server mínimo para validar el handshake del protocolo ps4debug.
Escucha en 127.0.0.1:1744 y responde a:
  - CMD_PROC_LIST
  - CMD_PROC_INFO
  - CMD_PROC_MAPS
  - CMD_PROC_READ
  - CMD_PROC_WRITE
  - CMD_CONSOLE_END
  - CMD_VERSION
  - CMD_CONSOLE_NOTIFY

Simula un proceso con pid=100, name="eboot.bin", con 2 secciones de memoria:
  - executable: 0x400000-0x401000 (r-x) — 4 KB
  - data:       0x10000000-0x10001000 (rw-) — 4 KB, llena de 0xCAFEBABE en uint32

Uso:
    python3 /home/z/my-project/ps4cheater-android/tests/mock_server_min.py &
    python3 /home/z/my-project/ps4cheater-android/tests/integration_phase1.py
"""
import socket
import struct
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import protocol as P
from lib import CMD, CMD_STATUS


HOST = "127.0.0.1"
PORT = 1744

# Simulated process memory
SIM_PID = 100
SIM_PROC_NAME = "eboot.bin"
SIM_PROC_TITLEID = "CUSA00001"

# Memory layout
SIM_EXEC_START = 0x400000
SIM_EXEC_END   = 0x401000  # 4 KB executable
SIM_DATA_START = 0x10000000
SIM_DATA_END   = 0x10001000  # 4 KB data, llena de 0xCAFEBABE

# We use a single bytearray for "memory" of the data section.
# Reads from outside return zeros.
SIM_DATA = bytearray(b"\xBE\xBA\xFE\xCA" * 1024)  # 4096 bytes = 1024 * 0xCAFEBABE


def build_status(status: CMD_STATUS) -> bytes:
    return struct.pack("<I", int(status))


def handle_conn(conn: socket.socket, addr):
    try:
        while True:
            header = recv_exact(conn, P.CMD_PACKET_SIZE)
            if not header:
                break
            magic, cmd, datalen = struct.unpack("<III", header)
            if magic != P.CMD_PACKET_MAGIC:
                print(f"[mock] bad magic 0x{magic:X}, dropping")
                break

            payload = b""
            if datalen > 0:
                payload = recv_exact(conn, datalen)

            cmd_e = CMD(cmd)
            print(f"[mock] cmd={cmd_e.name} datalen={datalen}")

            if cmd_e == CMD.CMD_PROC_LIST:
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))
                # 1 process
                count = struct.pack("<i", 1)
                entry = SIM_PROC_NAME.encode().ljust(32, b"\x00") + struct.pack("<i", SIM_PID)
                conn.sendall(count + entry)

            elif cmd_e == CMD.CMD_PROC_INFO:
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))
                info = struct.pack("<i", SIM_PID)
                info += SIM_PROC_NAME.encode().ljust(40, b"\x00")
                info += b"/system/vsh/app".ljust(64, b"\x00")
                info += SIM_PROC_TITLEID.encode().ljust(16, b"\x00")
                info += b"UP0001-" + SIM_PROC_TITLEID.encode()
                info = info.ljust(P.PROC_PROC_INFO_SIZE, b"\x00")
                conn.sendall(info[:P.PROC_PROC_INFO_SIZE])

            elif cmd_e == CMD.CMD_PROC_MAPS:
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))
                # 2 entries
                count = struct.pack("<i", 2)
                e1 = b"executable".ljust(32, b"\x00")
                e1 += struct.pack("<QQQH", SIM_EXEC_START, SIM_EXEC_END, 0, 0x5)
                e2 = b"data".ljust(32, b"\x00")
                e2 += struct.pack("<QQQH", SIM_DATA_START, SIM_DATA_END, 0, 0x3)
                conn.sendall(count + e1 + e2)

            elif cmd_e == CMD.CMD_PROC_READ:
                # payload: pid int32 + address uint64 + length int32
                pid, address, length = struct.unpack("<IQI", payload)
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))
                # Devolver `length` bytes
                data = bytearray(length)
                if SIM_DATA_START <= address < SIM_DATA_END:
                    off = address - SIM_DATA_START
                    n = min(length, len(SIM_DATA) - off)
                    if n > 0:
                        data[:n] = SIM_DATA[off:off + n]
                conn.sendall(bytes(data))

            elif cmd_e == CMD.CMD_PROC_WRITE:
                pid, address, length = struct.unpack("<IQI", payload)
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))
                # recibir los datos
                wdata = recv_exact(conn, length)
                if SIM_DATA_START <= address < SIM_DATA_END:
                    off = address - SIM_DATA_START
                    n = min(length, len(SIM_DATA) - off)
                    if n > 0:
                        SIM_DATA[off:off + n] = wdata[:n]
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))

            elif cmd_e == CMD.CMD_VERSION:
                length = struct.pack("<i", 11)
                conn.sendall(length + b"ps4d-1.0.0\x00")

            elif cmd_e == CMD.CMD_CONSOLE_NOTIFY:
                conn.sendall(build_status(CMD_STATUS.CMD_SUCCESS))

            elif cmd_e == CMD.CMD_CONSOLE_END:
                break

            else:
                conn.sendall(build_status(CMD_STATUS.CMD_ERROR))
    except (OSError, ConnectionError) as e:
        print(f"[mock] conn {addr} error: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def recv_exact(conn: socket.socket, length: int) -> bytes:
    buf = bytearray()
    while len(buf) < length:
        chunk = conn.recv(length - len(buf))
        if not chunk:
            return b""
        buf.extend(chunk)
    return bytes(buf)


def main():
    print(f"[mock] escuchando en {HOST}:{PORT}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    try:
        while True:
            conn, addr = srv.accept()
            print(f"[mock] conexion entrante de {addr}")
            t = threading.Thread(target=handle_conn, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[mock] cerrando")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
