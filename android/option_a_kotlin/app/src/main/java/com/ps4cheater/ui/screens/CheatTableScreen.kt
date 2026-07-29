package com.ps4cheater.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.ui.viewmodel.CheatViewModel

private val CHEAT_TYPES = listOf(
    "byte", "2 bytes", "4 bytes", "8 bytes", "float", "double", "string", "hex",
)

/**
 * CheatTableScreen — list, add, edit, freeze and apply cheats.
 *
 * Top card is the "add cheat" form (address, type dropdown, value,
 * description, frozen checkbox, "Añadir" button). Below it, action
 * buttons: "Aplicar todos" + "Start Freeze"/"Stop Freeze" toggle.
 * The list shows every cheat with a freeze checkbox and a delete
 * (trash) IconButton.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CheatTableScreen(
    navController: NavController,
    repository: Ps4Repository,
) {
    val context = LocalContext.current
    val viewModel: CheatViewModel = viewModel(factory = CheatViewModel.factory(repository))
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    var addr by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("4 bytes") }
    var value by remember { mutableStateOf("") }
    var desc by remember { mutableStateOf("") }
    var frozen by remember { mutableStateOf(false) }
    var typeExpanded by remember { mutableStateOf(false) }

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
        }

        Text(
            text = "Cheat Table",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )

        // ----- Add cheat card -----
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Column(
                modifier = Modifier.padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = addr,
                    onValueChange = { addr = it },
                    label = { Text("Dirección") },
                    placeholder = { Text("0x...") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                ExposedDropdownMenuBox(
                    expanded = typeExpanded,
                    onExpandedChange = { typeExpanded = !typeExpanded },
                ) {
                    OutlinedTextField(
                        value = type,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Tipo") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                    )
                    ExposedDropdownMenu(
                        expanded = typeExpanded,
                        onDismissRequest = { typeExpanded = false },
                    ) {
                        CHEAT_TYPES.forEach { t ->
                            DropdownMenuItem(
                                text = { Text(t) },
                                onClick = {
                                    type = t
                                    typeExpanded = false
                                },
                            )
                        }
                    }
                }

                OutlinedTextField(
                    value = value,
                    onValueChange = { value = it },
                    label = { Text("Valor") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = desc,
                    onValueChange = { desc = it },
                    label = { Text("Descripción") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = frozen, onCheckedChange = { frozen = it })
                    Text("Frozen")
                }

                Button(
                    onClick = {
                        viewModel.addCheat(addr, type, value, desc, frozen)
                        addr = ""
                        value = ""
                        desc = ""
                        frozen = false
                    },
                    enabled = addr.isNotBlank() && value.isNotBlank(),
                ) {
                    Text("Añadir")
                }
            }
        }

        // ----- Action buttons -----
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.applyAll() }) {
                Text("Aplicar todos")
            }
            if (uiState.freezeRunning) {
                OutlinedButton(onClick = { viewModel.stopFreeze(context) }) {
                    Text("Stop Freeze")
                }
            } else {
                OutlinedButton(onClick = { viewModel.startFreeze(context) }) {
                    Text("Start Freeze")
                }
            }
        }

        if (uiState.message.isNotEmpty()) {
            Text(
                text = uiState.message,
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        // ----- Cheat list -----
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(uiState.cheats, key = { it.id }) { cheat ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "#${cheat.id}  0x${cheat.address.toString(16).uppercase()}",
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.weight(1f),
                            )
                            Checkbox(
                                checked = cheat.frozen,
                                onCheckedChange = { viewModel.toggleFrozen(cheat.id, it) },
                            )
                            IconButton(onClick = { viewModel.removeCheat(cheat.id) }) {
                                Icon(Icons.Filled.Delete, contentDescription = "Eliminar")
                            }
                        }
                        Text(
                            text = "Tipo: ${cheat.valueType}   Valor: ${cheat.value}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        if (cheat.description.isNotEmpty()) {
                            Text(
                                text = cheat.description,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(0.dp))
    }
}
