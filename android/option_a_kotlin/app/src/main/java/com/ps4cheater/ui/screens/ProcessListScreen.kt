package com.ps4cheater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.ps4cheater.data.AttachResult
import com.ps4cheater.data.ProcessInfo
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.ui.navigation.Screen
import kotlinx.coroutines.launch

/**
 * ProcessListScreen — lists the running processes on the PS4 and lets
 * the user attach to one. On success, shows a "Ir a Scanner →" button.
 *
 * State is held locally with [remember] + [rememberCoroutineScope] since
 * this screen has no dedicated ViewModel.
 */
@Composable
fun ProcessListScreen(
    navController: NavController,
    repository: Ps4Repository,
) {
    val scope = rememberCoroutineScope()
    var procs by remember { mutableStateOf<List<ProcessInfo>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Pulsa Refrescar para listar procesos") }
    var attached by remember { mutableStateOf<AttachResult?>(null) }

    fun refresh() {
        if (loading) return
        loading = true
        message = "Cargando procesos…"
        scope.launch {
            repository.getProcs()
                .onSuccess { list ->
                    procs = list
                    loading = false
                    message = "${list.size} procesos"
                }
                .onFailure { e ->
                    loading = false
                    message = "Error: ${e.message ?: "desconocido"}"
                }
        }
    }

    fun attach(pid: Int) {
        if (loading) return
        loading = true
        message = "Attaching pid=$pid…"
        scope.launch {
            repository.attach(pid)
                .onSuccess { result ->
                    attached = result
                    loading = false
                    message = "Attached: ${result.name} (${result.sectionCount} secciones)"
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
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = { navController.popBackStack() }) {
                Text("← Volver")
            }
            Spacer(modifier = Modifier.width(16.dp))
            Text(
                text = "Procesos",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = { refresh() }, enabled = !loading) {
                Text("Refrescar")
            }
            if (loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp), strokeWidth = 2.dp)
            }
        }

        Text(text = message, style = MaterialTheme.typography.bodyLarge)

        attached?.let { att ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text("Attach: ${att.name}", fontWeight = FontWeight.SemiBold)
                    Text("${att.sectionCount} secciones")
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(onClick = { navController.navigate(Screen.Scanner.route) }) {
                        Text("Ir a Scanner →")
                    }
                }
            }
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(procs, key = { it.pid }) { proc ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(text = proc.name, fontWeight = FontWeight.SemiBold)
                            Text(
                                text = "PID: ${proc.pid}",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                        Button(onClick = { attach(proc.pid) }, enabled = !loading) {
                            Text("Attach")
                        }
                    }
                }
            }
        }
    }
}
