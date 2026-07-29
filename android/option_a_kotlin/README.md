# PS4Cheater Android — Opción A (Kotlin + Jetpack Compose + Chaquopy)

App Android nativa completa con UI Jetpack Compose que reutiliza 100% del
código Python (`lib/` y `core/`) vía [Chaquopy](https://chaquo.com/chaquopy/).

## Arquitectura

```
┌──────────────────────────────────────────┐
│ App Android (Kotlin + Jetpack Compose)    │
│  - 5 pantallas Material 3                  │
│  - 3 ViewModels (Connection, Scanner,     │
│    Cheat)                                  │
│  - Foreground Service para freeze loop    │
│  - Navigation Compose                     │
└──────────────┬───────────────────────────┘
               │ Chaquopy (JNI → Python 3.10)
┌──────────────▼───────────────────────────┐
│ chaquopy_bridge.py                        │
│  - Estado global del módulo               │
│  - 25+ funciones: connect, scan, cheat…   │
│  - Devuelve dicts {"ok": true/false, ...} │
└──────────────┬───────────────────────────┘
               │ import
┌──────────────▼───────────────────────────┐
│ lib/ + core/ (Python puro)                │
│  - PS4DBG (cliente TCP)                    │
│  - ScanEngine (escaneo vectorial)          │
│  - CheatList + Freeze loop                 │
│  - PointerList (DFS multi-nivel)           │
└──────────────┬───────────────────────────┘
               │ TCP socket (puerto 744/9090)
┌──────────────▼───────────────────────────┐
│ PS4 con ps4debug/GoldHEN                  │
└──────────────────────────────────────────┘
```

## Pantallas

| # | Pantalla | Función |
|---|----------|---------|
| 1 | **ConnectScreen** | IP, puerto, botón conectar, indicador de estado |
| 2 | **ProcessListScreen** | Lista de procesos PS4, botón Attach |
| 3 | **ScannerScreen** | Tipo de valor, comparación, input, scan, resultados |
| 4 | **HexEditorScreen** | Hex view/edit de memoria |
| 5 | **CheatTableScreen** | Lista de cheats, toggle freeze, add/edit/delete |

## Estructura

```
android/option_a_kotlin/
├── settings.gradle.kts              # Config Gradle (incluye repo Chaquopy)
├── build.gradle.kts                 # Plugins AGP + Chaquopy + Kotlin
├── gradle.properties
├── gradle/wrapper/
│   └── gradle-wrapper.properties    # Gradle 8.5
├── app/
│   ├── build.gradle.kts             # Deps Compose + Chaquopy config
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml      # Permisos + FreezeService
│       ├── python/                  # Código Python empaquetado en APK
│       │   ├── chaquopy_bridge.py   # Bridge Kotlin ↔ Python
│       │   ├── lib/                 # Copia de lib/ (PS4DBG)
│       │   └── core/                # Copia de core/ (scanner, cheats…)
│       ├── java/com/ps4cheater/
│       │   ├── Ps4CheaterApp.kt     # Application: inicializa Python
│       │   ├── MainActivity.kt      # Actividad principal (Compose)
│       │   ├── data/
│       │   │   ├── Models.kt        # Data classes (Status, ProcessInfo…)
│       │   │   ├── PythonBridge.kt  # Wrapper Chaquopy (Kotlin → Python)
│       │   │   └── Ps4Repository.kt # Capa coroutine (suspend functions)
│       │   ├── service/
│       │   │   └── FreezeService.kt # Foreground Service para freeze loop
│       │   └── ui/
│       │       ├── theme/           # Color.kt, Theme.kt, Type.kt
│       │       ├── navigation/
│       │       │   └── NavGraph.kt  # NavHost con 5 rutas
│       │       ├── viewmodel/
│       │       │   ├── ConnectionViewModel.kt
│       │       │   ├── ScannerViewModel.kt
│       │       │   └── CheatViewModel.kt
│       │       └── screens/
│       │           ├── ConnectScreen.kt
│       │           ├── ProcessListScreen.kt
│       │           ├── ScannerScreen.kt
│       │           ├── HexEditorScreen.kt
│       │           └── CheatTableScreen.kt
│       └── res/
│           ├── values/              # strings.xml, colors.xml, themes.xml
│           ├── drawable/            # Launcher icons (vector)
│           ├── mipmap-anydpi-v26/   # Adaptive icons
│           └── xml/                 # backup_rules, data_extraction_rules
└── README.md (este archivo)
```

## Requisitos

- **Android Studio** Hedgehog (2023.1.1) o superior
- **JDK 17**
- **Android SDK** API 34 (compileSdk)
- **Min SDK** 24 (Android 7.0)
- **Gradle** 8.5 (descargado automáticamente por el wrapper)
- **PS4** con ps4debug o GoldHEN cargado en la misma red WiFi

## Compilar

### Opción 1: Android Studio (recomendada)

1. Abre Android Studio
2. `File → Open` y selecciona la carpeta `android/option_a_kotlin/`
3. Espera a que Gradle sync termine (descargará Chaquopy y todas las deps)
4. Conecta tu teléfono Android (con debugging USB activado) o crea un emulador
5. Pulsa `Run ▶` (Shift+F10)

### Opción 2: Línea de comandos

```bash
cd android/option_a_kotlin

# Generar el wrapper de Gradle (si no existe)
# (necesitas Gradle 8.5 instalado, o usa Android Studio)
gradle wrapper --gradle-version 8.5

# Build debug APK
./gradlew assembleDebug

# Instalar en dispositivo conectado
./gradlew installDebug

# O instalar el APK manualmente:
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Uso

1. **Conectar**: Abre la app, introduce la IP de tu PS4, pulsa "ps4debug (744)" o "GoldHEN (9090)", luego "Conectar"
2. **Procesos**: Pulsa "Continuar →", selecciona el proceso del juego (ej: `eboot.bin`)
3. **Scanner**: Pulsa "Ir a Scanner →", marca "rw-only", elige tipo de valor y comparación, introduce el valor a buscar, pulsa "New Scan"
4. **Resultados**: Modifica el valor en el juego, vuelve a la app, pulsa "Next Scan" con el comparador adecuado (changed, increased, etc.)
5. **Memoria**: Pulsa "Memoria" para leer/escribir direcciones específicas
6. **Cheats**: Pulsa "Cheats", añade cheats con dirección + tipo + valor, marca "Freeze" para mantener valores constantes

## Cómo funciona Chaquopy

1. Al iniciar la app, `Ps4CheaterApp.onCreate()` llama a `Python.start(AndroidPlatform(this))`
2. Chaquopy extrae el runtime de Python 3.10 + los archivos en `app/src/main/python/` al almacenamiento interno
3. Desde Kotlin, `Python.getInstance().getModule("chaquopy_bridge")` obtiene una referencia al módulo Python
4. `module.callAttr("connect", ip, port)` invoca la función Python y devuelve un `PyObject`
5. `PythonBridge.kt` convierte el `PyObject` a `Result<T>` de Kotlin
6. `Ps4Repository.kt` envuelve las llamadas en `withContext(Dispatchers.IO)` para que sean `suspend`
7. Los ViewModels usan `viewModelScope.launch` para llamar al Repository
8. Las screens observan el `StateFlow` del ViewModel con `collectAsStateWithLifecycle()`

## Freeze Loop

El freeze loop (re-escribir cheats frozen cada 100ms) se implementa con un
**Foreground Service** (`FreezeService.kt`) para que sobreviva cuando la app
va a background:

1. `CheatViewModel.startFreeze(context)` llama a `FreezeService.start(context)`
2. El servicio muestra una notificación persistente (requerido por Android para foreground services)
3. Una coroutine en `Dispatchers.IO` llama `repository.applyFrozen()` cada 100ms
4. `applyFrozen()` invoca `chaquopy_bridge.apply_frozen()` que llama `CheatList.apply_frozen()` en Python
5. Los cheats marcados como frozen se re-escriben en memoria de la PS4

## Dependencias

| Dependencia | Versión | Uso |
|-------------|---------|-----|
| AGP | 8.1.4 | Android Gradle Plugin |
| Kotlin | 1.9.10 | Lenguaje |
| Compose BOM | 2023.10.01 | Jetpack Compose |
| Compose Compiler | 1.5.3 | Compose compiler |
| Chaquopy | 15.0.0 | Python en Android |
| Navigation Compose | 2.7.5 | Navegación |
| Lifecycle | 2.6.2 | ViewModels + compose |
| Coroutines | 1.7.3 | Async |
| numpy | (pip) | Escaneo vectorial en Python |

## Notas

- El APK incluirá el runtime de Python (~10MB) + numpy (~15MB), sumando ~25MB al tamaño del APK
- La primera vez que se inicia la app, Chaquopy extrae Python al almacenamiento interno (tarda ~5 segundos)
- Las llamadas a Python son síncronas y se ejecutan en `Dispatchers.IO` para no bloquear la UI
- El código Python es el MISMO que el de la CLI Termux (`lib/` y `core/`), solo copiado a `app/src/main/python/`

## Troubleshooting

### "Python not started" al iniciar la app

Asegúrate de que `Ps4CheaterApp` está declarado como `android:name` en el `<application>` del manifest.

### Crash al llamar a Python

Verifica que los archivos `lib/__init__.py` y `core/__init__.py` existen en `app/src/main/python/`. Sin ellos, Python no puede importar los paquetes.

### "ModuleNotFoundError: No module named 'numpy'"

Chaquopy instala numpy vía pip durante el build. Si falla, verifica tu conexión a internet durante el build, o quita `install("numpy")` de `app/build.gradle.kts` (el scanner caerá al modo lento en Python puro).

### El freeze loop se detiene al cerrar la app

Es esperado: el Foreground Service se detiene cuando la app es matada. Para que sobreviva, mantén la app en background (no la cierres desde Recent Apps).
