# FASE 0 — Análisis del protocolo ps4debug y arquitectura original

Este documento resume el análisis del repositorio original `a0zhar/PS4Cheater`,
la librería `a0zhar2/libdebug` (port C# del protocolo ps4debug) y la librería
PyPI `ps4debug`. Sirve de base para el port a Python/Termux.

## 1. Protocolo binario ps4debug

### 1.1 Cabecera de paquete (12 bytes, little-endian)

```c
struct cmd_packet {
    uint32_t magic;     // 0xFFAABBCC  (bytes: CC BB AA FF en el wire)
    uint32_t cmd;       // uno de los CMD_* (ver abajo)
    uint32_t datalen;   // longitud del payload que sigue a la cabecera
} __attribute__((packed));
```

Tamaño total de la cabecera: **12 bytes**. Tras la cabecera se envía el
payload de longitud `datalen`.

### 1.2 Códigos de comando

| Constante                  | Valor       | Descripción                              |
|----------------------------|-------------|------------------------------------------|
| `CMD_VERSION`              | `0xBD000001`| Versión del payload ps4debug cargado     |
| `CMD_EXT_FW_VERSION`       | `0xBD000500`| Versión extendida de firmware            |
| `CMD_PROC_LIST`            | `0xBDAA0001`| Lista de procesos                        |
| `CMD_PROC_READ`            | `0xBDAA0002`| Leer memoria                             |
| `CMD_PROC_WRITE`           | `0xBDAA0003`| Escribir memoria                         |
| `CMD_PROC_MAPS`            | `0xBDAA0004`| Mapa de memoria de un proceso            |
| `CMD_PROC_INTALL`          | `0xBDAA0005`| Instalar RPC stub                        |
| `CMD_PROC_CALL`            | `0xBDAA0006`| Llamar función vía RPC                   |
| `CMD_PROC_ELF`             | `0xBDAA0007`| Cargar ELF                               |
| `CMD_PROC_PROTECT`         | `0xBDAA0008`| Cambiar protección de memoria            |
| `CMD_PROC_SCAN`            | `0xBDAA0009`| Escaneo de memoria (server-side)         |
| `CMD_PROC_INFO`            | `0xBDAA000A`| Información de un proceso                |
| `CMD_PROC_ALLOC`           | `0xBDAA000B`| Alocar memoria RWX                       |
| `CMD_PROC_FREE`            | `0xBDAA000C`| Liberar memoria                          |
| `CMD_DEBUG_ATTACH`         | `0xBDBB0001`| Attachearse a proceso para debug         |
| `CMD_DEBUG_DETACH`         | `0xBDBB0002`| Desatachar                               |
| `CMD_DEBUG_BREAKPT`        | `0xBDBB0003`| Setear breakpoint                        |
| `CMD_DEBUG_WATCHPT`        | `0xBDBB0004`| Setear watchpoint                        |
| `CMD_DEBUG_THREADS`        | `0xBDBB0005`| Listar threads                           |
| `CMD_DEBUG_STOPTHR`        | `0xBDBB0006`| Detener thread                           |
| `CMD_DEBUG_RESUMETHR`      | `0xBDBB0007`| Resumir thread                           |
| `CMD_DEBUG_GETREGS`        | `0xBDBB0008`| Leer registros                           |
| `CMD_DEBUG_SETREGS`        | `0xBDBB0009`| Escribir registros                       |
| `CMD_DEBUG_GETFPREGS`      | `0xBDBB000A`| Leer registros FP                        |
| `CMD_DEBUG_SETFPREGS`      | `0xBDBB000B`| Escribir registros FP                    |
| `CMD_DEBUG_GETDBGREGS`     | `0xBDBB000C`| Leer debug regs                          |
| `CMD_DEBUG_SETDBGREGS`     | `0xBDBB000D`| Escribir debug regs                      |
| `CMD_DEBUG_STOPGO`         | `0xBDBB0010`| Stop/Go de proceso                       |
| `CMD_DEBUG_THRINFO`        | `0xBDBB0011`| Info de thread                           |
| `CMD_DEBUG_SINGLESTEP`     | `0xBDBB0012`| Single step                              |
| `CMD_DEBUG_EXT_STOPGO`     | `0xBDBB0500`| Stop/Go extendido                        |
| `CMD_KERN_BASE`            | `0xBDCC0001`| Kernel base address                      |
| `CMD_KERN_READ`            | `0xBDCC0002`| Leer memoria kernel                      |
| `CMD_KERN_WRITE`           | `0xBDCC0003`| Escribir memoria kernel                  |
| `CMD_CONSOLE_REBOOT`       | `0xBDDD0001`| Reboot                                   |
| `CMD_CONSOLE_END`          | `0xBDDD0002`| Cerrar sesión                            |
| `CMD_CONSOLE_PRINT`        | `0xBDDD0003`| Print a log                              |
| `CMD_CONSOLE_NOTIFY`       | `0xBDDD0004`| Notificación en pantalla                 |
| `CMD_CONSOLE_INFO`         | `0xBDDD0005`| Info de consola                          |

### 1.3 Códigos de estado de respuesta (4 bytes, little-endian)

| Constante              | Valor        |
|------------------------|--------------|
| `CMD_SUCCESS`          | `0x80000000` |
| `CMD_ERROR`            | `0xF0000001` |
| `CMD_TOO_MUCH_DATA`    | `0xF0000002` |
| `CMD_DATA_NULL`        | `0xF0000003` |
| `CMD_ALREADY_DEBUG`    | `0xF0000004` |
| `CMD_INVALID_INDEX`    | `0xF0000005` |

### 1.4 Puertos

| Puerto | Uso                                  |
|--------|--------------------------------------|
| 744    | ps4debug estándar (TCP)              |
| 755    | ps4debug debug events (TCP, async)   |
| 9090   | GoldHEN 2.x (TCP, mismo protocolo)   |
| 9020   | GoldHEN FTP                          |
| 9021   | GoldHEN HTTP                         |
| 1010   | Broadcast discovery (UDP, magic `0xFFFFAAAA`) |

El protocolo binario es **idéntico** entre ps4debug y GoldHEN. Solo cambia
el puerto. Por eso `connect(ip, port=744)` y `connect_goldhen(ip)` son
esencialmente el mismo código con distinto puerto por defecto.

## 2. Estructuras de datos del protocolo (wire format, little-endian)

### 2.1 `CMD_PROC_LIST`

- Request: cabecera (cmd=`0xBDAA0001`, datalen=0)
- Response: status + int32 count + count * 36 bytes
- Cada entrada (36 bytes):
  - `name[32]`  ASCII, zero-padded
  - `pid`       int32

### 2.2 `CMD_PROC_INFO`

- Request payload (4 bytes): `pid int32`
- Response: status + 188 bytes de `ProcessInfo`:
  - `pid int32`
  - `name[40]`
  - `path[64]`
  - `titleid[16]`
  - `contentid[64]`

### 2.3 `CMD_PROC_MAPS`

- Request payload (4 bytes): `pid int32`
- Response: status + int32 count + count * 58 bytes
- Cada `MemoryEntry` (58 bytes):
  - `name[32]`    ASCII
  - `start uint64`
  - `end uint64`
  - `offset uint64`
  - `prot uint16`

### 2.4 `CMD_PROC_READ`

- Request payload (16 bytes): `pid int32` + 4 bytes pad + `address uint64` + `length int32`
  - (En C# usan `BitConverter.GetBytes(pid) + BitConverter.GetBytes(address) + BitConverter.GetBytes(length)` que da 4+8+4=16 bytes; el pack `<I` no alinea.)
- Response: status + `length` bytes de datos

### 2.5 `CMD_PROC_WRITE`

- Request: cabecera (datalen=16) + payload (16 bytes: pid+address+length) + status response + datos (`length` bytes) + status response
- El servidor responde con status dos veces: una tras recibir la cabecera+payload, otra tras recibir los datos.

### 2.6 `CMD_PROC_SCAN` (escaneo server-side, opcional)

- Request payload (10 bytes): `pid int32 + valType uint8 + compareType uint8 + length int32`
- Tras status OK, se envían `length` bytes (1 valor) o `2*length` bytes (2 valores).
- Tras status OK, el servidor envía resultados como una secuencia de `uint64` address hasta que envía `0xFFFFFFFFFFFFFFFF` como terminador.

**Importante:** ps4debug PyPI y libdebug C# soportan scan server-side, pero el
PS4Cheater original NO lo usa: hace todo el escaneo **client-side** leyendo
bloques con `CMD_PROC_READ`. Mantendremos ese enfoque para tener control
total de la lógica de comparación y poder replicar `ResultList` (bitmap).

## 3. Arquitectura original (C#)

### 3.1 Módulos

| Archivo C#               | Líneas | Función                                                            |
|--------------------------|--------|-------------------------------------------------------------------|
| `PS4APIWarpper.cs`       | 12     | Interfaz mínima sobre libdebug                                    |
| `MemoryHelper.cs`        | 1068   | Conversiones de tipos, 14 comparadores, lectura/escritura         |
| `ProcessManager.cs`      | 435    | MappedSection, MappedSectionList (bsearch), ResultList (bitmap)   |
| `ScanThread.cs`          | 231    | PeekThread + ComparerThread (producer/consumer)                   |
| `CheatList.cs`           | 972    | Cheat operators, freeze, save/load, aritmética                    |
| `PointerList.cs`         | 306    | Pointer scanning multi-nivel con DFS                              |
| `Util.cs`                | 198    | Constantes, GameInfo, Config (app.config)                         |

### 3.2 Flujo de un escaneo nuevo (new scan)

```
1. MemoryHelper.Connect(ip) — abre 3 conexiones TCP (paralelismo)
2. GetProcessList + GetProcessInfo(pid) + GetProcessMaps(pid)
3. MappedSectionList.InitMemorySectionList(processMap)
   - filtra entradas con (prot & 0x1)==0x1 (legibles)
   - divide entradas grandes en bloques de 128 MB (PEEK_BUFFER_LENGTH)
   - el ejecutable (prot & 0x5)==0x5 queda en un solo bloque
4. Usuario marca qué secciones escanear (SectionCheck)
5. ScanThread: PeekThread lee bloques de 128 MB por TCP y los encola
   en un buffer_queue de MAX_PEEK_QUEUE=4 slots
   ComparerThread consume bloques, recorre con alignment, compara cada
   posición, llama ResultList.Add(address, value)
6. ResultList usa un bitmap compacto:
   - Cada "tag" ocupa 4 (offset base) + 8 (bitmap de 64 bits) + N*element_size
   - Un tag cubre hasta 64 posiciones alineadas
   - Cuando se llena, se avanza al siguiente tag (o nueva página de 64 KB)
```

### 3.3 Comparadores (14 tipos)

`EXACT_VALUE, FUZZY_VALUE, INCREASED_VALUE, INCREASED_VALUE_BY,
DECREASED_VALUE, DECREASED_VALUE_BY, BIGGER_THAN_VALUE,
SMALLER_THAN_VALUE, CHANGED_VALUE, UNCHANGED_VALUE, BETWEEN_VALUE,
UNKNOWN_INITIAL_VALUE, POINTER_VALUE, NONE`

Cada uno tiene 6 variantes por tipo (uint8/16/32/64, float, double) excepto
`EXACT` (que también soporta hex y string), `FUZZY` (solo float/double) y
`UNKNOWN_INITIAL_VALUE` (cualquier tipo numérico).

Total funciones comparadoras: ~80.

### 3.4 ResultList (bitmap compacto)

```
Página de buffer_size = 4096*16 = 65536 bytes
Cada tag:  [offset_base uint32][bitmap uint64][value_0][value_1]...[value_n]
                                              \-- hasta 64 values, ordenados por bit position
bit i del bitmap = 1  =>  hay un value en (offset_base + i*alignment)
```

Esta estructura es **compacta** y permite re-escanear muy rápido porque solo
recorre direcciones previamente matcheadas.

### 3.5 PointerList (pointer scanning DFS)

```
1. Para cada sección marcada, lee memoria en bloques de 128 MB
2. Por cada qword (8 bytes) encontrado, si apunta a una dirección dentro
   de cualquier MappedSection, agrega {Address, PointerValue} a PointerList
3. Init(): ordena por Address y por PointerValue (dos listas paralelas)
4. FindPointerList(target_address, range):
   - DFS recursivo buscando cadenas base → [offset_0] → [offset_1] → ... → target
   - range[i] = máximo offset permitido en nivel i
   - max_pointer_count = 15 por nivel
   - Emite evento NewPathGenerated por cada cadena encontrada
```

### 3.6 CheatList

Tipos de operadores: `DATA, OFFSET, ADDRESS, SIMPLE_POINTER, POINTER, ARITHMETIC`

Cada cheat tiene:
- `address` (AddressCheatOperator) — dirección absoluta o relativa a sección
- `value` (DataCheatOperator) — valor a escribir
- `type` (ValueType) — uint/float/string/hex/etc.
- `frozen` (bool) — si está congelado, un thread lo escribe periódicamente
- `lock` (bool) — bloquear edición

Save format: texto con `|` y `_` como separadores, una línea por cheat.

## 4. Decisiones de port a Python/Termux

1. **Endianness:** Toda la PS4 es little-endian x86-64. Python `struct` con `<` es correcto.

2. **TCP chunks:** El C# envía/recibe en bloques de `NET_MAX_LENGTH=0x20000` (128 KB).
   En Python usaremos `sock.sendall()` y un loop de `recv()` hasta completar el length esperado.
   No es necesario chunking explícito para send (sendall lo hace), pero sí para recv.

3. **Thread-safety:** El original usa 3 conexiones paralelas con mutexes para
   paralelizar reads. En Python usaremos un pool de conexiones con `threading.Lock`
   por conexión. El GIL limita el paralelismo CPU pero no el I/O.

4. **ResultList:** Port directo del bitmap. Es importante para next-scan eficiente.

5. **ScanThread:** Patrón producer/consumer con `queue.Queue` (thread-safe).
   - 1 thread productor lee bloques de memoria por TCP
   - N threads consumidores comparan
   - Buffer configurable: default 32 MB en móvil (no 128 MB)

6. **Tipos:** Usaremos `enum.IntEnum` para `ValueType` y `CompareType`.
   Las conversiones con `struct.pack/unpack`.

7. **Optimización:** Para uint32/uint64 scan, usar `numpy.frombuffer` para
   decodificar el buffer de una sola vez y comparar vectorialmente. Para
   otros tipos, `struct.unpack` en loop o `array.array`.

8. **CLI:** `click` para subcomandos + `rich` para tablas/progreso + `prompt_toolkit`
   para el REPL con autocompletado.

9. **Android nativa (Fase 5):** Dejaremos esqueleto + README con 3 opciones:
   - A: Kotlin + Chaquopy (empaquetar Python core)
   - B: Flutter + FFI a libdebug C
   - C: WebView sobre Flask local (más rápido de implementar)

10. **Mock server:** Para testing sin PS4. Implementa CMD_PROC_LIST, CMD_PROC_INFO,
    CMD_PROC_MAPS, CMD_PROC_READ, CMD_PROC_WRITE con datos simulados.

## 5. Validación de constantes

| Constante                  | Valor original C#        | Valor en Python port  |
|----------------------------|--------------------------|------------------------|
| `CMD_PACKET_MAGIC`         | `0xFFAABBCC`             | `0xFFAABBCC`           |
| `CMD_PACKET_SIZE`          | `12`                     | `12`                   |
| `NET_MAX_LENGTH`           | `0x20000` (128 KB)       | `0x20000`              |
| `PEEK_BUFFER_LENGTH`       | `32 * 1024 * 1024` (32MB)| `32 * 1024 * 1024`     |
| `MAX_PEEK_QUEUE`           | `4`                      | `4`                    |
| `ResultList.buffer_size`   | `4096 * 16 = 65536`      | `65536`                |
| `PROC_LIST_ENTRY_SIZE`     | `36`                     | `36`                   |
| `PROC_MAP_ENTRY_SIZE`      | `58`                     | `58`                   |
| `PROC_PROC_INFO_SIZE`      | `188`                    | `188`                  |
| `CMD_PROC_READ_PACKET_SIZE`| `16`                     | `16`                   |

---

Fase 0 completa. Procedemos a FASE 1.
