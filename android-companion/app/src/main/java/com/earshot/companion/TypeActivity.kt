package com.earshot.companion

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.TypedValue
import android.view.Gravity
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * "I'm Deaf. Please type here." Shown over the lock screen without unlocking,
 * like an incoming call. What the other person types is sent to the glasses.
 */
class TypeActivity : Activity() {

    companion object {
        @Volatile var current: TypeActivity? = null
            private set
    }

    private lateinit var input: EditText
    private lateinit var status: TextView
    private lateinit var history: TextView
    private val sent = mutableListOf<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        current = this
        Notifications.cancelTypeScreen(this)
        buildUi()
        BridgeState.typeScreenOpen = true
        BridgeState.log("SYS", "type screen opened")
        BridgeService.instance?.onTypeScreenChanged()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Notifications.cancelTypeScreen(this)
        focusInput()
    }

    override fun onResume() {
        super.onResume()
        focusInput()
    }

    override fun onDestroy() {
        if (current === this) current = null
        BridgeState.typeScreenOpen = false
        BridgeState.log("SYS", "type screen closed")
        BridgeService.instance?.onTypeScreenChanged()
        super.onDestroy()
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun buildUi() {
        val yellow = Color.parseColor("#FFD54F")
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
        }
        val scroll = ScrollView(this).apply { isFillViewport = true }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(16))
        }
        col.addView(TextView(this).apply {
            text = "I'm Deaf.\nPlease type here"
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 40f)
            typeface = Typeface.DEFAULT_BOLD
        })
        col.addView(TextView(this).apply {
            text = "Your words appear on my glasses."
            setTextColor(Color.parseColor("#BBBBBB"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setPadding(0, dp(6), 0, dp(14))
        })
        input = EditText(this).apply {
            hint = "Type here…"
            setHintTextColor(Color.parseColor("#888888"))
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            minLines = 3
            gravity = Gravity.TOP or Gravity.START
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or
                InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_AUTO_CORRECT
            imeOptions = EditorInfo.IME_ACTION_SEND
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#222222"))
                setStroke(dp(2), yellow)
                cornerRadius = dp(10).toFloat()
            }
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    BridgeService.instance?.sendTyping(s?.toString().orEmpty())
                }
            })
        }
        col.addView(input, LinearLayout.LayoutParams(-1, -2))
        col.addView(Button(this).apply {
            text = "Send"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.BLACK)
            background = GradientDrawable().apply {
                setColor(yellow)
                cornerRadius = dp(12).toFloat()
            }
            setOnClickListener { send() }
        }, LinearLayout.LayoutParams(-1, dp(72)).apply { topMargin = dp(14) })
        status = TextView(this).apply {
            setTextColor(yellow)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
            setPadding(0, dp(10), 0, dp(4))
        }
        col.addView(status)
        history = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
        }
        col.addView(history)
        col.addView(Button(this).apply {
            text = "Done"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(16); gravity = Gravity.END })
        scroll.addView(col)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        root.setOnApplyWindowInsetsListener { v, insets ->
            val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsets.CONSUMED
        }
        setContentView(root)
    }

    private fun focusInput() {
        input.requestFocus()
        input.postDelayed({ window.insetsController?.show(WindowInsets.Type.ime()) }, 250)
    }

    private fun send() {
        val text = input.text.toString().trim()
        if (text.isEmpty()) return
        val service = BridgeService.instance
        if (service == null) {
            status.text = "Not sent: the Cue service is not running."
            return
        }
        val peers = service.sendTypedText(text)
        status.text = if (peers > 0) "Sent ✓" else "Saved, but the glasses are not connected."
        sent.add(0, text)
        history.text = sent.joinToString("\n\n") { "“$it”" }
        input.setText("")
    }
}
