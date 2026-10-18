package com.earshot.companion

import org.json.JSONArray
import org.json.JSONObject

/** Builders for outgoing bridge messages. The format is documented in docs/BRIDGE.md. */
object Protocol {
    const val VERSION = 1

    private fun msg(type: String) = JSONObject().put("v", VERSION).put("type", type)

    fun pong(ref: String?, echoTs: Any?) = msg("pong").apply {
        if (ref != null) put("ref", ref)
        if (echoTs != null) put("echo_ts", echoTs)
        put("ts", System.currentTimeMillis())
    }

    fun ack(ref: String?, what: String) = msg("ack").apply {
        if (ref != null) put("ref", ref)
        put("ok", true)
        put("what", what)
    }

    fun spoken(ref: String?, reply: String?) = msg("spoken").apply {
        if (ref != null) put("ref", ref)
        if (reply != null) put("reply", reply)
    }

    fun error(ref: String?, code: String, message: String) = msg("error").apply {
        if (ref != null) put("ref", ref)
        put("code", code)
        put("message", message)
    }

    fun typedText(id: String, text: String) = msg("typed_text")
        .put("id", id).put("text", text).put("ts", System.currentTimeMillis())

    fun typing(text: String) = msg("typing").put("text", text)

    fun welcome(prefs: Prefs, status: JSONObject) = msg("welcome").apply {
        put("app", "earshot-companion")
        put("app_version", BuildConfig.VERSION_NAME)
        put("protocol", VERSION)
        put("replies", JSONArray().apply {
            Phrases.ALL.forEach { p ->
                put(JSONObject()
                    .put("id", p.id)
                    .put("label", p.label)
                    .put("text", prefs.phraseText(p))
                    .put("opens_type_screen", p.opensTypeScreen))
            }
        })
        put("status", status)
    }

    fun status() = msg("status").apply {
        put("tts", if (BridgeState.ttsStatus.startsWith("ready")) "ready" else BridgeState.ttsStatus)
        put("audio_allowed", BridgeState.audioAllowed ?: JSONObject.NULL)
        put("type_screen", if (BridgeState.typeScreenOpen) "open" else "closed")
        put("clients", BridgeState.clients)
    }
}
