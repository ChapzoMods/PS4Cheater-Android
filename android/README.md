# PS4Cheater Android — App Nativa (FASE 5)

Esta carpeta contiene el esqueleto y documentación para la app Android nativa
de PS4Cheater. La versión CLI para Termux (carpeta `/cli/`) es la prioridad
principal y está completa; esta carpeta ofrece tres opciones para una UI
gráfica nativa, ordenadas por **tiempo de implementación**.

## Comparativa de opciones

| Opción | Stack | Tiempo | Pros | Contras |
|--------|-------|--------|------|---------|
| **A** | Kotlin + Jetpack Compose + Chaquopy | Alto (3-5 días) | UX nativa máxima, foreground service para freeze loop | Complejo de empaquetar, Chaquopy adds ~30MB al APK |
| **B** | Flutter + FFI a libdebug C | Muy alto (5-7 días) | Multiplataforma (iOS también), rendimiento C | Requiere portear libdebug a C compartido, configuración NDK compleja |
| **C** | WebView + Flask local | Bajo (medio día) | Reutiliza 100% del código Python, UI inmediata | No es "app nativa" real, requiere Termux + Flask corriendo en background |

**Recomendación:** Empezar con **Opción C** (MVP rápido) y migrar a **Opción A**
si se quiere una app Play Store-ready.

---

## Opción C — WebView + Flask local (recomendada para MVP)

### Arquitectura

```
┌─────────────────────────────────┐
│ App Android (WebView)            │
│  - Carga http://localhost:8080   │
│  - UI: HTML+JS+CSS responsive    │
└────────────┬────────────────────┘
             │ HTTP
┌────────────▼────────────────────┐
│ Flask server (en Termux bg)      │
│  - endpoints REST: /api/...      │
│  - reusa lib/ y core/ de Python  │
└────────────┬────────────────────┘
             │ TCP 744/9090
┌────────────▼────────────────────┐
│ PS4 con ps4debug/GoldHEN         │
└─────────────────────────────────┘
```

### Estructura

```
android/option_c_webview/
├── app/                        # App Android mínima (WebView)
│   ├── build.gradle
│   └── src/main/java/com/ps4cheater/MainActivity.kt
├── server/                     # Servidor Flask local
│   ├── app.py                  # Endpoints REST
│   ├── templates/              # HTML
│   └── static/                 # JS/CSS
└── README.md                   # Instrucciones de build
```

Ver `option_c_webview/README.md` para instrucciones detalladas.

---

## Opción A — Kotlin + Jetpack Compose + Chaquopy

### Arquitectura

```
┌────────────────────────────────────┐
│ App Android (Kotlin + Compose)      │
│  - 5 pantallas (Connect, Procs,     │
│    Scanner, HexEditor, Cheats)      │
│  - Foreground Service para freeze   │
└────────────┬───────────────────────┘
             │ Chaquopy (JNI)
┌────────────▼───────────────────────┐
│ Python core (lib/ + core/)          │
│  - Empaquetado dentro del APK       │
│  - Invocado via Chaquopy Python API │
└────────────┬───────────────────────┘
             │ TCP 744/9090
┌────────────▼───────────────────────┐
│ PS4 con ps4debug/GoldHEN            │
└────────────────────────────────────┘
```

### Pantallas

1. **ConnectScreen** — IP, puerto, botón conectar, indicador de estado
2. **ProcessListScreen** — RecyclerView/LazyColumn de procesos
3. **ScannerScreen** — tipo de valor, comparación, input, botón scan, progreso, resultados
4. **HexEditorScreen** — hex view/edit de una dirección de memoria
5. **CheatTableScreen** — lista de cheats, toggle freeze, add/edit/delete

### Dependencias

- Kotlin 1.9+
- Jetpack Compose BOM 2024.x
- Chaquopy 14.0+ (para ejecutar Python dentro del APK)
- Material 3
- AndroidX Lifecycle, ViewModel, LiveData
- Foreground service para freeze loop

### Build

Ver `option_a_kotlin/README.md` (pendiente de implementar).

---

## Opción B — Flutter + FFI

### Arquitectura

```
┌────────────────────────────────────┐
│ App Flutter (Dart)                  │
│  - 5 pantallas (Material Design)    │
│  - Background isolate para freeze   │
└────────────┬───────────────────────┘
             │ dart:ffi
┌────────────▼───────────────────────┐
│ libps4cheater.so (C)                │
│  - Port de lib/protocol.c           │
│  - Funciones exportadas: connect,   │
│    read_memory, write_memory, etc.  │
└────────────┬───────────────────────┘
             │ TCP 744/9090
┌────────────▼───────────────────────┐
│ PS4 con ps4debug/GoldHEN            │
└────────────────────────────────────┘
```

### Pros vs Opción A

- Multiplataforma (iOS, desktop)
- Mejor rendimiento que Chaquopy (sin overhead de Python)
- Hot reload para desarrollo

### Contras

- Requiere portear `lib/ps4dbg.py` y partes de `core/` a C
- Configuración NDK/CMake más compleja
- No reutiliza directamente el código Python existente

### Build

Ver `option_b_flutter/README.md` (pendiente de implementar).

---

## Estado actual

- ✅ **CLI Termux** (FASE 4) — Completo y testeado (169 tests pytest)
- ✅ **Opción A (Kotlin+Chaquopy)** — **Implementada completa** en `option_a_kotlin/`
- ⏳ **Opción C (WebView)** — Implementada en `option_c_webview/`
- ❌ **Opción B (Flutter+FFI)** — Solo documentación

## Recomendación de uso

1. **Para usuarios finales hoy:** Instalar Termux + `bash install_termux.sh` y usar la CLI.
2. **Para una app nativa Play Store-ready:** Abrir `option_a_kotlin/` en Android Studio y compilar (Opción A, completa).
3. **Para una app web rápida:** Usar `option_c_webview/` (Flask + WebView, medio día).
