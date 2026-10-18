package com.earshot.companion

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.io.File
import java.util.Locale
import kotlin.math.ceil

/**
 * Speaks phrases out loud. For instant playback, each configured phrase is
 * rendered to a WAV file once with TextToSpeech, then kept in a prepared
 * MediaPlayer. Any other text goes straight to TextToSpeech.
 */
class Speaker(private val context: Context, private val onChange: () -> Unit) : TextToSpeech.OnInitListener {
    private val main = Handler(Looper.getMainLooper())
    private val audio = context.getSystemService(AudioManager::class.java)
    private val attrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()
    private val focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
        .setAudioAttributes(attrs)
        .build()

    private val tts = TextToSpeech(context, this)
    private var ready = false
    private var wanted: List<Pair<String, String>> = emptyList()

    /** phrase id -> (text it was rendered from, prepared player) */
    private val players = HashMap<String, Pair<String, MediaPlayer>>()
    /** utterance id -> render job */
    private val renders = HashMap<String, Triple<String, String, File>>()
    /** utterance id -> callback when speech finishes */
    private val doneCallbacks = HashMap<String, () -> Unit>()
    private var current: MediaPlayer? = null
    private var counter = 0

    var volumePercent = 100

    init {
        BridgeState.ttsStatus = "starting"
    }

    override fun onInit(status: Int) {
        main.post {
            if (status != TextToSpeech.SUCCESS) {
                BridgeState.ttsStatus = "failed to start (code $status)"
                BridgeState.log("ERR", "TextToSpeech failed to start: $status")
                onChange(); return@post
            }
            tts.setAudioAttributes(attrs)
            val lang = tts.setLanguage(Locale.US)
            tts.setOnUtteranceProgressListener(progress)
            ready = true
            BridgeState.ttsStatus = if (lang < 0) "ready (US English voice missing)" else "ready"
            BridgeState.log("SYS", "TTS ${BridgeState.ttsStatus}, engine ${tts.defaultEngine}")
            prepare(wanted)
            onChange()
        }
    }

    /** Pre-render these (id, text) phrases so they play instantly. Safe to call again when texts change. */
    fun prepare(phrases: List<Pair<String, String>>) {
        wanted = phrases
        if (!ready) return
        for ((id, text) in phrases) {
            if (players[id]?.first == text) continue
            val file = File(context.cacheDir, "phrase_${id}_${Integer.toHexString(text.hashCode())}.wav")
            if (file.exists() && file.length() > 1000) {
                load(id, text, file)
            } else {
                val uid = "render:$id:${SystemClock.uptimeMillis()}"
                renders[uid] = Triple(id, text, file)
                tts.synthesizeToFile(text, Bundle(), file, uid)
            }
        }
    }

    private fun load(id: String, text: String, file: File) {
        try {
            val mp = MediaPlayer().apply {
                setAudioAttributes(attrs)
                setDataSource(file.absolutePath)
                prepare()
            }
            players.put(id, text to mp)?.second?.release()
            // Remove stale renders of this phrase.
            context.cacheDir.listFiles { f -> f.name.startsWith("phrase_${id}_") && f != file }?.forEach { it.delete() }
            BridgeState.log("SYS", "pre-rendered '$id' (${mp.duration} ms)")
        } catch (e: Exception) {
            BridgeState.log("ERR", "could not load rendered '$id': ${e.message}")
        }
    }

    /**
     * Speak [text]. If [id] names a pre-rendered phrase with the same text, plays the
     * rendered file (instant); otherwise uses TextToSpeech. [onDone] runs on the main thread.
     */
    fun speak(id: String?, text: String, onDone: () -> Unit = {}) {
        stopCurrent()
        raiseVolume()
        requestFocus()
        val player = id?.let { players[it] }?.takeIf { it.first == text }?.second
        if (player != null) {
            current = player
            player.setOnCompletionListener {
                current = null
                audio.abandonAudioFocusRequest(focusRequest)
                onDone()
            }
            player.seekTo(0)
            player.start()
            BridgeState.log("SYS", "playing '$id' (pre-rendered)")
            return
        }
        if (!ready) {
            BridgeState.log("ERR", "TTS not ready, cannot speak: $text")
            onDone(); return
        }
        val uid = "say:${counter++}"
        doneCallbacks[uid] = onDone
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, uid)
        BridgeState.log("SYS", "speaking with TTS: $text")
    }

    private fun stopCurrent() {
        current?.let { if (it.isPlaying) it.pause() }
        current = null
        if (ready) tts.stop()
    }

    private fun raiseVolume() {
        if (volumePercent <= 0) return
        try {
            val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            val target = ceil(max * volumePercent / 100.0).toInt().coerceIn(1, max)
            if (audio.getStreamVolume(AudioManager.STREAM_MUSIC) < target) {
                audio.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
            }
        } catch (e: Exception) {
            BridgeState.log("ERR", "could not raise volume: ${e.message}")
        }
    }

    /**
     * Android 17 silently mutes background audio unless our foreground service was
     * started from a visible screen. Audio focus is refused in exactly that case,
     * so its result tells us whether the phrase is really audible.
     */
    private fun requestFocus() {
        val granted = audio.requestAudioFocus(focusRequest) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        if (BridgeState.audioAllowed != granted) {
            BridgeState.audioAllowed = granted
            onChange()
        }
        if (!granted) {
            BridgeState.log("ERR", "Android refused audio focus: speech may be silent. Open the app once to re-arm.")
        }
    }

    private val progress = object : UtteranceProgressListener() {
        override fun onStart(utteranceId: String) {}
        override fun onDone(utteranceId: String) = finish(utteranceId, null)
        @Deprecated("Deprecated in Java")
        override fun onError(utteranceId: String) = finish(utteranceId, "error")
        override fun onError(utteranceId: String, errorCode: Int) = finish(utteranceId, "error $errorCode")
    }

    private fun finish(uid: String, error: String?) {
        main.post {
            renders.remove(uid)?.let { (id, text, file) ->
                if (error == null) load(id, text, file)
                else BridgeState.log("ERR", "rendering '$id' failed: $error (will use live TTS)")
                return@post
            }
            if (error != null) BridgeState.log("ERR", "TTS $error")
            audio.abandonAudioFocusRequest(focusRequest)
            doneCallbacks.remove(uid)?.invoke()
        }
    }

    fun shutdown() {
        stopCurrent()
        tts.shutdown()
        players.values.forEach { it.second.release() }
        players.clear()
        audio.abandonAudioFocusRequest(focusRequest)
    }
}
