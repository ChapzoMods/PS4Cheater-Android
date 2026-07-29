"""core — Núcleo del motor de escaneo, gestión de procesos, cheats y pointers."""

from .types import (
    ValueType, CompareType,
    MemoryTypeHandler, make_handler,
    lookup_value_type, lookup_compare_type,
    VALUE_TYPE_TO_STR, STR_TO_VALUE_TYPE,
    COMPARE_TYPE_TO_STR, STR_TO_COMPARE_TYPE,
)
from .process_manager import (
    MappedSection, MappedSectionList, ProcessManager, ResultList,
)
from .scanner import (
    ScanEngine, ScanProgress,
    DEFAULT_PEEK_BUFFER, DEFAULT_MAX_PEEK_QUEUE, DEFAULT_NUM_COMPARERS,
)
from .pointers import Pointer, PointerList, PointerResult
from .cheats import CheatEntry, CheatList

__all__ = [
    "ValueType", "CompareType",
    "MemoryTypeHandler", "make_handler",
    "lookup_value_type", "lookup_compare_type",
    "VALUE_TYPE_TO_STR", "STR_TO_VALUE_TYPE",
    "COMPARE_TYPE_TO_STR", "STR_TO_COMPARE_TYPE",
    "MappedSection", "MappedSectionList", "ProcessManager", "ResultList",
    "ScanEngine", "ScanProgress",
    "DEFAULT_PEEK_BUFFER", "DEFAULT_MAX_PEEK_QUEUE", "DEFAULT_NUM_COMPARERS",
    "Pointer", "PointerList", "PointerResult",
    "CheatEntry", "CheatList",
]
