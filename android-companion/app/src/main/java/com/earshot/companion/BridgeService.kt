package com.earshot.companion

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import org.json.JSONException
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Foreground service that owns the bridge (WebSocket server or relay client),
 * the speaker, and the lock-screen notifications. Runs until stopped, including
 * while the phone is locked.
 */
class BridgeService : Service(), TransportListener {

    companion object {
        const val ACTION_START = "com.earshot.companion.START"
        const val ACTION_SPEAK = "com.earshot.companion.SPEAK"
        const val ACTION_SHOW_TYPE = "com.earshot.companion.SHOW_TYPE"
        const val ACTION_STOP = "com.earshot.companion.STOP"
        const val ACTION_DISMISS_ALERT = "com.earshot.companion.DISMISS_ALERT"
        const val EXTRA_REPLY = "reply"
        const val EXTRA_ALERT_ID = "alert_id"

        /** The glasses resend an active alert every 5 s; this long without one, it is treated as over. */
        private const val ALERT_TIMEOUT_MS = 15_000L

        @Volatile var instance: BridgeService? = null
            private set

        /** Call from a visible screen: Android 17 only lets a service started that way play audio in the background. */
        fun start(context: Context) {
            context.startForegroundService(Intent(context, BridgeService::class.java).setAction(ACTION_START))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, BridgeService::class.java).setAction(ACTION_STOP))
        }
    }

    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var prefs: Prefs
    private lateinit var speaker: Speaker
    private var transport: Transport? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var nextTypedId = 1
    private var typingPending: String? = null
    private val alertTimeout = Runnable {
        Alerts.active?.let { endAlert(it.id, "no update from the glasses for ${ALERT_TIMEOUT_MS / 1000} s") }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = Prefs(this)
        goForeground()
        BridgeState.serviceRunning = true
        BridgeState.log("SYS", "service started")
        speaker = Speaker(this) { refresh() }
        speaker.prepare(phraseTexts())
        // Keep the CPU awake so frames are handled promptly while the screen is off.
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Earshot:bridge")
            .apply { setReferenceCounted(false); acquire() }
        startBridge()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        goForeground()
        when (intent?.action) {
            null -> BridgeState.log("SYS", "service restarted by Android; open the app once so speech is allowed while locked")
            ACTION_STOP -> { stopSelf(); return START_NOT_STICKY }
            ACTION_SPEAK -> speakReply(intent.getStringExtra(EXTRA_REPLY), null, null, source = "notification")
            ACTION_SHOW_TYPE -> showTypeScreen()
            ACTION_DISMISS_ALERT -> dismissAlert(intent.getStringExtra(EXTRA_ALERT_ID))
        }
        return START_STICKY
    }

    override fun onDestroy() {
        BridgeState.log("SYS", "service stopped")
        main.removeCallbacks(alertTimeout)
        Alerts.active = null
        Notifications.cancelAlert(this)
        val t = transport
        transport = null
        io.execute { t?.shutdown() }
        io.shutdown()
        speaker.shutdown()
        wakeLock?.release()
        instance = null
        BridgeState.serviceRunning = false
        BridgeState.bridgeStatus = "stopped"
        BridgeState.clients = 0
        BridgeState.changed()
        super.onDestroy()
    }

    private fun goForeground() {
        try {
            startForeground(Notifications.ID_BRIDGE, Notifications.bridge(this, statusLine()),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } catch (e: Exception) {
            BridgeState.log("ERR", "could not start foreground: ${e.message}")
        }
    }

    private fun statusLine(): String {
        val who = when {
            BridgeState.clients == 1 -> "glasses connected"
            BridgeState.clients > 1 -> "${BridgeState.clients} clients connected"
            else -> "waiting for glasses"
        }
        val audio = if (BridgeState.audioAllowed == false) " · AUDIO BLOCKED: open app" else ""
        return "Bridge ${BridgeState.bridgeStatus} ($who)$audio"
    }

    /** Update the notification and the debug panel. */
    private fun refresh() {
        main.post {
            if (instance == null) return@post
            goForeground()
            BridgeState.changed()
        }
    }

    private fun phraseTexts() = Phrases.ALL.map { it.id to prefs.phraseText(it) }

    // ---- Bridge transport ----

    fun restartBridge() = startBridge()

    private fun startBridge() {
        val old = transport
        val t = if (prefs.mode == Prefs.MODE_RELAY) RelayClient(prefs.relayUrl, this)
        else LocalServer(prefs.bindHost, prefs.port, this)
        transport = t
        BridgeState.clients = 0
        io.execute {
            old?.shutdown()
            try { t.start() } catch (e: Exception) {
                onState("error: ${e.message}", "")
            }
        }
    }

    override fun onState(state: String, address: String) {
        BridgeState.bridgeStatus = state
        BridgeState.bridgeAddress = address
        BridgeState.log(if (state.startsWith("error")) "ERR" else "SYS", "bridge $state $address")
        refresh()
    }

    override fun onPeers(count: Int, note: String) {
        BridgeState.clients = count
        BridgeState.log("SYS", note)
        refresh()
    }

    override fun onText(text: String, reply: (String) -> Unit) {
        main.post { handle(text, reply) }
    }

    private fun send(reply: ((String) -> Unit)?, json: JSONObject) {
        val s = json.toString()
        BridgeState.log("OUT", s)
        reply?.invoke(s)
    }

    private fun broadcast(json: JSONObject, log: Boolean = true) {
        val s = json.toString()
        if (log) BridgeState.log("OUT", s)
        val t = transport ?: return
        if (io.isShutdown) return
        io.execute { try { t.sendToAll(s) } catch (e: Exception) { BridgeState.log("ERR", "send failed: ${e.message}") } }
    }

    /** Handle one incoming frame. Format: docs/BRIDGE.md. */
    private fun handle(text: String, reply: (String) -> Unit) {
        BridgeState.log("IN", text)
        val msg = try { JSONObject(text) } catch (e: JSONException) {
            send(reply, Protocol.error(null, "bad_json", "Frame is not a JSON object")); return
        }
        val id = msg.optString("id").ifEmpty { null }

        // PLAN.md compatibility: {"t":"say","phrase":"repeat"}
        if (msg.optString("t") == "say") {
            speakReply(msg.optString("phrase"), id, reply, source = "bridge")
            return
        }

        when (val type = msg.optString("type")) {
            "ping" -> send(reply, Protocol.pong(id, msg.opt("ts")))
            "hello" -> send(reply, Protocol.welcome(prefs, Protocol.status()))
            "get_status" -> send(reply, Protocol.status().apply { if (id != null) put("ref", id) })
            "speak" -> {
                val r = msg.optString("reply").ifEmpty { null }
                val custom = msg.optString("text").ifEmpty { null }
                when {
                    r != null -> speakReply(r, id, reply, source = "bridge",
                        showScreen = msg.optBoolean("show_type_screen", true))
                    custom != null -> {
                        send(reply, Protocol.ack(id, "speak"))
                        speaker.speak(null, custom) { send(reply, Protocol.spoken(id, null)) }
                    }
                    else -> send(reply, Protocol.error(id, "missing_field", "speak needs \"reply\" or \"text\""))
                }
            }
            "show_type_screen" -> { showTypeScreen(); send(reply, Protocol.ack(id, "show_type_screen")) }
            "hide_type_screen" -> { hideTypeScreen(); send(reply, Protocol.ack(id, "hide_type_screen")) }
            // No reply: it is resent every 5 s, and through the server nobody reads replies.
            "alert" -> receiveAlert(msg)
            // Our own message types echoed back by a relay, or replies from the other side: ignore.
            "pong", "ack", "status", "welcome", "spoken", "error", "typed_text", "typing" -> {}
            "" -> send(reply, Protocol.error(id, "missing_field", "Frame has no \"type\""))
            else -> send(reply, Protocol.error(id, "unknown_type", "Unknown type \"$type\""))
        }
    }

    // ---- Actions (from the bridge, the debug panel, or notification buttons) ----

    /** Speak a configured reply by id. Replies that ask the person to type also open the type page. */
    fun speakReply(raw: String?, ref: String?, reply: ((String) -> Unit)?, source: String, showScreen: Boolean = true) {
        val phrase = Phrases.resolve(raw)
        if (phrase == null) {
            send(reply, Protocol.error(ref, "unknown_reply",
                "Unknown reply \"$raw\". Known: ${Phrases.ALL.joinToString { it.id }}"))
            return
        }
        if (reply != null) send(reply, Protocol.ack(ref, "speak"))
        else BridgeState.log("SYS", "speak '${phrase.id}' from $source")
        if (phrase.opensTypeScreen && showScreen) showTypeScreen()
        speaker.speak(phrase.id, prefs.phraseText(phrase)) {
            if (reply != null) send(reply, Protocol.spoken(ref, phrase.id))
        }
    }

    fun showTypeScreen() {
        if (App.uiVisible) {
            // One of our screens is in front: open the page directly.
            startActivity(Intent(this, TypeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } else {
            // Phone locked or another app in front: the full-screen intent wakes the screen.
            Notifications.postTypeScreen(this)
        }
        BridgeState.log("SYS", "type screen requested")
    }

    fun hideTypeScreen() {
        Notifications.cancelTypeScreen(this)
        TypeActivity.current?.finish()
    }

    /** Called by the type page. Returns the number of connected peers it was sent to. */
    fun sendTypedText(text: String): Int {
        broadcast(Protocol.typedText("p${nextTypedId++}", text))
        return BridgeState.clients
    }

    /** Live preview while the person types, throttled to one frame per 300 ms. */
    fun sendTyping(text: String) {
        val first = typingPending == null
        typingPending = text
        if (!first) return
        main.postDelayed({
            val t = typingPending
            typingPending = null
            if (t != null) broadcast(Protocol.typing(t), log = false)
        }, 300)
    }

    fun onTypeScreenChanged() {
        broadcast(Protocol.status())
        refresh()
    }

    fun onPhrasesChanged() {
        speaker.prepare(phraseTexts())
        refresh()
    }

    // ---- Sound alerts: the glasses are flashing something, so ring like a call ----

    /** Handle an "alert" frame (docs/BRIDGE.md). Also called by the debug panel's test buttons. */
    fun receiveAlert(msg: JSONObject) {
        val id = msg.optString("id").ifEmpty { "alert" }
        if (!msg.optBoolean("active", true)) {
            endAlert(id, "sound stopped")
            return
        }
        main.removeCallbacks(alertTimeout)
        main.postDelayed(alertTimeout, ALERT_TIMEOUT_MS)
        val alert = Alert.from(msg)
        val prev = Alerts.active
        if (alert == prev) return // a refresh with nothing new
        val isNew = prev?.id != alert.id
        Alerts.active = alert
        Alerts.latest = alert
        if (isNew) BridgeState.log("SYS", "alert: ${alert.title} ${alert.where} (${alert.tier})")
        if (prefs.alertsEnabled && alert.id != Alerts.dismissedId) {
            // A new sound rings again; the same sound moving only updates the notification.
            Notifications.postAlert(this, alert, ring = isNew)
            if (isNew && App.uiVisible) {
                // One of our screens is in front, so the full-screen intent would only show a heads-up.
                startActivity(Intent(this, AlertActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
        }
        BridgeState.changed()
    }

    private fun endAlert(id: String, why: String) {
        val alert = Alerts.active ?: return
        if (alert.id != id) return // the end of an alert a newer one already replaced
        main.removeCallbacks(alertTimeout)
        Alerts.active = null
        Notifications.cancelAlert(this)
        BridgeState.log("SYS", "alert ended: ${alert.title} ($why)")
        BridgeState.changed()
    }

    /** The wearer dismissed the alert on the phone. Only the phone stops ringing; the glasses keep showing it. */
    fun dismissAlert(id: String?) {
        val alert = Alerts.latest ?: return
        if (id != null && alert.id != id) return
        Alerts.dismissedId = alert.id
        Notifications.cancelAlert(this)
        AlertActivity.current?.finish()
        BridgeState.log("SYS", "alert dismissed on the phone: ${alert.title}")
        BridgeState.changed()
    }
}
