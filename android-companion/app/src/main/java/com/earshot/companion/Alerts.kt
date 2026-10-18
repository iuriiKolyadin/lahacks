package com.earshot.companion

import org.json.JSONObject

/** A sound the glasses are flashing, from an "alert" frame. Format: docs/BRIDGE.md. */
data class Alert(
    val id: String,
    val label: String,
    /** What to call it on screen, e.g. "Doorbell". */
    val title: String,
    /** left, right, front, behind, center (ahead or behind) or near (unknown). */
    val dir: String,
    /** critical or medium: the tiers that keep flashing on the glasses. */
    val tier: String,
) {
    val critical get() = tier == "critical"

    /** Where it came from, as words; empty when the glasses could not tell. */
    val where: String get() = when (dir) {
        "left" -> "On your left"
        "right" -> "On your right"
        "front" -> "In front of you"
        "behind" -> "Behind you"
        "center" -> "Ahead of or behind you"
        else -> ""
    }

    companion object {
        /** Used when the frame has no "text". Matches LABEL_NAMES in plugin/src/settings.ts. */
        private val NAMES = mapOf(
            "alarm" to "Smoke / fire alarm", "siren" to "Siren", "name" to "Someone said your name",
            "doorbell" to "Doorbell", "knock" to "Knock", "horn" to "Car horn", "dog" to "Dog bark",
            "clap" to "Clapping", "snap" to "Finger snap", "speech" to "Someone talking",
        )

        fun from(msg: JSONObject): Alert {
            val label = msg.optString("label").ifEmpty { "sound" }
            return Alert(
                id = msg.optString("id").ifEmpty { "alert" },
                label = label,
                title = msg.optString("text").ifEmpty { NAMES[label] ?: label.replaceFirstChar { it.uppercase() } },
                dir = msg.optString("dir").ifEmpty { "near" },
                tier = msg.optString("tier").ifEmpty { "critical" },
            )
        }
    }
}

/** The alert the phone is showing. Written by BridgeService on the main thread; read by AlertActivity. */
object Alerts {
    /** The sound happening now, or null. */
    @Volatile var active: Alert? = null
    /** The newest alert. Still set after it ends, so the alert screen can say it stopped. */
    @Volatile var latest: Alert? = null
    /** Dismissed on the phone: its 5 s refreshes do not ring again. */
    @Volatile var dismissedId: String? = null
}
