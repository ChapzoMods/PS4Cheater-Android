# PS4Cheater para Android/Termux

Port 100% funcional del proyecto [PS4Cheater](https://github.com/a0zhar/PS4Cheater)
de @a0zhar a Python, diseñado para correr en **Android/Termux sin root** y
opcionalmente como app Android nativa.

Permite a un usuario con un teléfono Android en la misma red que una PS4
(con ps4debug o GoldHEN cargado) hacer todo lo que hace la versión Windows
original: escanear memoria, encontrar valores, hacer next-scan, editar valores
en tiempo real, gestionar cheat tables y hacer pointer scanning.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests: 169 passing](https://img.shields.io/badge/tests-169%20passing-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: Android/Termux](https://img.shields.io/badge/platform-Android%2FTermux-orange)

## Características

- ✅ **Cliente TCP completo del protocolo ps4debug/GoldHEN** (puerto 744/9090)
- ✅ **Motor de escaneo client-side** con 14 tipos de comparación (exact, fuzzy, increased, decreased, changed, unchanged, between, bigger, smaller, unknown, pointer, etc.)
- ✅ **9 tipos de valor** soportados (uint8/16/32/64, float, double, hex, string, pointer)
- ✅ **Escaneo vectorial con numpy** (10-50x más rápido que loop Python para tipos numéricos)
- ✅ **ResultList compacto con bitmap** (igual que el C# original) para next-scan eficiente
- ✅ **CheatList con freeze loop** (thread que re-escribe valores constantemente)
- ✅ **Pointer scanning multi-nivel** (DFS con depth configurable, max 5 niveles)
- ✅ **Export/import cheat tables** en JSON y formato .CT (Cheat Engine)
- ✅ **CLI interactiva** con Click + Rich + prompt_toolkit (REPL con autocompletado)
- ✅ **App Android** (Opción C: WebView + Flask local — funcional; Opciones A y B documentadas)
- ✅ **Persistencia entre comandos** (session, scan state, cheats en JSON)
- ✅ **Sin root requerido** para la versión Termux
- ✅ **169 tests pytest** pasando (mock server + tests unitarios + integración end-to-end)

## Requisitos

### Para uso en Termux (recomendado)

- Android 7.0+ (API 24+)
- [Termux](https://termux.dev/) instalado
- Python 3.10+ (`pkg install python`)
- PS4 con [ps4debug](https://github.com/jogolden/ps4debug) o [GoldHEN](https://github.com/GoldHEN/GoldHEN) cargado
- Ambos dispositivos en la misma red WiFi

### Para desarrollo

- Python 3.10+
- Dependencias: `click`, `rich`, `prompt_toolkit`, `numpy`, `flask` (opcional, para la app web)
- `pytest` para tests

## Instalación rápida (Termux)

```bash
# Opción 1: Script auto-instalador
curl -L https://raw.githubusercontent.com/<user>/ps4cheater-android/main/scripts/install_termux.sh | bash

# Opción 2: Manual
pkg update && pkg install -y python git
pip install click rich prompt_toolkit numpy
git clone https://github.com/<user>/ps4cheater-android.git ~/ps4cheater-android
echo 'alias ps4cheater="python3 ~/ps4cheater-android/cli/main.py"' >> ~/.bashrc
source ~/.bashrc
```

## Uso rápido

```bash
# 1. Conectar a la PS4 (ps4debug puerto 744)
ps4cheater connect 192.168.1.100

# Para GoldHEN (puerto 9090):
ps4cheater connect 192.168.1.100 --goldhen

# 2. Listar procesos
ps4cheater procs

# 3. Attachear al proceso del juego
ps4cheater attach eboot.bin

# 4. Marcar secciones rw- para escanear
ps4cheater sections --rw-only

# 5. Primer escaneo: buscar valor 1337 (uint32)
ps4cheater scan new uint32 exact 1337

# 6. Filtrar resultados: solo los que cambiaron
ps4cheater scan next changed

# 7. Ver resultados
ps4cheater scan results --limit 50

# 8. Escribir un valor
ps4cheater write 0x10000000 DEADBEEF

# 9. Añadir cheat con freeze (mantiene el valor constante)
ps4cheater cheat add 0x10000000 uint32 9999 --freeze --desc "HP"

# 10. Listar cheats
ps4cheater cheat list

# 11. Modo interactivo (REPL con autocompletado)
ps4cheater repl

# 12. Desconectar
ps4cheater disconnect
```

## Comandos disponibles

| Comando                                          | Descripción                              |
|--------------------------------------------------|------------------------------------------|
| `connect <IP> [--port P] [--goldhen]`           | Conectar a PS4                           |
| `disconnect`                                     | Cerrar conexión                          |
| `status`                                         | Estado de la sesión                      |
| `procs`                                          | Listar procesos                          |
| `attach <pid\|nombre>`                           | Attachear a proceso                      |
| `sections [--rw-only\|--check-all\|--uncheck-all]`| Listar/marcar secciones                |
| `scan new <tipo> <cmp> <v1> [v2] [--hex-fmt]`   | Primer escaneo                           |
| `scan next <cmp> [v1] [v2]`                      | Siguiente escaneo                        |
| `scan results [--limit N] [--refresh]`           | Ver resultados                           |
| `read <addr> <length>`                           | Leer memoria (hexdump)                   |
| `write <addr> <hex_bytes>`                       | Escribir memoria                         |
| `cheat add <addr> <tipo> <val> [--freeze] [--hex] [--desc T]` | Añadir cheat            |
| `cheat list`                                     | Listar cheats                            |
| `cheat remove <id>`                              | Eliminar cheat                           |
| `cheat freeze <id> on\|off`                      | Toggle freeze                            |
| `cheat apply <id>`                               | Aplicar cheat inmediatamente             |
| `pointer scan <addr> [--depth N]`                | Pointer scanning                         |
| `export <file> [--format json\|ct]`              | Exportar cheat table                     |
| `import <file> [--format json\|ct] [--merge]`    | Importar cheat table                     |
| `notify <msg>`                                   | Enviar notificación a PS4                |
| `reboot`                                         | Reiniciar PS4                            |
| `repl`                                           | Modo interactivo                         |

### Tipos de valor soportados

`byte`, `1 byte`, `2 bytes`/`uint16`, `4 bytes`/`uint32`, `8 bytes`/`uint64`,
`float`, `double`, `string`, `hex`, `pointer`

### Tipos de comparación soportados

`exact`, `fuzzy`, `bigger than`, `smaller than`, `between`, `changed`,
`unchanged`, `increased`, `increased by`, `decreased`, `decreased by`,
`unknown` (unknown initial value), `pointer`

## Estructura del proyecto

```
ps4cheater-android/
├── lib/                          # Cliente TCP del protocolo ps4debug
│   ├── protocol.py               # Constantes, serialización, parsing
│   ├── ps4dbg.py                 # PS4DBG (cliente) + PS4DBGPool
│   └── __init__.py
├── core/                         # Núcleo del motor
│   ├── types.py                  # ValueType, CompareType, 80+ comparadores
│   ├── process_manager.py        # MappedSection, ResultList (bitmap), ProcessManager
│   ├── scanner.py                # ScanEngine (new/next/pointer scan)
│   ├── cheats.py                 # CheatList, freeze loop, export/import
│   ├── pointers.py               # PointerList, DFS multi-nivel
│   └── __init__.py
├── cli/                          # CLI interactiva para Termux
│   ├── main.py                   # Click CLI (16 comandos)
│   ├── repl.py                   # REPL con prompt_toolkit
│   └── __init__.py
├── android/                      # App Android nativa (objetivo secundario)
│   ├── README.md                 # Comparativa de 3 opciones (A/B/C)
│   └── option_c_webview/         # Opción C: WebView + Flask (implementada)
│       ├── server/               # Flask + HTML/CSS/JS
│       └── app/                  # App Android mínima (Kotlin)
├── tests/                        # 169 tests pytest
│   ├── conftest.py               # Fixtures (mock_server, ps4_client)
│   ├── mock_server.py            # Mock TCP server con memoria simulada
│   ├── mock_server_min.py        # Mock mínimo para smoke tests
│   ├── test_protocol.py          # 44 tests
│   ├── test_ps4dbg.py            # 24 tests
│   ├── test_types.py             # 37 tests
│   ├── test_resultlist.py        # 29 tests
│   ├── test_scanner.py           # 15 tests
│   ├── test_cheats.py            # 32 tests
│   ├── test_integration.py       # 8 tests end-to-end
│   ├── smoke_phase1.py           # Smoke test FASE 1
│   ├── smoke_phase2.py           # Smoke test FASE 2
│   ├── smoke_phase3.py           # Smoke test FASE 3
│   ├── smoke_phase4.py           # Smoke test FASE 4 (CLI)
│   └── integration_phase1.py     # Integración FASE 1
├── scripts/
│   ├── install_termux.sh         # Auto-instalador para Termux
│   └── run.sh                    # Lanzador rápido
├── docs/
│   └── PHASE0_ANALYSIS.md        # Análisis del protocolo y arquitectura
├── README.md
├── LICENSE
├── requirements.txt
└── __init__.py
```

## Testing

```bash
# Instalar pytest
pip install pytest

# Ejecutar todos los tests
python3 -m pytest tests/ -v

# Solo tests de un módulo
python3 -m pytest tests/test_protocol.py -v

# Con coverage
pip install pytest-cov
python3 -m pytest tests/ --cov=lib --cov=core
```

Resultado actual: **169 tests pasan en ~1.5s**.

## App Android nativa

Hay 3 opciones documentadas en [`android/README.md`](android/README.md):

| Opción | Stack | Tiempo | Estado |
|--------|-------|--------|--------|
| **A** | Kotlin + Jetpack Compose + Chaquopy | 3-5 días | Solo documentación |
| **B** | Flutter + FFI a libdebug C | 5-7 días | Solo documentación |
| **C** | WebView + Flask local | medio día | ✅ Implementada |

La Opción C (recomendada para MVP) reutiliza 100% del código Python sirviéndolo
vía un servidor Flask local que la app Android carga en un WebView.

Ver [`android/option_c_webview/README.md`](android/option_c_webview/README.md)
para instrucciones de setup.

## Troubleshooting

### No puedo conectar a la PS4

1. Verifica que la PS4 y el teléfono están en la misma red WiFi
2. Verifica que ps4debug o GoldHEN está cargado en la PS4 (debes ver el payload en Settings > System)
3. Verifica la IP de la PS4 (Settings > Network > View Connection Status)
4. En GoldHEN 2.x, el puerto por defecto es **9090** (usa `--goldhen`)
5. Desactiva firewall del teléfono si bloquea conexiones salientes

### El escaneo es muy lento

1. Marca solo las secciones `rw-` con `sections --rw-only` (no escanees código ejecutable)
2. Instala `numpy` (`pip install numpy`) para escaneo vectorial
3. Usa buffers más pequeños editando `DEFAULT_PEEK_BUFFER` en `core/scanner.py`

### Los resultados no se filtran con `scan next`

1. Asegúrate de haber hecho un `scan new` primero
2. Verifica que el valor del juego cambió entre scans
3. Si tienes muchos resultados (>1M), el next-scan puede tardar varios segundos

### El freeze loop no mantiene el valor

1. Verifica que el cheat tiene `frozen=True` (`cheat list` debe mostrar ❄)
2. Verifica que el freeze loop está corriendo (`status` debe mostrar "Freeze loop: activo")
3. Si el juego escribe el valor más rápido que el freeze loop (60 FPS), considera reducir el intervalo

## Créditos

- **[ctn123](https://github.com/ctn123)** — autor original de PS4Cheater (PS4_Cheat_Engine)
- **[a0zhar](https://github.com/a0zhar)** — mantenedor actual de PS4Cheater
- **[jogolden](https://github.com/jogolden)** — autor de [ps4debug](https://github.com/jogolden/ps4debug) (payload + libdebug C)
- **[a0zhar2](https://github.com/a0zhar2)** — autor de [libdebug C#](https://github.com/a0zhar2/libdebug) (referencia del protocolo TCP)
- **[LightningMods](https://github.com/LightningMods)** — autor de [GoldHEN](https://github.com/GoldHEN/GoldHEN)

Este port mantiene los créditos a todos los autores originales. Sin su trabajo
previo (especialmente la ingeniería inversa del protocolo ps4debug), este
proyecto no existiría.

## Licencia

MIT — ver [`LICENSE`](LICENSE).

## Disclaimer

Este proyecto es para uso educativo y personal. El autor no se hace responsable
del uso que se le dé. Modificar la memoria de un juego puede:

- Corromper saves (siempre haz backup antes)
- Causar crashes inesperados
- Ser detectado por juegos online (puede resultar en ban)
- Violar los términos de servicio de Sony y de los juegos

Úsalo solo en juegos single-player y en PS4 que te pertenecen.
