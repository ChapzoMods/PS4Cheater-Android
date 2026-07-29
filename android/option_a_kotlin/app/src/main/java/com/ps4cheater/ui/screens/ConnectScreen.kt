package com.ps4cheater.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.ui.navigation.Screen
import com.ps4cheater.ui.viewmodel.ConnectionViewModel

/**
 * ConnectScreen — initial screen.
 *
 * Lets the user enter the PS4 IP/port, choose between ps4debug (744)
 * and GoldHEN (9090) presets, and connect/disconnect. When connected,
 * shows buttons to navigate to the Process list, Memory editor and
 * Cheat table.
 */
@Composable
fun ConnectScreen(
    navController: NavController,
    repository: Ps4Repository,
) {
    val viewModel: ConnectionViewModel =
        viewModel(factory = ConnectionViewModel.factory(repository))
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    var ip by remember { mutableStateOf("192.168.1.100") }
    var port by remember { mutableStateOf("744") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = "PS4Cheater",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        // Status indicator (green/red dot)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(if (uiState.connected) Color(0xFF4CAF50) else Color(0xFFF44336))
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = if (uiState.connected) "Conectado" else "Desconectado",
                style = MaterialTheme.typography.bodyLarge,
            )
        }

        OutlinedTextField(
            value = ip,
            onValueChange = { ip = it },
            label = { Text("IP de la PS4") },
            placeholder = { Text("192.168.1.100") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = port,
            onValueChange = { port = it.filter { c -> c.isDigit() } },
            label = { Text("Puerto") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { port = "744" }) {
                Text("ps4debug (744)")
            }
            OutlinedButton(onClick = { port = "9090" }) {
                Text("GoldHEN (9090)")
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(
                onClick = { viewModel.connect(ip, port.toIntOrNull() ?: 744) },
                enabled = !uiState.loading,
            ) {
                Text("Conectar")
            }
            OutlinedButton(
                onClick = { viewModel.disconnect() },
                enabled = uiState.connected && !uiState.loading,
            ) {
                Text("Desconectar")
            }
            if (uiState.loading) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Text(
                text = uiState.status,
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodyLarge,
            )
        }

        if (uiState.connected) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { navController.navigate(Screen.ProcessList.route) }) {
                    Text("Continuar →")
                }
                OutlinedButton(onClick = { navController.navigate(Screen.HexEditor.route) }) {
                    Text("Memoria")
                }
                OutlinedButton(onClick = { navController.navigate(Screen.CheatTable.route) }) {
                    Text("Cheats")
                }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
