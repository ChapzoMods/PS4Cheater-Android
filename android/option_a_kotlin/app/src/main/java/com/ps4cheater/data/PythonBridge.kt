package com.ps4cheater.data

import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.PyException
import com.chaquo.python.PyObject
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * PythonBridge — puente entre Kotlin y el módulo Python `chaquopy_bridge`.
 *
 * Usa Chaquopy para invocar funciones Python. Todas las llamadas son síncronas
 * y DEBEN ejecutarse fuera del hilo principal (usar Dispatchers.IO).
 *
 * Cada función Python devuelve un dict con {"ok": true/false, ...}.
 * Si ocurre una excepción en Python, se propaga como PyException.
 */
class PythonBridge {

    companion object {
        private const val TAG = "PythonBridge"
        private const val MODULE = "chaquopy_bridge"
    }

    private val py: Python get() = Python.getInstance()
    private val module: PyObject get() = py.getModule(MODULE)

    // ------------------------------------------------------------------
    // Helper: llama una función Python y devuelve su dict resultado
    // ------------------------------------------------------------------

    private fun call(fn: String, vararg args: Any?): PyObject {
        return module.callAttr(fn, *args)
    }

    private fun callStr(fn: String, vararg args: Any?): String {
        return call(fn, *args).toString()
    }

    // ------------------------------------------------------------------
    // Import check
    // ------------------------------------------------------------------

    fun checkImports(): Boolean {
        return try {
            val result = call("check_imports").asMap()
            result["ok"]?.toString() == "True"
        } catch (e: Exception) {
            Log.e(TAG, "checkImports failed", e)
            false
        }
    }

    // ------------------------------------------------------------------
    // Connection
    // ------------------------------------------------------------------

    fun connect(ip: String, port: Int): Result<String> = try {
        val result = call("connect", ip, port).asMap()
        if (result["ok"]?.toString() == "True") {
            Result.success(result["version"]?.toString() ?: "")
        } else {
            Result.failure(Exception(result["error"]?.toString() ?: "unknown error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun disconnect(): Result<Unit> = try {
        call("disconnect")
        Result.success(Unit)
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun getStatus(): Status = try {
        val m = call("get_status").asMap()
        Status(
            connected = m["connected"]?.toString() == "True",
            ip = m["ip"]?.toString() ?: "",
            port = (m["port"]?.toString() ?: "0").toIntOrNull() ?: 0,
            pid = (m["pid"]?.toString() ?: "0").toIntOrNull() ?: 0,
            procName = m["proc_name"]?.toString() ?: "",
            sectionCount = (m["section_count"]?.toString() ?: "0").toIntOrNull() ?: 0,
            resultCount = (m["result_count"]?.toString() ?: "0").toIntOrNull() ?: 0,
            cheatCount = (m["cheat_count"]?.toString() ?: "0").toIntOrNull() ?: 0,
            freezeRunning = m["freeze_running"]?.toString() == "True",
        )
    } catch (e: Exception) {
        Log.e(TAG, "getStatus failed", e)
        Status()
    }

    // ------------------------------------------------------------------
    // Processes
    // ------------------------------------------------------------------

    fun getProcs(): Result<List<ProcessInfo>> = try {
        val m = call("get_procs").asMap()
        if (m["ok"]?.toString() == "True") {
            val procs = (m["procs"] as? PyObject)?.asList()?.map { item ->
                val p = item.asMap()
                ProcessInfo(
                    pid = (p["pid"]?.toString() ?: "0").toIntOrNull() ?: 0,
                    name = p["name"]?.toString() ?: "",
                )
            } ?: emptyList()
            Result.success(procs)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "unknown error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun attach(pid: Int): Result<AttachResult> = try {
        val m = call("attach", pid).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success(AttachResult(
                name = m["name"]?.toString() ?: "",
                sectionCount = (m["section_count"]?.toString() ?: "0").toIntOrNull() ?: 0,
            ))
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "unknown error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    // ------------------------------------------------------------------
    // Sections
    // ------------------------------------------------------------------

    fun getSections(): Result<List<SectionInfo>> = try {
        val m = call("get_sections").asMap()
        if (m["ok"]?.toString() == "True") {
            val sections = (m["sections"] as? PyObject)?.asList()?.map { item ->
                val s = item.asMap()
                SectionInfo(
                    idx = (s["idx"]?.toString() ?: "0").toIntOrNull() ?: 0,
                    name = s["name"]?.toString() ?: "",
                    start = (s["start"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    end = (s["end"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    length = (s["length"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    prot = (s["prot"]?.toString() ?: "0").toIntOrNull() ?: 0,
                    protStr = s["prot_str"]?.toString() ?: "---",
                    check = s["check"]?.toString() == "True",
                )
            } ?: emptyList()
            Result.success(sections)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "unknown error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun setSectionCheck(idx: Int, checked: Boolean): Result<Unit> = try {
        val m = call("set_section_check", idx, checked).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun checkAllSections(mode: String): Result<Unit> = try {
        val m = call("check_all_sections", mode).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    // ------------------------------------------------------------------
    // Scan
    // ------------------------------------------------------------------

    fun scanNew(
        valueType: String, compareType: String,
        value1: String, value2: String,
        hexFmt: Boolean = false, unaligned: Boolean = false, length: Int = 0,
    ): Result<Int> = try {
        val m = call("scan_new", valueType, compareType, value1, value2, hexFmt, unaligned, length).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["count"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun scanNext(compareType: String, value1: String, value2: String, hexFmt: Boolean = false): Result<Int> = try {
        val m = call("scan_next", compareType, value1, value2, hexFmt).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["count"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun getScanResults(limit: Int = 50): Result<ScanResults> = try {
        val m = call("get_scan_results", limit).asMap()
        if (m["ok"]?.toString() == "True") {
            val results = (m["results"] as? PyObject)?.asList()?.map { item ->
                val r = item.asMap()
                ScanResult(
                    address = (r["address"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    value = r["value"]?.toString() ?: "",
                    valueHex = r["value_hex"]?.toString() ?: "",
                )
            } ?: emptyList()
            Result.success(ScanResults(
                results = results,
                total = (m["total"]?.toString() ?: "0").toIntOrNull() ?: 0,
                valueType = m["value_type"]?.toString() ?: "",
                compareType = m["compare_type"]?.toString() ?: "",
            ))
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    // ------------------------------------------------------------------
    // Memory read/write
    // ------------------------------------------------------------------

    fun readMemory(address: String, length: Int): Result<MemoryRead> = try {
        val m = call("read_memory", address, length).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success(MemoryRead(
                address = (m["address"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                length = (m["length"]?.toString() ?: "0").toIntOrNull() ?: 0,
                hex = m["hex"]?.toString() ?: "",
                ascii = m["ascii"]?.toString() ?: "",
            ))
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun writeMemory(address: String, hexBytes: String): Result<Int> = try {
        val m = call("write_memory", address, hexBytes).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["written"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    // ------------------------------------------------------------------
    // Cheats
    // ------------------------------------------------------------------

    fun addCheat(
        address: String, valueType: String, value: String,
        description: String = "", frozen: Boolean = false, hexValue: Boolean = false,
    ): Result<Int> = try {
        val m = call("add_cheat", address, valueType, value, description, frozen, hexValue).asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["id"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun listCheats(): Result<List<CheatEntry>> = try {
        val m = call("list_cheats").asMap()
        if (m["ok"]?.toString() == "True") {
            val cheats = (m["cheats"] as? PyObject)?.asList()?.map { item ->
                val c = item.asMap()
                CheatEntry(
                    id = (c["id"]?.toString() ?: "0").toIntOrNull() ?: 0,
                    address = (c["address"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    valueType = c["value_type"]?.toString() ?: "",
                    value = c["value"]?.toString() ?: "",
                    frozen = c["frozen"]?.toString() == "True",
                    hexValue = c["hex_value"]?.toString() == "True",
                    description = c["description"]?.toString() ?: "",
                )
            } ?: emptyList()
            Result.success(cheats)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun removeCheat(id: Int): Result<Unit> = try {
        val m = call("remove_cheat", id).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun setCheatFrozen(id: Int, frozen: Boolean): Result<Unit> = try {
        val m = call("set_cheat_frozen", id, frozen).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun applyCheat(id: Int): Result<Unit> = try {
        val m = call("apply_cheat", id).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun applyAllCheats(): Result<Int> = try {
        val m = call("apply_all_cheats").asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["applied"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun applyFrozen(): Result<Int> = try {
        val m = call("apply_frozen").asMap()
        if (m["ok"]?.toString() == "True") {
            Result.success((m["applied"]?.toString() ?: "0").toIntOrNull() ?: 0)
        } else {
            Result.success(0)  // no error, just 0 applied
        }
    } catch (e: PyException) {
        Result.success(0)  // don't crash the freeze loop
    }

    // ------------------------------------------------------------------
    // Freeze control
    // ------------------------------------------------------------------

    fun startFreeze(): Result<Unit> = try {
        call("start_freeze")
        Result.success(Unit)
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun stopFreeze(): Result<Unit> = try {
        call("stop_freeze")
        Result.success(Unit)
    } catch (e: PyException) {
        Result.failure(e)
    }

    // ------------------------------------------------------------------
    // Misc
    // ------------------------------------------------------------------

    fun notify(message: String, type: Int = 0): Result<Unit> = try {
        val m = call("notify", message, type).asMap()
        if (m["ok"]?.toString() == "True") Result.success(Unit)
        else Result.failure(Exception(m["error"]?.toString() ?: "error"))
    } catch (e: PyException) {
        Result.failure(e)
    }

    fun pointerScan(targetAddress: String, depth: Int = 3, maxRange: Long = 0x10000): Result<PointerScanResult> = try {
        val m = call("pointer_scan", targetAddress, depth, maxRange).asMap()
        if (m["ok"]?.toString() == "True") {
            val paths = (m["paths"] as? PyObject)?.asList()?.map { item ->
                val p = item.asMap()
                PointerPath(
                    baseAddress = (p["base_address"]?.toString() ?: "0").toLongOrNull() ?: 0L,
                    offsets = (p["offsets"] as? PyObject)?.asList()?.map {
                        (it.toString()).toLongOrNull() ?: 0L
                    } ?: emptyList(),
                )
            } ?: emptyList()
            Result.success(PointerScanResult(
                paths = paths,
                total = (m["total"]?.toString() ?: "0").toIntOrNull() ?: 0,
                pointerCount = (m["pointer_count"]?.toString() ?: "0").toIntOrNull() ?: 0,
            ))
        } else {
            Result.failure(Exception(m["error"]?.toString() ?: "error"))
        }
    } catch (e: PyException) {
        Result.failure(e)
    }
}
