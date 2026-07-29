#!/usr/bin/env python3
"""
Smoke test de FASE 4: valida que la CLI funciona end-to-end contra el mock server.

Levanta el mock server, ejecuta varios comandos CLI, valida salida.
"""
import os
import re
import socket
import struct
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

HOST = "127.0.0.1"
PORT = 1744
MOCK_SCRIPT = os.path.join(REPO_ROOT, "tests", "mock_server_min.py")


def wait_for_server(timeout: float = 0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect((HOST, PORT))
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def run_cli(*args, timeout: float = 10.0) -> tuple[int, str, str]:
    """Ejecuta la CLI con args dados y devuelve (exit_code, stdout, stderr)."""
    cmd = [sys.executable, os.path.join(REPO_ROOT, "cli", "main.py")] + list(args)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def main():
    # Lanzar mock server
    print("[test] lanzando mock server…")
    mock_proc = subprocess.Popen([sys.executable, MOCK_SCRIPT],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_for_server(timeout=3.0):
        print("❌ No se pudo iniciar el mock server")
        mock_proc.terminate()
        sys.exit(1)

    try:
        # 1. status (sin conexión)
        print("\n--- 1. status (sin conexión) ---")
        code, out, err = run_cli("status")
        assert code == 0, f"exit={code} stderr={err}"
        assert "Conectado" in out
        print(out.strip())

        # 2. connect
        print("\n--- 2. connect ---")
        code, out, err = run_cli("connect", HOST, "--port", str(PORT))
        assert code == 0, f"exit={code} stderr={err}"
        assert "Conectado" in out
        print(out.strip())

        # 3. procs
        print("\n--- 3. procs ---")
        code, out, err = run_cli("procs")
        assert code == 0, f"exit={code} stderr={err}"
        assert "eboot.bin" in out
        assert "100" in out
        print(out.strip())

        # 4. attach
        print("\n--- 4. attach ---")
        code, out, err = run_cli("attach", "100")
        assert code == 0, f"exit={code} stderr={err}"
        assert "eboot.bin" in out
        assert "secciones" in out
        print(out.strip())

        # 5. sections
        print("\n--- 5. sections ---")
        code, out, err = run_cli("sections")
        assert code == 0, f"exit={code} stderr={err}"
        assert "executable" in out or "data" in out
        print(out.strip()[:500] + "..." if len(out) > 500 else out.strip())

        # 6. sections --rw-only
        print("\n--- 6. sections --rw-only ---")
        code, out, err = run_cli("sections", "--rw-only")
        assert code == 0
        assert "secciones rw- marcadas" in out
        print(out.strip())

        # 7. scan new uint32 exact (buscar 0xCAFEBABE)
        # El mock server llena la data section con 0xCAFEBABE repetido
        print("\n--- 7. scan new uint32 exact 3405691582 (0xCAFEBABE) ---")
        # 0xCAFEBABE = 3405691582 en little-endian uint32
        code, out, err = run_cli("scan", "new", "uint32", "exact", "3405691582")
        assert code == 0, f"exit={code} stderr={err}"
        assert "Scan completado" in out
        # Debe encontrar 1024 resultados (4096 bytes / 4 bytes = 1024)
        match = re.search(r"(\d+) resultado\(s\)", out)
        assert match, f"no encontró count en: {out}"
        count = int(match.group(1))
        assert count > 0, f"expected >0 results, got {count}"
        print(out.strip())

        # 8. scan results
        print("\n--- 8. scan results --limit 10 ---")
        code, out, err = run_cli("scan", "results", "--limit", "10")
        assert code == 0, f"exit={code} stderr={err}"
        # Debe mostrar al menos 1 fila con 0x10000000
        assert "0x0000000010000000" in out
        print(out.strip()[:500] + "..." if len(out) > 500 else out.strip())

        # 9. read
        print("\n--- 9. read 0x10000000 16 ---")
        code, out, err = run_cli("read", "0x10000000", "16")
        assert code == 0, f"exit={code} stderr={err}"
        # Debe contener el hexdump con BA FE CA (little-endian de CAFEBABE)
        assert "BE BA FE CA" in out or "BA FE CA" in out
        print(out.strip())

        # 10. write
        print("\n--- 10. write 0x10000000 DEADBEEF ---")
        code, out, err = run_cli("write", "0x10000000", "EFBEADDE")  # little-endian de DEADBEEF
        assert code == 0, f"exit={code} stderr={err}"
        assert "Escritos" in out
        print(out.strip())

        # 11. read again para verificar write
        print("\n--- 11. read 0x10000000 4 (verifica write) ---")
        code, out, err = run_cli("read", "0x10000000", "4")
        assert code == 0
        assert "EF BE AD DE" in out
        print(out.strip())

        # 12. cheat add
        print("\n--- 12. cheat add 0x10000000 uint32 9999 ---")
        code, out, err = run_cli("cheat", "add", "0x10000000", "uint32", "9999")
        assert code == 0, f"exit={code} stderr={err}"
        assert "Cheat #1" in out
        print(out.strip())

        # 13. cheat list
        print("\n--- 13. cheat list ---")
        code, out, err = run_cli("cheat", "list")
        assert code == 0
        assert "9999" in out
        print(out.strip())

        # 14. cheat freeze 1 on
        print("\n--- 14. cheat freeze 1 on ---")
        code, out, err = run_cli("cheat", "freeze", "1", "on")
        assert code == 0
        assert "freeze=on" in out
        print(out.strip())

        # 15. notify
        print("\n--- 15. notify 'Hola PS4' ---")
        code, out, err = run_cli("notify", "Hola PS4")
        assert code == 0
        assert "Notificación enviada" in out
        print(out.strip())

        # 16. disconnect
        print("\n--- 16. disconnect ---")
        code, out, err = run_cli("disconnect")
        assert code == 0
        assert "Desconectado" in out
        print(out.strip())

        print("\n✅ Todos los tests de FASE 4 (CLI) pasan.")
        return 0
    except AssertionError as e:
        print(f"\n❌ Assertion failed: {e}")
        if 'out' in dir():
            print(f"STDOUT:\n{out}")
        if 'err' in dir():
            print(f"STDERR:\n{err}")
        return 1
    finally:
        mock_proc.terminate()
        mock_proc.wait(timeout=2.0)


if __name__ == "__main__":
    sys.exit(main())
