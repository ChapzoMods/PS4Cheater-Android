#!/data/data/com.termux/files/usr/bin/bash
#
# PS4Cheater for Termux — Installer
# Idempotent: can be re-run safely.
#
set -e

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

REPO_URL="${1:-https://github.com/ChapzoMods/PS4Cheater-Android.git}"
INSTALL_DIR="$HOME/ps4cheater"
ZIP_PATH="$HOME/storage/downloads/ps4cheater.zip"
WRAPPER="$PREFIX/bin/ps4cheater"
NUMPY_OK=1

echo -e "${CYAN}"
echo "============================================================"
echo "   PS4Cheater for Termux — Installer"
echo "============================================================"
echo -e "${NC}"

# ------------------------------------------------------------------
# Step 1: Update packages
# ------------------------------------------------------------------
echo -e "${CYAN}[1/7]${NC} Actualizando lista de paquetes..."
pkg update -y

# ------------------------------------------------------------------
# Step 2: Install system deps
# ------------------------------------------------------------------
echo -e "${CYAN}[2/7]${NC} Instalando dependencias del sistema (python, git, unzip)..."
pkg install -y python git unzip

# ------------------------------------------------------------------
# Step 3: termux-setup-storage
# ------------------------------------------------------------------
echo -e "${CYAN}[3/7]${NC} Verificando acceso a almacenamiento..."
if [ ! -d "$HOME/storage" ]; then
    echo -e "${YELLOW}  Nota:${NC} se solicitara permiso de almacenamiento."
    echo -e "${YELLOW}  Pulsa 'Permitir' en el dialogo del sistema.${NC}"
    termux-setup-storage
    # Wait a moment for the storage symlinks to materialize
    sleep 2
else
    echo -e "${GREEN}  OK${NC} ~/storage ya existe."
fi

# ------------------------------------------------------------------
# Step 4: Obtain the source
# ------------------------------------------------------------------
echo -e "${CYAN}[4/7]${NC} Obteniendo los scripts de PS4Cheater..."

if [ -f "$ZIP_PATH" ]; then
    echo -e "${GREEN}  Zip encontrado:${NC} $ZIP_PATH"
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}  Directorio existente encontrado, eliminando...${NC}"
        rm -rf "$INSTALL_DIR"
    fi
    echo -e "${CYAN}  Descomprimiendo a $INSTALL_DIR...${NC}"
    mkdir -p "$INSTALL_DIR"
    unzip -o -q "$ZIP_PATH" -d "$INSTALL_DIR"
    echo -e "${GREEN}  OK${NC} scripts extraidos."
elif [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}  No se encontro el zip, pero ~/ps4cheater ya existe.${NC}"
    echo -e "${YELLOW}  Asumiendo que el repositorio ya esta clonado.${NC}"
else
    echo -e "${RED}  No se encontro $ZIP_PATH ni $INSTALL_DIR.${NC}"
    echo ""
    echo -e "${YELLOW}  Opciones:${NC}"
    echo -e "  ${CYAN}a)${NC} Descarga el APK desde:"
    echo -e "       https://github.com/ChapzoMods/PS4Cheater-Android/releases/latest"
    echo -e "     Abre la app y pulsa 'Empaquetar scripts a Downloads',"
    echo -e "     luego vuelve a ejecutar este script."
    echo ""
    echo -e "  ${CYAN}b)${NC} Clonar el repositorio directamente:"
    echo -e "       git clone ${REPO_URL} ${INSTALL_DIR}"
    echo ""
    echo -e "${YELLOW}  Procediendo con la opcion (b)...${NC}"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ------------------------------------------------------------------
# Step 5: Python dependencies
# ------------------------------------------------------------------
echo -e "${CYAN}[5/7]${NC} Instalando dependencias de Python..."
pip install --upgrade pip
pip install click rich prompt_toolkit

echo -e "${CYAN}  Instalando numpy (opcional)...${NC}"
if pip install numpy; then
    echo -e "${GREEN}  OK${NC} numpy instalado. El escaneo sera rapido (vectorial)."
    NUMPY_OK=0
else
    echo -e "${YELLOW}  WARNING:${NC} numpy no pudo instalarse (bionic libc)."
    echo -e "${YELLOW}           El escaneo funcionara pero sera mas lento.${NC}"
    NUMPY_OK=1
fi

# ------------------------------------------------------------------
# Step 6: Wrapper script
# ------------------------------------------------------------------
echo -e "${CYAN}[6/7]${NC} Creando wrapper 'ps4cheater' en $PREFIX/bin..."
mkdir -p "$PREFIX/bin"
cat > "$WRAPPER" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python3 "$INSTALL_DIR/cli/main.py" "\$@"
EOF
chmod +x "$WRAPPER"
echo -e "${GREEN}  OK${NC} wrapper creado."

# ------------------------------------------------------------------
# Step 7: Done
# ------------------------------------------------------------------
echo -e "${CYAN}[7/7]${NC} Instalacion completa."
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  PS4Cheater listo para usar.${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "${CYAN}Proximos pasos:${NC}"
echo -e "  ${GREEN}ps4cheater connect <IP_PS4>${NC}        # conectar (puerto 744 ps4debug)"
echo -e "  ${GREEN}ps4cheater connect <IP_PS4> --goldhen${NC}  # GoldHEN (puerto 9090)"
echo -e "  ${GREEN}ps4cheater procs${NC}                   # listar procesos"
echo -e "  ${GREEN}ps4cheater repl${NC}                    # modo interactivo"
echo ""
echo -e "${CYAN}Troubleshooting:${NC}"
if [ "$NUMPY_OK" -ne 0 ]; then
    echo -e "  ${YELLOW}- numpy no esta instalado.${NC}"
    echo -e "    El escaneo funcionara pero sera mas lento."
    echo -e "    Para instalar numpy: ${GREEN}pip install numpy${NC}"
    echo -e "    Alternativa: ${GREEN}pkg install python-numpy${NC}"
fi
echo -e "  ${YELLOW}- Si no puedes conectar a la PS4:${NC}"
echo -e "    * Verifica que PS4 y telefono esten en la misma red WiFi"
echo -e "    * Confirma que ps4debug o GoldHEN esten cargados"
echo -e "    * Comprueba la IP y que no haya firewall bloqueando el puerto"
echo ""
echo -e "${CYAN}Repo:${NC} https://github.com/ChapzoMods/PS4Cheater-Android"
echo ""
