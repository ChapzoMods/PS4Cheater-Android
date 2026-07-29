# PS4Cheater Android

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Android](https://img.shields.io/badge/Android-7.0%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-169%20passing-brightgreen)

Port de **PS4Cheater** a Android/Termux. Permite escaneo de memoria y gestión de
cheats para PS4 directamente desde el teléfono, mediante el protocolo ps4debug
(puerto 744) o GoldHEN (puerto 9090). Incluye una app Android nativa que empaqueta
los scripts de Python y un CLI completo para Termux.

## Features

- ✅ CLI interactiva para Termux (16 comandos + REPL)
- ✅ 14 tipos de comparación (exact, fuzzy, increased, changed, between, etc.)
- ✅ 9 tipos de valor (uint8/16/32/64, float, double, hex, string, pointer)
- ✅ Escaneo vectorial con numpy (opcional, fallback a Python puro)
- ✅ ResultList bitmap compacto (igual que C# original)
- ✅ CheatList con freeze loop (Foreground Service en la app nativa)
- ✅ Pointer scanning multi-nivel (DFS, max 5 niveles)
- ✅ Export/import cheat tables (JSON + .CT Cheat Engine)
- ✅ App Android nativa con Jetpack Compose + Material 3
- ✅ 169 tests pytest + mock server TCP
- ✅ Sin root requerido

## Descarga rápida

- **APK directa:** https://github.com/ChapzoMods/PS4Cheater-Android/releases/latest
- **Repo:** https://github.com/ChapzoMods/PS4Cheater-Android

## Instalación

### Opción A: App Android + Termux (recomendada)

1. Descarga e instala el APK desde [Releases](https://github.com/ChapzoMods/PS4Cheater-Android/releases/latest)
2. Abre la app, pulsa "Empaquetar scripts a Downloads"
3. Instala [Termux desde F-Droid](https://f-droid.org/packages/com.termux/) (NO Play Store)
4. En Termux:
   ```bash
   bash <(curl -sL https://raw.githubusercontent.com/ChapzoMods/PS4Cheater-Android/main/scripts/install_termux.sh)
   ```
5. O manualmente:
   ```bash
   termux-setup-storage
   unzip ~/storage/downloads/ps4cheater.zip -d ~/ps4cheater
   cd ~/ps4cheater
   pip install click rich prompt_toolkit
   pip install numpy  # opcional, acelera el escaneo
   echo 'alias ps4cheater="python3 ~/ps4cheater/cli/main.py"' >> ~/.bashrc
   source ~/.bashrc
   ```

### Opción B: Solo Termux (sin app Android)

```bash
pkg install python git
git clone https://github.com/ChapzoMods/PS4Cheater-Android.git ~/ps4cheater
cd ~/ps4cheater
pip install click rich prompt_toolkit numpy
alias ps4cheater="python3 ~/ps4cheater/cli/main.py"
```

## Uso rápido

```bash
ps4cheater connect 192.168.1.100           # ps4debug (744)
ps4cheater connect 192.168.1.100 --goldhen # GoldHEN (9090)
ps4cheater procs                           # listar procesos
ps4cheater attach eboot.bin                # attachear
ps4cheater sections --rw-only              # marcar secciones
ps4cheater scan new uint32 exact 1337      # buscar valor
ps4cheater scan next changed               # filtrar cambiados
ps4cheater scan results                    # ver resultados
ps4cheater write 0x10000000 DEADBEEF       # escribir memoria
ps4cheater cheat add 0x10000000 uint32 9999 --freeze --desc "HP"
ps4cheater repl                            # modo interactivo
```

## Estructura del proyecto

```
ps4cheater-android/
├── lib/              # Cliente TCP ps4debug (Python)
├── core/             # Motor: scanner, ResultList, cheats, pointers
├── cli/              # CLI Click + Rich + REPL
├── android/          # App Android (Kotlin + Compose)
├── tests/            # 169 tests pytest + mock server
├── scripts/          # install_termux.sh
├── docs/             # Análisis del protocolo
└── .github/workflows/build.yml  # CI
```

## Testing

```bash
python3 -m pytest tests/
```

→ 169 tests en ~1.5s

## Troubleshooting

- **Permission denied al copiar archivos**: usar la app Android para generar el zip en Downloads, luego `termux-setup-storage` y `unzip ~/storage/downloads/ps4cheater.zip`
- **numpy no instala**: es opcional, el escaneo funciona sin él (más lento). `pip install numpy` puede fallar por bionic libc en algunos Termux; intentar `pkg install python-numpy` como alternativa
- **No puedo conectar a la PS4**: verificar misma red WiFi, ps4debug/GoldHEN cargado, IP correcta, firewall
- **El escaneo es lento**: instalar numpy, marcar solo secciones rw-, usar `--unaligned` solo si es necesario

## Créditos

- **ctn123** — PS4_Cheat_Engine (original)
- **a0zhar** — PS4Cheater (fork)
- **jogolden** — ps4debug
- **a0zhar2** — libdebug (C#)
- **LightningMods** — GoldHEN

## Licencia

MIT

## Disclaimer

Este proyecto es de uso educativo. No nos hacemos responsables del uso que se
le dé. Existe riesgo de ban en juegos online — usar solo en partidas
single-player.
