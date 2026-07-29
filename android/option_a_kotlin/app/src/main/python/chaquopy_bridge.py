"""
chaquopy_bridge.py — Bridge entre Kotlin (Chaquopy) y el core de Python.

Este módulo es invocado desde Kotlin via Chaquopy:
    val py = Python.getInstance()
    val module = py.getModule("chaquopy_bridge")
    val result = module.callAttr("connect", ip, port)

Cada función devuelve un dict (Python) que Chaquopy convierte a PyObject/Map
en Java/Kotlin. Todas las funciones devuelven:
    {"ok": True, ...}               en caso de éxito
    {"ok": False, "error": "..."}   en caso de error

El estado (ps4, pool, process_manager, scan_engine, cheats, handler) se
mantiene a nivel de módulo para persistir entre llamadas.
"""

from __future__ import annotations

import os
import sys
import struct
import threading
import traceback
from typing import Any, Dict, List, Optional

# Chaquopy pone app/src/main/python/ en sys.path, así que podemos importar
# lib y core como paquetes normales.
try:
    from lib import (
        PS4DBG, PS4DBGPool, PS4DBGError,
        PS4DBG_PORT, GOLDHEN_PORT,
    )
    from lib import protocol as P
    from core import (
        ValueType, CompareType,
        MemoryTypeHandler, make_handler,
        lookup_value_type, lookup_compare_type,
        MappedSection, MappedSectionList, ProcessManager, ResultList,
        ScanEngine, ScanProgress,
        CheatEntry, CheatList,
        Pointer, PointerList, PointerResult,
        VALUE_TYPE_TO_STR,
    )
    _IMPORTS_OK = True
    _IMPORT_ERROR = ""
except Exception as e:
    _IMPORTS_OK = False
    _IMPORT_ERROR = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Estado global del módulo (persiste entre llamadas de Kotlin)
# ---------------------------------------------------------------------------

class _State:
    def __init__(self):
        self.ps4: Optional[PS4DBG] = None
        self.pool: Optional[PS4DBGPool] = None
        self.pm: ProcessManager = ProcessManager()
        self.scan_engine: Optional[ScanEngine] = None
        self.cheats: CheatList = CheatList()
        self.handler: Optional[MemoryTypeHandler] = None
        self.connected: bool = False
        self._lock = threading.RLock()

    def reset(self):
        with self._lock:
            if self.cheats and self.cheats.freeze_running:
                self.cheats.stop_freeze_loop()
            if self.pool:
                try:
                    self.pool.disconnect_all()
                except Exception:
                    pass
            elif self.ps4:
                try:
                    self.ps4.disconnect()
                except Exception:
                    pass
            self.ps4 = None
            self.pool = None
            self.scan_engine = None
            self.connected = False
            self.pm = ProcessManager()
            self.cheats = CheatList()
            self.handler = None


_state = _State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(**kwargs) -> Dict[str, Any]:
    d = {"ok": True}
    d.update(kwargs)
    return d


def _err(msg: str) -> Dict[str, Any]:
    return {"ok": False, "error": str(msg)}


def _require_connected() -> Optional[Dict[str, Any]]:
    if not _state.connected or _state.ps4 is None:
        return _err("not connected")
    return None


def _require_attached() -> Optional[Dict[str, Any]]:
    e = _require_connected()
    if e:
        return e
    if _state.pm.pid == 0:
        return _err("not attached")
    return None


def _parse_address(s: str) -> int:
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    if all(c in "0123456789abcdefABCDEF" for c in s) and any(c in "abcdefABCDEF" for c in s):
        return int(s, 16)
    try:
        v = int(s)
        if v > 0x10000:
            return int(s, 16)
        return v
    except ValueError:
        return int(s, 16)


# ---------------------------------------------------------------------------
# API pública (invocada desde Kotlin)
# ---------------------------------------------------------------------------

def check_imports() -> Dict[str, Any]:
    """Verifica que los módulos Python se cargaron correctamente."""
    if _IMPORTS_OK:
        return _ok(message="imports OK")
    return _err(_IMPORT_ERROR)


def connect(ip: str, port: int = 744) -> Dict[str, Any]:
    """Conecta a una PS4 con ps4debug/GoldHEN."""
    try:
        _state.reset()
        _state.ps4 = PS4DBG(ip, int(port), timeout=30.0)
        if not _state.ps4.connect():
            return _err(f"cannot connect to {ip}:{port}")
        _state.pool = PS4DBGPool(ip, int(port), size=2, timeout=30.0)
        _state.pool.connect_all()
        _state.scan_engine = ScanEngine(_state.pool, _state.pm, num_comparers=1)
        _state.cheats = CheatList(ps4=_state.ps4, pid=0)
        _state.connected = True
        try:
            version = _state.ps4.get_console_debug_version()
        except Exception:
            version = ""
        return _ok(version=version, ip=ip, port=int(port))
    except Exception as e:
        return _err(f"{type(e).__name__}: {e}")


def disconnect() -> Dict[str, Any]:
    """Cierra la conexión."""
    try:
        _state.reset()
        return _ok()
    except Exception as e:
        return _err(str(e))


def get_status() -> Dict[str, Any]:
    """Devuelve el estado actual de la sesión."""
    return _ok(
        connected=_state.connected,
        ip=_state.ps4.ip if _state.ps4 else "",
        port=_state.ps4.port if _state.ps4 else 0,
        pid=_state.pm.pid,
        proc_name=_state.pm.name,
        section_count=_state.pm.section_count,
        result_count=_state.pm.mapped_section_list.total_result_count(),
        cheat_count=len(_state.cheats),
        freeze_running=_state.cheats.freeze_running if _state.cheats else False,
    )


def get_procs() -> Dict[str, Any]:
    """Lista los procesos de la PS4."""
    e = _require_connected()
    if e:
        return e
    try:
        procs = _state.ps4.get_process_list()
        return _ok(procs=[{"pid": p.pid, "name": p.name} for p in procs])
    except Exception as ex:
        return _err(str(ex))


def attach(pid: int) -> Dict[str, Any]:
    """Attachea a un proceso y carga sus memory maps."""
    e = _require_connected()
    if e:
        return e
    try:
        pid = int(pid)
        procs = _state.ps4.get_process_list()
        name = ""
        for p in procs:
            if p.pid == pid:
                name = p.name
                break
        pmap = _state.ps4.get_process_maps(pid)
        _state.pm.mapped_section_list.clear_result_lists()
        _state.pm.init_sections(pmap, buffer_length=32 * 1024 * 1024)
        _state.pm.attach(pid, name)
        _state.cheats.pid = pid
        _state.handler = None
        return _ok(name=name, section_count=_state.pm.section_count)
    except Exception as ex:
        return _err(str(ex))


def get_sections() -> Dict[str, Any]:
    """Lista las secciones de memoria del proceso attacheado."""
    e = _require_attached()
    if e:
        return e
    try:
        sections = []
        for i, s in enumerate(_state.pm.mapped_section_list):
            sections.append({
                "idx": i,
                "name": s.name,
                "start": s.start,
                "end": s.end,
                "length": s.length,
                "prot": s.prot,
                "prot_str": ("r" if s.readable else "-") + ("w" if s.writable else "-") + ("x" if s.executable else "-"),
                "check": s.check,
            })
        return _ok(sections=sections, total_size=_state.pm.total_memory_size)
    except Exception as ex:
        return _err(str(ex))


def set_section_check(idx: int, checked: bool) -> Dict[str, Any]:
    e = _require_attached()
    if e:
        return e
    try:
        idx = int(idx)
        if idx < 0 or idx >= _state.pm.section_count:
            return _err("invalid section idx")
        _state.pm.mapped_section_list.section_check(idx, bool(checked))
        return _ok(total_size=_state.pm.total_memory_size)
    except Exception as ex:
        return _err(str(ex))


def check_all_sections(mode: str = "rw_only") -> Dict[str, Any]:
    """Marca secciones: 'all', 'none', o 'rw_only' (solo rw- no ejecutables)."""
    e = _require_attached()
    if e:
        return e
    try:
        if mode == "all":
            _state.pm.mapped_section_list.check_all(True)
        elif mode == "none":
            _state.pm.mapped_section_list.check_all(False)
        else:
            _state.pm.mapped_section_list.check_all(False)
            for i, s in enumerate(_state.pm.mapped_section_list):
                if s.writable and not s.executable:
                    _state.pm.mapped_section_list.section_check(i, True)
        return _ok(total_size=_state.pm.total_memory_size)
    except Exception as ex:
        return _err(str(ex))


def scan_new(value_type: str, compare_type: str, value1: str = "",
             value2: str = "", hex_fmt: bool = False, unaligned: bool = False,
             length: int = 0) -> Dict[str, Any]:
    """Primer escaneo."""
    e = _require_attached()
    if e:
        return e
    try:
        vt = lookup_value_type(value_type)
        ct = lookup_compare_type(compare_type)
        _state.pm.mapped_section_list.clear_result_lists()
        handler = make_handler(vt, ct, is_aligned=not bool(unaligned), type_length=int(length))
        _state.handler = handler
        v0 = handler.parse_value(value1, bool(hex_fmt)) if handler.parse_first_value and value1 else b""
        v1 = handler.parse_value(value2, bool(hex_fmt)) if handler.parse_second_value and value2 else b""
        if _state.pm.total_memory_size == 0:
            # Auto-marcar rw- si no hay nada marcado
            for i, s in enumerate(_state.pm.mapped_section_list):
                if s.writable and not s.executable:
                    _state.pm.mapped_section_list.section_check(i, True)
            if _state.pm.total_memory_size == 0:
                return _err("no sections marked for scan")
        count = _state.scan_engine.new_scan(handler, v0, v1)
        return _ok(count=count)
    except ValueError as ex:
        return _err(str(ex))
    except Exception as ex:
        return _err(f"{type(ex).__name__}: {ex}")


def scan_next(compare_type: str, value1: str = "", value2: str = "",
              hex_fmt: bool = False) -> Dict[str, Any]:
    """Escaneo sucesivo."""
    e = _require_attached()
    if e:
        return e
    try:
        if _state.handler is None:
            return _err("no previous scan")
        ct = lookup_compare_type(compare_type)
        handler = make_handler(_state.handler.value_type, ct,
                               is_aligned=(_state.handler.alignment != 1),
                               type_length=_state.handler.length)
        _state.handler = handler
        v0 = handler.parse_value(value1, bool(hex_fmt)) if handler.parse_first_value and value1 else b""
        v1 = handler.parse_value(value2, bool(hex_fmt)) if handler.parse_second_value and value2 else b""
        count = _state.scan_engine.next_scan(handler, v0, v1)
        return _ok(count=count)
    except Exception as ex:
        return _err(f"{type(ex).__name__}: {ex}")


def get_scan_results(limit: int = 50) -> Dict[str, Any]:
    """Devuelve los resultados del último scan."""
    e = _require_attached()
    if e:
        return e
    try:
        if _state.handler is None:
            return _err("no previous scan")
        items = _state.scan_engine.get_all_results(limit=int(limit))
        h = _state.handler
        results = []
        for addr, val in items:
            try:
                val_str = h.bytes_to_string(val)
            except Exception:
                val_str = "?"
            try:
                val_hex = h.bytes_to_hex_string(val) if h.bytes_to_hex_string else val.hex()
            except Exception:
                val_hex = val.hex()
            results.append({
                "address": addr,
                "value": val_str,
                "value_hex": val_hex,
            })
        return _ok(
            results=results,
            total=_state.pm.mapped_section_list.total_result_count(),
            value_type=_state.handler.value_type.name,
            compare_type=_state.handler.compare_type.name,
        )
    except Exception as ex:
        return _err(str(ex))


def read_memory(address: str, length: int) -> Dict[str, Any]:
    """Lee memoria y devuelve hex + ascii."""
    e = _require_attached()
    if e:
        return e
    try:
        addr = _parse_address(str(address))
        length = int(length)
        mem = _state.ps4.read_memory(_state.pm.pid, addr, length)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in mem)
        return _ok(
            address=addr,
            length=length,
            hex=mem.hex(),
            ascii=ascii_str,
        )
    except Exception as ex:
        return _err(str(ex))


def write_memory(address: str, hex_bytes: str) -> Dict[str, Any]:
    """Ecribe bytes hex en memoria."""
    e = _require_attached()
    if e:
        return e
    try:
        addr = _parse_address(str(address))
        hex_str = str(hex_bytes).replace(" ", "").replace("\t", "")
        if hex_str.lower().startswith("0x"):
            hex_str = hex_str[2:]
        mem = bytes.fromhex(hex_str)
        _state.ps4.write_memory(_state.pm.pid, addr, mem)
        return _ok(written=len(mem))
    except ValueError as ex:
        return _err(f"invalid hex: {ex}")
    except Exception as ex:
        return _err(str(ex))


def add_cheat(address: str, value_type: str, value: str,
              description: str = "", frozen: bool = False,
              hex_value: bool = False) -> Dict[str, Any]:
    """Añade un cheat y lo aplica inmediatamente."""
    e = _require_attached()
    if e:
        return e
    try:
        vt = lookup_value_type(value_type)
        addr = _parse_address(str(address))
        entry = _state.cheats.add(
            address=addr, value_type=vt, value=str(value),
            description=str(description), frozen=bool(frozen),
            hex_value=bool(hex_value),
        )
        _state.cheats.apply(entry)
        if entry.frozen and not _state.cheats.freeze_running:
            _state.cheats.start_freeze_loop()
        return _ok(id=entry.id)
    except Exception as ex:
        return _err(f"{type(ex).__name__}: {ex}")


def list_cheats() -> Dict[str, Any]:
    """Lista todos los cheats."""
    try:
        cheats = []
        for e in _state.cheats:
            cheats.append({
                "id": e.id,
                "address": e.address,
                "value_type": e.value_type.name,
                "value": e.value,
                "frozen": e.frozen,
                "hex_value": e.hex_value,
                "description": e.description,
            })
        return _ok(cheats=cheats, freeze_running=_state.cheats.freeze_running)
    except Exception as ex:
        return _err(str(ex))


def remove_cheat(cid: int) -> Dict[str, Any]:
    try:
        if _state.cheats.remove(int(cid)):
            return _ok()
        return _err("cheat not found")
    except Exception as ex:
        return _err(str(ex))


def set_cheat_frozen(cid: int, frozen: bool) -> Dict[str, Any]:
    try:
        if _state.cheats.set_frozen(int(cid), bool(frozen)):
            if frozen and not _state.cheats.freeze_running:
                _state.cheats.start_freeze_loop()
            return _ok()
        return _err("cheat not found")
    except Exception as ex:
        return _err(str(ex))


def apply_cheat(cid: int) -> Dict[str, Any]:
    e = _require_connected()
    if e:
        return e
    try:
        entry = _state.cheats.get(int(cid))
        if entry is None:
            return _err("cheat not found")
        if _state.cheats.apply(entry):
            return _ok()
        return _err("apply failed")
    except Exception as ex:
        return _err(str(ex))


def apply_all_cheats() -> Dict[str, Any]:
    e = _require_connected()
    if e:
        return e
    try:
        n = _state.cheats.apply_all()
        return _ok(applied=n)
    except Exception as ex:
        return _err(str(ex))


def apply_frozen() -> Dict[str, Any]:
    """Aplica solo los cheats frozen. Llamado periódicamente por el FreezeService."""
    e = _require_connected()
    if e:
        return e
    try:
        n = _state.cheats.apply_frozen()
        return _ok(applied=n)
    except Exception:
        return _ok(applied=0)


def start_freeze() -> Dict[str, Any]:
    """Inicia el freeze loop dentro de Python (alternativa al FreezeService de Kotlin)."""
    try:
        if not _state.cheats.freeze_running:
            _state.cheats.start_freeze_loop(interval=0.1)
        return _ok()
    except Exception as ex:
        return _err(str(ex))


def stop_freeze() -> Dict[str, Any]:
    try:
        _state.cheats.stop_freeze_loop()
        return _ok()
    except Exception as ex:
        return _err(str(ex))


def notify(message: str, ntype: int = 0) -> Dict[str, Any]:
    """Envía una notificación a la PS4."""
    e = _require_connected()
    if e:
        return e
    try:
        _state.ps4.notify(int(ntype), str(message))
        return _ok()
    except Exception as ex:
        return _err(str(ex))


def pointer_scan(target_address: str, depth: int = 3, max_range: int = 0x10000) -> Dict[str, Any]:
    """Escanea buscando punteros que terminen en target_address."""
    e = _require_attached()
    if e:
        return e
    try:
        addr = _parse_address(str(target_address))
        depth = max(1, min(5, int(depth)))
        pl = PointerList()
        _state.scan_engine.pointer_scan(pl)
        pl.init()
        ranges = [int(max_range)] * depth
        results = pl.find_pointer_list(addr, ranges)
        paths = []
        for r in results[:50]:
            paths.append({
                "base_address": r.base_address,
                "offsets": r.offsets,
            })
        return _ok(paths=paths, total=len(results), pointer_count=pl.count)
    except Exception as ex:
        return _err(str(ex))


def get_value_types() -> Dict[str, Any]:
    """Devuelve la lista de tipos de valor soportados (para UI)."""
    from core.types import STR_TO_VALUE_TYPE
    return _ok(types=list(STR_TO_VALUE_TYPE.keys()))


def get_compare_types() -> Dict[str, Any]:
    """Devuelve la lista de comparadores soportados (para UI)."""
    from core.types import STR_TO_COMPARE_TYPE
    return _ok(types=list(STR_TO_COMPARE_TYPE.keys()))
