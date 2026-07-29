"""
core/pointers.py — Pointer scanning multi-nivel.

Port de PointerList.cs. La búsqueda recursiva (PointerFinder DFS) se implementa
igual que en C#: dado un target_address, busca cadenas
base → [offset_0] → [offset_1] → … → target.

Para usar primero hay que llenar la lista con `pointer_scan()` de ScanEngine,
que escanea todas las secciones buscando qwords que apunten a memoria mapeada.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


@dataclass
class Pointer:
    """Un qword encontrado que apunta a memoria mapeada."""
    address: int          # dónde está el puntero (en memoria)
    pointer_value: int    # a qué apunta


@dataclass
class PointerResult:
    """Una cadena de punteros encontrada por FindPointerList."""
    base_address: int                  # dirección del último puntero (más profundo)
    offsets: List[int] = field(default_factory=list)  # offsets para llegar al target desde base

    def __str__(self) -> str:
        offs = " -> ".join(f"+0x{o:X}" for o in self.offsets)
        return f"base=0x{self.base_address:X} [{offs}]"


class PointerList:
    """
    Lista de Pointer con dos índices internos (por address y por pointer_value)
    para búsqueda binaria.

    Port de PointerList.cs.
    """

    MAX_POINTER_COUNT: int = 15  # límite por nivel (igual que C#)

    def __init__(self):
        self._by_address: List[Pointer] = []
        self._by_value: List[Pointer] = []
        self._sorted: bool = False
        self.stop: bool = False

    @property
    def count(self) -> int:
        return len(self._by_address)

    def __len__(self) -> int:
        return len(self._by_address)

    def add(self, pointer: Pointer) -> None:
        self._by_address.append(pointer)
        self._by_value.append(pointer)
        self._sorted = False

    def clear(self) -> None:
        self._by_address.clear()
        self._by_value.clear()
        self._sorted = False
        self.stop = False

    def init(self) -> None:
        """Ordena ambas listas. Llamar antes de find_pointer_list."""
        self._by_address.sort(key=lambda p: p.address)
        self._by_value.sort(key=lambda p: (p.pointer_value, p.address))
        self._sorted = True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _get_pointers_by_value(self, value: int) -> List[Pointer]:
        """Devuelve todos los Pointer cuyo pointer_value == value."""
        if not self._sorted:
            self.init()
        # bisect sobre la lista ordenada por (pointer_value, address)
        lo = _bisect_value(self._by_value, value)
        hi = _bisect_value_right(self._by_value, value)
        return self._by_value[lo:hi]

    def _get_pointer_by_address(self, address: int) -> Optional[Pointer]:
        """Devuelve el Pointer con address == `address`, o el más cercano menor."""
        if not self._sorted:
            self.init()
        idx = _bisect_addr(self._by_address, address)
        if idx < len(self._by_address) and self._by_address[idx].address == address:
            return self._by_address[idx]
        if idx > 0:
            return self._by_address[idx - 1]
        return None

    def _get_pointers_in_range_by_address(self, lo_addr: int, hi_addr: int) -> List[Pointer]:
        """Devuelve todos los Pointer con address en [lo_addr, hi_addr]."""
        if not self._sorted:
            self.init()
        lo_idx = _bisect_addr(self._by_address, lo_addr)
        hi_idx = _bisect_addr_right(self._by_address, hi_addr)
        return self._by_address[lo_idx:hi_idx]

    # ------------------------------------------------------------------
    # Find pointer paths (DFS)
    # ------------------------------------------------------------------

    def find_pointer_list(
        self,
        target_address: int,
        ranges: List[int],
        on_new_path: Optional[Callable[[PointerResult], None]] = None,
    ) -> List[PointerResult]:
        """
        Busca cadenas de punteros que terminen en `target_address`.

        Args:
            target_address: dirección final a la que debe apuntar la cadena.
            ranges: lista de máximos offsets permitidos en cada nivel.
                    len(ranges) = profundidad máxima.
            on_new_path: callback invocado por cada cadena encontrada.

        Returns: lista de PointerResult encontrados.
        """
        if not self._sorted:
            self.init()
        self.stop = False
        results: List[PointerResult] = []
        path_offset: List[int] = []
        path_address: List[Pointer] = []

        def _emit():
            if path_address:
                base = path_address[-1].address
                # offsets son las distancias calculadas en cada nivel
                pr = PointerResult(base_address=base, offsets=list(path_offset))
                results.append(pr)
                if on_new_path:
                    on_new_path(pr)

        def _dfs(address: int, level: int):
            if self.stop:
                return
            if level >= len(ranges):
                _emit()
                return

            # Buscar punteros cuya pointer_value == address (cualquier offset dentro del rango)
            # En C# esto es: iterar por los Pointer con address cercana a `address`
            # (donde "cercana" = address - range[level] <= p.address <= address)
            # y luego para cada uno, buscar punteros que apunten a p.address.
            #
            # El algoritmo original es un poco rebuscado. Simplificación:
            # Para cada puntero p cuyo `pointer_value == address`, calculamos
            # offset = address - p.address y descendemos buscando punteros que
            # apunten a p.address.
            for p in self._get_pointers_by_value(address):
                if self.stop:
                    return
                # Evitar ciclos
                if any(pa.address == p.address or pa.pointer_value == p.pointer_value for pa in path_address):
                    continue

                # offset desde p.address hasta address (negativo o positivo)
                offset = address - p.address
                if abs(offset) > ranges[level]:
                    continue

                path_offset.append(offset)
                path_address.append(p)

                # Recursión: ahora buscamos punteros que apunten a p.address
                _dfs(p.address, level + 1)

                path_address.pop()
                path_address_appeared = False
                path_offset.pop()

        _dfs(target_address, 0)
        return results


# ---------------------------------------------------------------------------
# Python 3.10+ tiene bisect con key=; para versiones anteriores, helpers manuales.
# ---------------------------------------------------------------------------

def _bisect_addr(lst: List[Pointer], address: int) -> int:
    """bisect_left sobre lista ordenada por .address."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid].address < address:
            lo = mid + 1
        else:
            hi = mid
    return lo

def _bisect_addr_right(lst: List[Pointer], address: int) -> int:
    """bisect_right sobre lista ordenada por .address."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid].address <= address:
            lo = mid + 1
        else:
            hi = mid
    return lo

def _bisect_value(lst: List[Pointer], value: int) -> int:
    """bisect_left sobre lista ordenada por .pointer_value (con .address como tiebreaker)."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid].pointer_value < value:
            lo = mid + 1
        else:
            hi = mid
    return lo

def _bisect_value_right(lst: List[Pointer], value: int) -> int:
    """bisect_right sobre lista ordenada por .pointer_value (con .address como tiebreaker)."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid].pointer_value <= value:
            lo = mid + 1
        else:
            hi = mid
    return lo
