package com.ps4cheater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.ps4cheater.data.MemoryRead
import com.ps4cheater.data.Ps4Repository
import kotlinx.coroutines.launch

/**
 * HexEditorScreen — manual memory read/write.
 *
 * Address + length fields, "Leer" button, hex dump display in monospace,
 * and a write section (hex bytes + "Escribir" button).
 *
 * State is held locally with [remember] + [rememberCoroutineScope] since
 * this screen has no dedicated ViewModel.
 */
@Composable
fun HexEditorScreen(
    navController: NavController,
    repository: Ps4Repository,
) {
    val scope = rememberCoroutineScope()
    var address by remember { mutableStateOf("0x10000000") }
    var length by remember { mutableStateOf("32") }
    var hexBytes by remember { mutableStateOf("") }
    var memory by remember { mutableStateOf<MemoryRead?>(null) }
    var loading by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }

    fun read() {
        if (loading) return
        val len = length.toIntOrNull() ?: 32
        loading = true
        message = "Leyendo $address ($len bytes)…"
        scope.launch {
            repository.readMemory(address, len)
                .onSuccess { mr ->
                    memory = mr
                    loading = false
                    message = "Leídos ${mr.length} bytes desde 0x${mr.address.toString(16).uppercase()}"
                }
                .onFailure { e ->
                    loading = false
                    message = "Error: ${e.message ?: "desconocido"}"
                }
        }
    }

    fun write() {
        if (loading || hexBytes.isBlank()) return
        loading = true
        message = "Escribiendo $hexBytes en $address…"
        scope.launch {
            repository.writeMemory(address, hexBytes)
                .onSuccess { n ->
                    loading = false
                    message = "Escritos $n bytes"
                    // Refresh the read view so the user sees the change.
                    read()
                }
                .onFailure { e ->
                    loading = false
                    message = "Error: ${e.message ?: "desconocido"}"
                }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = { navController.popBackStack() }) {
                Text("← Volver")
            }
        }

        Text(
            text = "Lectura/escritura de memoria",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )

        OutlinedTextField(
            value = address,
            onValueChange = { address = it },
            label = { Text("Dirección") },
            placeholder = { Text("0x10000000") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = length,
            onValueChange = { length = it.filter { c -> c.isDigit() } },
            label = { Text("Longitud") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { read() }, enabled = !loading) {
                Text("Leer")
            }
            if (loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp), strokeWidth = 2.dp)
            }
        }

        memory?.let { mr ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = "Hex dump @ 0x${mr.address.toString(16).uppercase()} (${mr.length} bytes)",
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = formatHexDump(mr),
                        fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }

        OutlinedTextField(
            value = hexBytes,
            onValueChange = { hexBytes = it },
            label = { Text("Bytes hex (escribir)") },
            placeholder = { Text("DEADBEEF") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = { write() },
            enabled = !loading && hexBytes.isNotBlank(),
        ) {
            Text("Escribir")
        }

        if (message.isNotEmpty()) {
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/**
 * Format a [MemoryRead] as a classic hex dump:
 *
 * ```
 * 0x00000000  DE AD BE EF  ...  |...|
 * 0x00000010  00 11 22 33  ...  |.."3|
 * ```
 *
 * The ASCII column is derived from the hex bytes directly so that
 * non-printable bytes are rendered as `.` regardless of what the
 * Python bridge returned in [MemoryRead.ascii].
 */
private fun formatHexDump(mr: MemoryRead): String {
    val hex = mr.hex.split(' ', '\n', '\t').filter { it.isNotEmpty() }
    if (hex.isEmpty()) return "(vacío)"
    val sb = StringBuilder()
    var addr = mr.address
    var i = 0
    while (i < hex.size) {
        val lineEnd = minOf(i + 16, hex.size)
        val lineBytes = hex.subList(i, lineEnd)
        val addrStr = "0x${addr.toString(16).padStart(8, '0').uppercase()}"
        val hexPart = lineBytes.joinToString(" ").padEnd(47, ' ')
        val asciiPart = lineBytes.joinToString("") { b ->
            try {
                val v = b.toInt(16)
                if (v in 32..126) v.toChar().toString() else "."
            } catch (e: NumberFormatException) {
                "."
            }
        }
        sb.append(addrStr).append("  ").append(hexPart).append("  |").append(asciiPart).append("|\n")
        addr += lineBytes.size
        i += 16
    }
    return sb.toString().trimEnd()
}
