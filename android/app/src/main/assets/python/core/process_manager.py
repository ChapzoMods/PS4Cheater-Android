"""
core/process_manager.py — Gestión de procesos y memoria.

Port de ProcessManager.cs:
  - MappedSection: una región de memoria con start/length/prot/name/result_list
  - MappedSectionList: lista de secciones con búsqueda binaria por address
  - ResultList: almacenamiento compacto bitmap+values (igual que C#)
  - ProcessManager: orquestador (procesos + section list)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

from lib import ProcessMap, MemoryEntry


# ---------------------------------------------------------------------------
# ResultList — bitmap compacto (port exacto de C#)
# ---------------------------------------------------------------------------

class ResultList:
    """
    Almacenamiento compacto de resultados de scan.

    Estructura (igual que C#):
      - Buffer de páginas de `buffer_size = 65536` bytes cada una
      - Cada "tag" dentro de una página:
          [offset_base uint32][bitmap uint64][value_0][value_1]...
        El bitmap indica cuáles de las 64 posiciones alineadas a partir de
        offset_base tienen un valor almacenado.
      - Un tag puede cubrir hasta 64 elementos. Cuando se llena, se crea el
        siguiente tag (o una nueva página si la actual no tiene espacio).

    Nota: a diferencia de un dict {addr: value}, esta estructura ocupa mucho
    menos memoria cuando hay muchos valores contiguos o cercanos.
    """

    BIT_MAP_SIZE: int = 8          # 64 bits
    BUFFER_SIZE: int = 4096 * 16   # 65536 bytes por página
    OFFSET_SIZE: int = 4

    def __init__(self, element_size: int, element_alignment: int):
        if element_size <= 0:
            raise ValueError("element_size must be > 0")
        if element_alignment <= 0:
            raise ValueError("element_alignment must be > 0")
        self.element_size = element_size
        self.element_alignment = element_alignment

        # Estado interno
        self._buffers: List[bytearray] = [bytearray(self.BUFFER_SIZE)]
        self._buffer_id: int = 0
        self._buffer_tag_offset: int = 0
        self._buffer_tag_elem_count: int = 0
        self._count: int = 0

        # Iterador
        self._iter_idx: int = 0
        self._iter_buffer_id: int = 0
        self._iter_tag_offset: int = 0
        self._iter_tag_elem_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        return self._count

    def __len__(self) -> int:
        return self._count

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def add(self, memory_address_offset: int, memory_value: bytes) -> None:
        """
        Agrega un resultado. La address_offset debe ser >= la última añadida
        dentro del tag actual.
        Replica ResultList.Add() de C#.
        """
        if len(memory_value) != self.element_size:
            raise ValueError(f"value size mismatch: {len(memory_value)} != {self.element_size}")

        buf = self._buffers[self._buffer_id]

        # Lee el tag actual
        tag_address_offset_base = struct.unpack_from("<I", buf, self._buffer_tag_offset)[0] if self._buffer_tag_elem_count > 0 or self._has_tag_data() else 0
        # El C# siempre lee los 4 bytes, así que hacemos lo mismo:
        tag_address_offset_base = struct.unpack_from("<I", buf, self._buffer_tag_offset)[0]

        if self._count > 0 and tag_address_offset_base > memory_address_offset:
            # En el C# esto lanza excepción; pero ocurre normalmente solo si se añaden desordenados.
            # Lo toleramos mejor: forzamos un nuevo tag.
            self._advance_tag(advance_to_new_page_if_needed=True)
            return self._add_to_fresh_tag(memory_address_offset, memory_value)

        # Si el bitmap está vacío, este es el primer elemento del tag
        bitmap = struct.unpack_from("<Q", buf, self._buffer_tag_offset + self.OFFSET_SIZE)[0]
        if bitmap == 0:
            tag_address_offset_base = memory_address_offset
            struct.pack_into("<I", buf, self._buffer_tag_offset, memory_address_offset)

        offset_in_bit_map = (memory_address_offset - tag_address_offset_base) // self.element_alignment
        if offset_in_bit_map < 64:
            # Cabe en el tag actual
            byte_pos = self._buffer_tag_offset + self.OFFSET_SIZE + (offset_in_bit_map // 8)
            buf[byte_pos] |= (1 << (offset_in_bit_map % 8))
            value_pos = self._buffer_tag_offset + self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * self._buffer_tag_elem_count
            buf[value_pos:value_pos + self.element_size] = memory_value
            self._buffer_tag_elem_count += 1
        else:
            # No cabe: avanzar al siguiente tag (posiblemente nueva página)
            self._advance_tag(advance_to_new_page_if_needed=True)
            self._add_to_fresh_tag(memory_address_offset, memory_value)

        self._count += 1

    def _has_tag_data(self) -> bool:
        return self._buffer_tag_elem_count > 0

    def _advance_tag(self, advance_to_new_page_if_needed: bool = True) -> None:
        """Avanza `_buffer_tag_offset` al siguiente tag."""
        self._buffer_tag_offset += self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * self._buffer_tag_elem_count
        # ¿Necesita nueva página?
        needed = self._buffer_tag_offset + self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * 64
        if needed >= self.BUFFER_SIZE:
            if advance_to_new_page_if_needed:
                self._buffers.append(bytearray(self.BUFFER_SIZE))
                self._buffer_id += 1
                self._buffer_tag_offset = 0
            # Reset del contador de elementos del tag
        self._buffer_tag_elem_count = 0
        # Limpiar bitmap en la nueva posición
        if 0 <= self._buffer_tag_offset < self.BUFFER_SIZE:
            buf = self._buffers[self._buffer_id]
            # Asegurar que bitmap = 0
            struct.pack_into("<Q", buf, self._buffer_tag_offset + self.OFFSET_SIZE, 0)
            struct.pack_into("<I", buf, self._buffer_tag_offset, 0)

    def _add_to_fresh_tag(self, memory_address_offset: int, memory_value: bytes) -> None:
        """Añade el primer elemento a un tag recién creado/avanzado.
        Nota: NO incrementa _count; el caller (add()) ya lo hace."""
        buf = self._buffers[self._buffer_id]
        # Set tag base address
        struct.pack_into("<I", buf, self._buffer_tag_offset, memory_address_offset)
        # Set bitmap con bit 0
        struct.pack_into("<Q", buf, self._buffer_tag_offset + self.OFFSET_SIZE, 1)
        # Set value
        value_pos = self._buffer_tag_offset + self.OFFSET_SIZE + self.BIT_MAP_SIZE
        buf[value_pos:value_pos + self.element_size] = memory_value
        self._buffer_tag_elem_count = 1

    # ------------------------------------------------------------------
    # Iteración (Begin / End / Next / Get)
    # ------------------------------------------------------------------

    def begin(self) -> None:
        """Inicia iteración."""
        self._iter_idx = 0
        self._iter_buffer_id = 0
        self._iter_tag_offset = 0
        self._iter_tag_elem_count = 0

    def end(self) -> bool:
        return self._iter_idx == self._count

    def get(self) -> Tuple[int, bytes]:
        """Devuelve (address_offset, value) del elemento actual."""
        buf = self._buffers[self._iter_buffer_id]
        offset_base = struct.unpack_from("<I", buf, self._iter_tag_offset)[0]
        bitmap = struct.unpack_from("<Q", buf, self._iter_tag_offset + self.OFFSET_SIZE)[0]
        bit_pos = _bit_position(bitmap, self._iter_tag_elem_count)
        addr = bit_pos * self.element_alignment + offset_base
        value_pos = self._iter_tag_offset + self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * self._iter_tag_elem_count
        value = bytes(buf[value_pos:value_pos + self.element_size])
        return addr, value

    def next(self) -> None:
        """Avanza al siguiente elemento."""
        self._iter_idx += 1
        if self._iter_idx >= self._count:
            return

        buf = self._buffers[self._iter_buffer_id]
        bitmap = struct.unpack_from("<Q", buf, self._iter_tag_offset + self.OFFSET_SIZE)[0]
        self._iter_tag_elem_count += 1

        # Si ya consumimos todos los bits set del tag, avanzar al siguiente tag
        if _bit_count(bitmap, 63) <= self._iter_tag_elem_count:
            self._iter_tag_offset += self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * self._iter_tag_elem_count
            if self._iter_tag_offset + self.OFFSET_SIZE + self.BIT_MAP_SIZE + self.element_size * 64 >= self.BUFFER_SIZE:
                self._iter_buffer_id += 1
                self._iter_tag_offset = 0
                self._iter_tag_elem_count = 0
            else:
                self._iter_tag_elem_count = 0

    def __iter__(self) -> Iterator[Tuple[int, bytes]]:
        self.begin()
        while not self.end():
            yield self.get()
            self.next()

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._buffers = [bytearray(self.BUFFER_SIZE)]
        self._buffer_id = 0
        self._buffer_tag_offset = 0
        self._buffer_tag_elem_count = 0
        self._count = 0
        self._iter_idx = 0
        self._iter_buffer_id = 0
        self._iter_tag_offset = 0
        self._iter_tag_elem_count = 0

    def get_addresses(self) -> List[int]:
        """Devuelve todas las addresses (para debugging)."""
        out: List[int] = []
        for addr, _ in self:
            out.append(addr)
        return out


# ---------------------------------------------------------------------------
# Bit helpers (replica bit_count y bit_position de C#)
# ---------------------------------------------------------------------------

def _bit_count(data: int, end: int) -> int:
    """Cuenta bits set en posiciones 0..end inclusive."""
    s = 0
    for i in range(end + 1):
        if (data >> i) & 1:
            s += 1
    return s

def _bit_position(data: int, pos: int) -> int:
    """Devuelve la posición del bit `pos`-ésimo set (0-indexed)."""
    s = 0
    for i in range(64):
        if (data >> i) & 1:
            if s == pos:
                return i
            s += 1
    return -1


# ---------------------------------------------------------------------------
# MappedSection
# ---------------------------------------------------------------------------

@dataclass
class MappedSection:
    """Una región de memoria del proceso a la que se le puede hacer scan."""
    start: int
    length: int
    name: str
    prot: int
    check: bool = False
    result_list: Optional[ResultList] = None

    @property
    def end(self) -> int:
        return self.start + self.length

    @property
    def readable(self) -> bool:
        return bool(self.prot & 0x1)

    @property
    def writable(self) -> bool:
        return bool(self.prot & 0x2)

    @property
    def executable(self) -> bool:
        return bool(self.prot & 0x4)

    def contains(self, address: int) -> bool:
        return self.start <= address < self.end

    def __str__(self) -> str:
        prot_str = "".join([
            "r" if self.prot & 0x1 else "-",
            "w" if self.prot & 0x2 else "-",
            "x" if self.prot & 0x4 else "-",
        ])
        return (f"{self.name:36s} {prot_str} "
                f"0x{self.start:016X}-0x{self.end:016X} ({self.length // 1024} KB)")


# ---------------------------------------------------------------------------
# MappedSectionList
# ---------------------------------------------------------------------------

class MappedSectionList:
    """
    Lista de MappedSections con búsqueda binaria por address.
    Port de MappedSectionList de C#.
    """

    def __init__(self):
        self._sections: List[MappedSection] = []
        self.total_memory_size: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._sections)

    def __len__(self) -> int:
        return len(self._sections)

    def __getitem__(self, idx: int) -> MappedSection:
        return self._sections[idx]

    def __iter__(self):
        return iter(self._sections)

    # ------------------------------------------------------------------
    # Init from ProcessMap
    # ------------------------------------------------------------------

    def init_from_process_map(self, pm: ProcessMap, buffer_length: int = 128 * 1024 * 1024) -> None:
        """
        Inicializa la lista a partir de un ProcessMap.
        Replica InitMemorySectionList de C#:
          - Filtra entradas con (prot & 0x1) == 0x1 (legibles)
          - Divide entradas grandes en chunks de `buffer_length` (128 MB por defecto)
          - El ejecutable (prot & 0x5) == 0x5 se deja en un solo bloque
        """
        self._sections.clear()
        self.total_memory_size = 0

        for entry in pm.entries:
            if not (entry.prot & 0x1):  # readable
                continue
            length = entry.end - entry.start
            start = entry.start
            name = entry.name
            idx = 0
            cur_buffer_length = buffer_length

            # Executable section: se deja en un solo bloque
            if (entry.prot & 0x5) == 0x5:
                cur_buffer_length = length

            while length != 0:
                cur_length = cur_buffer_length
                if cur_length > length:
                    cur_length = length
                    length = 0
                else:
                    length -= cur_length

                section = MappedSection(
                    start=start,
                    length=cur_length,
                    name=f"{name}[{idx}]",
                    prot=entry.prot,
                    check=False,
                )
                self._sections.append(section)
                start += cur_length
                idx += 1

    # ------------------------------------------------------------------
    # Section check / total size
    # ------------------------------------------------------------------

    def section_check(self, idx: int, checked: bool) -> None:
        """Marca/desmarca una sección para scan."""
        s = self._sections[idx]
        if s.check == checked:
            return
        s.check = checked
        if checked:
            self.total_memory_size += s.length
        else:
            self.total_memory_size -= s.length

    def check_all(self, checked: bool = True) -> None:
        for i in range(len(self._sections)):
            self.section_check(i, checked)

    def clear_result_lists(self) -> None:
        for s in self._sections:
            if s.result_list is not None:
                s.result_list.clear()
                s.result_list = None

    def total_result_count(self) -> int:
        n = 0
        for s in self._sections:
            if s.check and s.result_list is not None:
                n += s.result_list.count
        return n

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_mapped_section(self, address: int) -> Optional[MappedSection]:
        sid = self.get_mapped_section_id(address)
        if sid < 0:
            return None
        return self._sections[sid]

    def get_mapped_section_id(self, address: int) -> int:
        """Búsqueda binaria."""
        if not self._sections:
            return -1
        start = self._sections[0].start
        last = self._sections[-1]
        end = last.start + last.length
        if address < start or address >= end:
            return -1
        return self._find_section_id(address)

    def _find_section_id(self, address: int) -> int:
        low = 0
        high = len(self._sections) - 1
        while low <= high:
            middle = (low + high) // 2
            s = self._sections[middle]
            if address >= s.start + s.length:
                low = middle + 1
            elif address < s.start:
                high = middle - 1
            else:
                return middle
        return -1

    def get_sections_by_name_prot(self, name: str, prot: int) -> List[MappedSection]:
        out: List[MappedSection] = []
        for s in self._sections:
            if s.prot == prot and s.name.startswith(name):
                out.append(s)
        return out

    def get_section_name(self, idx: int) -> str:
        if idx < 0 or idx >= len(self._sections):
            return f"Section Index {idx} wrong!"
        s = self._sections[idx]
        return f"{s.name}-0x{s.prot:X}-0x{s.start:X}-{s.length // 1024}KB"


# ---------------------------------------------------------------------------
# ProcessManager
# ---------------------------------------------------------------------------

@dataclass
class ProcessManager:
    """
    Orquestador: holds una MappedSectionList y (opcionalmente) info del proceso.
    """
    pid: int = 0
    name: str = ""
    mapped_section_list: MappedSectionList = field(default_factory=MappedSectionList)

    def init_sections(self, pm: ProcessMap, buffer_length: int = 32 * 1024 * 1024) -> None:
        """Inicializa la section list a partir del process map de un proceso."""
        self.mapped_section_list.init_from_process_map(pm, buffer_length=buffer_length)

    def attach(self, pid: int, name: str = "") -> None:
        self.pid = pid
        self.name = name

    @property
    def total_memory_size(self) -> int:
        return self.mapped_section_list.total_memory_size

    @property
    def section_count(self) -> int:
        return self.mapped_section_list.count
