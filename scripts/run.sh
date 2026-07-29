#!/data/data/com.termux/files/usr/bin/bash
# run.sh — Lanzador rápido para Termux o Linux
# Uso: bash run.sh [comando args...]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

exec python3 "$PROJECT_ROOT/cli/main.py" "$@"
