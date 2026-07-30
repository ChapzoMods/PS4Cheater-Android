"""
core/cheats.py — CheatList, freeze loop, export/import.

Port simplificado de CheatList.cs. El original soporta operadores compuestos
(aritmética, offsets, simple pointers, multi-level pointers). Aquí implementamos
una versión más práctica para CLI:

  - CheatEntry: address + value_type + value + frozen + description
  - CheatList: lista de entradas con add/remove/edit/freeze
  - FreezeThread: thread que re-escribe valores frozen cada N ms
  - Export/import JSON (formato propio) y .CT básico (compatible Cheat Engine)
"""

from __future__ import annotations

import json
import struct
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional

from lib import PS4DBG
from .types import ValueType, CompareType, MemoryTypeHandler, make_handler


# ---------------------------------------------------------------------------
# Mapeo con los VariableType de Cheat Engine (.CT)
# ---------------------------------------------------------------------------

CT_VARIABLE_TYPE_BY_VALUE_TYPE: dict[ValueType, str] = {
    ValueType.BYTE_TYPE:   "0",
    ValueType.USHORT_TYPE: "1",
    ValueType.UINT_TYPE:   "2",
    ValueType.ULONG_TYPE:  "3",
    ValueType.FLOAT_TYPE:  "4",
    ValueType.DOUBLE_TYPE: "5",
    ValueType.STRING_TYPE: "6",
    ValueType.HEX_TYPE:    "7",
}

CT_VALUE_TYPE_BY_VARIABLE_TYPE: dict[str, ValueType] = {
    ct_type: value_type for value_type, ct_type in CT_VARIABLE_TYPE_BY_VALUE_TYPE.items()
}


# ---------------------------------------------------------------------------
# CheatEntry
# ---------------------------------------------------------------------------

@dataclass
class CheatEntry:
    """Una entrada de cheat: dirección + tipo + valor + flags."""
    id: int
    address: int
    value_type: ValueType
    value: str              # valor en formato string (se convierte a bytes con handler)
    description: str = ""
    frozen: bool = False
    hex_value: bool = False   # si True, value se interpreta como hex string

    def to_handler(self) -> MemoryTypeHandler:
        return make_handler(self.value_type, CompareType.EXACT_VALUE, is_aligned=True)

    def to_bytes(self) -> bytes:
        return self.to_handler().parse_value(self.value, is_hex=self.hex_value)

    def from_bytes(self, data: bytes) -> str:
        return self.to_handler().format_value(data, hex_fmt=self.hex_value)


# ---------------------------------------------------------------------------
# CheatList
# ---------------------------------------------------------------------------

class CheatList:
    """
    Gestión de cheat entries con freeze loop opcional.
    """

    def __init__(self, ps4: Optional[PS4DBG] = None, pid: int = 0):
        self._entries: List[CheatEntry] = []
        self._next_id: int = 1
        self.ps4 = ps4
        self.pid = pid
        self._freeze_thread: Optional[threading.Thread] = None
        self._freeze_stop = threading.Event()
        self._freeze_interval: float = 0.1  # 100 ms
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def entries(self) -> List[CheatEntry]:
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, address: int, value_type: ValueType, value: str,
            description: str = "", frozen: bool = False, hex_value: bool = False) -> CheatEntry:
        with self._lock:
            entry = CheatEntry(
                id=self._next_id,
                address=address,
                value_type=value_type,
                value=value,
                description=description,
                frozen=frozen,
                hex_value=hex_value,
            )
            self._entries.append(entry)
            self._next_id += 1
            return entry

    def remove(self, entry_id: int) -> bool:
        with self._lock:
            for i, e in enumerate(self._entries):
                if e.id == entry_id:
                    self._entries.pop(i)
                    return True
            return False

    def get(self, entry_id: int) -> Optional[CheatEntry]:
        with self._lock:
            for e in self._entries:
                if e.id == entry_id:
                    return e
            return None

    def update(self, entry_id: int, **fields) -> bool:
        """Actualiza campos de una entrada. Devuelve False si el id no existe."""
        with self._lock:
            e = self.get(entry_id)
            if e is None:
                return False
            for name, value in fields.items():
                setattr(e, name, value)
            return True

    def set_frozen(self, entry_id: int, frozen: bool) -> bool:
        return self.update(entry_id, frozen=frozen)

    def set_value(self, entry_id: int, value: str) -> bool:
        return self.update(entry_id, value=value)

    def set_address(self, entry_id: int, address: int) -> bool:
        return self.update(entry_id, address=address)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._next_id = 1

    # ------------------------------------------------------------------
    # Apply / read
    # ------------------------------------------------------------------

    @property
    def _writable(self) -> bool:
        return self.ps4 is not None and self.ps4.is_connected

    def apply(self, entry: CheatEntry) -> bool:
        """Escribe el valor del cheat en memoria."""
        if not self._writable:
            return False
        try:
            data = entry.to_bytes()
            self.ps4.write_memory(self.pid, entry.address, data)
            return True
        except Exception:
            return False

    def apply_all(self) -> int:
        """Aplica TODOS los cheats (frozen o no). Returns: número de successes."""
        return sum(1 for e in self.entries if self.apply(e))

    def apply_frozen(self) -> int:
        """Aplica solo los cheats con frozen=True."""
        return sum(1 for e in self.entries if e.frozen and self.apply(e))

    def read_current(self, entry: CheatEntry) -> Optional[str]:
        """Lee el valor actual de la memoria y lo devuelve formateado."""
        if not self._writable:
            return None
        try:
            h = entry.to_handler()
            data = self.ps4.read_memory(self.pid, entry.address, h.length)
            return entry.from_bytes(data)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Freeze loop
    # ------------------------------------------------------------------

    def start_freeze_loop(self, interval: float = 0.1) -> bool:
        """Arranca el thread que re-escribe cheats frozen cada `interval` segundos."""
        if self._freeze_thread is not None and self._freeze_thread.is_alive():
            return True
        self._freeze_interval = interval
        self._freeze_stop.clear()
        self._freeze_thread = threading.Thread(target=self._freeze_loop, daemon=True)
        self._freeze_thread.start()
        return True

    def stop_freeze_loop(self) -> None:
        """Detiene el thread de freeze."""
        if self._freeze_thread is None:
            return
        self._freeze_stop.set()
        self._freeze_thread.join(timeout=2.0)
        self._freeze_thread = None

    def _freeze_loop(self) -> None:
        while not self._freeze_stop.is_set():
            try:
                self.apply_frozen()
            except Exception:
                pass
            self._freeze_stop.wait(self._freeze_interval)

    @property
    def freeze_running(self) -> bool:
        return self._freeze_thread is not None and self._freeze_thread.is_alive()

    # ------------------------------------------------------------------
    # Export / Import JSON
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "pid": self.pid,
            "entries": [
                {
                    "id": e.id,
                    "address": e.address,
                    "value_type": int(e.value_type),
                    "value_type_name": e.value_type.name,
                    "value": e.value,
                    "description": e.description,
                    "frozen": e.frozen,
                    "hex_value": e.hex_value,
                }
                for e in self._entries
            ],
        }

    @classmethod
    def from_dict(cls, d: dict, ps4: Optional[PS4DBG] = None) -> "CheatList":
        cl = cls(ps4=ps4, pid=d.get("pid", 0))
        for ed in d.get("entries", []):
            vt = ValueType(ed.get("value_type", int(ValueType.UINT_TYPE)))
            if "value_type_name" in ed:
                try:
                    vt = ValueType[ed["value_type_name"]]
                except KeyError:
                    pass
            entry = CheatEntry(
                id=ed["id"],
                address=ed["address"],
                value_type=vt,
                value=ed["value"],
                description=ed.get("description", ""),
                frozen=ed.get("frozen", False),
                hex_value=ed.get("hex_value", False),
            )
            cl._entries.append(entry)
            cl._next_id = max(cl._next_id, entry.id + 1)
        return cl

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, path: str, ps4: Optional[PS4DBG] = None) -> "CheatList":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f), ps4=ps4)

    # ------------------------------------------------------------------
    # Export .CT (Cheat Engine format — XML básico)
    # ------------------------------------------------------------------

    def save_ct(self, path: str, game_title: str = "PS4") -> None:
        """
        Guarda como .CT (XML de Cheat Engine).
        Nota: las addresses de PS4 son 64-bit; Cheat Engine las interpreta como
        hex string. El formato es compatible a nivel estructural pero las
        addresses pueden no funcionar directamente en Cheat Engine x86.
        """
        import xml.etree.ElementTree as ET
        root = ET.Element("CheatTable")
        cheat_entries = ET.SubElement(root, "CheatEntries")
        for e in self._entries:
            ce = ET.SubElement(cheat_entries, "CheatEntry")
            ce.set("ID", str(e.id))
            ET.SubElement(ce, "Description").text = e.description or f"cheat_{e.id}"
            ET.SubElement(ce, "VariableType").text = CT_VARIABLE_TYPE_BY_VALUE_TYPE.get(e.value_type, "2")
            ET.SubElement(ce, "Address").text = f"{e.address:X}"
            ET.SubElement(ce, "Active").text = "1" if e.frozen else "0"
        tree = ET.ElementTree(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)

    @classmethod
    def load_ct(cls, path: str, ps4: Optional[PS4DBG] = None) -> "CheatList":
        """Carga un .CT de Cheat Engine. Mapea variable types a ValueType."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        root = tree.getroot()
        cl = cls(ps4=ps4)
        for ce in root.iter("CheatEntry"):
            desc_el = ce.find("Description")
            vt_el = ce.find("VariableType")
            addr_el = ce.find("Address")
            active_el = ce.find("Active")
            desc = desc_el.text if desc_el is not None and desc_el.text else ""
            vt = CT_VALUE_TYPE_BY_VARIABLE_TYPE.get(vt_el.text if vt_el is not None else "2",
                                                    ValueType.UINT_TYPE)
            try:
                addr = int(addr_el.text, 16) if addr_el is not None and addr_el.text else 0
            except ValueError:
                continue
            frozen = active_el is not None and active_el.text == "1"
            cl.add(address=addr, value_type=vt, value="0", description=desc, frozen=frozen)
        return cl
