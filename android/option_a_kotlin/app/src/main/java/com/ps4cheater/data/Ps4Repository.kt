package com.ps4cheater.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Ps4Repository — wrapper coroutine sobre PythonBridge.
 *
 * Todas las operaciones se ejecutan en Dispatchers.IO porque las llamadas
 * a Python (Chaquopy) son síncronas y bloqueantes.
 */
class Ps4Repository(private val bridge: PythonBridge) {

    suspend fun checkImports(): Boolean = withContext(Dispatchers.IO) {
        bridge.checkImports()
    }

    // ------------------------------------------------------------------
    // Connection
    // ------------------------------------------------------------------

    suspend fun connect(ip: String, port: Int): Result<String> = withContext(Dispatchers.IO) {
        bridge.connect(ip, port)
    }

    suspend fun disconnect(): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.disconnect()
    }

    suspend fun getStatus(): Status = withContext(Dispatchers.IO) {
        bridge.getStatus()
    }

    // ------------------------------------------------------------------
    // Processes
    // ------------------------------------------------------------------

    suspend fun getProcs(): Result<List<ProcessInfo>> = withContext(Dispatchers.IO) {
        bridge.getProcs()
    }

    suspend fun attach(pid: Int): Result<AttachResult> = withContext(Dispatchers.IO) {
        bridge.attach(pid)
    }

    // ------------------------------------------------------------------
    // Sections
    // ------------------------------------------------------------------

    suspend fun getSections(): Result<List<SectionInfo>> = withContext(Dispatchers.IO) {
        bridge.getSections()
    }

    suspend fun setSectionCheck(idx: Int, checked: Boolean): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.setSectionCheck(idx, checked)
    }

    suspend fun checkAllSections(mode: String): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.checkAllSections(mode)
    }

    // ------------------------------------------------------------------
    // Scan
    // ------------------------------------------------------------------

    suspend fun scanNew(
        valueType: String, compareType: String,
        value1: String, value2: String,
        hexFmt: Boolean = false, unaligned: Boolean = false, length: Int = 0,
    ): Result<Int> = withContext(Dispatchers.IO) {
        bridge.scanNew(valueType, compareType, value1, value2, hexFmt, unaligned, length)
    }

    suspend fun scanNext(compareType: String, value1: String, value2: String, hexFmt: Boolean = false): Result<Int> = withContext(Dispatchers.IO) {
        bridge.scanNext(compareType, value1, value2, hexFmt)
    }

    suspend fun getScanResults(limit: Int = 50): Result<ScanResults> = withContext(Dispatchers.IO) {
        bridge.getScanResults(limit)
    }

    // ------------------------------------------------------------------
    // Memory
    // ------------------------------------------------------------------

    suspend fun readMemory(address: String, length: Int): Result<MemoryRead> = withContext(Dispatchers.IO) {
        bridge.readMemory(address, length)
    }

    suspend fun writeMemory(address: String, hexBytes: String): Result<Int> = withContext(Dispatchers.IO) {
        bridge.writeMemory(address, hexBytes)
    }

    // ------------------------------------------------------------------
    // Cheats
    // ------------------------------------------------------------------

    suspend fun addCheat(
        address: String, valueType: String, value: String,
        description: String = "", frozen: Boolean = false, hexValue: Boolean = false,
    ): Result<Int> = withContext(Dispatchers.IO) {
        bridge.addCheat(address, valueType, value, description, frozen, hexValue)
    }

    suspend fun listCheats(): Result<List<CheatEntry>> = withContext(Dispatchers.IO) {
        bridge.listCheats()
    }

    suspend fun removeCheat(id: Int): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.removeCheat(id)
    }

    suspend fun setCheatFrozen(id: Int, frozen: Boolean): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.setCheatFrozen(id, frozen)
    }

    suspend fun applyCheat(id: Int): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.applyCheat(id)
    }

    suspend fun applyAllCheats(): Result<Int> = withContext(Dispatchers.IO) {
        bridge.applyAllCheats()
    }

    fun applyFrozen(): Result<Int> = bridge.applyFrozen()

    // ------------------------------------------------------------------
    // Freeze control
    // ------------------------------------------------------------------

    fun startFreeze(): Result<Unit> = bridge.startFreeze()
    fun stopFreeze(): Result<Unit> = bridge.stopFreeze()

    // ------------------------------------------------------------------
    // Misc
    // ------------------------------------------------------------------

    suspend fun notify(message: String, type: Int = 0): Result<Unit> = withContext(Dispatchers.IO) {
        bridge.notify(message, type)
    }

    suspend fun pointerScan(targetAddress: String, depth: Int = 3, maxRange: Long = 0x10000): Result<PointerScanResult> = withContext(Dispatchers.IO) {
        bridge.pointerScan(targetAddress, depth, maxRange)
    }
}
