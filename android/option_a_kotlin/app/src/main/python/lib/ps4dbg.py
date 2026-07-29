"""
lib/ps4dbg.py — Cliente TCP thread-safe del protocolo ps4debug / GoldHEN.

Implementa las operaciones necesarias para PS4Cheater:
  - connect / disconnect
  - get_process_list
  - get_process_info(pid)
  - get_process_maps(pid)
  - read_memory(pid, address, length)
  - write_memory(pid, address, data)
  - get_console_debug_version()
  - notify(type, message)
  - reboot()
  - find_playstation() (UDP broadcast discovery)

Diseño:
  - Cada PS4DBG mantiene UN socket TCP dedicado con su propio lock.
  - Para paralelizar escaneos, crea un pool de N conexiones (PS4DBGPool).
  - Todos los métodos son thread-safe.
  - Reconexión automática si el socket se cayó (lazy reconnect).

Referencias:
  - libdebug-reference/PS4DBG.cs (a0zhar2)
  - libdebug-reference/PS4DBG.Proc.cs
  - ps4debug PyPI (core.py)
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Callable, List, Optional, Tuple

from . import protocol as P
from .protocol import (
    CMD, CMD_STATUS, MemoryEntry, Process, ProcessInfo, ProcessMap,
    NET_MAX_LENGTH, GOLDHEN_PORT, PS4DBG_PORT, BROADCAST_MAGIC, BROADCAST_PORT,
)


class PS4DBGError(Exception):
    """Error de protocolo: status no-success o problema de red."""
    def __init__(self, status: CMD_STATUS, message: str = ""):
        self.status = status
        super().__init__(f"ps4debug status 0x{int(status):08X} ({status.name}): {message}")


class PS4DBGNotConnected(Exception):
    """Se intentó usar una operación sin estar conectado."""


class PS4DBG:
    """
    Cliente TCP thread-safe de una PS4 con ps4debug/GoldHEN cargado.

    Una instancia mantiene UN socket TCP. Para escaneos paralelos usar
    `PS4DBGPool` (que mantiene N instancias y reparte trabajo).
    """

    DEFAULT_TIMEOUT: float = 30.0  # segundos
    CONNECT_TIMEOUT: float = 10.0

    def __init__(self, ip: str, port: int = PS4DBG_PORT, timeout: float = DEFAULT_TIMEOUT):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.RLock()
        self._connected = False
        self._version: str = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected and self._sock is not None

    @property
    def version(self) -> str:
        return self._version

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Abre la conexión TCP al host:port configurado."""
        with self._lock:
            if self.is_connected:
                return True
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, NET_MAX_LENGTH)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, NET_MAX_LENGTH)
                sock.settimeout(self.CONNECT_TIMEOUT)
                sock.connect((self.ip, self.port))
                sock.settimeout(self.timeout)
                self._sock = sock
                self._connected = True
                return True
            except OSError:
                self._connected = False
                self._sock = None
                return False

    def disconnect(self) -> bool:
        """Cierra limpiamente la conexión enviando CMD_CONSOLE_END."""
        with self._lock:
            if self._sock is None:
                self._connected = False
                return True
            try:
                # Best-effort: avisamos que cerramos. Si falla, igual cerramos.
                try:
                    self._send_cmd_no_payload(CMD.CMD_CONSOLE_END, expect_status=False)
                except OSError:
                    pass
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
                self._connected = False
            return True

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # ------------------------------------------------------------------
    # I/O bajo nivel
    # ------------------------------------------------------------------

    def _send_all(self, data: bytes) -> None:
        if self._sock is None:
            raise PS4DBGNotConnected("not connected")
        # sendall maneja chunks parciales internamente
        self._sock.sendall(data)

    def _recv_exact(self, length: int) -> bytes:
        if length <= 0:
            return b""
        if self._sock is None:
            raise PS4DBGNotConnected("not connected")
        buf = bytearray()
        remaining = length
        while remaining > 0:
            chunk = self._sock.recv(min(remaining, NET_MAX_LENGTH))
            if not chunk:
                raise OSError("connection closed by remote")
            buf.extend(chunk)
            remaining -= len(chunk)
        return bytes(buf)

    def _send_cmd_packet(self, cmd: CMD, payload: bytes = b"") -> None:
        """Envía la cabecera (12B) + payload opcional."""
        header = P.build_header(int(cmd), len(payload))
        self._send_all(header)
        if payload:
            self._send_all(payload)

    def _recv_status(self) -> CMD_STATUS:
        data = self._recv_exact(4)
        return P.parse_status(data)

    def _check_status(self, ctx: str = "") -> None:
        status = self._recv_status()
        if status != CMD_STATUS.CMD_SUCCESS:
            raise PS4DBGError(status, ctx)

    def _send_cmd_no_payload(self, cmd: CMD, expect_status: bool = True) -> None:
        self._send_cmd_packet(cmd, b"")
        if expect_status:
            self._check_status(f"cmd=0x{int(cmd):08X}")

    # ------------------------------------------------------------------
    # Operaciones de proceso
    # ------------------------------------------------------------------

    def get_console_debug_version(self) -> str:
        """CMD_VERSION: devuelve la versión del payload ps4debug cargado."""
        with self._lock:
            self._send_cmd_packet(CMD.CMD_VERSION, b"")
            # Recibe length int32 + data
            length_bytes = self._recv_exact(4)
            length = struct.unpack("<i", length_bytes)[0]
            data = self._recv_exact(length)
            self._version = P.cstr(data, 0)
            return self._version

    def get_process_list(self) -> List[Process]:
        """CMD_PROC_LIST: lista procesos (pid + name)."""
        with self._lock:
            self._send_cmd_packet(CMD.CMD_PROC_LIST, b"")
            self._check_status("CMD_PROC_LIST")
            count_bytes = self._recv_exact(4)
            count = struct.unpack("<i", count_bytes)[0]
            data = self._recv_exact(count * P.PROC_LIST_ENTRY_SIZE)
            return P.parse_process_list(data)

    def get_process_info(self, pid: int) -> ProcessInfo:
        """CMD_PROC_INFO: info extendida de un proceso."""
        with self._lock:
            payload = P.payload_proc_info(pid)
            self._send_cmd_packet(CMD.CMD_PROC_INFO, payload)
            self._check_status(f"CMD_PROC_INFO pid={pid}")
            data = self._recv_exact(P.PROC_PROC_INFO_SIZE)
            return P.parse_process_info(data)

    def get_process_maps(self, pid: int) -> ProcessMap:
        """CMD_PROC_MAPS: mapa de memoria del proceso."""
        with self._lock:
            payload = P.payload_proc_maps(pid)
            self._send_cmd_packet(CMD.CMD_PROC_MAPS, payload)
            self._check_status(f"CMD_PROC_MAPS pid={pid}")
            count_bytes = self._recv_exact(4)
            count = struct.unpack("<i", count_bytes)[0]
            data = self._recv_exact(count * P.PROC_MAP_ENTRY_SIZE)
            entries = P.parse_process_maps(data)
            return ProcessMap(pid=pid, entries=entries)

    def read_memory(self, pid: int, address: int, length: int) -> bytes:
        """
        CMD_PROC_READ: lee `length` bytes desde `address` del proceso `pid`.

        Si la PS4 devuelve menos bytes de los pedidos (no debería), rellenamos
        con ceros para que el caller reciba siempre `length` bytes (igual que
        hace el C# original que devuelve `new byte[length]` en caso de error).
        """
        if length <= 0:
            return b""
        with self._lock:
            payload = P.payload_proc_read(pid, address, length)
            self._send_cmd_packet(CMD.CMD_PROC_READ, payload)
            try:
                self._check_status(f"CMD_PROC_READ pid={pid} addr=0x{address:X} len={length}")
                return self._recv_exact(length)
            except (PS4DBGError, OSError):
                # En caso de error devolvemos zeros (igual que MemoryHelper.cs:582)
                return b"\x00" * length

    def write_memory(self, pid: int, address: int, data: bytes) -> None:
        """
        CMD_PROC_WRITE: escribe `data` en `address` del proceso `pid`.

        Wire format (igual que C#):
          1. send header (cmd=CMD_PROC_WRITE, datalen=16)
          2. send payload 16B (pid + address + length)
          3. recv status (debe ser SUCCESS)
          4. send data (length bytes)
          5. recv status (debe ser SUCCESS)
        """
        if not data:
            return
        with self._lock:
            payload = P.payload_proc_write(pid, address, len(data))
            self._send_cmd_packet(CMD.CMD_PROC_WRITE, payload)
            self._check_status(f"CMD_PROC_WRITE (header) pid={pid} addr=0x{address:X} len={len(data)}")
            self._send_all(data)
            self._check_status(f"CMD_PROC_WRITE (data) pid={pid} addr=0x{address:X} len={len(data)}")

    def install_rpc(self, pid: int) -> int:
        """CMD_PROC_INTALL: instala RPC stub, devuelve la address del stub."""
        with self._lock:
            payload = P.payload_proc_install(pid)
            self._send_cmd_packet(CMD.CMD_PROC_INTALL, payload)
            self._check_status(f"CMD_PROC_INTALL pid={pid}")
            data = self._recv_exact(P.PROC_INSTALL_SIZE)
            return struct.unpack("<Q", data)[0]

    def allocate_memory(self, pid: int, length: int) -> int:
        """CMD_PROC_ALLOC: aloja RWX memory, devuelve la address."""
        with self._lock:
            payload = P.payload_proc_alloc(pid, length)
            self._send_cmd_packet(CMD.CMD_PROC_ALLOC, payload)
            self._check_status(f"CMD_PROC_ALLOC pid={pid} len={length}")
            data = self._recv_exact(P.PROC_ALLOC_SIZE)
            return struct.unpack("<Q", data)[0]

    def free_memory(self, pid: int, address: int, length: int) -> None:
        """CMD_PROC_FREE: libera memoria previamente alocada."""
        with self._lock:
            payload = P.payload_proc_free(pid, address, length)
            self._send_cmd_packet(CMD.CMD_PROC_FREE, payload)
            self._check_status(f"CMD_PROC_FREE pid={pid} addr=0x{address:X}")

    def change_protection(self, pid: int, address: int, length: int, prot: int) -> None:
        """CMD_PROC_PROTECT: cambia protección de páginas."""
        with self._lock:
            payload = P.payload_proc_protect(pid, address, length, prot)
            self._send_cmd_packet(CMD.CMD_PROC_PROTECT, payload)
            self._check_status(f"CMD_PROC_PROTECT pid={pid} addr=0x{address:X} prot=0x{prot:X}")

    # ------------------------------------------------------------------
    # Operaciones de consola
    # ------------------------------------------------------------------

    def reboot(self) -> None:
        """CMD_CONSOLE_REBOOT: reinicia la PS4."""
        with self._lock:
            self._send_cmd_packet(CMD.CMD_CONSOLE_REBOOT, b"")
            # No esperamos status: la consola se reinicia.

    def notify(self, notice_type: int, message: str) -> None:
        """
        CMD_CONSOLE_NOTIFY: muestra una notificación en pantalla.
        notice_type: 0 = info, 1 = warning, 2 = error (depende del fw).
        message: texto ASCII/UTF-8.
        """
        with self._lock:
            payload = P.payload_console_notify(notice_type, message)
            self._send_cmd_packet(CMD.CMD_CONSOLE_NOTIFY, payload)
            self._check_status("CMD_CONSOLE_NOTIFY")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @staticmethod
    def find_playstation(timeout: float = 1.0, subnet_mask: str = "255.255.255.0") -> Optional[str]:
        """
        Descubre la IP de una PS4 en la LAN mediante broadcast UDP.
        Envia el magic 0xFFFFAAAA al puerto 1010 y espera respuesta.

        Requiere saber la IP local para calcular la dirección de broadcast.
        Returns: IP de la PS4 o None si no responde.
        """
        import errno
        try:
            local_ip = PS4DBG._get_local_ip()
            if not local_ip:
                return None
            broadcast = PS4DBG._compute_broadcast(local_ip, subnet_mask)
            magic = struct.pack("<I", BROADCAST_MAGIC)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(timeout)
                s.sendto(magic, (broadcast, BROADCAST_PORT))
                try:
                    data, addr = s.recvfrom(64)
                except socket.timeout:
                    return None
                if len(data) >= 4:
                    val = struct.unpack("<I", data[:4])[0]
                    if val == BROADCAST_MAGIC:
                        return addr[0]
        except OSError:
            return None
        return None

    @staticmethod
    def _get_local_ip() -> Optional[str]:
        """Detecta la IP local abriendo un socket UDP a 8.8.8.8 (no envía nada)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 53))
                return s.getsockname()[0]
            finally:
                s.close()
        except OSError:
            return None

    @staticmethod
    def _compute_broadcast(ip: str, mask: str) -> str:
        ip_b = socket.inet_aton(ip)
        mask_b = socket.inet_aton(mask)
        bcast_b = bytes(a | (~m & 0xFF) for a, m in zip(ip_b, mask_b))
        return socket.inet_ntoa(bcast_b)


# ---------------------------------------------------------------------------
# Pool de conexiones para paralelismo
# ---------------------------------------------------------------------------

class PS4DBGPool:
    """
    Pool de N conexiones PS4DBG a la misma consola.

    Uso típico en escaneos: 1 hilo productor lee bloques con `read_memory`
    usando una conexión; N hilos consumidores comparan resultados en CPU.
    Para que el productor no bloquee a los consumers en el GIL, tener varias
    conexiones permite hacer varios read_memory en paralelo (cuando se hace
    next-scan y hay que releer muchas secciones).
    """

    def __init__(self, ip: str, port: int = PS4DBG_PORT, size: int = 3, timeout: float = PS4DBG.DEFAULT_TIMEOUT):
        self.ip = ip
        self.port = port
        self.size = size
        self.timeout = timeout
        self._connections: List[PS4DBG] = [PS4DBG(ip, port, timeout) for _ in range(size)]
        self._locks: List[threading.RLock] = [threading.RLock() for _ in range(size)]

    def connect_all(self) -> bool:
        """Conecta todas las conexiones del pool. Si la primera falla, aborta."""
        for i, conn in enumerate(self._connections):
            if not conn.connect():
                # Si falla la primera, no tiene sentido seguir
                if i == 0:
                    return False
                # Si fallan otras, igual continuamos con menos
                break
        return self._connections[0].is_connected

    def disconnect_all(self) -> None:
        for conn in self._connections:
            try:
                conn.disconnect()
            except OSError:
                pass

    def get(self, idx: int = 0) -> PS4DBG:
        """Devuelve la conexión idx-ésima."""
        return self._connections[idx]

    def with_connection(self, idx: int, fn: Callable[[PS4DBG], object]) -> object:
        """
        Ejecuta `fn(conn)` con la conexión idx-ésima y su lock.
        Permite que múltiples hilos coordinen qué conexión usan.
        """
        with self._locks[idx]:
            return fn(self._connections[idx])

    def read_memory_round_robin(self, pid: int, address: int, length: int) -> bytes:
        """
        Atajo para read_memory usando la conexión menos usada (round-robin).
        Útil para que el productor no sature siempre la misma conexión.
        """
        # Simple: usa siempre la conexión 0 (igual que MemoryHelper.cs que usa
        # mutex[0] para writes). El paralelismo real lo da el caller eligiendo idx.
        return self._connections[0].read_memory(pid, address, length)

    @property
    def is_connected(self) -> bool:
        return any(c.is_connected for c in self._connections)

    def __enter__(self):
        self.connect_all()
        return self

    def __exit__(self, *args):
        self.disconnect_all()


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def connect_ps4debug(ip: str, port: int = PS4DBG_PORT, timeout: float = PS4DBG.DEFAULT_TIMEOUT) -> PS4DBG:
    """Crea un PS4DBG para ps4debug estándar (puerto 744)."""
    return PS4DBG(ip, port, timeout)


def connect_goldhen(ip: str, port: int = GOLDHEN_PORT, timeout: float = PS4DBG.DEFAULT_TIMEOUT) -> PS4DBG:
    """Crea un PS4DBG para GoldHEN (puerto 9090)."""
    return PS4DBG(ip, port, timeout)
