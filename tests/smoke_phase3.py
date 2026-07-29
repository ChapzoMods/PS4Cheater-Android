#!/usr/bin/env python3
"""Smoke tests para FASE 3: CheatList, freeze loop, export/import."""
import os
import sys
import struct
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import CheatList, CheatEntry, ValueType, Pointer, PointerList, PointerResult
from lib import PS4DBG


# ---------------------------------------------------------------------------
# CheatList CRUD
# ---------------------------------------------------------------------------

def test_cheatlist_crud():
    cl = CheatList(ps4=None, pid=100)
    e1 = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", description="hp")
    e2 = cl.add(address=0x10000010, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")
    e3 = cl.add(address=0x10000020, value_type=ValueType.ULONG_TYPE, value="42", description="gold")
    assert len(cl) == 3
    assert e1.id == 1 and e2.id == 2 and e3.id == 3
    assert cl.get(2).value == "99.5"

    # Update
    cl.set_value(1, "9999")
    cl.set_frozen(2, True)
    cl.set_address(3, 0x20000000)
    e1 = cl.get(1)
    e2 = cl.get(2)
    e3 = cl.get(3)
    assert e1.value == "9999"
    assert e2.frozen is True
    assert e3.address == 0x20000000
    print(f"[OK] CheatList CRUD: 3 entries, updates correctos")

    # Remove
    cl.remove(2)
    assert len(cl) == 2
    assert cl.get(2) is None
    print(f"[OK] CheatList remove")


def test_cheat_to_bytes():
    """Verifica conversiones de CheatEntry a bytes."""
    cl = CheatList(ps4=None, pid=100)

    e = cl.add(address=0, value_type=ValueType.UINT_TYPE, value="1337")
    assert e.to_bytes() == struct.pack("<I", 1337)

    e = cl.add(address=0, value_type=ValueType.USHORT_TYPE, value="65535")
    assert e.to_bytes() == struct.pack("<H", 65535)

    e = cl.add(address=0, value_type=ValueType.BYTE_TYPE, value="200")
    assert e.to_bytes() == struct.pack("<B", 200)

    e = cl.add(address=0, value_type=ValueType.FLOAT_TYPE, value="3.14")
    assert e.to_bytes() == struct.pack("<f", 3.14)

    e = cl.add(address=0, value_type=ValueType.HEX_TYPE, value="AABBCCDD", hex_value=False)
    assert e.to_bytes() == bytes.fromhex("AABBCCDD")

    e = cl.add(address=0, value_type=ValueType.STRING_TYPE, value="hello")
    assert e.to_bytes() == b"hello"

    print(f"[OK] CheatEntry to_bytes para 6 tipos")


def test_cheatlist_export_import_json():
    cl = CheatList(ps4=None, pid=100)
    cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", description="hp", frozen=True)
    cl.add(address=0x10000010, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")
    cl.add(address=0x10000020, value_type=ValueType.HEX_TYPE, value="DEADBEEF", hex_value=True, description="color")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    try:
        cl.save_json(path)
        cl2 = CheatList.load_json(path)
        assert len(cl2) == 3
        assert cl2.pid == 100
        e1 = cl2.get(1)
        assert e1.address == 0x10000000
        assert e1.value == "1337"
        assert e1.value_type == ValueType.UINT_TYPE
        assert e1.frozen is True
        assert e1.description == "hp"

        e2 = cl2.get(2)
        assert e2.value == "99.5"
        assert e2.value_type == ValueType.FLOAT_TYPE

        e3 = cl2.get(3)
        assert e3.value == "DEADBEEF"
        assert e3.hex_value is True
        assert e3.value_type == ValueType.HEX_TYPE

        print(f"[OK] CheatList JSON export/import round-trip")
    finally:
        os.unlink(path)


def test_cheatlist_export_ct():
    cl = CheatList(ps4=None, pid=100)
    cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", description="hp", frozen=True)
    cl.add(address=0x10000010, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")

    with tempfile.NamedTemporaryFile(suffix=".ct", delete=False, mode="w") as f:
        path = f.name
    try:
        cl.save_ct(path)
        # Cargar de vuelta
        cl2 = CheatList.load_ct(path)
        assert len(cl2) == 2
        # Las descriptions deben preservarse
        descriptions = [e.description for e in cl2]
        assert "hp" in descriptions
        assert "mana" in descriptions
        # Las addresses deben preservarse (formato hex)
        e_hp = next(e for e in cl2 if e.description == "hp")
        assert e_hp.address == 0x10000000
        assert e_hp.frozen is True
        print(f"[OK] CheatList .CT export/import")
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Freeze loop (con mock PS4DBG)
# ---------------------------------------------------------------------------

class FakePS4(PS4DBG):
    """PS4DBG fake para tests sin red."""
    def __init__(self):
        self.memory: dict = {}
        self._connected = True
        self.write_count = 0
        self.last_writes: list = []

    @property
    def is_connected(self) -> bool:
        return True

    def write_memory(self, pid, address, data):
        self.memory[address] = data
        self.write_count += 1
        self.last_writes.append((address, data))

    def read_memory(self, pid, address, length):
        return self.memory.get(address, b"\x00" * length)[:length]


def test_freeze_loop():
    """Verifica que el freeze loop reescribe el valor periódicamente."""
    fake = FakePS4()
    cl = CheatList(ps4=fake, pid=100)
    cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", frozen=True)
    cl.add(address=0x10000010, value_type=ValueType.UINT_TYPE, value="999", frozen=False)  # no frozen

    cl.start_freeze_loop(interval=0.05)
    time.sleep(0.3)  # dejar que escriba ~6 veces
    cl.stop_freeze_loop()

    # Debe haber escrito la dirección frozen al menos 3 veces
    writes_to_frozen = sum(1 for addr, _ in fake.last_writes if addr == 0x10000000)
    writes_to_non_frozen = sum(1 for addr, _ in fake.last_writes if addr == 0x10000010)
    assert writes_to_frozen >= 3, f"expected >=3 writes to frozen, got {writes_to_frozen}"
    assert writes_to_non_frozen == 0, f"non-frozen should not be written, got {writes_to_non_frozen}"
    # El valor escrito debe ser siempre 1337
    for addr, data in fake.last_writes:
        if addr == 0x10000000:
            assert struct.unpack("<I", data)[0] == 1337

    print(f"[OK] Freeze loop: {writes_to_frozen} escrituras en 0.3s, valor constante")


# ---------------------------------------------------------------------------
# PointerList (extendido del test de FASE 2)
# ---------------------------------------------------------------------------

def test_pointer_list_dfs():
    """Verifica find_pointer_list con una cadena simple de 2 niveles."""
    pl = PointerList()
    # Memoria:
    # 0x1000: ptr -> 0x2000
    # 0x2000: ptr -> 0x3000
    # 0x3000: ptr -> 0x4000  (target)
    pl.add(Pointer(address=0x1000, pointer_value=0x2000))
    pl.add(Pointer(address=0x2000, pointer_value=0x3000))
    pl.add(Pointer(address=0x3000, pointer_value=0x4000))
    # distractores
    pl.add(Pointer(address=0x5000, pointer_value=0xDEAD))
    pl.add(Pointer(address=0x6000, pointer_value=0x1000))

    pl.init()
    results = pl.find_pointer_list(0x4000, ranges=[0x1000, 0x1000, 0x1000])
    # Debe encontrar al menos una cadena: 0x1000 -> 0x2000 -> 0x3000 -> 0x4000
    # Con offsets [0x1000, 0x1000, 0x1000] (desde target hacia atrás)
    assert len(results) > 0, f"expected at least 1 path, got {len(results)}"
    print(f"[OK] PointerList DFS: {len(results)} path(s) encontrados a 0x4000")
    for r in results[:3]:
        print(f"     {r}")


if __name__ == "__main__":
    print("=== FASE 3 Smoke Tests ===")
    test_cheatlist_crud()
    test_cheat_to_bytes()
    test_cheatlist_export_import_json()
    test_cheatlist_export_ct()
    test_freeze_loop()
    test_pointer_list_dfs()
    print("\n✅ Todos los smoke tests de FASE 3 pasan.")
