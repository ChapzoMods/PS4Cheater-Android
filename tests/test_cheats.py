"""Tests de CheatList, freeze loop, export/import."""
import os
import struct
import tempfile
import time
import pytest

from core import CheatList, CheatEntry, ValueType, Pointer, PointerList
from lib import PS4DBG


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


class TestCheatEntry:
    def test_to_bytes_uint32(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.UINT_TYPE, value="1337")
        assert e.to_bytes() == struct.pack("<I", 1337)

    def test_to_bytes_uint8(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.BYTE_TYPE, value="200")
        assert e.to_bytes() == struct.pack("<B", 200)

    def test_to_bytes_float(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.FLOAT_TYPE, value="3.14")
        assert e.to_bytes() == struct.pack("<f", 3.14)

    def test_to_bytes_hex(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.HEX_TYPE, value="DEADBEEF", hex_value=False)
        assert e.to_bytes() == bytes.fromhex("DEADBEEF")

    def test_to_bytes_string(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.STRING_TYPE, value="hello")
        assert e.to_bytes() == b"hello"

    def test_from_bytes_uint32(self):
        cl = CheatList(ps4=None)
        e = cl.add(address=0, value_type=ValueType.UINT_TYPE, value="0")
        assert e.from_bytes(struct.pack("<I", 1337)) == "1337"


class TestCheatListCRUD:
    def test_add_get(self):
        cl = CheatList(ps4=None, pid=100)
        e1 = cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100", description="hp")
        e2 = cl.add(address=0x2000, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")
        assert len(cl) == 2
        assert e1.id == 1 and e2.id == 2
        assert cl.get(1).value == "100"
        assert cl.get(2).description == "mana"
        assert cl.get(999) is None

    def test_set_value(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        assert cl.set_value(1, "999")
        assert cl.get(1).value == "999"
        assert not cl.set_value(999, "1")

    def test_set_frozen(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        assert cl.set_frozen(1, True)
        assert cl.get(1).frozen is True
        assert cl.set_frozen(1, False)
        assert cl.get(1).frozen is False

    def test_set_address(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        assert cl.set_address(1, 0x2000)
        assert cl.get(1).address == 0x2000

    def test_remove(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        cl.add(address=0x2000, value_type=ValueType.UINT_TYPE, value="200")
        assert len(cl) == 2
        assert cl.remove(1)
        assert len(cl) == 1
        assert cl.get(1) is None
        assert cl.get(2) is not None
        # Remove non-existent
        assert not cl.remove(999)

    def test_clear(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        cl.add(address=0x2000, value_type=ValueType.UINT_TYPE, value="200")
        cl.clear()
        assert len(cl) == 0
        # Next id should reset
        e = cl.add(address=0, value_type=ValueType.UINT_TYPE, value="0")
        assert e.id == 1

    def test_iter(self):
        cl = CheatList(ps4=None)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        cl.add(address=0x2000, value_type=ValueType.UINT_TYPE, value="200")
        entries = list(cl)
        assert len(entries) == 2
        assert entries[0].address == 0x1000


class TestCheatApply:
    def test_apply_single(self):
        fake = FakePS4()
        cl = CheatList(ps4=fake, pid=100)
        e = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337")
        assert cl.apply(e)
        assert fake.write_count == 1
        assert fake.memory[0x10000000] == struct.pack("<I", 1337)

    def test_apply_all(self):
        fake = FakePS4()
        cl = CheatList(ps4=fake, pid=100)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100")
        cl.add(address=0x2000, value_type=ValueType.UINT_TYPE, value="200")
        cl.add(address=0x3000, value_type=ValueType.UINT_TYPE, value="300")
        n = cl.apply_all()
        assert n == 3
        assert fake.write_count == 3

    def test_apply_frozen_only(self):
        fake = FakePS4()
        cl = CheatList(ps4=fake, pid=100)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100", frozen=True)
        cl.add(address=0x2000, value_type=ValueType.UINT_TYPE, value="200", frozen=False)
        cl.add(address=0x3000, value_type=ValueType.UINT_TYPE, value="300", frozen=True)
        n = cl.apply_frozen()
        assert n == 2
        assert fake.write_count == 2
        addresses_written = [addr for addr, _ in fake.last_writes]
        assert 0x1000 in addresses_written
        assert 0x3000 in addresses_written
        assert 0x2000 not in addresses_written

    def test_read_current(self):
        fake = FakePS4()
        fake.memory[0x10000000] = struct.pack("<I", 9999)
        cl = CheatList(ps4=fake, pid=100)
        e = cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="0")
        val = cl.read_current(e)
        assert val == "9999"


class TestFreezeLoop:
    def test_freeze_writes_repeatedly(self):
        fake = FakePS4()
        cl = CheatList(ps4=fake, pid=100)
        cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", frozen=True)
        cl.add(address=0x10000010, value_type=ValueType.UINT_TYPE, value="999", frozen=False)

        cl.start_freeze_loop(interval=0.05)
        time.sleep(0.3)
        cl.stop_freeze_loop()

        # Debe haber escrito el cheat frozen varias veces
        frozen_writes = sum(1 for addr, _ in fake.last_writes if addr == 0x10000000)
        non_frozen_writes = sum(1 for addr, _ in fake.last_writes if addr == 0x10000010)
        assert frozen_writes >= 3
        assert non_frozen_writes == 0
        # El valor escrito debe ser siempre 1337
        for addr, data in fake.last_writes:
            if addr == 0x10000000:
                assert struct.unpack("<I", data)[0] == 1337

    def test_freeze_running_property(self):
        fake = FakePS4()
        cl = CheatList(ps4=fake, pid=100)
        cl.add(address=0x1000, value_type=ValueType.UINT_TYPE, value="100", frozen=True)
        assert not cl.freeze_running
        cl.start_freeze_loop(interval=0.5)
        assert cl.freeze_running
        cl.stop_freeze_loop()
        assert not cl.freeze_running

    def test_stop_freeze_loop_idempotent(self):
        """Stop sin haber start no debe fallar."""
        cl = CheatList(ps4=None)
        cl.stop_freeze_loop()  # no-op


class TestExportImport:
    def test_json_roundtrip(self, tmp_path):
        cl = CheatList(ps4=None, pid=100)
        cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", description="hp", frozen=True)
        cl.add(address=0x10000010, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")
        cl.add(address=0x10000020, value_type=ValueType.HEX_TYPE, value="DEADBEEF", hex_value=True)

        path = tmp_path / "cheats.json"
        cl.save_json(str(path))
        cl2 = CheatList.load_json(str(path))

        assert len(cl2) == 3
        assert cl2.pid == 100
        e1 = cl2.get(1)
        assert e1.address == 0x10000000
        assert e1.value_type == ValueType.UINT_TYPE
        assert e1.value == "1337"
        assert e1.frozen is True
        assert e1.description == "hp"

        e2 = cl2.get(2)
        assert e2.value_type == ValueType.FLOAT_TYPE
        assert e2.value == "99.5"

        e3 = cl2.get(3)
        assert e3.value_type == ValueType.HEX_TYPE
        assert e3.hex_value is True

    def test_ct_roundtrip(self, tmp_path):
        cl = CheatList(ps4=None, pid=100)
        cl.add(address=0x10000000, value_type=ValueType.UINT_TYPE, value="1337", description="hp", frozen=True)
        cl.add(address=0x10000010, value_type=ValueType.FLOAT_TYPE, value="99.5", description="mana")

        path = tmp_path / "cheats.ct"
        cl.save_ct(str(path))
        cl2 = CheatList.load_ct(str(path))

        assert len(cl2) == 2
        descriptions = [e.description for e in cl2]
        assert "hp" in descriptions
        assert "mana" in descriptions
        # Las addresses deben preservarse
        e_hp = next(e for e in cl2 if e.description == "hp")
        assert e_hp.address == 0x10000000
        assert e_hp.frozen is True

    def test_load_ct_rejects_dtd_entities(self, tmp_path):
        """Un .CT con DTD/entidades (billion laughs / XXE) debe ser rechazado."""
        from core.cheats import UnsafeXMLError

        malicious = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE lolz [\n'
            '  <!ENTITY lol "lol">\n'
            '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">\n'
            ']>\n'
            '<CheatTable><CheatEntries><CheatEntry>'
            '<Description>&lol2;</Description><Address>10</Address>'
            '</CheatEntry></CheatEntries></CheatTable>'
        )
        path = tmp_path / "evil.ct"
        path.write_text(malicious)
        # defusedxml lanza EntitiesForbidden; el fallback lanza UnsafeXMLError.
        with pytest.raises(Exception) as exc_info:
            CheatList.load_ct(str(path))
        name = type(exc_info.value).__name__
        assert isinstance(exc_info.value, UnsafeXMLError) or "Forbidden" in name

    def test_load_ct_rejects_external_entity(self, tmp_path):
        """Un .CT que referencia una entidad externa (XXE) debe ser rechazado."""
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET")
        xxe = (
            '<?xml version="1.0"?>\n'
            f'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file://{secret}">]>\n'
            '<CheatTable><CheatEntries><CheatEntry>'
            '<Description>&xxe;</Description><Address>10</Address>'
            '</CheatEntry></CheatEntries></CheatTable>'
        )
        path = tmp_path / "xxe.ct"
        path.write_text(xxe)
        with pytest.raises(Exception):
            cl = CheatList.load_ct(str(path))
            # Si por alguna razón no lanza, el secreto NO debe haberse filtrado.
            assert all("TOP-SECRET" not in (e.description or "") for e in cl)


class TestPointerList:
    def test_add_count(self):
        pl = PointerList()
        pl.add(Pointer(address=0x1000, pointer_value=0x2000))
        pl.add(Pointer(address=0x2000, pointer_value=0x3000))
        assert pl.count == 2

    def test_clear(self):
        pl = PointerList()
        pl.add(Pointer(address=0x1000, pointer_value=0x2000))
        pl.clear()
        assert pl.count == 0

    def test_dfs_simple_chain(self):
        """Cadena: 0x1000 -> 0x2000 -> 0x3000 -> 0x4000 (target)."""
        pl = PointerList()
        pl.add(Pointer(address=0x1000, pointer_value=0x2000))
        pl.add(Pointer(address=0x2000, pointer_value=0x3000))
        pl.add(Pointer(address=0x3000, pointer_value=0x4000))
        pl.add(Pointer(address=0x5000, pointer_value=0xDEAD))  # distractor
        pl.init()

        results = pl.find_pointer_list(0x4000, ranges=[0x10000, 0x10000, 0x10000])
        assert len(results) > 0
        # La cadena encontrada debe tener base 0x1000 (la más profunda)
        bases = [r.base_address for r in results]
        assert 0x1000 in bases

    def test_dfs_no_path(self):
        """Sin punteros que apunten al target."""
        pl = PointerList()
        pl.add(Pointer(address=0x1000, pointer_value=0x2000))
        pl.add(Pointer(address=0x2000, pointer_value=0x3000))
        pl.init()
        results = pl.find_pointer_list(0x99999, ranges=[0x10000])
        assert len(results) == 0

    def test_dfs_with_callback(self):
        pl = PointerList()
        pl.add(Pointer(address=0x1000, pointer_value=0x2000))
        pl.add(Pointer(address=0x2000, pointer_value=0x3000))
        pl.init()
        paths = []
        results = pl.find_pointer_list(0x3000, ranges=[0x10000, 0x10000],
                                       on_new_path=lambda r: paths.append(r))
        assert len(results) > 0
        assert len(paths) > 0  # callback fue invocado
