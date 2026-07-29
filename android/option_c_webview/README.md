# PS4Cheater Android — Opción C (WebView + Flask)

Implementación más rápida de la app Android nativa. Reutiliza 100% del código
Python (lib/ y core/) sirviéndolo vía un servidor Flask local. La app Android
es solo un WebView que carga `http://localhost:8080`.

## Arquitectura

```
┌─────────────────────────────────┐
│ App Android (WebView)            │
│  - Carga http://localhost:8080   │
└────────────┬────────────────────┘
             │ HTTP
┌────────────▼────────────────────┐
│ Flask server (en Termux bg)      │
│  - server/app.py                 │
│  - reusa lib/ y core/            │
└────────────┬────────────────────┘
             │ TCP 744/9090
┌────────────▼────────────────────┐
│ PS4 con ps4debug/GoldHEN         │
└─────────────────────────────────┘
```

## Requisitos

- Android 7.0+ (API 24+)
- Termux instalado
- Python 3.10+ con Flask (`pip install flask`)
- PS4 con ps4debug o GoldHEN cargado en la misma red WiFi

## Setup (3 pasos)

### Paso 1: Instalar Flask en Termux

```bash
pkg install python
pip install flask
```

### Paso 2: Lanzar el servidor Flask

```bash
cd ~/ps4cheater-android/android/option_c_webview/server
python3 app.py --host 127.0.0.1 --port 8080
```

(dejarlo corriendo en background con `nohup ... &` o en una sesión tmux)

### Paso 3: Instalar la APK

La APK debe compilarse desde Android Studio o Gradle. Por simplicidad, también
puedes abrir `http://127.0.0.1:8080/` directamente en el navegador del móvil
sin necesidad de instalar la APK.

```bash
# Compilar APK (requiere Android SDK)
cd android/option_c_webview
./gradlew assembleDebug
# APK generado en app/build/outputs/apk/debug/app-debug.apk
```

## Uso

1. Abre la app (o navega a `http://127.0.0.1:8080/` en el navegador)
2. En la pestaña "Conexión", introduce la IP de tu PS4 y pulsa "Conectar"
3. En "Procesos", selecciona el proceso del juego y pulsa "Attach"
4. En "Scan", elige tipo de valor, comparación y valor, y pulsa "New Scan"
5. Repite con "Next Scan" para filtrar resultados
6. En "Memoria", lee/escribe direcciones específicas con hexdump
7. En "Cheats", añade cheats y marca "Freeze" para mantener valores constantes

## Limitaciones

- El servidor Flask debe estar corriendo en Termux (no se auto-inicia)
- Solo accesible desde el mismo dispositivo (localhost)
- El freeze loop corre dentro del proceso Flask (no sobrevive a un cierre de Termux)
- No es una "app nativa" real (WebView)

## Migración a Opción A (Kotlin + Chaquopy)

Cuando se quiera una app Play Store-ready:

1. Empaquetar `lib/` y `core/` dentro del APK usando Chaquopy
2. Reemplazar el servidor Flask por invocaciones directas a Python desde Kotlin
3. Implementar Foreground Service para que el freeze loop sobreviva
4. UI nativa con Jetpack Compose (5 pantallas: Connect, Procs, Scan, Memory, Cheats)

Ver `../README.md` para más detalles sobre Opción A.
