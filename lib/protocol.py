"""
lib/protocol.py — Constantes y serialización del protocolo ps4debug.

Protocolo binario sobre TCP:
  - Cabecera: 12 bytes (magic uint32 LE, cmd uint32 LE, datalen uint32 LE)
  - Tras cabecera: payload de `datalen` bytes
  - Respuestas: 4 bytes status (CMD_SUCCESS / CMD_ERROR / ...)

Referencias:
  - https://github.com/jogolden/ps4debug (carpeta libdebug/)
  - https://github.com/a0zhar2/libdebug/blob/main/PS4DBG.cs
  - pip download ps4debug (implementación Python de referencia)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Callable, List, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Constantes de red
# ---------------------------------------------------------------------------

CMD_PACKET_MAGIC: int = 0xFFAABBCC
CMD_PACKET_SIZE: int = 12
NET_MAX_LENGTH: int = 0x20000  # 128 KB por chunk (igual que C#)

# Puertos por defecto
PS4DBG_PORT: int = 744         # ps4debug estándar
PS4DBG_DEBUG_PORT: int = 755   # eventos de debug asíncronos
GOLDHEN_PORT: int = 9090       # GoldHEN 2.x (mismo protocolo)
BROADCAST_PORT: int = 1010     # discovery UDP
BROADCAST_MAGIC: int = 0xFFFFAAAA


# ---------------------------------------------------------------------------
# Comandos (todos little-endian uint32)
# ---------------------------------------------------------------------------

class CMD(IntEnum):
    # Version
    CMD_VERSION          = 0xBD000001
    CMD_EXT_FW_VERSION   = 0xBD000500

    # Proc
    CMD_PROC_LIST        = 0xBDAA0001
    CMD_PROC_READ        = 0xBDAA0002
    CMD_PROC_WRITE       = 0xBDAA0003
    CMD_PROC_MAPS        = 0xBDAA0004
    CMD_PROC_INTALL      = 0xBDAA0005
    CMD_PROC_CALL        = 0xBDAA0006
    CMD_PROC_ELF         = 0xBDAA0007
    CMD_PROC_PROTECT     = 0xBDAA0008
    CMD_PROC_SCAN        = 0xBDAA0009
    CMD_PROC_INFO        = 0xBDAA000A
    CMD_PROC_ALLOC       = 0xBDAA000B
    CMD_PROC_FREE        = 0xBDAA000C

    # Debug
    CMD_DEBUG_ATTACH     = 0xBDBB0001
    CMD_DEBUG_DETACH     = 0xBDBB0002
    CMD_DEBUG_BREAKPT    = 0xBDBB0003
    CMD_DEBUG_WATCHPT    = 0xBDBB0004
    CMD_DEBUG_THREADS    = 0xBDBB0005
    CMD_DEBUG_STOPTHR    = 0xBDBB0006
    CMD_DEBUG_RESUMETHR  = 0xBDBB0007
    CMD_DEBUG_GETREGS    = 0xBDBB0008
    CMD_DEBUG_SETREGS    = 0xBDBB0009
    CMD_DEBUG_GETFPREGS  = 0xBDBB000A
    CMD_DEBUG_SETFPREGS  = 0xBDBB000B
    CMD_DEBUG_GETDBGREGS = 0xBDBB000C
    CMD_DEBUG_SETDBGREGS = 0xBDBB000D
    CMD_DEBUG_STOPGO     = 0xBDBB0010
    CMD_DEBUG_THRINFO    = 0xBDBB0011
    CMD_DEBUG_SINGLESTEP = 0xBDBB0012
    CMD_DEBUG_EXT_STOPGO = 0xBDBB0500

    # Kernel
    CMD_KERN_BASE        = 0xBDCC0001
    CMD_KERN_READ        = 0xBDCC0002
    CMD_KERN_WRITE       = 0xBDCC0003

    # Console
    CMD_CONSOLE_REBOOT   = 0xBDDD0001
    CMD_CONSOLE_END      = 0xBDDD0002
    CMD_CONSOLE_PRINT    = 0xBDDD0003
    CMD_CONSOLE_NOTIFY   = 0xBDDD0004
    CMD_CONSOLE_INFO     = 0xBDDD0005


class CMD_STATUS(IntEnum):
    CMD_SUCCESS        = 0x80000000
    CMD_ERROR          = 0xF0000001
    CMD_TOO_MUCH_DATA  = 0xF0000002
    CMD_DATA_NULL      = 0xF0000003
    CMD_ALREADY_DEBUG  = 0xF0000004
    CMD_INVALID_INDEX  = 0xF0000005


# ---------------------------------------------------------------------------
# Protecciones de memoria
# ---------------------------------------------------------------------------

class VMProtection(IntFlag):
    VM_PROT_NONE     = 0x00
    VM_PROT_READ     = 0x01
    VM_PROT_WRITE    = 0x02
    VM_PROT_EXECUTE  = 0x04
    VM_PROT_DEFAULT  = 0x03
    VM_PROT_ALL      = 0x07
    VM_PROT_NOCHANGE = 0x08
    VM_PROT_COPY     = 0x10


# ---------------------------------------------------------------------------
# Tamaños de estructuras wire
# ---------------------------------------------------------------------------

PROC_LIST_ENTRY_SIZE: int = 36     # name[32] + pid int32
PROC_MAP_ENTRY_SIZE:  int = 58     # name[32] + start/end/offset uint64 + prot uint16
PROC_PROC_INFO_SIZE:  int = 188    # pid int32 + name[40] + path[64] + titleid[16] + contentid[64]
PROC_INSTALL_SIZE:    int = 8      # stub address uint64
PROC_ALLOC_SIZE:      int = 8      # address uint64
PROC_CALL_SIZE:       int = 12     # status uint32 + rax uint64

CMD_PROC_READ_PACKET_SIZE:    int = 16
CMD_PROC_WRITE_PACKET_SIZE:   int = 16
CMD_PROC_INFO_PACKET_SIZE:    int = 4
CMD_PROC_MAPS_PACKET_SIZE:    int = 4
CMD_PROC_INSTALL_PACKET_SIZE: int = 4
CMD_PROC_ALLOC_PACKET_SIZE:   int = 8
CMD_PROC_FREE_PACKET_SIZE:    int = 16
CMD_PROC_PROTECT_PACKET_SIZE: int = 20
CMD_PROC_SCAN_PACKET_SIZE:    int = 10
CMD_PROC_ELF_PACKET_SIZE:     int = 8


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass
class Process:
    """Proceso PS4: nombre + pid."""
    name: str
    pid: int

    def __str__(self) -> str:
        return f"[{self.pid}] {self.name}"


@dataclass
class ProcessInfo:
    """Información extendida de un proceso (CMD_PROC_INFO)."""
    pid: int = 0
    name: str = ""
    path: str = ""
    titleid: str = ""
    contentid: str = ""


def format_protection(prot: int) -> str:
    """Formatea un bitmask de protección como 'rwx' (con '-' por bit ausente)."""
    return ("r" if prot & VMProtection.VM_PROT_READ else "-") + \
           ("w" if prot & VMProtection.VM_PROT_WRITE else "-") + \
           ("x" if prot & VMProtection.VM_PROT_EXECUTE else "-")


class MemoryProtectionMixin:
    """Accesores de protección para cualquier región con un campo `prot`."""

    prot: int

    @property
    def readable(self) -> bool:
        return bool(self.prot & VMProtection.VM_PROT_READ)

    @property
    def writable(self) -> bool:
        return bool(self.prot & VMProtection.VM_PROT_WRITE)

    @property
    def executable(self) -> bool:
        return bool(self.prot & VMProtection.VM_PROT_EXECUTE)

    @property
    def prot_string(self) -> str:
        return format_protection(self.prot)


def format_region(name: str, prot: int, start: int, end: int, name_width: int) -> str:
    """Representación textual común de una región de memoria."""
    return (f"{name:{name_width}s} {format_protection(prot)} "
            f"0x{start:016X}-0x{end:016X} ({(end - start) // 1024} KB)")


@dataclass
class MemoryEntry(MemoryProtectionMixin):
    """Entrada del mapa de memoria de un proceso (CMD_PROC_MAPS)."""
    name: str = ""
    start: int = 0
    end: int = 0
    offset: int = 0
    prot: int = 0

    @property
    def length(self) -> int:
        return self.end - self.start

    def __str__(self) -> str:
        return format_region(self.name, self.prot, self.start, self.end, name_width=32)


@dataclass
class ProcessMap:
    """Mapa de memoria completo de un proceso."""
    pid: int
    entries: List[MemoryEntry] = field(default_factory=list)

    def find(self, name: str, contains: bool = False) -> Optional[MemoryEntry]:
        for e in self.entries:
            if contains:
                if name in e.name:
                    return e
            else:
                if e.name == name:
                    return e
        return None


# ---------------------------------------------------------------------------
# Serialización / deserialización
# ---------------------------------------------------------------------------

def build_header(cmd: int, datalen: int = 0) -> bytes:
    """Construye la cabecera de 12 bytes de un comando ps4debug."""
    return struct.pack("<III", CMD_PACKET_MAGIC, int(cmd), int(datalen))


def build_packet(cmd: int, payload: bytes = b"") -> bytes:
    """Construye un paquete completo: cabecera + payload."""
    return build_header(cmd, len(payload)) + payload


def parse_status(data: bytes) -> CMD_STATUS:
    """Convierte 4 bytes en un CMD_STATUS."""
    if len(data) < 4:
        raise ValueError("status buffer too short")
    return CMD_STATUS(struct.unpack("<I", data[:4])[0])


def cstr(data: bytes, offset: int = 0, encoding: str = "ascii") -> str:
    """
    Lee un string C (terminado en \\x00) desde `data` empezando en `offset`.
    Si no hay \\x00, devuelve hasta el final de `data`.
    """
    end = data.find(b"\x00", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode(encoding, errors="replace")


def parse_records(data: bytes, entry_size: int, parse_entry: Callable[[bytes], T]) -> List[T]:
    """Parsea `data` como una secuencia de registros de `entry_size` bytes."""
    return [
        parse_entry(data[off:off + entry_size])
        for off in range(0, (len(data) // entry_size) * entry_size, entry_size)
    ]


def _parse_process_entry(entry: bytes) -> Process:
    return Process(name=cstr(entry), pid=struct.unpack("<i", entry[32:36])[0])


def _parse_map_entry(entry: bytes) -> MemoryEntry:
    start, end, offset, prot = struct.unpack("<QQQH", entry[32:58])
    return MemoryEntry(name=cstr(entry), start=start, end=end, offset=offset, prot=prot)


def parse_process_list(data: bytes) -> List[Process]:
    """
    Parsea el payload de CMD_PROC_LIST: N * 36 bytes.
    Cada 36 bytes: name[32] + pid int32.
    """
    return parse_records(data, PROC_LIST_ENTRY_SIZE, _parse_process_entry)


def parse_process_info(data: bytes) -> ProcessInfo:
    """Parsea los 188 bytes de CMD_PROC_INFO."""
    if len(data) < PROC_PROC_INFO_SIZE:
        raise ValueError(f"process info buffer too short: {len(data)} < {PROC_PROC_INFO_SIZE}")
    pid = struct.unpack("<i", data[0:4])[0]
    name = cstr(data, 4)
    path = cstr(data, 44)
    titleid = cstr(data, 108)
    contentid = cstr(data, 124)
    return ProcessInfo(pid=pid, name=name, path=path, titleid=titleid, contentid=contentid)


def parse_process_maps(data: bytes) -> List[MemoryEntry]:
    """
    Parsea el payload de CMD_PROC_MAPS: N * 58 bytes.
    Cada 58 bytes: name[32] + start uint64 + end uint64 + offset uint64 + prot uint16.
    """
    return parse_records(data, PROC_MAP_ENTRY_SIZE, _parse_map_entry)


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def payload_pid(pid: int) -> bytes:
    """Payload de los comandos que solo llevan el pid: 4 bytes."""
    return struct.pack("<i", pid)


def payload_pid_address_length(pid: int, address: int, length: int) -> bytes:
    """
    Payload de CMD_PROC_READ / CMD_PROC_WRITE: 16 bytes.
    C# usa: BitConverter.GetBytes(pid) [4] + BitConverter.GetBytes(address) [8] + BitConverter.GetBytes(length) [4]
    Nota: NO hay padding, va pegado (4 + 8 + 4 = 16).
    """
    return struct.pack("<IQI", pid, address, length)


# Alias por comando (mismo wire format, nombres del protocolo)
payload_proc_read = payload_pid_address_length
payload_proc_write = payload_pid_address_length
payload_proc_info = payload_pid
payload_proc_maps = payload_pid
payload_proc_install = payload_pid


def payload_proc_alloc(pid: int, length: int) -> bytes:
    """Payload de CMD_PROC_ALLOC: 8 bytes (pid + length)."""
    return struct.pack("<ii", pid, length)


def payload_proc_free(pid: int, address: int, length: int) -> bytes:
    """Payload de CMD_PROC_FREE: 16 bytes (pid + address + length)."""
    return struct.pack("<iQI", pid, address, length)


def payload_proc_protect(pid: int, address: int, length: int, prot: int) -> bytes:
    """Payload de CMD_PROC_PROTECT: 20 bytes (pid + address + length + prot)."""
    return struct.pack("<iQII", pid, address, length, prot)


def payload_proc_scan(pid: int, value_type: int, compare_type: int, length: int) -> bytes:
    """Payload de CMD_PROC_SCAN: 10 bytes (pid + valType + compareType + length)."""
    return struct.pack("<IBBi", pid, value_type, compare_type, length)


def payload_console_notify(notice_type: int, message: str) -> bytes:
    """Payload de CMD_CONSOLE_NOTIFY: type int32 + length int32 + message bytes (UTF-8)."""
    msg_bytes = message.encode("utf-8")
    return struct.pack("<II", notice_type, len(msg_bytes)) + msg_bytes
