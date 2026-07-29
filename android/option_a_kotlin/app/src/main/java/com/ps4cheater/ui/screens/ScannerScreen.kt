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
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.ui.navigation.Screen
import com.ps4cheater.ui.viewmodel.ScannerViewModel

private val VALUE_TYPES = listOf(
    "byte", "2 bytes", "4 bytes", "8 bytes", "float", "double", "string", "hex",
)

private val COMPARE_TYPES = listOf(
    "exact", "bigger than", "smaller than", "between",
    "changed", "unchanged", "increased", "decreased", "unknown",
)

/**
 * ScannerScreen — memory scanner.
 *
 * Two dropdowns (value type + compare type), two value fields
 * (value2 only visible when compareType == "between"), New/Next Scan
 * buttons, a "Marcar rw-only" button, results count and a LazyColumn
 * with up to 50 results. A bottom NavigationBar lets the user jump to
 * ProcessList / HexEditor / CheatTable screens.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScannerScreen(
    navController: NavController,
    repository: Ps4Repository,
) {
    val viewModel: ScannerViewModel = viewModel(factory = ScannerViewModel.factory(repository))
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    var valueType by remember { mutableStateOf("4 bytes") }
    var compareType by remember { mutableStateOf("exact") }
    var value1 by remember { mutableStateOf("") }
    var value2 by remember { mutableStateOf("") }
    var vTypeExpanded by remember { mutableStateOf(false) }
    var cTypeExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Escaneo de memoria",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )

        // Value type dropdown
        ExposedDropdownMenuBox(
            expanded = vTypeExpanded,
            onExpandedChange = { vTypeExpanded = !vTypeExpanded },
        ) {
            OutlinedTextField(
                value = valueType,
                onValueChange = {},
                readOnly = true,
                label = { Text("Tipo de valor") },
                trailingIcon = {
                    ExposedDropdownMenuDefaults.TrailingIcon(expanded = vTypeExpanded)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = vTypeExpanded,
                onDismissRequest = { vTypeExpanded = false },
            ) {
                VALUE_TYPES.forEach { t ->
                    DropdownMenuItem(
                        text = { Text(t) },
                        onClick = {
                            valueType = t
                            vTypeExpanded = false
                        },
                    )
                }
            }
        }

        // Compare type dropdown
        ExposedDropdownMenuBox(
            expanded = cTypeExpanded,
            onExpandedChange = { cTypeExpanded = !cTypeExpanded },
        ) {
            OutlinedTextField(
                value = compareType,
                onValueChange = {},
                readOnly = true,
                label = { Text("Tipo de comparación") },
                trailingIcon = {
                    ExposedDropdownMenuDefaults.TrailingIcon(expanded = cTypeExpanded)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = cTypeExpanded,
                onDismissRequest = { cTypeExpanded = false },
            ) {
                COMPARE_TYPES.forEach { t ->
                    DropdownMenuItem(
                        text = { Text(t) },
                        onClick = {
                            compareType = t
                            cTypeExpanded = false
                        },
                    )
                }
            }
        }

        OutlinedTextField(
            value = value1,
            onValueChange = { value1 = it },
            label = { Text("Valor 1") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (compareType == "between") {
            OutlinedTextField(
                value = value2,
                onValueChange = { value2 = it },
                label = { Text("Valor 2") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(
                onClick = { viewModel.scanNew(valueType, compareType, value1, value2) },
                enabled = !uiState.loading,
            ) {
                Text("New Scan")
            }
            Button(
                onClick = { viewModel.scanNext(compareType, value1, value2) },
                enabled = !uiState.loading,
            ) {
                Text("Next Scan")
            }
            OutlinedButton(
                onClick = { viewModel.checkAllRwOnly() },
                enabled = !uiState.loading,
            ) {
                Text("Marcar rw-only")
            }
            if (uiState.loading) {
                CircularProgressIndicator(modifier = Modifier.height(20.dp), strokeWidth = 2.dp)
            }
        }

        Text(
            text = "Resultados: ${uiState.resultCount}",
            fontWeight = FontWeight.SemiBold,
        )
        if (uiState.message.isNotEmpty()) {
            Text(
                text = uiState.message,
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            items(uiState.results.take(50), key = { it.address }) { result ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(8.dp),
                    ) {
                        Text(
                            text = "0x${result.address.toString(16).uppercase()}",
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            text = result.value,
                            fontFamily = FontFamily.Monospace,
                        )
                    }
                }
            }
        }

        NavigationBar {
            NavigationBarItem(
                selected = false,
                onClick = { navController.navigate(Screen.ProcessList.route) },
                icon = { Icon(Icons.Filled.List, contentDescription = "Procesos") },
                label = { Text("Procesos") },
            )
            NavigationBarItem(
                selected = false,
                onClick = { navController.navigate(Screen.HexEditor.route) },
                icon = { Icon(Icons.Filled.Memory, contentDescription = "Memoria") },
                label = { Text("Memoria") },
            )
            NavigationBarItem(
                selected = false,
                onClick = { navController.navigate(Screen.CheatTable.route) },
                icon = { Icon(Icons.Filled.Code, contentDescription = "Cheats") },
                label = { Text("Cheats") },
            )
        }
    }
}
