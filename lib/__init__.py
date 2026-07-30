"""lib — Cliente TCP del protocolo ps4debug/GoldHEN."""

from .protocol import (
    CMD, CMD_STATUS, VMProtection,
    Process, ProcessInfo, MemoryEntry, ProcessMap,
    MemoryProtectionMixin, format_protection, format_region,
    build_header, build_packet, parse_status, cstr, parse_records,
    parse_process_list, parse_process_info, parse_process_maps,
    payload_pid, payload_pid_address_length,
    payload_proc_read, payload_proc_write, payload_proc_info,
    payload_proc_maps, payload_proc_install, payload_proc_alloc,
    payload_proc_free, payload_proc_protect, payload_proc_scan,
    payload_console_notify,
    CMD_PACKET_MAGIC, CMD_PACKET_SIZE, NET_MAX_LENGTH,
    PS4DBG_PORT, GOLDHEN_PORT, BROADCAST_PORT, BROADCAST_MAGIC,
    PROC_LIST_ENTRY_SIZE, PROC_MAP_ENTRY_SIZE, PROC_PROC_INFO_SIZE,
)
from .ps4dbg import (
    PS4DBG, PS4DBGPool, PS4DBGError, PS4DBGNotConnected,
    connect_ps4debug, connect_goldhen,
)

__all__ = [
    # protocol
    "CMD", "CMD_STATUS", "VMProtection",
    "Process", "ProcessInfo", "MemoryEntry", "ProcessMap",
    "MemoryProtectionMixin", "format_protection", "format_region",
    "build_header", "build_packet", "parse_status", "cstr", "parse_records",
    "parse_process_list", "parse_process_info", "parse_process_maps",
    "payload_pid", "payload_pid_address_length",
    "payload_proc_read", "payload_proc_write", "payload_proc_info",
    "payload_proc_maps", "payload_proc_install", "payload_proc_alloc",
    "payload_proc_free", "payload_proc_protect", "payload_proc_scan",
    "payload_console_notify",
    "CMD_PACKET_MAGIC", "CMD_PACKET_SIZE", "NET_MAX_LENGTH",
    "PS4DBG_PORT", "GOLDHEN_PORT", "BROADCAST_PORT", "BROADCAST_MAGIC",
    "PROC_LIST_ENTRY_SIZE", "PROC_MAP_ENTRY_SIZE", "PROC_PROC_INFO_SIZE",
    # ps4dbg
    "PS4DBG", "PS4DBGPool", "PS4DBGError", "PS4DBGNotConnected",
    "connect_ps4debug", "connect_goldhen",
]
