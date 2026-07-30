package com.ps4cheater

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Textos y widgets compartidos por las pantallas de MainActivity.
 * Los comandos de Termux y los pasos de instalación viven aquí una sola vez.
 */

/** Nombre del zip que se publica en Downloads. */
const val ZIP_NAME = "ps4cheater.zip"

/** Directorio en el que se descomprime el zip en Termux. */
const val TERMUX_INSTALL_DIR = "~/ps4cheater"

/** Directorios de assets Python que se empaquetan en el zip. */
val PYTHON_ASSET_DIRS = listOf("lib", "core", "cli")

/** Comandos de Termux mostrados en la UI (fuente única para todas las pantallas). */
val TERMUX_COMMANDS = listOf(
    "termux-setup-storage",
    "unzip ~/storage/downloads/$ZIP_NAME -d $TERMUX_INSTALL_DIR",
    "cd $TERMUX_INSTALL_DIR && pip install click rich prompt_toolkit",
    "python cli/main.py connect <IP_PS4>",
    "python -m http.server 8080 &",
)

/** Pasos de instalación (se numeran al renderizar). */
val SETUP_STEPS = listOf(
    "Pulsa \"Empaquetar scripts\" abajo — se creará $ZIP_NAME en tu carpeta Downloads",
    "Instala Termux desde F-Droid (NO desde Play Store)",
    "En Termux ejecuta: termux-setup-storage (otorga permiso)",
    "Descomprime: unzip ~/storage/downloads/$ZIP_NAME -d $TERMUX_INSTALL_DIR",
    "Instala dependencias: cd $TERMUX_INSTALL_DIR && pip install click rich prompt_toolkit",
    "(Opcional) numpy: pip install numpy (si falla, el escaneo será más lento pero funcional)",
    "Conecta: python cli/main.py connect <IP_PS4>",
    "Inicia servidor web: python -m http.server 8080 & (opcional, para UI web)",
    "Vuelve a esta app y pulsa \"Abrir interfaz web\"",
)

/** Lista de comandos en monoespaciado, usada en varias pantallas. */
@Composable
fun CommandList(commands: List<String> = TERMUX_COMMANDS, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        commands.forEach { command ->
            Text(
                command,
                fontFamily = FontFamily.Monospace,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.secondary
            )
            Spacer(Modifier.height(4.dp))
        }
    }
}

/** Par de botones de ancho completo (acción principal + secundaria) de las pantallas. */
@Composable
fun ScreenActions(
    primaryLabel: String,
    onPrimary: () -> Unit,
    secondaryLabel: String,
    onSecondary: () -> Unit,
) {
    Button(onClick = onPrimary, modifier = Modifier.fillMaxWidth()) {
        Text(primaryLabel)
    }
    Spacer(Modifier.height(8.dp))
    OutlinedButton(onClick = onSecondary, modifier = Modifier.fillMaxWidth()) {
        Text(secondaryLabel)
    }
}
