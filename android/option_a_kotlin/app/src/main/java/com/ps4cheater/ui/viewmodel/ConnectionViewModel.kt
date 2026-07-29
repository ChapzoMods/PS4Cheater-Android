package com.ps4cheater.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ps4cheater.data.Ps4Repository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * UI state for the Connect screen.
 */
data class ConnectionUiState(
    val connected: Boolean = false,
    val ip: String = "",
    val port: Int = 0,
    val pid: Int = 0,
    val procName: String = "",
    val status: String = "Desconectado",
    val loading: Boolean = false,
)

/**
 * ConnectionViewModel — manages PS4 connection lifecycle.
 *
 * Exposes a [ConnectionUiState] via [uiState] and exposes
 * [connect], [disconnect] and [refreshStatus] for the UI to call.
 * All bridge calls run inside [viewModelScope] on Dispatchers.IO
 * (the repository takes care of the dispatcher).
 */
class ConnectionViewModel(
    private val repository: Ps4Repository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ConnectionUiState())
    val uiState: StateFlow<ConnectionUiState> = _uiState.asStateFlow()

    init {
        // Sync with the bridge's current status (e.g. on app cold start).
        refreshStatus()
    }

    /** Connect to the PS4 at [ip]:[port]. */
    fun connect(ip: String, port: Int) {
        if (_uiState.value.loading) return
        _uiState.update {
            it.copy(loading = true, status = "Conectando a $ip:$port…")
        }
        viewModelScope.launch {
            repository.connect(ip, port)
                .onSuccess { version ->
                    val status = repository.getStatus()
                    _uiState.update {
                        it.copy(
                            loading = false,
                            connected = status.connected,
                            ip = status.ip,
                            port = status.port,
                            pid = status.pid,
                            procName = status.procName,
                            status = "Conectado a ${status.ip}:${status.port}" +
                                if (version.isNotBlank()) " (versión $version)" else "",
                        )
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            status = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Disconnect from the PS4. */
    fun disconnect() {
        if (_uiState.value.loading) return
        _uiState.update { it.copy(loading = true, status = "Desconectando…") }
        viewModelScope.launch {
            repository.disconnect()
                .onSuccess {
                    _uiState.update {
                        it.copy(
                            loading = false,
                            connected = false,
                            ip = "",
                            port = 0,
                            pid = 0,
                            procName = "",
                            status = "Desconectado",
                        )
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            status = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Refresh the cached status from the bridge. */
    fun refreshStatus() {
        viewModelScope.launch {
            val status = repository.getStatus()
            _uiState.update {
                it.copy(
                    connected = status.connected,
                    ip = status.ip,
                    port = status.port,
                    pid = status.pid,
                    procName = status.procName,
                )
            }
        }
    }

    companion object {
        /** Factory that injects the shared [Ps4Repository] into the ViewModel. */
        fun factory(repository: Ps4Repository): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { ConnectionViewModel(repository) }
            }
    }
}
