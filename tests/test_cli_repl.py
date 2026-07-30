"""
Tests de cli/repl.py — completer, ayuda y bucle del REPL.

El REPL usa prompt_toolkit.PromptSession. Los tests inyectan un PromptSession
falso que devuelve una secuencia predefinida de líneas y luego EOF, evitando
cualquier I/O interactiva real.
"""
import pytest

from cli import repl as repl_mod
from cli.repl import build_completer, print_help, run_repl, COMMANDS, VALUE_TYPES, COMPARE_TYPES


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------

class TestBuildCompleter:
    def test_includes_all_command_words(self):
        completer = build_completer()
        words = set(completer.words)
        for cmd in COMMANDS:
            assert cmd in words
        for subs in COMMANDS.values():
            for s in subs:
                assert s in words

    def test_includes_value_and_compare_types(self):
        words = set(build_completer().words)
        for w in VALUE_TYPES:
            assert w in words
        for w in COMPARE_TYPES:
            assert w in words

    def test_words_sorted_and_unique(self):
        words = build_completer().words
        assert words == sorted(words)
        assert len(words) == len(set(words))


# ---------------------------------------------------------------------------
# print_help
# ---------------------------------------------------------------------------

class TestPrintHelp:
    def test_prints_table(self, capsys):
        print_help(session=None)
        captured = capsys.readouterr()
        assert "Comandos disponibles" in captured.out
        assert "connect" in captured.out


# ---------------------------------------------------------------------------
# run_repl
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self, connected=False, ip="192.168.1.5", pid=0):
        self.connected = connected
        self.ip = ip
        self.pid = pid
        self.disconnected = False

    def disconnect(self):
        self.disconnected = True


class FakePromptSession:
    """Devuelve líneas de `lines` y luego lanza EOFError (Ctrl+D)."""
    def __init__(self, lines):
        self._lines = list(lines)
        self.prompts = []

    def prompt(self, prompt, completer=None):
        self.prompts.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


@pytest.fixture
def patch_prompt(monkeypatch, tmp_path):
    """Reemplaza PromptSession/FileHistory por fakes y aísla el historial."""
    monkeypatch.setattr(repl_mod, "FileHistory", lambda path: None)

    def make(lines):
        fake = FakePromptSession(lines)
        monkeypatch.setattr(repl_mod, "PromptSession",
                            lambda history=None: fake)
        return fake

    return make


class TestRunRepl:
    def test_exit_command(self, patch_prompt, capsys):
        patch_prompt(["exit"])
        session = FakeSession(connected=False)
        run_repl(session)
        out = capsys.readouterr().out
        assert "PS4Cheater REPL" in out
        # No conectado → no debe intentar desconectar
        assert session.disconnected is False

    def test_quit_disconnects_when_connected(self, patch_prompt, capsys):
        patch_prompt(["quit"])
        session = FakeSession(connected=True)
        run_repl(session)
        out = capsys.readouterr().out
        assert session.disconnected is True
        assert "Desconectado" in out

    def test_help_command(self, patch_prompt, capsys):
        patch_prompt(["help", "exit"])
        run_repl(FakeSession())
        out = capsys.readouterr().out
        assert "Comandos disponibles" in out

    def test_empty_line_skipped(self, patch_prompt, capsys):
        fake = patch_prompt(["", "   ", "exit"])
        run_repl(FakeSession())
        # las 3 líneas fueron consumidas
        assert len(fake.prompts) == 3

    def test_eof_breaks_loop(self, patch_prompt, capsys):
        patch_prompt([])  # inmediatamente EOF
        run_repl(FakeSession())
        out = capsys.readouterr().out
        assert "Saliendo" in out

    def test_parse_error_handled(self, patch_prompt, capsys):
        # comilla sin cerrar → shlex ValueError
        patch_prompt(['write "unterminated', "exit"])
        run_repl(FakeSession())
        out = capsys.readouterr().out
        assert "Parse error" in out

    def test_dispatches_to_click(self, patch_prompt, capsys):
        # 'status' es un comando real que no requiere conexión
        patch_prompt(["status", "exit"])
        run_repl(FakeSession())
        out = capsys.readouterr().out
        assert "Estado de sesión" in out

    def test_prompt_reflects_connection_state(self, patch_prompt):
        fake = patch_prompt(["exit"])
        session = FakeSession(connected=True, ip="10.0.0.9", pid=1234)
        run_repl(session)
        assert fake.prompts[0] == "ps4@10.0.0.9[1234]> "

    def test_prompt_connected_no_pid(self, patch_prompt):
        fake = patch_prompt(["exit"])
        session = FakeSession(connected=True, ip="10.0.0.9", pid=0)
        run_repl(session)
        assert fake.prompts[0] == "ps4@10.0.0.9> "

    def test_prompt_disconnected(self, patch_prompt):
        fake = patch_prompt(["exit"])
        run_repl(FakeSession(connected=False))
        assert fake.prompts[0] == "ps4> "
