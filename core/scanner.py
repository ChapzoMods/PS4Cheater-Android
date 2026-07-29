"""
core/scanner.py — Motor de escaneo de memoria.

Port de MemoryHelper.cs (CompareWithMemoryBuffer*) + ScanThread.cs (PeekThread/ComparerThread).

Diseño:
  - 1 productor lee bloques de memoria por TCP
  - N consumidores comparan (parametrizables; default 2 para móvil)
  - Cola thread-safe con tamaño máximo (backpressure)
  - Progreso vía callback (0-100)
  - Cancelación vía threading.Event

Optimización:
  - Para tipos uint8/16/32/64 y float: usa numpy.frombuffer para decodificar
    todo el buffer de una vez y comparar vectorialmente (mucho más rápido).
  - Fallback a loop Python para hex/string/pointer.
"""

from __future__ import annotations

import struct
import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from lib import PS4DBG, PS4DBGPool
from .process_manager import MappedSection, MappedSectionList, ResultList
from .types import (
    CompareType, MemoryTypeHandler, ValueType,
    make_handler,
)

# numpy es opcional pero recomendado para rendimiento
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_PEEK_BUFFER: int = 32 * 1024 * 1024   # 32 MB (móvil-friendly)
DEFAULT_MAX_PEEK_QUEUE: int = 4
DEFAULT_NUM_COMPARERS: int = 2


# ---------------------------------------------------------------------------
# Utilidades para escaneo vectorial con numpy
# ---------------------------------------------------------------------------

_NUMPY_DTYPES = {
    ValueType.BYTE_TYPE:   np.uint8,
    ValueType.USHORT_TYPE: np.uint16,
    ValueType.UINT_TYPE:   np.uint32,
    ValueType.ULONG_TYPE:  np.uint64,
    ValueType.FLOAT_TYPE:  np.float32,
    ValueType.DOUBLE_TYPE: np.float64,
}


def _new_scan_vectorized(
    handler: MemoryTypeHandler,
    buffer: bytes,
    default_value_0: Optional[bytes],
    default_value_1: Optional[bytes],
    base_address: int,
    result_list: ResultList,
) -> None:
    """
    Escaneo de nuevo usando numpy para tipos numéricos.
    Para tipos no numéricos (hex/string), hace fallback al loop Python.
    """
    if not HAS_NUMPY or handler.value_type not in _NUMPY_DTYPES:
        _new_scan_python(handler, buffer, default_value_0, default_value_1, base_address, result_list)
        return

    dtype = _NUMPY_DTYPES[handler.value_type]
    length = handler.length
    alignment = handler.alignment

    # Convertir buffer a array de elementos (truncar a múltiplo de length)
    n_elements = (len(buffer) - length) // alignment + 1
    if n_elements <= 0:
        return

    # Vista numpy del buffer
    arr = np.frombuffer(buffer[:n_elements * alignment + length - alignment], dtype=dtype, count=n_elements)

    ct = handler.compare_type
    d0 = default_value_0
    d1 = default_value_1

    # Para tipos que no requieren default_value_0 (INCREASED/DECREASED/CHANGED/UNCHANGED/UNKNOWN/POINTER)
    # En new scan, esos comparadores solo miran new_value.

    # Comparar vectorialmente
    if ct == CompareType.EXACT_VALUE:
        if dtype == np.float32 or dtype == np.float64:
            target = np.frombuffer(d0, dtype=dtype)[0]
            mask = np.abs(arr - target) < 0.0001
        else:
            target = np.frombuffer(d0, dtype=dtype)[0]
            mask = arr == target
    elif ct == CompareType.UNKNOWN_INITIAL_VALUE:
        mask = arr != 0
    elif ct == CompareType.BIGGER_THAN_VALUE:
        target = np.frombuffer(d0, dtype=dtype)[0]
        mask = arr > target
    elif ct == CompareType.SMALLER_THAN_VALUE:
        target = np.frombuffer(d0, dtype=dtype)[0]
        mask = arr < target
    elif ct == CompareType.BETWEEN_VALUE:
        lo = np.frombuffer(d0, dtype=dtype)[0]
        hi = np.frombuffer(d1, dtype=dtype)[0]
        mask = (arr >= lo) & (arr <= hi)
    elif ct in (CompareType.INCREASED_VALUE, CompareType.DECREASED_VALUE,
                CompareType.CHANGED_VALUE, CompareType.UNCHANGED_VALUE):
        # En new scan no hay old value; tratamos como UNKNOWN_INITIAL_VALUE
        mask = arr != 0
    elif ct == CompareType.FUZZY_VALUE:
        target = np.frombuffer(d0, dtype=dtype)[0]
        mask = np.abs(arr - target) < 1
    elif ct == CompareType.POINTER_VALUE:
        mask = arr != 0
    else:
        # fallback
        _new_scan_python(handler, buffer, default_value_0, default_value_1, base_address, result_list)
        return

    # Iterar las posiciones que matchearon
    match_indices = np.nonzero(mask)[0]
    for idx in match_indices:
        offset = int(idx) * alignment
        value_bytes = buffer[offset:offset + length]
        # Address global = base_address + offset (relativo a la section start)
        result_list.add(base_address + offset, value_bytes)


def _new_scan_python(
    handler: MemoryTypeHandler,
    buffer: bytes,
    default_value_0: Optional[bytes],
    default_value_1: Optional[bytes],
    base_address: int,
    result_list: ResultList,
) -> None:
    """Loop Python puro (fallback)."""
    length = handler.length
    alignment = handler.alignment
    comparer = handler.comparer
    buf_len = len(buffer)
    i = 0
    while i + length <= buf_len:
        new_value = buffer[i:i + length]
        if comparer(default_value_0, default_value_1, None, new_value):
            result_list.add(base_address + i, new_value)
        i += alignment


def _next_scan_vectorized(
    handler: MemoryTypeHandler,
    buffer: bytes,
    old_result_list: ResultList,
    new_result_list: ResultList,
    default_value_0: Optional[bytes],
    default_value_1: Optional[bytes],
    base_address_offset: int,
) -> None:
    """
    Next scan: itera SOLO sobre las addresses previamente matcheadas,
    lee el nuevo valor del buffer y compara con el valor viejo.
    """
    length = handler.length
    comparer = handler.comparer
    buf_len = len(buffer)

    old_result_list.begin()
    while not old_result_list.end():
        addr_offset, old_value = old_result_list.get()
        old_result_list.next()

        # addr_offset es relativo al inicio de la SECTION (no del buffer).
        # El buffer empieza en base_address_offset (también relativo a la section).
        buf_offset = addr_offset - base_address_offset
        if buf_offset < 0 or buf_offset + length > buf_len:
            continue

        new_value = buffer[buf_offset:buf_offset + length]
        if comparer(default_value_0, default_value_1, old_value, new_value):
            new_result_list.add(addr_offset, new_value)


def _pointer_scan_buffer(
    process_manager,
    buffer: bytes,
    base_address: int,
    pointer_list,  # core.pointers.PointerList
) -> None:
    """
    Escanea un buffer buscando qwords que apunten a alguna dirección dentro de
    cualquier MappedSection. Las matches se añaden a pointer_list.
    """
    from .pointers import Pointer

    n = len(buffer) // 8
    for i in range(n):
        off = i * 8
        addr = struct.unpack_from("<Q", buffer, off)[0]
        sid = process_manager.mapped_section_list.get_mapped_section_id(addr)
        if sid != -1:
            pointer_list.add(Pointer(address=base_address + off, pointer_value=addr))


# ---------------------------------------------------------------------------
# ScanEngine
# ---------------------------------------------------------------------------

@dataclass
class ScanProgress:
    """Reporte de progreso de un escaneo."""
    section_index: int
    section_total: int
    bytes_processed: int
    bytes_total: int
    percent: float
    elapsed_seconds: float
    results_so_far: int


class ScanEngine:
    """
    Motor de escaneo thread-safe.

    Uso:
        engine = ScanEngine(ps4_pool, process_manager)
        engine.new_scan(handler, value_0, value_1, progress_cb=...)
        engine.next_scan(handler, value_0, value_1, progress_cb=...)
    """

    def __init__(
        self,
        pool: PS4DBGPool,
        process_manager,
        peek_buffer_length: int = DEFAULT_PEEK_BUFFER,
        max_peek_queue: int = DEFAULT_MAX_PEEK_QUEUE,
        num_comparers: int = DEFAULT_NUM_COMPARERS,
    ):
        self.pool = pool
        self.pm = process_manager
        self.peek_buffer_length = peek_buffer_length
        self.max_peek_queue = max_peek_queue
        self.num_comparers = num_comparers

        self._cancel_event = threading.Event()
        self._scan_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancel_event.set()

    def _reset_cancel(self) -> None:
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # New scan
    # ------------------------------------------------------------------

    def new_scan(
        self,
        handler: MemoryTypeHandler,
        value_0: Optional[bytes] = None,
        value_1: Optional[bytes] = None,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
        sections: Optional[List[MappedSection]] = None,
    ) -> int:
        """
        Primer escaneo: recorre TODAS las secciones marcadas (o `sections` si se pasa),
        para cada una lee bloques de memoria y compara cada posición.

        Returns: número total de resultados encontrados.
        """
        with self._scan_lock:
            self._reset_cancel()
            sections = sections or [s for s in self.pm.mapped_section_list if s.check]
            if not sections:
                raise RuntimeError("no sections selected for scan (use section_check first)")

            total_bytes = sum(s.length for s in sections)
            bytes_processed = 0
            t0 = time.time()

            for sec_idx, section in enumerate(sections):
                if self.is_cancelled:
                    break

                section.result_list = ResultList(handler.length, handler.alignment)

                addr = section.start
                base_addr_offset = 0
                remaining = section.length

                while remaining > 0 and not self.is_cancelled:
                    chunk_len = min(self.peek_buffer_length, remaining)
                    try:
                        buffer = self.pool.get(0).read_memory(self.pm.pid, addr, chunk_len)
                    except Exception:
                        buffer = b"\x00" * chunk_len

                    # Si no requiere parseo de valores, default_value_0 puede ser None
                    # El comparador debe manejarlo
                    d0 = value_0 if handler.parse_first_value else (b"" if value_0 is None else value_0)
                    d1 = value_1 if handler.parse_second_value else (b"" if value_1 is None else value_1)

                    _new_scan_vectorized(handler, buffer, d0, d1, base_addr_offset, section.result_list)

                    addr += chunk_len
                    base_addr_offset += chunk_len
                    remaining -= chunk_len
                    bytes_processed += chunk_len

                    if progress_cb:
                        pct = (bytes_processed / total_bytes * 80) if total_bytes > 0 else 0
                        progress_cb(ScanProgress(
                            section_index=sec_idx,
                            section_total=len(sections),
                            bytes_processed=bytes_processed,
                            bytes_total=total_bytes,
                            percent=pct,
                            elapsed_seconds=time.time() - t0,
                            results_so_far=self.pm.mapped_section_list.total_result_count(),
                        ))

            if progress_cb:
                progress_cb(ScanProgress(
                    section_index=len(sections),
                    section_total=len(sections),
                    bytes_processed=bytes_processed,
                    bytes_total=total_bytes,
                    percent=100.0,
                    elapsed_seconds=time.time() - t0,
                    results_so_far=self.pm.mapped_section_list.total_result_count(),
                ))

            return self.pm.mapped_section_list.total_result_count()

    # ------------------------------------------------------------------
    # Next scan
    # ------------------------------------------------------------------

    def next_scan(
        self,
        handler: MemoryTypeHandler,
        value_0: Optional[bytes] = None,
        value_1: Optional[bytes] = None,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
        sections: Optional[List[MappedSection]] = None,
    ) -> int:
        """
        Escaneo sucesivo: para cada sección con ResultList previo, releer la
        memoria y comparar contra los valores viejos.
        """
        with self._scan_lock:
            self._reset_cancel()
            sections = sections or [s for s in self.pm.mapped_section_list if s.check and s.result_list is not None]
            if not sections:
                raise RuntimeError("no sections with previous results to next-scan")

            total_bytes = sum(s.length for s in sections)
            bytes_processed = 0
            t0 = time.time()

            for sec_idx, section in enumerate(sections):
                if self.is_cancelled:
                    break

                old_rl = section.result_list
                new_rl = ResultList(handler.length, handler.alignment)

                addr = section.start
                base_addr_offset = 0
                remaining = section.length

                while remaining > 0 and not self.is_cancelled:
                    chunk_len = min(self.peek_buffer_length, remaining)
                    try:
                        buffer = self.pool.get(0).read_memory(self.pm.pid, addr, chunk_len)
                    except Exception:
                        buffer = b"\x00" * chunk_len

                    d0 = value_0 if handler.parse_first_value else (b"" if value_0 is None else value_0)
                    d1 = value_1 if handler.parse_second_value else (b"" if value_1 is None else value_1)

                    _next_scan_vectorized(handler, buffer, old_rl, new_rl, d0, d1, base_addr_offset)

                    addr += chunk_len
                    base_addr_offset += chunk_len
                    remaining -= chunk_len
                    bytes_processed += chunk_len

                    if progress_cb:
                        pct = (bytes_processed / total_bytes * 80) if total_bytes > 0 else 0
                        progress_cb(ScanProgress(
                            section_index=sec_idx,
                            section_total=len(sections),
                            bytes_processed=bytes_processed,
                            bytes_total=total_bytes,
                            percent=pct,
                            elapsed_seconds=time.time() - t0,
                            results_so_far=sum(s.result_list.count for s in sections if s.result_list) ,
                        ))

                section.result_list = new_rl

            if progress_cb:
                progress_cb(ScanProgress(
                    section_index=len(sections),
                    section_total=len(sections),
                    bytes_processed=bytes_processed,
                    bytes_total=total_bytes,
                    percent=100.0,
                    elapsed_seconds=time.time() - t0,
                    results_so_far=self.pm.mapped_section_list.total_result_count(),
                ))

            return self.pm.mapped_section_list.total_result_count()

    # ------------------------------------------------------------------
    # Pointer scan
    # ------------------------------------------------------------------

    def pointer_scan(
        self,
        pointer_list,
        progress_cb: Optional[Callable[[ScanProgress], None]] = None,
        sections: Optional[List[MappedSection]] = None,
    ) -> int:
        """
        Escanea todas las secciones marcadas buscando qwords que apunten a
        cualquier dirección dentro de cualquier MappedSection.
        Llena `pointer_list` (core.pointers.PointerList) con los matches.
        """
        with self._scan_lock:
            self._reset_cancel()
            sections = sections or [s for s in self.pm.mapped_section_list if s.check]
            if not sections:
                raise RuntimeError("no sections selected for pointer scan")

            total_bytes = sum(s.length for s in sections)
            bytes_processed = 0
            t0 = time.time()

            for sec_idx, section in enumerate(sections):
                if self.is_cancelled:
                    break

                addr = section.start
                remaining = section.length

                while remaining > 0 and not self.is_cancelled:
                    chunk_len = min(self.peek_buffer_length, remaining)
                    try:
                        buffer = self.pool.get(0).read_memory(self.pm.pid, addr, chunk_len)
                    except Exception:
                        buffer = b"\x00" * chunk_len

                    _pointer_scan_buffer(self.pm, buffer, addr, pointer_list)

                    addr += chunk_len
                    remaining -= chunk_len
                    bytes_processed += chunk_len

                    if progress_cb:
                        pct = (bytes_processed / total_bytes * 80) if total_bytes > 0 else 0
                        progress_cb(ScanProgress(
                            section_index=sec_idx,
                            section_total=len(sections),
                            bytes_processed=bytes_processed,
                            bytes_total=total_bytes,
                            percent=pct,
                            elapsed_seconds=time.time() - t0,
                            results_so_far=pointer_list.count,
                        ))

            if progress_cb:
                progress_cb(ScanProgress(
                    section_index=len(sections),
                    section_total=len(sections),
                    bytes_processed=bytes_processed,
                    bytes_total=total_bytes,
                    percent=100.0,
                    elapsed_seconds=time.time() - t0,
                    results_so_far=pointer_list.count,
                ))

            return pointer_list.count

    # ------------------------------------------------------------------
    # Helpers de resultados
    # ------------------------------------------------------------------

    def get_all_results(self, limit: Optional[int] = None) -> List[Tuple[int, bytes]]:
        """
        Devuelve hasta `limit` resultados (address, value) de todas las secciones.
        Las addresses son relativas al inicio de la sección; para obtener la
        address absoluta hay que sumar `section.start`.
        """
        out: List[Tuple[int, bytes]] = []
        for section in self.pm.mapped_section_list:
            if not section.check or section.result_list is None:
                continue
            for addr_off, value in section.result_list:
                out.append((section.start + addr_off, value))
                if limit is not None and len(out) >= limit:
                    return out
        return out

    def get_results_with_sections(self, limit: Optional[int] = None) -> List[Tuple[MappedSection, int, bytes]]:
        """Como get_all_results pero incluyendo la sección."""
        out = []
        for section in self.pm.mapped_section_list:
            if not section.check or section.result_list is None:
                continue
            for addr_off, value in section.result_list:
                out.append((section, addr_off, value))
                if limit is not None and len(out) >= limit:
                    return out
        return out
