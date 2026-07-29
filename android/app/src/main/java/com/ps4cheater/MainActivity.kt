package com.ps4cheater

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.ps4cheater.ui.theme.PS4CheaterTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PS4CheaterTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    AppContent()
                }
            }
        }
    }
}

@Composable
fun AppContent() {
    // State machine for the 4 screens: "home", "extracting", "done", "webview"
    var screen by remember { mutableStateOf("home") }
    var extractResult by remember { mutableStateOf("") }

    when (screen) {
        "home" -> HomeScreen(
            onExtractStart = { screen = "extracting" },
            onExtractComplete = { result ->
                extractResult = result
                screen = "done"
            },
            onWebView = { screen = "webview" }
        )
        "extracting" -> LoadingScreen()
        "done" -> DoneScreen(
            message = extractResult,
            onHome = { screen = "home" },
            onWebView = { screen = "webview" }
        )
        "webview" -> WebViewScreen(onBack = { screen = "home" })
    }
}

@Composable
fun HomeScreen(
    onExtractStart: () -> Unit,
    onExtractComplete: (String) -> Unit,
    onWebView: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "PS4Cheater",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Android Edition v1.0",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.secondary
        )
        Spacer(Modifier.height(24.dp))

        // Instructions card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    "Cómo usar",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 18.sp
                )
                Spacer(Modifier.height(12.dp))

                val steps = listOf(
                    "1" to "Pulsa \"Empaquetar scripts\" abajo — se creará ps4cheater.zip en tu carpeta Downloads",
                    "2" to "Instala Termux desde F-Droid (NO desde Play Store)",
                    "3" to "En Termux ejecuta: termux-setup-storage (otorga permiso)",
                    "4" to "Descomprime: unzip ~/storage/downloads/ps4cheater.zip -d ~/ps4cheater",
                    "5" to "Instala dependencias: cd ~/ps4cheater && pip install click rich prompt_toolkit",
                    "6" to "(Opcional) numpy: pip install numpy (si falla, el escaneo será más lento pero funcional)",
                    "7" to "Conecta: python cli/main.py connect <IP_PS4>",
                    "8" to "Inicia servidor web: python -m http.server 8080 & (opcional, para UI web)",
                    "9" to "Vuelve a esta app y pulsa \"Abrir interfaz web\""
                )
                steps.forEach { (num, text) ->
                    Text("$num. $text", fontSize = 16.sp)
                    Spacer(Modifier.height(4.dp))
                }

                Spacer(Modifier.height(12.dp))
                // Command snippets card (darker background)
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            "termux-setup-storage",
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "unzip ~/storage/downloads/ps4cheater.zip -d ~/ps4cheater",
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "cd ~/ps4cheater && pip install click rich prompt_toolkit",
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "python cli/main.py connect <IP_PS4>",
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "python -m http.server 8080 &",
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // Buttons
        Button(
            onClick = {
                // 1. Switch to the loading screen immediately
                onExtractStart()
                // 2. Launch a background coroutine to build & publish the zip
                scope.launch {
                    val result = withContext(Dispatchers.IO) {
                        extractPythonAssetsToDownloads(context)
                    }
                    // 3 & 4. Store the result and switch to the done screen
                    onExtractComplete(result)
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Empaquetar scripts a Downloads")
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onWebView,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Abrir interfaz web (localhost:8080)")
        }
    }
}

@Composable
fun LoadingScreen() {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(16.dp))
        Text(
            "Empaquetando scripts...",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Comprimiendo lib/, core/, cli/ en ps4cheater.zip",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.secondary
        )
    }
}

@Composable
fun DoneScreen(
    message: String,
    onHome: () -> Unit,
    onWebView: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            "¡Listo!",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.height(16.dp))

        // Status message
        Text(
            message,
            fontFamily = FontFamily.Monospace,
            fontSize = 12.sp
        )

        Spacer(Modifier.height(24.dp))

        // Termux commands card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    "Comandos para Termux:",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.height(8.dp))
                val commands = listOf(
                    "termux-setup-storage",
                    "unzip ~/storage/downloads/ps4cheater.zip -d ~/ps4cheater",
                    "cd ~/ps4cheater",
                    "pip install click rich prompt_toolkit",
                    "python cli/main.py connect <IP_PS4>"
                )
                commands.forEach { cmd ->
                    Text(
                        cmd,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.secondary
                    )
                    Spacer(Modifier.height(4.dp))
                }
            }
        }

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = onHome,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Volver al inicio")
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onWebView,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Abrir interfaz web")
        }
    }
}

@Composable
fun WebViewScreen(onBack: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Top bar with back button and title
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(onClick = onBack) {
                Text("← Volver", color = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.width(8.dp))
            Text(
                "Interfaz web",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary
            )
        }
        AndroidView(
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webViewClient = WebViewClient()
                    loadUrl("http://localhost:8080/")
                }
            },
            modifier = Modifier.fillMaxSize()
        )
    }
}

/**
 * Builds a zip from the bundled Python assets (lib/, core/, cli/) and writes it
 * to the public Downloads folder using the MediaStore API (API 29+) or a direct
 * File path on older Android versions. Returns a status string for the UI.
 */
fun extractPythonAssetsToDownloads(context: Context): String {
    return try {
        // 1. Build the zip into the app cache dir first
        val cacheZip = File(context.cacheDir, "ps4cheater.zip")
        ZipOutputStream(cacheZip.outputStream().buffered()).use { zos ->
            val dirs = listOf("lib", "core", "cli")
            for (dir in dirs) {
                val assetPath = "python/$dir"
                val files = context.assets.list(assetPath) ?: emptyArray()
                for (file in files) {
                    val entryPath = "$dir/$file"
                    zos.putNextEntry(ZipEntry(entryPath))
                    context.assets.open("$assetPath/$file").use { input ->
                        input.copyTo(zos)
                    }
                    zos.closeEntry()
                }
            }
        }

        val sizeBytes = cacheZip.length()
        val sizeKb = sizeBytes / 1024

        // 2. Publish the zip to the public Downloads folder
        val resolver = context.contentResolver
        val downloadedUri: Uri? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Android 10+: use MediaStore.Downloads with RELATIVE_PATH
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, "ps4cheater.zip")
                put(MediaStore.Downloads.MIME_TYPE, "application/zip")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            if (uri != null) {
                resolver.openOutputStream(uri)?.use { out ->
                    cacheZip.inputStream().use { input ->
                        input.copyTo(out)
                    }
                }
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            }
            uri
        } else {
            // Android 9 and below: write directly to the public Downloads directory
            val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!downloadsDir.exists()) downloadsDir.mkdirs()
            val targetFile = File(downloadsDir, "ps4cheater.zip")
            cacheZip.inputStream().use { input ->
                targetFile.outputStream().use { out ->
                    input.copyTo(out)
                }
            }
            Uri.fromFile(targetFile)
        }

        if (downloadedUri == null) {
            "Error: no se pudo crear ps4cheater.zip en Downloads (MediaStore devolvió null)"
        } else {
            "✓ ps4cheater.zip guardado en Downloads\n\n" +
                    "Tamaño: $sizeKb KB\n\n" +
                    "Ahora en Termux:\n" +
                    "termux-setup-storage\n" +
                    "unzip ~/storage/downloads/ps4cheater.zip -d ~/ps4cheater"
        }
    } catch (e: Exception) {
        "Error: ${e.message ?: e.toString()}"
    } finally {
        // Clean up the cached zip regardless of success/failure
        try {
            File(context.cacheDir, "ps4cheater.zip").delete()
        } catch (_: Exception) {
            // ignore cleanup errors
        }
    }
}
