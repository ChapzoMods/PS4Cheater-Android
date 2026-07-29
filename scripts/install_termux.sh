#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
# install_termux.sh — Auto-instalador de PS4Cheater para Termux (sin root)
# ============================================================================
# Uso:
#   curl -L https://raw.githubusercontent.com/<user>/ps4cheater-android/main/scripts/install_termux.sh | bash
#   o:
#   bash install_termux.sh
# ============================================================================

set -e

# Colores
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}=== PS4Cheater para Termux — Instalador ===${NC}"
echo ""

# 1. Verificar que estamos en Termux (o al menos en Android/Linux)
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${YELLOW}⚠ No se detectó Termux. El script funcionará igual en Linux normal.${NC}"
fi

# 2. Actualizar paquetes e instalar dependencias del sistema
echo -e "${CYAN}[1/5] Actualizando paquetes…${NC}"
pkg update -y || apt-get update -y

echo -e "${CYAN}[2/5] Instalando dependencias del sistema…${NC}"
pkg install -y python git || apt-get install -y python git

# 3. Instalar dependencias Python
echo -e "${CYAN}[3/5] Instalando dependencias Python…${NC}"
pip install --upgrade pip
pip install \
    click \
    rich \
    prompt_toolkit \
    numpy \
    struct \
    hexdump

# numpy puede fallar en algunos Termux antiguos; si falla, continuar sin numpy
if ! python -c "import numpy" 2>/dev/null; then
    echo -e "${YELLOW}⚠ numpy no se pudo instalar. El escaneo será más lento pero funcional.${NC}"
fi

# 4. Clonar repo
REPO_URL="${1:-https://github.com/a0zhar/PS4Cheater-Android.git}"
INSTALL_DIR="$HOME/ps4cheater-android"

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}[4/5] Directorio $INSTALL_DIR ya existe. Pull…${NC}"
    cd "$INSTALL_DIR"
    git pull || echo -e "${YELLOW}⚠ No se pudo hacer pull. Continuando con la versión local.${NC}"
else
    echo -e "${CYAN}[4/5] Clonando $REPO_URL…${NC}"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# 5. Crear wrapper y alias
echo -e "${CYAN}[5/5] Creando comando 'ps4cheater'…${NC}"

# Wrapper script
WRAPPER="$PREFIX/bin/ps4cheater"
if [ -w "$PREFIX/bin" ]; then
    cat > "$WRAPPER" << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
exec python3 "$HOME/ps4cheater-android/cli/main.py" "$@"
EOF
    chmod +x "$WRAPPER"
    echo -e "${GREEN}✓ Wrapper creado en $WRAPPER${NC}"
else
    # Fallback: alias en .bashrc
    BASHRC="$HOME/.bashrc"
    if ! grep -q "ps4cheater=" "$BASHRC" 2>/dev/null; then
        echo 'alias ps4cheater="python3 $HOME/ps4cheater-android/cli/main.py"' >> "$BASHRC"
        echo -e "${GREEN}✓ Alias añadido a $BASHRC${NC}"
        echo -e "${YELLOW}  Ejecuta 'source ~/.bashrc' o abre un nuevo terminal para usarlo.${NC}"
    fi
fi

# 6. Verificar instalación
echo ""
echo -e "${GREEN}=== Instalación completa ===${NC}"
echo ""
echo "Para usar:"
echo -e "  ${CYAN}ps4cheater connect 192.168.1.X${NC}        # ps4debug (puerto 744)"
echo -e "  ${CYAN}ps4cheater connect 192.168.1.X --goldhen${NC}  # GoldHEN (puerto 9090)"
echo -e "  ${CYAN}ps4cheater procs${NC}                     # listar procesos"
echo -e "  ${CYAN}ps4cheater attach eboot.bin${NC}          # attachear"
echo -e "  ${CYAN}ps4cheater sections --rw-only${NC}        # marcar secciones legibles"
echo -e "  ${CYAN}ps4cheater scan new uint32 exact 100${NC} # buscar valor 100"
echo -e "  ${CYAN}ps4cheater scan next changed${NC}         # filtrar cambiados"
echo -e "  ${CYAN}ps4cheater scan results${NC}              # ver resultados"
echo -e "  ${CYAN}ps4cheater cheat add 0x10000000 uint32 9999 --freeze${NC}"
echo -e "  ${CYAN}ps4cheater repl${NC}                      # modo interactivo"
echo ""
echo -e "${YELLOW}Requisitos:${NC}"
echo "  - PS4 con ps4debug o GoldHEN cargado"
echo "  - Teléfono Android en la misma red WiFi que la PS4"
echo "  - Firewall permitiendo conexiones salientes a los puertos 744/9090"
echo ""
echo -e "${YELLOW}Troubleshooting:${NC}"
echo "  - Si la conexión falla, verifica que la PS4 y el teléfono están en la misma red"
echo "  - Asegúrate de que ps4debug/GoldHEN está cargado en la PS4"
echo "  - En GoldHEN 2.x, el puerto por defecto es 9090"
echo "  - Para conexiones lentas, usa --port 744 (ps4debug directo)"
