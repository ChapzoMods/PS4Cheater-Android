package com.ps4cheater

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import android.webkit.WebView
import android.webkit.WebViewClient
import com.ps4cheater.ui.theme.PS4CheaterTheme
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PS4CheaterTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    AppContent(this)
                }
            }
        }
    }
}

@Composable
fun AppContent(context: Context) {
    var screen by remember { mutableStateOf("home") }
    var extractMsg by remember { mutableStateOf("") }

    when (screen) {
        "home" -> HomeScreen(
            onExtract = {
                extractMsg = extractPythonAssets(context)
                screen = "extracted"
            },
            onWebView = { screen = "webview" }
        )
        "webview" -> WebViewScreen()
        "extracted" -> ExtractedScreen(extractMsg, onBack = { screen = "home" })
    }
}

@Composable
fun HomeScreen(onExtract: () -> Unit, onWebView: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("PS4Cheater", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(8.dp))
        Text("Android Edition v1.0", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.secondary)
        Spacer(Modifier.height(24.dp))

        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Cómo usar esta app:", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(8.dp))
                Text("1. Instala Termux desde F-Droid", fontSize = 14.sp)
                Text("2. Pulsa \"Extraer scripts Python\" abajo", fontSize = 14.sp)
                Text("3. En Termux ejecuta:", fontSize = 14.sp)
                Text("   cd ~/ps4cheater && pip install click rich prompt_toolkit numpy flask", fontFamily = FontFamily.Monospace, fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
                Text("   python -m http.server 8080 &", fontFamily = FontFamily.Monospace, fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
                Text("   python cli/main.py connect <IP_PS4>", fontFamily = FontFamily.Monospace, fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
                Text("4. Vuelve a esta app y pulsa \"Abrir interfaz web\"", fontSize = 14.sp)
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(onClick = onExtract, modifier = Modifier.fillMaxWidth()) {
            Text("Extraer scripts Python a ~/ps4cheater/")
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = onWebView, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)) {
            Text("Abrir interfaz web (localhost:8080)")
        }
    }
}

@Composable
fun WebViewScreen() {
    Column(modifier = Modifier.fillMaxSize()) {
        Text("Interfaz web — localhost:8080", modifier = Modifier.padding(8.dp), color = MaterialTheme.colorScheme.primary)
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

@Composable
fun ExtractedScreen(msg: String, onBack: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Extracción completada", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(16.dp))
        Text(msg, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
        Spacer(Modifier.height(16.dp))
        Button(onClick = onBack) { Text("Volver") }
    }
}

fun extractPythonAssets(context: Context): String {
    val targetDir = File(context.getExternalFilesDir(null), "ps4cheater")
    val sb = StringBuilder()
    try {
        val assetManager = context.assets
        val dirs = listOf("lib", "core", "cli")
        for (dir in dirs) {
            val files = assetManager.list("python/$dir") ?: emptyArray()
            val destDir = File(targetDir, dir)
            destDir.mkdirs()
            for (file in files) {
                val input = assetManager.open("python/$dir/$file")
                val output = File(destDir, file)
                input.use { it.copyTo(output.outputStream()) }
                sb.appendLine("✓ $dir/$file")
            }
        }
        sb.appendLine("\nScripts extraídos en:")
        sb.appendLine(targetDir.absolutePath)
        sb.appendLine("\nCopia esta carpeta a Termux:")
        sb.appendLine("cp -r ${targetDir.absolutePath} ~/ps4cheater")
    } catch (e: Exception) {
        sb.appendLine("Error: ${e.message}")
    }
    return sb.toString()
}
