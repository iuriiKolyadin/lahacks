package com.earshot.companion

import android.content.Context

/** A reply the wearer can pick on the glasses. The id is what goes over the bridge; the text is editable. */
data class Phrase(
    val id: String,
    val label: String,
    val defaultText: String,
    val opensTypeScreen: Boolean,
)

object Phrases {
    val ALL = listOf(
        Phrase("type_it", "Please type", "Hi, I'm Deaf. Could you type what you said on my phone?", opensTypeScreen = true),
        Phrase("repeat", "Repeat", "Sorry, could you repeat that while facing me?", opensTypeScreen = false),
        Phrase("thanks", "Thanks", "Thank you!", opensTypeScreen = false),
    )

    /** Other names accepted over the bridge, including the ids from PLAN.md section 3. */
    private val ALIASES = mapOf(
        "deaf_intro" to "type_it",
        "type" to "type_it",
        "please_type" to "type_it",
        "thank_you" to "thanks",
        "1" to "type_it",
        "2" to "repeat",
        "3" to "thanks",
    )

    fun resolve(raw: String?): Phrase? {
        val key = raw?.trim()?.lowercase() ?: return null
        val id = ALIASES[key] ?: key
        return ALL.firstOrNull { it.id == id }
    }
}

/** Everything the user can configure, stored in SharedPreferences. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("earshot", Context.MODE_PRIVATE)

    /**
     * "server": the phone hosts the WebSocket server. "relay": the phone connects out to a
     * laptop: tools/relay.mjs, or the Cue server's /ws/pendant (which also sends sound alerts).
     */
    var mode: String
        get() = sp.getString("mode", MODE_SERVER) ?: MODE_SERVER
        set(v) = sp.edit().putString("mode", v).apply()

    /** 127.0.0.1 = only apps on this phone can connect. 0.0.0.0 = anything on the Wi-Fi can connect. */
    var bindHost: String
        get() = sp.getString("bind_host", "127.0.0.1") ?: "127.0.0.1"
        set(v) = sp.edit().putString("bind_host", v).apply()

    var port: Int
        get() = sp.getInt("port", DEFAULT_PORT)
        set(v) = sp.edit().putInt("port", v).apply()

    var relayUrl: String
        get() = sp.getString("relay_url", "ws://192.168.1.10:8787/phone") ?: ""
        set(v) = sp.edit().putString("relay_url", v).apply()

    /** Ring like an incoming call when the glasses flash an alert. */
    var alertsEnabled: Boolean
        get() = sp.getBoolean("alerts_enabled", true)
        set(v) = sp.edit().putBoolean("alerts_enabled", v).apply()

    fun phraseText(p: Phrase): String = sp.getString("phrase_${p.id}", null) ?: p.defaultText

    fun setPhraseText(p: Phrase, text: String) {
        val t = text.trim()
        if (t.isEmpty() || t == p.defaultText) sp.edit().remove("phrase_${p.id}").apply()
        else sp.edit().putString("phrase_${p.id}", t).apply()
    }

    companion object {
        const val MODE_SERVER = "server"
        const val MODE_RELAY = "relay"
        const val DEFAULT_PORT = 8765
    }
}
