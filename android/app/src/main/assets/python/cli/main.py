#!/usr/bin/env python3
"""
cli/main.py — CLI de PS4Cheater para Termux.

Uso:
    python3 cli/main.py connect <IP> [--port 744|9090]
    python3 cli/main.py procs
    python3 cli/main.py attach <pid|nombre>
    python3 cli/main.py sections [--check-all|--uncheck-all]
    python3 cli/main.py scan new <tipo> <comparación> <valor> [valor2]
    python3 cli/main.py scan next <comparación> [valor] [valor2]
    python3 cli/main.py scan results [--limit 50]
    python3 cli/main.py read <address> <length>
    python3 cli/main.py write <address> <hex_bytes>
    python3 cli/main.py cheat add <address> <type> <value> [--freeze] [--hex] [--desc TEXT]
    python3 cli/main.py cheat list
    python3 cli/main.py cheat remove <id>
    python3 cli/main.py cheat freeze <id> on|off
    python3 cli/main.py cheat apply <id>
    python3 cli/main.py pointer scan <address> [--depth 3]
    python3 cli/main.py export <file.json>
    python3 cli/main.py import <file.json>
    python3 cli/main.py disconnect
    python3 cli/main.py repl
    python3 cli/main.py status
"""

from __future__ import annotations

import json
import os
import sys
import struct
import xml.etree.ElementTree as ET

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.syntax import Syntax

from lib import (
    PS4DBG, PS4DBGPool, PS4DBGError,
    PS4DBG_PORT, GOLDHEN_PORT,
    Process, ProcessInfo, MemoryEntry, ProcessMap,
)
from core import (
    ValueType, CompareType,
    MemoryTypeHandler, make_handler,
    lookup_value_type, lookup_compare_type,
    MappedSection, MappedSectionList, ProcessManager, ResultList,
    ScanEngine, ScanProgress,
    Pointer, PointerList, PointerResult,
    CheatEntry, CheatList,
    VALUE_TYPE_TO_STR,
)

console = Console()


# ---------------------------------------------------------------------------
# Session state (mantenida entre comandos vía archivo de estado)
# ---------------------------------------------------------------------------

SESSION_FILE = os.path.expanduser("~/.ps4cheater_session.json")
SCAN_STATE_FILE = os.path.expanduser("~/.ps4cheater_scan.json")
CHEATS_FILE = os.path.expanduser("~/.ps4cheater_cheats.json")


class Session:
    """Estado persistente entre comandos."""
    def __init__(self):
        self.ip: str = ""
        self.port: int = PS4DBG_PORT
        self.pid: int = 0
        self.proc_name: str = ""
        self.connected: bool = False
        self.cheats_path: str = ""
        self.section_checks: list[bool] = []  # cuales secciones están marcadas
        # En memoria:
        self.ps4: PS4DBG | None = None
        self.pool: PS4DBGPool | None = None
        self.pm: ProcessManager = ProcessManager()
        self.scan_engine: ScanEngine | None = None
        self.cheats: CheatList = CheatList()
        self.handler: MemoryTypeHandler | None = None

    def save(self):
        data = {
            "ip": self.ip,
            "port": self.port,
            "pid": self.pid,
            "proc_name": self.proc_name,
            "cheats_path": self.cheats_path,
            "section_checks": self.section_checks,
        }
        try:
            with open(SESSION_FILE, "w") as f:
                json.dump(data, f)
        except OSError as e:
            console.print(f"[yellow]⚠ No se pudo guardar la sesión en {SESSION_FILE}: {e}[/yellow]")

    def load(self):
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE) as f:
                data = json.load(f)
            self.ip = data.get("ip", "")
            self.port = data.get("port", PS4DBG_PORT)
            self.pid = data.get("pid", 0)
            self.proc_name = data.get("proc_name", "")
            self.cheats_path = data.get("cheats_path", "")
            self.section_checks = data.get("section_checks", [])
        except (OSError, json.JSONDecodeError) as e:
            console.print(f"[yellow]⚠ Sesión en {SESSION_FILE} ilegible ({e}); "
                          f"empezando sin estado previo.[/yellow]")

    def sync_section_checks_to_pm(self):
        """Aplica self.section_checks al ProcessManager (después de cargar sections)."""
        if not self.section_checks:
            return
        for i, checked in enumerate(self.section_checks):
            if i < self.pm.section_count and checked:
                self.pm.mapped_section_list.section_check(i, True)

    def capture_section_checks(self):
        """Captura el estado de los section.checks a self.section_checks."""
        self.section_checks = [s.check for s in self.pm.mapped_section_list]

    def connect(self, ip: str, port: int = PS4DBG_PORT) -> bool:
        self.ip = ip
        self.port = port
        self.ps4 = PS4DBG(ip, port, timeout=30.0)
        if not self.ps4.connect():
            console.print(f"[red]❌ No se pudo conectar a {ip}:{port}: "
                          f"{self.ps4.last_error}[/red]")
            return False
        # Pool de 3 conexiones para paralelismo
        self.pool = PS4DBGPool(ip, port, size=3, timeout=30.0)
        if not self.pool.connect_all():
            console.print(f"[yellow]⚠ No se pudo abrir el pool de conexiones a {ip}:{port}; "
                          f"el escaneo usará la conexión principal.[/yellow]")
        self.connected = True
        self.scan_engine = ScanEngine(self.pool, self.pm, num_comparers=2)
        self.cheats.ps4 = self.ps4
        self.cheats.pid = self.pid
        self.save()
        return True

    def disconnect(self):
        if self.cheats.freeze_running:
            self.cheats.stop_freeze_loop()
        if self.pool:
            self.pool.disconnect_all()
        elif self.ps4:
            self.ps4.disconnect()
        self.connected = False
        self.ps4 = None
        self.pool = None

    def attach(self, pid: int, name: str = ""):
        self.pid = pid
        self.proc_name = name
        self.cheats.pid = pid
        self.save()

    # ------------------------------------------------------------------
    # Persistencia de scan state
    # ------------------------------------------------------------------

    def save_scan_state(self):
        """Persiste (value_type, compare_type, alignment, length, results) a disco."""
        if self.handler is None:
            return
        results = []
        for section in self.pm.mapped_section_list:
            if not section.check or section.result_list is None:
                continue
            for addr_off, value in section.result_list:
                results.append({
                    "section_start": section.start,
                    "address": section.start + addr_off,
                    "value_hex": value.hex(),
                })
        data = {
            "value_type": int(self.handler.value_type),
            "value_type_name": self.handler.value_type.name,
            "compare_type": int(self.handler.compare_type),
            "alignment": self.handler.alignment,
            "length": self.handler.length,
            "results": results,
        }
        try:
            with open(SCAN_STATE_FILE, "w") as f:
                json.dump(data, f)
        except OSError as e:
            console.print(f"[yellow]⚠ No se pudo guardar scan state: {e}[/yellow]")

    def load_scan_state(self) -> bool:
        """Carga scan state desde disco. Devuelve True si había."""
        if not os.path.exists(SCAN_STATE_FILE):
            return False
        try:
            with open(SCAN_STATE_FILE) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            console.print(f"[yellow]⚠ Scan state en {SCAN_STATE_FILE} ilegible: {e}[/yellow]")
            return False
        try:
            vt = ValueType(data["value_type"])
            ct = CompareType(data["compare_type"])
            self.handler = make_handler(vt, ct,
                                        is_aligned=(data["alignment"] != 1),
                                        type_length=data["length"])
        except (KeyError, ValueError) as e:
            console.print(f"[yellow]⚠ Scan state en {SCAN_STATE_FILE} inválido: {e}[/yellow]")
            return False
        # Re-poblar ResultList en las secciones
        skipped = 0
        for r in data.get("results", []):
            try:
                address = r["address"]
                value = bytes.fromhex(r["value_hex"])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue
            section = self.pm.mapped_section_list.get_mapped_section(address)
            if section is None:
                skipped += 1
                continue
            if section.result_list is None:
                section.result_list = ResultList(self.handler.length, self.handler.alignment)
            try:
                section.result_list.add(address - section.start, value)
            except ValueError:
                skipped += 1
        if skipped:
            console.print(f"[yellow]⚠ {skipped} resultado(s) del scan previo descartados "
                          f"(no encajan con las secciones actuales).[/yellow]")
        return True

    def clear_scan_state(self):
        """Borra el archivo de scan state."""
        try:
            if os.path.exists(SCAN_STATE_FILE):
                os.unlink(SCAN_STATE_FILE)
        except OSError as e:
            console.print(f"[yellow]⚠ No se pudo borrar {SCAN_STATE_FILE}: {e}[/yellow]")

    # ------------------------------------------------------------------
    # Persistencia de cheats
    # ------------------------------------------------------------------

    def save_cheats(self):
        """Persiste la cheat list a disco."""
        try:
            session.cheats.save_json(CHEATS_FILE)
        except OSError as e:
            console.print(f"[yellow]⚠ No se pudo guardar cheats: {e}[/yellow]")

    def load_cheats(self):
        """Carga la cheat list desde disco si existe."""
        if not os.path.exists(CHEATS_FILE):
            return
        try:
            new_cl = CheatList.load_json(CHEATS_FILE)
            # Preservar ps4 y pid actuales
            new_cl.ps4 = self.cheats.ps4
            new_cl.pid = self.pid
            self.cheats = new_cl
        except (OSError, json.JSONDecodeError, ValueError) as e:
            console.print(f"[yellow]⚠ No se pudieron cargar los cheats de {CHEATS_FILE}: {e}[/yellow]")


session = Session()
session.load()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_connected():
    # Auto-reconectar si tenemos IP guardada pero no estamos conectados
    if not session.connected and session.ip:
        session.connect(session.ip, session.port)
    if not session.connected or session.ps4 is None:
        console.print("[red]❌ No conectado. Ejecuta: ps4cheater connect <IP>[/red]")
        sys.exit(1)
    # Cargar cheats persistidos si hay archivo y no están en memoria
    _ensure_cheats_loaded()


def _ensure_cheats_loaded():
    """Carga cheats del disco si no están en memoria y el archivo existe."""
    if not session.cheats and os.path.exists(CHEATS_FILE):
        session.load_cheats()
        if session.ps4:
            session.cheats.ps4 = session.ps4
        session.cheats.pid = session.pid


def require_attached():
    require_connected()
    if session.pid == 0:
        console.print("[red]❌ No hay proceso attacheado. Ejecuta: ps4cheater attach <pid>[/red]")
        sys.exit(1)
    # Si tenemos pid pero no sections cargadas, recargarlas
    if session.pm.section_count == 0 and session.proc_name:
        try:
            pmap = session.ps4.get_process_maps(session.pid)
            session.pm.init_sections(pmap, buffer_length=32 * 1024 * 1024)
            session.sync_section_checks_to_pm()
            # Cargar scan state previo si existe
            session.load_scan_state()
        except (PS4DBGError, OSError) as e:
            console.print(f"[yellow]⚠ No se pudieron recargar las secciones de "
                          f"pid={session.pid}: {e}[/yellow]")


def parse_address(s: str) -> int:
    """Acepta '0x10000000' o '10000000' (hex) o '268435456' (decimal)."""
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    # Si todos los chars son hex y tiene letras A-F, asumir hex
    if all(c in "0123456789abcdefABCDEF" for c in s) and any(c in "abcdefABCDEF" for c in s):
        return int(s, 16)
    # Si es muy grande, asumir hex
    try:
        v = int(s)
        if v > 0x10000:  # ambiguo, asumir hex
            return int(s, 16)
        return v
    except ValueError:
        return int(s, 16)


def parse_hex_bytes(s: str) -> bytes:
    """Acepta 'AABBCCDD' o 'AA BB CC DD' o '0xAABBCCDD'."""
    s = s.strip()
    if s.lower().startswith("0x"):
        s = s[2:]
    s = s.replace(" ", "").replace("\t", "")
    return bytes.fromhex(s)


def hexdump(data: bytes, base_addr: int = 0, bytes_per_line: int = 16) -> str:
    """Formato hexdump clásico."""
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        addr = base_addr + i
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(bytes_per_line * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{addr:016X}  {hex_part}  |{ascii_part}|")
    return "\n".join(lines)


def _warn_failed_reads(engine: ScanEngine) -> None:
    """Avisa si la consola rechazó lecturas durante el escaneo (regiones omitidas)."""
    if engine.failed_reads:
        console.print(f"[yellow]⚠ {engine.failed_reads} bloque(s) "
                      f"({engine.failed_bytes // 1024} KB) no se pudieron leer y se omitieron; "
                      f"los resultados pueden estar incompletos.[/yellow]")


def format_value(value: bytes, value_type: ValueType) -> str:
    h = make_handler(value_type, CompareType.EXACT_VALUE)
    return h.bytes_to_string(value)


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=False, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option("1.5.2", prog_name="ps4cheater")
def cli():
    """PS4Cheater para Android/Termux — port del PS4Cheater de a0zhar."""
    pass


# ---------------------------------------------------------------------------
# connect / disconnect / status
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("ip")
@click.option("--port", default=PS4DBG_PORT, type=int,
              help=f"Puerto TCP (default ps4debug={PS4DBG_PORT}, GoldHEN={GOLDHEN_PORT})")
@click.option("--goldhen", is_flag=True, help="Atajo para --port 9090 (GoldHEN)")
def connect(ip, port, goldhen):
    """Conecta a una PS4 con ps4debug/GoldHEN cargado."""
    if goldhen:
        port = GOLDHEN_PORT
    console.print(f"[cyan]Conectando a {ip}:{port}…[/cyan]")
    if session.connect(ip, port):
        # Probar obtener versión
        try:
            ver = session.ps4.get_console_debug_version()
            console.print(f"[green]✓ Conectado.[/green] Versión payload: [bold]{ver}[/bold]")
        except (PS4DBGError, OSError):
            console.print(f"[green]✓ Conectado.[/green] (no se pudo obtener versión)")
    else:
        sys.exit(1)


@cli.command()
def disconnect():
    """Cierra la conexión."""
    session.disconnect()
    console.print("[green]✓ Desconectado.[/green]")


@cli.command()
def status():
    """Muestra el estado de la sesión actual."""
    table = Table(title="Estado de sesión", show_header=False)
    table.add_column("campo", style="cyan", no_wrap=True)
    table.add_column("valor")
    table.add_row("Conectado", "✓" if session.connected else "✗")
    table.add_row("IP", session.ip or "—")
    table.add_row("Puerto", str(session.port) if session.port else "—")
    table.add_row("PID attacheado", str(session.pid) if session.pid else "—")
    table.add_row("Proceso", session.proc_name or "—")
    table.add_row("Secciones", str(session.pm.section_count))
    table.add_row("Resultados scan", str(session.pm.mapped_section_list.total_result_count()))
    table.add_row("Cheats", str(len(session.cheats)))
    table.add_row("Freeze loop", "activo" if session.cheats.freeze_running else "inactivo")
    console.print(table)


# ---------------------------------------------------------------------------
# procs / attach / sections
# ---------------------------------------------------------------------------

@cli.command()
def procs():
    """Lista los procesos de la PS4."""
    require_connected()
    try:
        procs = session.ps4.get_process_list()
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ Error al listar procesos: {e}[/red]")
        sys.exit(1)
    table = Table(title=f"Procesos ({len(procs)})", show_lines=False)
    table.add_column("PID", justify="right", style="cyan")
    table.add_column("Nombre", style="white")
    for p in procs:
        table.add_row(str(p.pid), p.name)
    console.print(table)


@cli.command()
@click.argument("target")
def attach(target):
    """Attachea a un proceso por PID o nombre (prefijo)."""
    require_connected()
    try:
        procs = session.ps4.get_process_list()
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    # Intentar por PID
    match = None
    try:
        pid = int(target)
        for p in procs:
            if p.pid == pid:
                match = p
                break
    except ValueError:
        # Buscar por nombre (prefijo)
        for p in procs:
            if p.name.startswith(target):
                match = p
                break
        if match is None:
            for p in procs:
                if target.lower() in p.name.lower():
                    match = p
                    break
    if match is None:
        console.print(f"[red]❌ Proceso '{target}' no encontrado[/red]")
        sys.exit(1)
    session.attach(match.pid, match.name)
    console.print(f"[green]✓ Attacheado a {match.name} (pid={match.pid})[/green]")
    # Cargar sections automáticamente
    try:
        pmap = session.ps4.get_process_maps(match.pid)
        session.pm.init_sections(pmap, buffer_length=32 * 1024 * 1024)
        console.print(f"[cyan]→ {session.pm.section_count} secciones de memoria cargadas.[/cyan]")
    except (PS4DBGError, OSError) as e:
        console.print(f"[yellow]⚠ No se pudo cargar sections: {e}[/yellow]")


@cli.command()
@click.option("--check-all", is_flag=True, help="Marca todas las secciones legibles para scan")
@click.option("--uncheck-all", is_flag=True, help="Desmarca todas las secciones")
@click.option("--rw-only", is_flag=True, help="Marca solo secciones rw- (no exec)")
@click.option("--limit", default=50, type=int, help="Máximo a mostrar")
def sections(check_all, uncheck_all, rw_only, limit):
    """Lista secciones de memoria del proceso attacheado."""
    require_attached()
    if check_all:
        session.pm.mapped_section_list.check_all(True)
        session.capture_section_checks()
        session.save()
        console.print(f"[green]✓ {session.pm.section_count} secciones marcadas.[/green]")
        return
    if uncheck_all:
        session.pm.mapped_section_list.check_all(False)
        session.capture_section_checks()
        session.save()
        console.print(f"[green]✓ Todas las secciones desmarcadas.[/green]")
        return
    if rw_only:
        session.pm.mapped_section_list.check_all(False)
        n = 0
        for i, s in enumerate(session.pm.mapped_section_list):
            if s.writable and not s.executable:
                session.pm.mapped_section_list.section_check(i, True)
                n += 1
        session.capture_section_checks()
        session.save()
        console.print(f"[green]✓ {n} secciones rw- marcadas.[/green]")
        return
    table = Table(title=f"Secciones ({session.pm.section_count})", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("✓", justify="center")
    table.add_column("prot", style="yellow")
    table.add_column("start", style="white")
    table.add_column("end", style="white")
    table.add_column("size", justify="right", style="green")
    table.add_column("name", style="white")
    for i, s in enumerate(session.pm.mapped_section_list):
        if i >= limit:
            break
        prot_str = "".join([
            "r" if s.prot & 0x1 else "-",
            "w" if s.prot & 0x2 else "-",
            "x" if s.prot & 0x4 else "-",
        ])
        table.add_row(
            str(i),
            "✓" if s.check else "",
            prot_str,
            f"0x{s.start:016X}",
            f"0x{s.end:016X}",
            f"{s.length // 1024} KB",
            s.name,
        )
    console.print(table)
    console.print(f"[dim]Total memoria marcada: {session.pm.total_memory_size // (1024*1024)} MB[/dim]")


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@cli.group()
def scan():
    """Comandos de escaneo de memoria."""
    pass


@scan.command()
@click.argument("value_type_str")
@click.argument("compare_type_str")
@click.argument("value1")
@click.argument("value2", required=False, default="")
@click.option("--hex-fmt", "hex_fmt", is_flag=True, help="Interpretar valores como hex")
@click.option("--length", default=0, type=int, help="Longitud para hex/string (en bytes o hex chars)")
@click.option("--unaligned", is_flag=True, help="No alinear (escanea byte a byte)")
def new(value_type_str, compare_type_str, value1, value2, hex_fmt, length, unaligned):
    """Nuevo escaneo: scan new <tipo> <comparación> <valor> [valor2]"""
    require_attached()
    try:
        vt = lookup_value_type(value_type_str)
        ct = lookup_compare_type(compare_type_str)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    # Limpia resultados previos
    session.pm.mapped_section_list.clear_result_lists()
    # Construye handler
    handler = make_handler(vt, ct, is_aligned=not unaligned, type_length=length)
    session.handler = handler
    # Parsea valores
    try:
        v0 = handler.parse_value(value1, hex_fmt) if handler.parse_first_value else b""
        v1 = handler.parse_value(value2, hex_fmt) if (handler.parse_second_value and value2) else b""
    except (ValueError, struct.error) as e:
        console.print(f"[red]❌ Valor inválido para tipo {value_type_str}: {e}[/red]")
        sys.exit(1)
    if handler.parse_first_value and not v0:
        console.print(f"[red]❌ No se pudo parsear valor 1: {value1}[/red]")
        sys.exit(1)
    if handler.parse_second_value and not v1 and value2:
        console.print(f"[red]❌ No se pudo parsear valor 2: {value2}[/red]")
        sys.exit(1)

    # Verifica que haya secciones marcadas
    if session.pm.total_memory_size == 0:
        console.print("[yellow]⚠ No hay secciones marcadas. Marcando todas las rw- automáticamente…[/yellow]")
        for i, s in enumerate(session.pm.mapped_section_list):
            if s.writable and not s.executable:
                session.pm.mapped_section_list.section_check(i, True)
        if session.pm.total_memory_size == 0:
            console.print("[red]❌ Sigue sin haber secciones marcadas. Usa 'sections --rw-only' primero.[/red]")
            sys.exit(1)

    # Progreso
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Scanning {VALUE_TYPE_TO_STR.get(vt, '?')} {compare_type_str}…",
                                 total=100)
        def on_progress(p: ScanProgress):
            progress.update(task, completed=p.percent)

        try:
            count = session.scan_engine.new_scan(handler, v0, v1, progress_cb=on_progress)
        except Exception as e:
            console.print(f"[red]❌ Error en scan: {e}[/red]")
            sys.exit(1)
    # Persistir scan state
    session.save_scan_state()
    _warn_failed_reads(session.scan_engine)
    console.print(f"[green]✓ Scan completado: {count} resultado(s).[/green]")
    console.print(f"[dim]Mostrar con: ps4cheater scan results[/dim]")


@scan.command()
@click.argument("compare_type_str")
@click.argument("value1", required=False, default="")
@click.argument("value2", required=False, default="")
@click.option("--hex-fmt", "hex_fmt", is_flag=True)
def next(compare_type_str, value1, value2, hex_fmt):
    """Siguiente escaneo: scan next <comparación> [valor] [valor2]"""
    require_attached()
    # Cargar scan state previo si no hay handler en memoria
    if session.handler is None:
        if not session.load_scan_state():
            console.print("[red]❌ No hay scan previo. Ejecuta 'scan new' primero.[/red]")
            sys.exit(1)
    try:
        ct = lookup_compare_type(compare_type_str)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    # Mantener el value_type del scan anterior pero cambiar compare_type
    handler = make_handler(session.handler.value_type, ct,
                           is_aligned=(session.handler.alignment != 1),
                           type_length=session.handler.length)
    session.handler = handler
    try:
        v0 = handler.parse_value(value1, hex_fmt) if (handler.parse_first_value and value1) else b""
        v1 = handler.parse_value(value2, hex_fmt) if (handler.parse_second_value and value2) else b""
    except (ValueError, struct.error) as e:
        console.print(f"[red]❌ Valor inválido: {e}[/red]")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Next-scan {compare_type_str}…", total=100)
        def on_progress(p: ScanProgress):
            progress.update(task, completed=p.percent)
        try:
            count = session.scan_engine.next_scan(handler, v0, v1, progress_cb=on_progress)
        except Exception as e:
            console.print(f"[red]❌ Error en next-scan: {e}[/red]")
            sys.exit(1)
    session.save_scan_state()
    _warn_failed_reads(session.scan_engine)
    console.print(f"[green]✓ Next-scan completado: {count} resultado(s).[/green]")


@scan.command()
@click.option("--limit", default=50, type=int)
@click.option("--refresh", is_flag=True, help="Releer valor actual de memoria")
def results(limit, refresh):
    """Muestra los resultados del último scan."""
    require_attached()
    # Cargar scan state previo si no hay handler en memoria
    if session.handler is None:
        if not session.load_scan_state():
            console.print("[red]❌ No hay scan previo.[/red]")
            sys.exit(1)
    items = session.scan_engine.get_all_results(limit=limit)
    if not items:
        console.print("[yellow]No hay resultados.[/yellow]")
        return
    table = Table(title=f"Resultados ({len(items)} de {session.pm.mapped_section_list.total_result_count()})",
                  show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("address", style="white")
    table.add_column("value", style="green")
    if refresh:
        table.add_column("current", style="yellow")
    for i, (addr, val) in enumerate(items):
        row = [str(i + 1), f"0x{addr:016X}", format_value(val, session.handler.value_type)]
        if refresh:
            try:
                data = session.ps4.read_memory(session.pid, addr, session.handler.length)
                row.append(format_value(data, session.handler.value_type))
            except (PS4DBGError, OSError) as e:
                row.append(f"[red]error: {e}[/red]")
        table.add_row(*row)
    console.print(table)


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("address")
@click.argument("length", type=int)
def read(address, length):
    """Lee memoria: read <address> <length>"""
    require_attached()
    addr = parse_address(address)
    try:
        data = session.ps4.read_memory(session.pid, addr, length)
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    console.print(Panel(hexdump(data, addr), title=f"0x{addr:X} ({length} bytes)",
                        border_style="cyan"))


@cli.command()
@click.argument("address")
@click.argument("hex_bytes")
def write(address, hex_bytes):
    """Escribe memoria: write <address> <hex_bytes>"""
    require_attached()
    addr = parse_address(address)
    try:
        data = parse_hex_bytes(hex_bytes)
    except ValueError as e:
        console.print(f"[red]❌ hex inválido: {e}[/red]")
        sys.exit(1)
    try:
        session.ps4.write_memory(session.pid, addr, data)
        console.print(f"[green]✓ Escritos {len(data)} bytes en 0x{addr:016X}[/green]")
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# cheat
# ---------------------------------------------------------------------------

@cli.group()
def cheat():
    """Gestión de cheats."""
    pass


@cheat.command()
@click.argument("address")
@click.argument("value_type_str")
@click.argument("value")
@click.option("--freeze", is_flag=True, help="Marcar como frozen")
@click.option("--hex", "hex_value", is_flag=True, help="Interpretar value como hex string")
@click.option("--desc", "description", default="", help="Descripción")
def add(address, value_type_str, value, freeze, hex_value, description):
    """Añade un cheat: cheat add <addr> <type> <value>"""
    require_attached()
    addr = parse_address(address)
    try:
        vt = lookup_value_type(value_type_str)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)
    e = session.cheats.add(address=addr, value_type=vt, value=value,
                           description=description, frozen=freeze, hex_value=hex_value)
    # Aplicar inmediatamente
    if session.cheats.apply(e):
        console.print(f"[green]✓ Cheat #{e.id} añadido y aplicado en 0x{addr:016X}[/green]")
    else:
        console.print(f"[yellow]⚠ Cheat #{e.id} añadido pero no se pudo aplicar: "
                      f"{session.cheats.last_error}[/yellow]")
    if freeze and not session.cheats.freeze_running:
        session.cheats.start_freeze_loop()
        console.print("[cyan]→ Freeze loop iniciado.[/cyan]")
    session.save_cheats()


@cheat.command()
def list():
    """Lista todos los cheats."""
    _ensure_cheats_loaded()
    if not session.cheats:
        console.print("[yellow]No hay cheats. Usa 'cheat add'.[/yellow]")
        return
    table = Table(title=f"Cheats ({len(session.cheats)})")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("address", style="white")
    table.add_column("type", style="yellow")
    table.add_column("value", style="green")
    table.add_column("freeze", justify="center")
    table.add_column("description", style="dim")
    for e in session.cheats:
        table.add_row(
            str(e.id),
            f"0x{e.address:016X}",
            VALUE_TYPE_TO_STR.get(e.value_type, "?"),
            e.value,
            "❄" if e.frozen else "",
            e.description,
        )
    console.print(table)


@cheat.command()
@click.argument("entry_id", type=int)
def remove(entry_id):
    """Elimina un cheat: cheat remove <id>"""
    _ensure_cheats_loaded()
    if session.cheats.remove(entry_id):
        console.print(f"[green]✓ Cheat #{entry_id} eliminado.[/green]")
        session.save_cheats()
    else:
        console.print(f"[red]❌ Cheat #{entry_id} no encontrado.[/red]")


@cheat.command(name="freeze")
@click.argument("entry_id", type=int)
@click.argument("state", type=click.Choice(["on", "off"]))
def cheat_freeze(entry_id, state):
    """Activa/desactiva freeze: cheat freeze <id> on|off"""
    _ensure_cheats_loaded()
    if session.cheats.set_frozen(entry_id, state == "on"):
        if state == "on" and not session.cheats.freeze_running:
            session.cheats.start_freeze_loop()
            console.print("[cyan]→ Freeze loop iniciado.[/cyan]")
        console.print(f"[green]✓ Cheat #{entry_id} freeze={state}[/green]")
        session.save_cheats()
    else:
        console.print(f"[red]❌ Cheat #{entry_id} no encontrado.[/red]")


@cheat.command()
@click.argument("entry_id", type=int)
def apply(entry_id):
    """Aplica un cheat inmediatamente: cheat apply <id>"""
    require_connected()
    e = session.cheats.get(entry_id)
    if e is None:
        console.print(f"[red]❌ Cheat #{entry_id} no encontrado.[/red]")
        sys.exit(1)
    if session.cheats.apply(e):
        console.print(f"[green]✓ Cheat #{entry_id} aplicado en 0x{e.address:016X}[/green]")
    else:
        console.print(f"[red]❌ No se pudo aplicar cheat #{entry_id}: "
                      f"{session.cheats.last_error}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# pointer
# ---------------------------------------------------------------------------

@cli.group()
def pointer():
    """Pointer scanning."""
    pass


@pointer.command()
@click.argument("target_address")
@click.option("--depth", default=3, type=int, help="Profundidad máxima del DFS (1-5)")
@click.option("--range", "max_range", default=0x10000, type=int, help="Máximo offset por nivel")
def scan(target_address, depth, max_range):
    """Escanea buscando punteros que terminen en target_address."""
    require_attached()
    addr = parse_address(target_address)
    if depth < 1 or depth > 5:
        console.print("[red]❌ depth debe estar entre 1 y 5[/red]")
        sys.exit(1)
    # 1. Escanea todas las secciones para llenar PointerList
    pl = PointerList()
    console.print("[cyan]Escaneando secciones buscando qwords que apunten a memoria mapeada…[/cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("pointer scan…", total=100)
        def on_progress(p: ScanProgress):
            progress.update(task, completed=p.percent)
        session.scan_engine.pointer_scan(pl, progress_cb=on_progress)
    _warn_failed_reads(session.scan_engine)
    console.print(f"[green]✓ {pl.count} punteros encontrados.[/green]")
    # 2. DFS para encontrar caminos a addr
    pl.init()
    ranges = [max_range] * depth
    console.print(f"[cyan]Buscando caminos de profundidad ≤ {depth} hacia 0x{addr:X}…[/cyan]")
    results = pl.find_pointer_list(addr, ranges)
    if not results:
        console.print("[yellow]No se encontraron caminos.[/yellow]")
        return
    table = Table(title=f"Caminos encontrados ({len(results)})")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("base_address", style="white")
    table.add_column("offsets", style="green")
    for i, r in enumerate(results[:50]):
        offs = " → ".join(f"+0x{o:X}" for o in r.offsets)
        table.add_row(str(i + 1), f"0x{r.base_address:016X}", offs)
    console.print(table)


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path")
@click.option("--format", "fmt", type=click.Choice(["json", "ct"]), default="json")
def export(path, fmt):
    """Exporta cheat table."""
    if not session.cheats:
        console.print("[yellow]No hay cheats para exportar.[/yellow]")
        return
    try:
        if fmt == "json":
            session.cheats.save_json(path)
        else:
            session.cheats.save_ct(path)
        console.print(f"[green]✓ {len(session.cheats)} cheats exportados a {path}[/green]")
    except OSError as e:
        console.print(f"[red]❌ {e}[/red]")


@cli.command(name="import")
@click.argument("path")
@click.option("--format", "fmt", type=click.Choice(["json", "ct"]), default="json")
@click.option("--merge", is_flag=True, help="Combinar con cheats existentes (default: reemplazar)")
def import_(path, fmt, merge):
    """Importa cheat table."""
    try:
        if fmt == "json":
            new_cl = CheatList.load_json(path, ps4=session.ps4)
        else:
            new_cl = CheatList.load_ct(path, ps4=session.ps4)
        if merge:
            for e in new_cl.entries:
                session.cheats.add(
                    address=e.address, value_type=e.value_type, value=e.value,
                    description=e.description, frozen=e.frozen, hex_value=e.hex_value,
                )
        else:
            session.cheats.clear()
            for e in new_cl.entries:
                session.cheats.add(
                    address=e.address, value_type=e.value_type, value=e.value,
                    description=e.description, frozen=e.frozen, hex_value=e.hex_value,
                )
        session.cheats.pid = session.pid
        console.print(f"[green]✓ {len(new_cl)} cheats importados desde {path}[/green]")
    except (OSError, json.JSONDecodeError, ET.ParseError, ValueError, KeyError) as e:
        console.print(f"[red]❌ No se pudo importar {path}: {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# repl
# ---------------------------------------------------------------------------

@cli.command()
def repl():
    """Modo interactivo con autocompletado."""
    try:
        from .repl import run_repl
    except ImportError as e:
        console.print(f"[yellow]prompt_toolkit no instalado ({e}). Instalando…[/yellow]")
        import subprocess
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "prompt_toolkit"], check=True)
        except (subprocess.CalledProcessError, OSError) as pip_err:
            console.print(f"[red]❌ No se pudo instalar prompt_toolkit: {pip_err}\n"
                          f"Instálalo a mano con: pip install prompt_toolkit[/red]")
            sys.exit(1)
        from .repl import run_repl
    run_repl(session)


# ---------------------------------------------------------------------------
# notify / reboot
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("message")
@click.option("--type", "notice_type", default=0, type=int)
def notify(message, notice_type):
    """Envía una notificación a la PS4."""
    require_connected()
    try:
        session.ps4.notify(notice_type, message)
        console.print(f"[green]✓ Notificación enviada: {message}[/green]")
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ {e}[/red]")


@cli.command()
def reboot():
    """Reinicia la PS4."""
    require_connected()
    if not click.confirm("¿Reiniciar la PS4?"):
        return
    try:
        session.ps4.reboot()
        console.print("[green]✓ Reboot enviado.[/green]")
    except (PS4DBGError, OSError) as e:
        console.print(f"[red]❌ {e}[/red]")


if __name__ == "__main__":
    cli()
