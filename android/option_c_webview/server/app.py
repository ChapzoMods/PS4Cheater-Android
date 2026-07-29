"""
android/option_c_webview/server/app.py — Servidor Flask local para la app WebView.

Expone endpoints REST que envuelven la CLI/lib de PS4Cheater.
La app Android carga http://localhost:8080 en un WebView.

Uso (en Termux):
    pkg install python
    pip install flask
    python3 app.py --host 127.0.0.1 --port 8080

Endpoints:
    GET  /                          — UI HTML
    GET  /api/status                — estado de la sesión
    POST /api/connect               — {ip, port}
    POST /api/disconnect
    GET  /api/procs                 — listar procesos
    POST /api/attach                — {pid}
    GET  /api/sections              — listar secciones (con check state)
    POST /api/sections/check        — {section_idx, checked}
    POST /api/scan/new              — {value_type, compare_type, value1, value2}
    POST /api/scan/next             — {compare_type, value1, value2}
    GET  /api/scan/results          — ?limit=50
    POST /api/read                  — {address, length}
    POST /api/write                 — {address, hex_bytes}
    GET  /api/cheats                — listar cheats
    POST /api/cheats/add            — {address, value_type, value, freeze, hex_value, description}
    POST /api/cheats/freeze         — {id, frozen}
    DELETE /api/cheats/<id>         — eliminar
    POST /api/cheats/apply_all
    POST /api/notify                — {message, type}
"""
from __future__ import annotations

import os
import sys

# Añadir raíz del proyecto al path
# app.py está en android/option_c_webview/server/, así que subimos 4 niveles
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, jsonify, request, render_template

from lib import PS4DBG, PS4DBGPool, PS4DBGError, PS4DBG_PORT, GOLDHEN_PORT
from core import (
    ValueType, CompareType,
    MemoryTypeHandler, make_handler,
    lookup_value_type, lookup_compare_type,
    MappedSection, MappedSectionList, ProcessManager, ResultList,
    ScanEngine, ScanProgress,
    CheatEntry, CheatList,
    VALUE_TYPE_TO_STR, COMPARE_TYPE_TO_STR,
)

app = Flask(__name__, template_folder="templates", static_folder="static")


# ---------------------------------------------------------------------------
# Estado global (equivalente a Session de la CLI)
# ---------------------------------------------------------------------------

class State:
    def __init__(self):
        self.ps4: PS4DBG | None = None
        self.pool: PS4DBGPool | None = None
        self.pm: ProcessManager = ProcessManager()
        self.scan_engine: ScanEngine | None = None
        self.cheats: CheatList = CheatList()
        self.handler: MemoryTypeHandler | None = None
        self.connected: bool = False

    def reset(self):
        if self.cheats.freeze_running:
            self.cheats.stop_freeze_loop()
        if self.pool:
            self.pool.disconnect_all()
        elif self.ps4:
            self.ps4.disconnect()
        self.ps4 = None
        self.pool = None
        self.scan_engine = None
        self.connected = False


state = State()


def require_connected():
    return state.connected and state.ps4 is not None


def require_attached():
    return require_connected() and state.pm.pid != 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "connected": state.connected,
        "ip": state.ps4.ip if state.ps4 else "",
        "port": state.ps4.port if state.ps4 else 0,
        "pid": state.pm.pid,
        "proc_name": state.pm.name,
        "section_count": state.pm.section_count,
        "result_count": state.pm.mapped_section_list.total_result_count(),
        "cheat_count": len(state.cheats),
        "freeze_running": state.cheats.freeze_running,
    })


@app.route("/api/connect", methods=["POST"])
def api_connect():
    data = request.get_json()
    ip = data.get("ip", "")
    port = int(data.get("port", PS4DBG_PORT))
    if not ip:
        return jsonify({"ok": False, "error": "ip required"}), 400
    state.reset()
    state.ps4 = PS4DBG(ip, port, timeout=30.0)
    if not state.ps4.connect():
        return jsonify({"ok": False, "error": f"cannot connect to {ip}:{port}"}), 500
    state.pool = PS4DBGPool(ip, port, size=2, timeout=30.0)
    state.pool.connect_all()
    state.scan_engine = ScanEngine(state.pool, state.pm, num_comparers=2)
    state.cheats.ps4 = state.ps4
    state.connected = True
    try:
        version = state.ps4.get_console_debug_version()
    except Exception:
        version = ""
    return jsonify({"ok": True, "version": version})


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    state.reset()
    return jsonify({"ok": True})


@app.route("/api/procs")
def api_procs():
    if not require_connected():
        return jsonify({"ok": False, "error": "not connected"}), 400
    try:
        procs = state.ps4.get_process_list()
        return jsonify({"ok": True, "procs": [{"pid": p.pid, "name": p.name} for p in procs]})
    except (PS4DBGError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/attach", methods=["POST"])
def api_attach():
    if not require_connected():
        return jsonify({"ok": False, "error": "not connected"}), 400
    data = request.get_json()
    pid = int(data.get("pid", 0))
    if not pid:
        return jsonify({"ok": False, "error": "pid required"}), 400
    try:
        procs = state.ps4.get_process_list()
        name = next((p.name for p in procs if p.pid == pid), "")
        pmap = state.ps4.get_process_maps(pid)
        state.pm.mapped_section_list.clear_result_lists()
        state.pm.init_sections(pmap, buffer_length=32 * 1024 * 1024)
        state.pm.attach(pid, name)
        state.cheats.pid = pid
        return jsonify({"ok": True, "name": name, "section_count": state.pm.section_count})
    except (PS4DBGError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sections")
def api_sections():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    sections = []
    for i, s in enumerate(state.pm.mapped_section_list):
        sections.append({
            "idx": i,
            "name": s.name,
            "start": s.start,
            "end": s.end,
            "length": s.length,
            "prot": s.prot,
            "prot_str": ("r" if s.readable else "-") + ("w" if s.writable else "-") + ("x" if s.executable else "-"),
            "check": s.check,
        })
    return jsonify({"ok": True, "sections": sections, "total_size": state.pm.total_memory_size})


@app.route("/api/sections/check", methods=["POST"])
def api_sections_check():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = request.get_json()
    idx = int(data.get("section_idx", -1))
    checked = bool(data.get("checked", False))
    if idx < 0 or idx >= state.pm.section_count:
        return jsonify({"ok": False, "error": "invalid idx"}), 400
    state.pm.mapped_section_list.section_check(idx, checked)
    return jsonify({"ok": True, "total_size": state.pm.total_memory_size})


@app.route("/api/sections/check_all", methods=["POST"])
def api_sections_check_all():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = data = request.get_json(silent=True) or {}
    mode = data.get("mode", "rw_only")
    if mode == "all":
        state.pm.mapped_section_list.check_all(True)
    elif mode == "none":
        state.pm.mapped_section_list.check_all(False)
    else:
        state.pm.mapped_section_list.check_all(False)
        for i, s in enumerate(state.pm.mapped_section_list):
            if s.writable and not s.executable:
                state.pm.mapped_section_list.section_check(i, True)
    return jsonify({"ok": True, "total_size": state.pm.total_memory_size})


@app.route("/api/scan/new", methods=["POST"])
def api_scan_new():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = request.get_json()
    try:
        vt = lookup_value_type(data["value_type"])
        ct = lookup_compare_type(data["compare_type"])
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    v1 = data.get("value1", "")
    v2 = data.get("value2", "")
    hex_fmt = bool(data.get("hex_fmt", False))
    unaligned = bool(data.get("unaligned", False))
    type_length = int(data.get("length", 0))
    state.pm.mapped_section_list.clear_result_lists()
    handler = make_handler(vt, ct, is_aligned=not unaligned, type_length=type_length)
    state.handler = handler
    v0 = handler.parse_value(v1, hex_fmt) if handler.parse_first_value and v1 else b""
    v1b = handler.parse_value(v2, hex_fmt) if handler.parse_second_value and v2 else b""
    try:
        count = state.scan_engine.new_scan(handler, v0, v1b)
        return jsonify({"ok": True, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/scan/next", methods=["POST"])
def api_scan_next():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    if state.handler is None:
        return jsonify({"ok": False, "error": "no previous scan"}), 400
    data = request.get_json()
    try:
        ct = lookup_compare_type(data["compare_type"])
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    v1 = data.get("value1", "")
    v2 = data.get("value2", "")
    hex_fmt = bool(data.get("hex_fmt", False))
    handler = make_handler(state.handler.value_type, ct,
                           is_aligned=(state.handler.alignment != 1),
                           type_length=state.handler.length)
    state.handler = handler
    v0 = handler.parse_value(v1, hex_fmt) if handler.parse_first_value and v1 else b""
    v1b = handler.parse_value(v2, hex_fmt) if handler.parse_second_value and v2 else b""
    try:
        count = state.scan_engine.next_scan(handler, v0, v1b)
        return jsonify({"ok": True, "count": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/scan/results")
def api_scan_results():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    if state.handler is None:
        return jsonify({"ok": False, "error": "no previous scan"}), 400
    limit = int(request.args.get("limit", 50))
    items = state.scan_engine.get_all_results(limit=limit)
    h = state.handler
    results = []
    for addr, val in items:
        try:
            results.append({
                "address": addr,
                "value": h.bytes_to_string(val),
                "value_hex": h.bytes_to_hex_string(val) if h.bytes_to_hex_string else val.hex(),
            })
        except Exception:
            results.append({"address": addr, "value": "?", "value_hex": val.hex()})
    return jsonify({
        "ok": True,
        "results": results,
        "total": state.pm.mapped_section_list.total_result_count(),
        "value_type": state.handler.value_type.name,
        "compare_type": state.handler.compare_type.name,
    })


@app.route("/api/read", methods=["POST"])
def api_read():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = request.get_json()
    addr = int(data.get("address", 0), 0)
    length = int(data.get("length", 16))
    try:
        mem = state.ps4.read_memory(state.pm.pid, addr, length)
        return jsonify({
            "ok": True,
            "address": addr,
            "length": length,
            "hex": mem.hex(),
            "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in mem),
        })
    except (PS4DBGError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/write", methods=["POST"])
def api_write():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = request.get_json()
    addr = int(data.get("address", 0), 0)
    hex_str = data.get("hex_bytes", "").replace(" ", "")
    try:
        mem = bytes.fromhex(hex_str)
        state.ps4.write_memory(state.pm.pid, addr, mem)
        return jsonify({"ok": True, "written": len(mem)})
    except (ValueError, PS4DBGError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/cheats")
def api_cheats_list():
    return jsonify({
        "ok": True,
        "cheats": [
            {
                "id": e.id,
                "address": e.address,
                "value_type": e.value_type.name,
                "value": e.value,
                "frozen": e.frozen,
                "hex_value": e.hex_value,
                "description": e.description,
            }
            for e in state.cheats
        ],
        "freeze_running": state.cheats.freeze_running,
    })


@app.route("/api/cheats/add", methods=["POST"])
def api_cheats_add():
    if not require_attached():
        return jsonify({"ok": False, "error": "not attached"}), 400
    data = request.get_json()
    try:
        vt = lookup_value_type(data["value_type"])
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    addr = int(data.get("address", 0), 0)
    value = data.get("value", "0")
    description = data.get("description", "")
    frozen = bool(data.get("frozen", False))
    hex_value = bool(data.get("hex_value", False))
    e = state.cheats.add(address=addr, value_type=vt, value=value,
                         description=description, frozen=frozen, hex_value=hex_value)
    state.cheats.apply(e)
    if frozen and not state.cheats.freeze_running:
        state.cheats.start_freeze_loop()
    return jsonify({"ok": True, "id": e.id})


@app.route("/api/cheats/freeze", methods=["POST"])
def api_cheats_freeze():
    data = request.get_json()
    cid = int(data.get("id", 0))
    frozen = bool(data.get("frozen", False))
    if state.cheats.set_frozen(cid, frozen):
        if frozen and not state.cheats.freeze_running:
            state.cheats.start_freeze_loop()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/cheats/<int:cid>", methods=["DELETE"])
def api_cheats_delete(cid):
    if state.cheats.remove(cid):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/cheats/apply_all", methods=["POST"])
def api_cheats_apply_all():
    n = state.cheats.apply_all()
    return jsonify({"ok": True, "applied": n})


@app.route("/api/notify", methods=["POST"])
def api_notify():
    if not require_connected():
        return jsonify({"ok": False, "error": "not connected"}), 400
    data = request.get_json()
    msg = data.get("message", "")
    ntype = int(data.get("type", 0))
    try:
        state.ps4.notify(ntype, msg)
        return jsonify({"ok": True})
    except (PS4DBGError, OSError) as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()
    print(f"PS4Cheater web server en http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
