package com.earshot.companion

import android.animation.ValueAnimator
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationAttributes
import android.os.VibrationEffect
import android.os.VibratorManager
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * "Incoming call" for a sound the glasses are flashing: what it is, where it came
 * from, and one big button per reply so the phone can answer out loud. Shown over
 * the lock screen without unlocking. Flashes and vibrates like the glasses do for
 * that tier (critical fast, medium slow) until the wearer touches a reply or the
 * sound stops.
 */
class AlertActivity : Activity() {

    companion object {
        /** Opened from the notification's Answer button or a tap, so it should not ring. */
        const val EXTRA_ANSWERED = "answered"
        /** After the sound stops, an untouched page closes itself after this long. */
        private const val CLOSE_AFTER_END_MS = 8_000L

        @Volatile var current: AlertActivity? = null
            private set
    }

    private lateinit var prefs: Prefs
    private lateinit var band: LinearLayout
    private lateinit var title: TextView
    private lateinit var where: TextView
    private lateinit var status: TextView
    private lateinit var said: TextView
    private val main = Handler(Looper.getMainLooper())
    private val listener: () -> Unit = { render() }
    private val vibrator by lazy { getSystemService(VibratorManager::class.java).defaultVibrator }
    private val closeLater = Runnable { if (!touched) finish() }

    private var shownId: String? = null
    private var shownActive = false
    /** The wearer pressed a reply: stop ringing and stay open. */
    private var touched = false
    private var ringingTier: String? = null
    private var flash: ValueAnimator? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        current = this
        prefs = Prefs(this)
        buildUi()
        takeIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeIntent(intent)
        render()
    }

    override fun onStart() {
        super.onStart()
        BridgeState.addListener(listener)
        render()
    }

    override fun onStop() {
        BridgeState.removeListener(listener)
        stopRinging()
        super.onStop()
    }

    override fun onDestroy() {
        if (current === this) current = null
        main.removeCallbacks(closeLater)
        stopRinging()
        super.onDestroy()
    }

    private fun takeIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(EXTRA_ANSWERED, false) == true) {
            shownId = Alerts.latest?.id
            touched = true
        }
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun tierColor(a: Alert) = Color.parseColor(if (a.critical) "#FF453A" else "#FF9F0A")
    private fun tierDim(a: Alert) = Color.parseColor(if (a.critical) "#4A0F0B" else "#4A2E03")

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
        }
        band = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(24))
        }
        band.addView(TextView(this).apply {
            text = "Your glasses are showing"
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        })
        title = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 40f)
            typeface = Typeface.DEFAULT_BOLD
        }
        band.addView(title)
        where = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f)
        }
        band.addView(where)
        status = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setPadding(0, dp(8), 0, 0)
        }
        band.addView(status)
        root.addView(band, LinearLayout.LayoutParams(-1, -2))

        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(12), dp(20), dp(16))
        }
        col.addView(TextView(this).apply {
            text = "Say out loud:"
            setTextColor(Color.parseColor("#BBBBBB"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setPadding(0, 0, 0, dp(4))
        })
        for (p in Phrases.ALL) {
            col.addView(Button(this).apply {
                text = "${p.label}\n“${prefs.phraseText(p)}”"
                isAllCaps = false
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                setTextColor(Color.BLACK)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
                setPadding(dp(16), dp(12), dp(16), dp(12))
                minHeight = dp(80)
                background = GradientDrawable().apply {
                    setColor(Color.parseColor("#FFD54F"))
                    cornerRadius = dp(14).toFloat()
                }
                setOnClickListener { speak(p) }
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
        }
        said = TextView(this).apply {
            setTextColor(Color.parseColor("#FFD54F"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setPadding(0, dp(10), 0, 0)
        }
        col.addView(said)
        col.addView(Button(this).apply {
            text = "Dismiss"
            isAllCaps = false
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            typeface = Typeface.DEFAULT_BOLD
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#C62828"))
                cornerRadius = dp(36).toFloat()
            }
            setOnClickListener { dismiss() }
        }, LinearLayout.LayoutParams(-1, dp(72)).apply { topMargin = dp(20) })

        val scroll = ScrollView(this).apply { isFillViewport = true; addView(col) }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        root.setOnApplyWindowInsetsListener { v, insets ->
            val b = insets.getInsets(WindowInsets.Type.systemBars())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsets.CONSUMED
        }
        setContentView(root)
    }

    private fun render() {
        val a = Alerts.latest
        if (a == null || a.id == Alerts.dismissedId) {
            finish()
            return
        }
        val active = Alerts.active?.id == a.id
        if (a.id != shownId) {
            // A different sound: ring again even if the last one was answered.
            shownId = a.id
            touched = false
            shownActive = false
            said.text = ""
        }
        title.text = a.title
        where.text = a.where
        where.visibility = if (a.where.isEmpty()) View.GONE else View.VISIBLE
        if (active) {
            main.removeCallbacks(closeLater)
            status.text = if (a.critical) "Happening now · critical" else "Happening now"
            if (touched) stopRinging(steady = a) else startRinging(a)
        } else {
            status.text = "The sound has stopped"
            stopRinging(steady = null)
            if (shownActive && !touched) main.postDelayed(closeLater, CLOSE_AFTER_END_MS)
        }
        shownActive = active
    }

    private fun startRinging(a: Alert) {
        if (ringingTier == a.tier) return
        stopRinging(steady = null)
        ringingTier = a.tier
        // Same rhythm as the glasses (plugin/src/hud.ts FLASH): critical 300 ms, medium 700 ms.
        flash = ValueAnimator.ofArgb(tierColor(a), tierDim(a)).apply {
            duration = if (a.critical) 300 else 700
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { band.setBackgroundColor(it.animatedValue as Int) }
            start()
        }
        val pattern = if (a.critical) longArrayOf(0, 500, 250) else longArrayOf(0, 400, 1200)
        val usage = if (a.critical) VibrationAttributes.USAGE_ALARM else VibrationAttributes.USAGE_RINGTONE
        vibrator.vibrate(VibrationEffect.createWaveform(pattern, 0), VibrationAttributes.createForUsage(usage))
    }

    /** Stop flashing and vibrating. With [steady], the band keeps that alert's colour, not flashing. */
    private fun stopRinging(steady: Alert? = null) {
        flash?.cancel()
        flash = null
        if (ringingTier != null) vibrator.cancel()
        ringingTier = null
        if (::band.isInitialized) band.setBackgroundColor(if (steady != null) tierDim(steady) else Color.parseColor("#2E2E2E"))
    }

    private fun speak(p: Phrase) {
        touched = true
        main.removeCallbacks(closeLater)
        render()
        val service = BridgeService.instance
        if (service == null) {
            said.text = "Not spoken: the Cue service is not running."
            return
        }
        service.speakReply(p.id, null, null, source = "alert screen")
        said.text = "Speaking: “${prefs.phraseText(p)}”"
    }

    private fun dismiss() {
        BridgeService.instance?.dismissAlert(shownId)
        finish()
    }
}
