"""
cli/repl.py — REPL interactivo con prompt_toolkit.

Provee autocompletado de comandos, historial, y atajos.
"""
from __future__ import annotations

import os
import shlex
import sys
import traceback
from typing import Optional

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console

console = Console()


# Mapas de comandos y subcomandos para autocompletado
COMMANDS = {
    "connect": ["--port", "--goldhen"],
    "disconnect": [],
    "status": [],
    "procs": [],
    "attach": [],
    "sections": ["--check-all", "--uncheck-all", "--rw-only", "--limit"],
    "scan": ["new", "next", "results"],
    "read": [],
    "write": [],
    "cheat": ["add", "list", "remove", "freeze", "apply"],
    "pointer": ["scan"],
    "export": ["--format"],
    "import": ["--format", "--merge"],
    "notify": ["--type"],
    "reboot": [],
    "repl": [],
    "help": [],
    "exit": [],
    "quit": [],
}

VALUE_TYPES = ["byte", "1 byte", "2 bytes", "4 bytes", "8 bytes",
               "uint8", "uint16", "uint32", "uint64",
               "float", "double", "string", "hex", "pointer"]

COMPARE_TYPES = ["exact", "fuzzy", "increased", "increased by",
                 "decreased", "decreased by", "bigger than", "smaller than",
                 "changed", "unchanged", "between", "unknown", "any",
                 "pointer"]


def build_completer():
    """Construye un WordCompleter con todos los comandos y subcomandos."""
    words = set(COMMANDS.keys())
    for sub in COMMANDS.values():
        for w in sub:
            words.add(w)
    for w in VALUE_TYPES:
        words.add(w)
    for w in COMPARE_TYPES:
        words.add(w)
    return WordCompleter(sorted(words), ignore_case=True)


def print_help(session):
    """Imprime ayuda rápida."""
    from rich.table import Table
    t = Table(title="Comandos disponibles", show_header=True)
    t.add_column("comando", style="cyan")
    t.add_column("descripción", style="white")
    t.add_row("connect <IP> [--port P]", "Conectar a PS4")
    t.add_row("procs", "Listar procesos")
    t.add_row("attach <pid|nombre>", "Attachear a proceso")
    t.add_row("sections [--rw-only|--check-all]", "Listar/marcar secciones")
    t.add_row("scan new <tipo> <cmp> <v1> [v2]", "Primer escaneo")
    t.add_row("scan next <cmp> [v1] [v2]", "Siguiente escaneo")
    t.add_row("scan results [--limit N]", "Ver resultados")
    t.add_row("read <addr> <len>", "Leer memoria (hexdump)")
    t.add_row("write <addr> <hex>", "Escribir memoria")
    t.add_row("cheat add <addr> <tipo> <val>", "Añadir cheat")
    t.add_row("cheat list", "Listar cheats")
    t.add_row("cheat freeze <id> on|off", "Toggle freeze")
    t.add_row("cheat remove <id>", "Eliminar cheat")
    t.add_row("pointer scan <addr> [--depth N]", "Pointer scan")
    t.add_row("export <file>", "Exportar cheats")
    t.add_row("import <file>", "Importar cheats")
    t.add_row("notify <msg>", "Notificación en PS4")
    t.add_row("reboot", "Reiniciar PS4")
    t.add_row("status", "Estado de sesión")
    t.add_row("disconnect", "Desconectar")
    t.add_row("exit / quit", "Salir del REPL")
    console.print(t)


def run_repl(session):
    """Bucle principal del REPL."""
    console.print("[bold cyan]PS4Cheater REPL[/bold cyan] — escribe 'help' para ayuda, 'exit' para salir.")

    # Click command dispatch
    from .main import cli

    # Histórico persistente
    hist_path = os.path.expanduser("~/.ps4cheater_history")
    ps = PromptSession(history=FileHistory(hist_path))
    completer = build_completer()

    while True:
        try:
            # Prompt contextual
            if session.connected and session.pid:
                prompt = f"ps4@{session.ip}[{session.pid}]> "
            elif session.connected:
                prompt = f"ps4@{session.ip}> "
            else:
                prompt = "ps4> "

            line = ps.prompt(prompt, completer=completer)
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit"):
                break
            if line == "help":
                print_help(session)
                continue

            # Parsear con shlex y dispatch a Click
            try:
                args = shlex.split(line)
            except ValueError as e:
                console.print(f"[red]Parse error: {e}[/red]")
                continue

            # Click no retorna de forma limpia cuando se llama desde Python;
            # usamos standalone_mode=False para que no haga sys.exit()
            try:
                cli.main(args, prog_name="ps4cheater", standalone_mode=False)
            except SystemExit as e:
                # Los comandos usan sys.exit(1) para señalar fallo; en el REPL no
                # queremos salir, pero tampoco tragarnos el código de error.
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                if code:
                    console.print(f"[red]El comando '{args[0]}' terminó con código {code}.[/red]")
            except click.exceptions.UsageError as e:
                console.print(f"[yellow]Uso: {e.format_message()}[/yellow]")
            except click.exceptions.ClickException as e:
                console.print(f"[red]{e.format_message()}[/red]")
            except Exception:
                console.print(f"[red]Error inesperado ejecutando '{line}':[/red]")
                console.print(f"[dim]{traceback.format_exc()}[/dim]")

        except KeyboardInterrupt:
            console.print("\n[dim](Ctrl+C — escribe 'exit' para salir)[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]Saliendo…[/dim]")
            break

    # Cleanup al salir
    if session.connected:
        session.disconnect()
        console.print("[green]Desconectado.[/green]")
