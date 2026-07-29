package com.ps4cheater.data

import com.google.gson.annotations.SerializedName

// ---------------------------------------------------------------------------
// Domain models (mapped from Python bridge dicts)
// ---------------------------------------------------------------------------

data class Status(
    val connected: Boolean = false,
    val ip: String = "",
    val port: Int = 0,
    val pid: Int = 0,
    val procName: String = "",
    val sectionCount: Int = 0,
    val resultCount: Int = 0,
    val cheatCount: Int = 0,
    val freezeRunning: Boolean = false,
)

data class ProcessInfo(
    val pid: Int,
    val name: String,
)

data class AttachResult(
    val name: String,
    val sectionCount: Int,
)

data class SectionInfo(
    val idx: Int,
    val name: String,
    val start: Long,
    val end: Long,
    val length: Long,
    val prot: Int,
    val protStr: String,
    val check: Boolean,
)

data class ScanResult(
    val address: Long,
    val value: String,
    val valueHex: String,
)

data class ScanResults(
    val results: List<ScanResult>,
    val total: Int,
    val valueType: String,
    val compareType: String,
)

data class MemoryRead(
    val address: Long,
    val length: Int,
    val hex: String,
    val ascii: String,
)

data class CheatEntry(
    val id: Int,
    val address: Long,
    val valueType: String,
    val value: String,
    val frozen: Boolean,
    val hexValue: Boolean,
    val description: String,
)

data class PointerPath(
    val baseAddress: Long,
    val offsets: List<Long>,
)

data class PointerScanResult(
    val paths: List<PointerPath>,
    val total: Int,
    val pointerCount: Int,
)
