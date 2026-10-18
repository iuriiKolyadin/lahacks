package com.earshot.companion

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.util.TypedValue
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.net.Inet4Address
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Debug panel: bridge status, message log, manual triggers, permission checklist and settings. */
class MainActivity : Activity() {

    private companion object {
        const val REQ_NOTIFICATIONS = 1
        const val REQ_LOCAL_NETWORK = 2
        const val LOCAL_NETWORK = "android.permission.ACCESS_LOCAL_NETWORK"
    }

    private lateinit var prefs: Prefs
    private lateinit var statusText: TextView
    private lateinit var checklist: LinearLayout
    private lateinit var logText: TextView
    private val main = Handler(Looper.getMainLooper())
    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.US)
    private val listener: () -> Unit = { render() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        buildUi()
        // Started from a visible screen, so Android 17 lets the service play audio while locked.
        BridgeService.start(this)
    }

    override fun onStart() {
        super.onStart()
        BridgeState.addListener(listener)
        render()
    }

    override fun onResume() {
        super.onResume()
        // Re-arm in case Android restarted the service in the background.
        if (BridgeState.serviceRunning) BridgeService.start(this)
        render()
    }

    override fun onStop() {
        BridgeState.removeListener(listener)
        super.onStop()
    }

    // ---- UI building ----

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun header(parent: LinearLayout, text: String) {
        parent.addView(TextView(this).apply {
            this.text = text
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
            typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(20), 0, dp(6))
        })
    }

    private fun button(parent: LinearLayout, text: String, onClick: () -> Unit): Button =
        Button(this).apply {
            this.text = text
            isAllCaps = false
            setOnClickListener { onClick() }
        }.also { parent.addView(it, LinearLayout.LayoutParams(-1, -2)) }

    private fun field(parent: LinearLayout, label: String, value: String, type: Int = InputType.TYPE_CLASS_TEXT): EditText {
        parent.addView(TextView(this).apply { text = label; setPadding(0, dp(6), 0, 0) })
        return EditText(this).apply {
            setText(value)
            inputType = type
        }.also { parent.addView(it, LinearLayout.LayoutParams(-1, -2)) }
    }

    private fun buildUi() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(24))
        }
        col.addView(TextView(this).apply {
            text = "Earshot Companion"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 26f)
            typeface = Typeface.DEFAULT_BOLD
        })

        header(col, "Status")
        statusText = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setTextIsSelectable(true)
        }
        col.addView(statusText)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(Button(this).apply { text = "Start"; setOnClickListener { BridgeService.start(this@MainActivity) } },
            LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(Button(this).apply { text = "Stop"; setOnClickListener { BridgeService.stop(this@MainActivity) } },
            LinearLayout.LayoutParams(0, -2, 1f))
        col.addView(row)

        header(col, "Permissions checklist")
        checklist = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(checklist)

        header(col, "Test by hand")
        Phrases.ALL.forEach { p ->
            button(col, "Speak: ${p.label}") { withService { it.speakReply(p.id, null, null, source = "debug button") } }
        }
        button(col, "Show type screen") { withService { it.showTypeScreen() } }
        button(col, "Show type screen in 5 s (lock the phone now)") {
            Toast.makeText(this, "Lock the phone now", Toast.LENGTH_SHORT).show()
            main.postDelayed({ BridgeService.instance?.showTypeScreen() }, 5000)
        }
        button(col, "Speak \"Thank you\" in 5 s (lock the phone now)") {
            Toast.makeText(this, "Lock the phone now", Toast.LENGTH_SHORT).show()
            main.postDelayed({ BridgeService.instance?.speakReply("thanks", null, null, source = "delayed debug button") }, 5000)
        }
        button(col, "Send test typed text to glasses") { withService { it.sendTypedText("Test message from the phone") } }

        header(col, "Messages (newest first)")
        logText = TextView(this).apply {
            typeface = Typeface.MONOSPACE
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
            setTextIsSelectable(true)
        }
        col.addView(logText)

        header(col, "Phrases")
        val phraseFields = Phrases.ALL.map { p -> p to field(col, "${p.label} (id: ${p.id})", prefs.phraseText(p),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES) }
        button(col, "Save phrases") {
            phraseFields.forEach { (p, f) -> prefs.setPhraseText(p, f.text.toString()) }
            phraseFields.forEach { (p, f) -> f.setText(prefs.phraseText(p)) }
            BridgeService.instance?.onPhrasesChanged()
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
        }

        header(col, "Connection")
        val modeGroup = RadioGroup(this)
        val rServer = RadioButton(this).apply { id = View.generateViewId(); text = "Phone hosts the bridge (glasses app connects to the phone)" }
        val rRelay = RadioButton(this).apply { id = View.generateViewId(); text = "Connect to a laptop relay" }
        modeGroup.addView(rServer); modeGroup.addView(rRelay)
        modeGroup.check(if (prefs.mode == Prefs.MODE_RELAY) rRelay.id else rServer.id)
        col.addView(modeGroup)
        val host = field(col, "Listen address (127.0.0.1 = this phone only, 0.0.0.0 = whole Wi-Fi)", prefs.bindHost)
        val port = field(col, "Port", prefs.port.toString(), InputType.TYPE_CLASS_NUMBER)
        val relay = field(col, "Relay URL (laptop mode)", prefs.relayUrl, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI)
        val volume = field(col, "Raise media volume to at least this % before speaking (0 = don't touch)",
            prefs.volumePercent.toString(), InputType.TYPE_CLASS_NUMBER)
        button(col, "Apply and restart bridge") {
            prefs.mode = if (modeGroup.checkedRadioButtonId == rRelay.id) Prefs.MODE_RELAY else Prefs.MODE_SERVER
            prefs.bindHost = host.text.toString().trim().ifEmpty { "127.0.0.1" }
            prefs.port = port.text.toString().toIntOrNull() ?: Prefs.DEFAULT_PORT
            prefs.relayUrl = relay.text.toString().trim()
            prefs.volumePercent = volume.text.toString().toIntOrNull() ?: 100
            BridgeService.instance?.restartBridge() ?: BridgeService.start(this)
            Toast.makeText(this, "Bridge restarting", Toast.LENGTH_SHORT).show()
        }

        val scroll = ScrollView(this).apply { addView(col) }
        scroll.setOnApplyWindowInsetsListener { v, insets ->
            val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsets.CONSUMED
        }
        setContentView(scroll)
    }

    private fun withService(action: (BridgeService) -> Unit) {
        val s = BridgeService.instance
        if (s == null) {
            BridgeService.start(this)
            Toast.makeText(this, "Service was not running; starting it. Try again.", Toast.LENGTH_SHORT).show()
        } else action(s)
    }

    // ---- Rendering ----

    private fun render() {
        val audio = when (BridgeState.audioAllowed) {
            true -> "allowed"
            false -> "BLOCKED by Android (tap Start)"
            null -> "not tested yet (speak once)"
        }
        statusText.text = buildString {
            appendLine("Service: ${if (BridgeState.serviceRunning) "running" else "stopped"}")
            appendLine("Bridge: ${BridgeState.bridgeStatus} ${BridgeState.bridgeAddress}")
            appendLine("Connected clients: ${BridgeState.clients}")
            appendLine("Text-to-speech: ${BridgeState.ttsStatus}")
            appendLine("Audio while locked: $audio")
            appendLine("Type screen: ${if (BridgeState.typeScreenOpen) "open" else "closed"}")
            appendLine("Phone Wi-Fi IP: ${wifiIp() ?: "none"}")
            appendLine("Last in: ${BridgeState.lastIn ?: "-"}")
            append("Last out: ${BridgeState.lastOut ?: "-"}")
        }
        logText.text = BridgeState.snapshot().take(40).joinToString("\n") {
            "${timeFmt.format(Date(it.time))} ${it.kind.padEnd(3)} ${it.text}"
        }
        renderChecklist()
    }

    private data class Check(val label: String, val ok: Boolean, val note: String, val fixLabel: String, val fix: () -> Unit)

    private fun checks(): List<Check> {
        val nm = getSystemService(NotificationManager::class.java)
        val pm = getSystemService(PowerManager::class.java)
        val am = getSystemService(AudioManager::class.java)
        val notifPerm = checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        val list = mutableListOf<Check>()

        list += Check("Notifications allowed", notifPerm && nm.areNotificationsEnabled(), "", "Allow") {
            if (!notifPerm) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFICATIONS)
            else openSettings(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }
        val bridgeCh = nm.getNotificationChannel(Notifications.CHANNEL_BRIDGE)
        list += Check("Quick-reply notification on", bridgeCh != null && bridgeCh.importance >= NotificationManager.IMPORTANCE_DEFAULT,
            "shows on lock screen", "Open") { openChannel(Notifications.CHANNEL_BRIDGE) }
        val typeCh = nm.getNotificationChannel(Notifications.CHANNEL_TYPE)
        list += Check("Type-screen alerts on", typeCh != null && typeCh.importance >= NotificationManager.IMPORTANCE_HIGH,
            "", "Open") { openChannel(Notifications.CHANNEL_TYPE) }
        list += Check("Full-screen page over lock screen", nm.canUseFullScreenIntent(), "", "Allow") {
            openSettings(Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:$packageName")))
        }
        list += Check("Battery: unrestricted", pm.isIgnoringBatteryOptimizations(packageName),
            "keeps running when locked", "Allow") {
            openSettings(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        }
        if (Build.VERSION.SDK_INT >= 37) {
            list += Check("Local network", checkSelfPermission(LOCAL_NETWORK) == PackageManager.PERMISSION_GRANTED,
                "only for laptop relay / Wi-Fi test client", "Allow") {
                requestPermissions(arrayOf(LOCAL_NETWORK), REQ_LOCAL_NETWORK)
            }
        }
        list += Check("Text-to-speech ready", BridgeState.ttsStatus == "ready", BridgeState.ttsStatus, "Settings") {
            openSettings(Intent("com.android.settings.TTS_SETTINGS"))
        }
        list += Check("Service running, audio allowed", BridgeState.serviceRunning && BridgeState.audioAllowed != false,
            "", "Start") { BridgeService.start(this) }
        val vol = am.getStreamVolume(AudioManager.STREAM_MUSIC)
        val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        list += Check("Media volume loud ($vol/$max)", vol * 10 >= max * 7, "raised automatically when speaking", "Max") {
            am.setStreamVolume(AudioManager.STREAM_MUSIC, max, AudioManager.FLAG_SHOW_UI)
            render()
        }
        return list
    }

    private fun renderChecklist() {
        checklist.removeAllViews()
        for (c in checks()) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dp(2), 0, dp(2))
            }
            row.addView(TextView(this).apply {
                text = (if (c.ok) "✅  " else "❌  ") + c.label + if (c.note.isNotEmpty()) "\n      ${c.note}" else ""
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
                if (!c.ok) setTextColor(Color.parseColor("#D32F2F"))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            if (!c.ok) {
                row.addView(Button(this).apply {
                    text = c.fixLabel
                    isAllCaps = false
                    setOnClickListener { c.fix() }
                })
            }
            checklist.addView(row)
        }
    }

    private fun openChannel(id: String) = openSettings(
        Intent(Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
            .putExtra(Settings.EXTRA_CHANNEL_ID, id)
    )

    private fun openSettings(intent: Intent) {
        try { startActivity(intent) } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.isNotEmpty() && grantResults[0] != PackageManager.PERMISSION_GRANTED &&
            !shouldShowRequestPermissionRationale(permissions[0])) {
            // Denied for good: the only way left is the settings page.
            openSettings(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
        if (requestCode == REQ_NOTIFICATIONS) BridgeService.start(this)
        render()
    }

    private fun wifiIp(): String? {
        val cm = getSystemService(ConnectivityManager::class.java)
        return cm.allNetworks.asSequence()
            .mapNotNull { cm.getLinkProperties(it) }
            .flatMap { it.linkAddresses.asSequence() }
            .map { it.address }
            .filterIsInstance<Inet4Address>()
            .firstOrNull { !it.isLoopbackAddress && it.isSiteLocalAddress }
            ?.hostAddress
    }
}
