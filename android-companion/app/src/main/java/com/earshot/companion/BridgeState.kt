package com.earshot.companion

import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * Shared, observable state for the debug panel: bridge status and a log of
 * messages in and out. Everything is also written to logcat under the tag "Earshot".
 */
object BridgeState {
    const val TAG = "Earshot"
    private const val MAX_ENTRIES = 60

    data class Entry(val time: Long, val kind: String, val text: String)

    private val main = Handler(Looper.getMainLooper())
    private val entries = ArrayDeque<Entry>()
    private val listeners = mutableSetOf<() -> Unit>()

    @Volatile var serviceRunning = false
    @Volatile var bridgeStatus = "stopped"
    @Volatile var bridgeAddress = ""
    @Volatile var clients = 0
    @Volatile var ttsStatus = "not started"
    /** null = not known yet; false = Android refused audio (service was not started from the app screen). */
    @Volatile var audioAllowed: Boolean? = null
    @Volatile var typeScreenOpen = false
    @Volatile var lastIn: String? = null
    @Volatile var lastOut: String? = null

    /** kind: IN, OUT, SYS or ERR. */
    fun log(kind: String, text: String) {
        when (kind) {
            "ERR" -> Log.e(TAG, "$kind $text")
            else -> Log.i(TAG, "$kind $text")
        }
        if (kind == "IN") lastIn = text
        if (kind == "OUT") lastOut = text
        synchronized(entries) {
            entries.addFirst(Entry(System.currentTimeMillis(), kind, text))
            while (entries.size > MAX_ENTRIES) entries.removeLast()
        }
        changed()
    }

    fun snapshot(): List<Entry> = synchronized(entries) { entries.toList() }

    fun changed() {
        main.post { listeners.toList().forEach { it() } }
    }

    fun addListener(l: () -> Unit) { listeners += l }
    fun removeListener(l: () -> Unit) { listeners -= l }
}
