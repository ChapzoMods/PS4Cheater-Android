package com.ps4cheater.ui.viewmodel

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ps4cheater.data.CheatEntry
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.service.FreezeService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * UI state for the CheatTable screen.
 */
data class CheatUiState(
    val cheats: List<CheatEntry> = emptyList(),
    val freezeRunning: Boolean = false,
    val message: String = "",
)

/**
 * CheatViewModel — manages the cheat table and freeze service.
 *
 * Exposes operations to add / remove / freeze / apply cheats, and to
 * start/stop the [FreezeService] foreground service.
 *
 * The [Context] needed for [FreezeService] is passed in from the
 * Composable via [startFreeze] / [stopFreeze].
 */
class CheatViewModel(
    private val repository: Ps4Repository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(CheatUiState())
    val uiState: StateFlow<CheatUiState> = _uiState.asStateFlow()

    init {
        loadCheats()
    }

    /** Refresh the cheat list from the bridge. */
    fun loadCheats() {
        viewModelScope.launch {
            repository.listCheats()
                .onSuccess { cheats ->
                    _uiState.update {
                        it.copy(cheats = cheats, message = "${cheats.size} cheats cargados")
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(message = "Error: ${e.message ?: "desconocido"}")
                    }
                }
        }
    }

    /** Add a new cheat entry. */
    fun addCheat(
        address: String,
        type: String,
        value: String,
        desc: String,
        frozen: Boolean,
    ) {
        viewModelScope.launch {
            repository.addCheat(address, type, value, desc, frozen)
                .onSuccess { id ->
                    _uiState.update { it.copy(message = "Cheat añadido (id=$id)") }
                    loadCheats()
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(message = "Error: ${e.message ?: "desconocido"}")
                    }
                }
        }
    }

    /** Remove a cheat by [id]. */
    fun removeCheat(id: Int) {
        viewModelScope.launch {
            repository.removeCheat(id)
                .onSuccess {
                    _uiState.update { it.copy(message = "Cheat eliminado (id=$id)") }
                    loadCheats()
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(message = "Error: ${e.message ?: "desconocido"}")
                    }
                }
        }
    }

    /** Toggle the frozen flag of a cheat by [id]. */
    fun toggleFrozen(id: Int, frozen: Boolean) {
        viewModelScope.launch {
            repository.setCheatFrozen(id, frozen)
                .onSuccess {
                    _uiState.update { state ->
                        state.copy(
                            cheats = state.cheats.map {
                                if (it.id == id) it.copy(frozen = frozen) else it
                            }
                        )
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(message = "Error: ${e.message ?: "desconocido"}")
                    }
                }
        }
    }

    /** Apply every cheat in the table. */
    fun applyAll() {
        viewModelScope.launch {
            repository.applyAllCheats()
                .onSuccess { applied ->
                    _uiState.update { it.copy(message = "Aplicados $applied cheats") }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(message = "Error: ${e.message ?: "desconocido"}")
                    }
                }
        }
    }

    /** Start the freeze foreground service. */
    fun startFreeze(context: Context) {
        try {
            FreezeService.start(context)
            _uiState.update {
                it.copy(freezeRunning = true, message = "Freeze loop iniciado")
            }
        } catch (e: Exception) {
            _uiState.update {
                it.copy(message = "Error iniciando freeze: ${e.message ?: "desconocido"}")
            }
        }
    }

    /** Stop the freeze foreground service. */
    fun stopFreeze(context: Context) {
        try {
            FreezeService.stop(context)
            _uiState.update {
                it.copy(freezeRunning = false, message = "Freeze loop detenido")
            }
        } catch (e: Exception) {
            _uiState.update {
                it.copy(message = "Error deteniendo freeze: ${e.message ?: "desconocido"}")
            }
        }
    }

    companion object {
        /** Factory that injects the shared [Ps4Repository] into the ViewModel. */
        fun factory(repository: Ps4Repository): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { CheatViewModel(repository) }
            }
    }
}
