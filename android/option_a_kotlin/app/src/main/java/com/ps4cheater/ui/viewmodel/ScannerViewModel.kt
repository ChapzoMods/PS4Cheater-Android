package com.ps4cheater.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.data.ScanResult
import com.ps4cheater.data.SectionInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * UI state for the Scanner screen.
 */
data class ScannerUiState(
    val sections: List<SectionInfo> = emptyList(),
    val results: List<ScanResult> = emptyList(),
    val resultCount: Int = 0,
    val loading: Boolean = false,
    val message: String = "",
    val valueType: String = "4 bytes",
    val compareType: String = "exact",
)

/**
 * ScannerViewModel — manages memory scanning lifecycle.
 *
 * Holds the current section list, scan results and selected value/compare
 * types. All bridge calls run inside [viewModelScope] on Dispatchers.IO
 * (the repository takes care of the dispatcher).
 */
class ScannerViewModel(
    private val repository: Ps4Repository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ScannerUiState())
    val uiState: StateFlow<ScannerUiState> = _uiState.asStateFlow()

    init {
        loadSections()
    }

    /** Load sections from the attached process. */
    fun loadSections() {
        _uiState.update { it.copy(loading = true, message = "Cargando secciones…") }
        viewModelScope.launch {
            repository.getSections()
                .onSuccess { sections ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            sections = sections,
                            message = "${sections.size} secciones cargadas",
                        )
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            message = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Toggle the `check` flag of the section at [idx]. */
    fun toggleSection(idx: Int) {
        val current = _uiState.value.sections.firstOrNull { it.idx == idx } ?: return
        val newCheck = !current.check
        viewModelScope.launch {
            repository.setSectionCheck(idx, newCheck)
                .onSuccess {
                    _uiState.update { state ->
                        state.copy(
                            sections = state.sections.map {
                                if (it.idx == idx) it.copy(check = newCheck) else it
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

    /** Mark only the rw-only sections for scanning. */
    fun checkAllRwOnly() {
        _uiState.update { it.copy(loading = true, message = "Marcando secciones rw-only…") }
        viewModelScope.launch {
            repository.checkAllSections("rw_only")
                .onSuccess {
                    // reload sections to reflect the new flags
                    repository.getSections()
                        .onSuccess { sections ->
                            _uiState.update {
                                it.copy(
                                    loading = false,
                                    sections = sections,
                                    message = "Secciones rw-only marcadas (${sections.size})",
                                )
                            }
                        }
                        .onFailure { e ->
                            _uiState.update {
                                it.copy(
                                    loading = false,
                                    message = "Error: ${e.message ?: "desconocido"}",
                                )
                            }
                        }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            message = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Start a new scan with the given parameters. */
    fun scanNew(valueType: String, compareType: String, v1: String, v2: String) {
        _uiState.update {
            it.copy(
                loading = true,
                valueType = valueType,
                compareType = compareType,
                message = "Escaneando…",
            )
        }
        viewModelScope.launch {
            repository.scanNew(valueType, compareType, v1, v2)
                .onSuccess { count ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            resultCount = count,
                            message = "Nuevo scan: $count resultados",
                        )
                    }
                    loadResults()
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            message = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Refine the previous scan with the given parameters. */
    fun scanNext(compareType: String, v1: String, v2: String) {
        _uiState.update {
            it.copy(loading = true, message = "Refinando escaneo…", compareType = compareType)
        }
        viewModelScope.launch {
            repository.scanNext(compareType, v1, v2)
                .onSuccess { count ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            resultCount = count,
                            message = "Refinado: $count resultados",
                        )
                    }
                    loadResults()
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(
                            loading = false,
                            message = "Error: ${e.message ?: "desconocido"}",
                        )
                    }
                }
        }
    }

    /** Load up to 50 results from the current scan. */
    fun loadResults() {
        viewModelScope.launch {
            repository.getScanResults(50)
                .onSuccess { scanResults ->
                    _uiState.update {
                        it.copy(
                            results = scanResults.results,
                            resultCount = scanResults.total,
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

    companion object {
        /** Factory that injects the shared [Ps4Repository] into the ViewModel. */
        fun factory(repository: Ps4Repository): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { ScannerViewModel(repository) }
            }
    }
}
