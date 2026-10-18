package com.earshot.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Person
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon

object Notifications {
    /** Ongoing service notification. Also the fallback: its buttons speak the phrases from the lock screen. */
    const val CHANNEL_BRIDGE = "bridge"
    /** High-priority alert whose full-screen intent opens the type page over the lock screen. */
    const val CHANNEL_TYPE = "type_screen"
    /** Call-style alert for a sound the glasses are flashing; its full-screen intent opens the alert page. */
    const val CHANNEL_ALERT = "sound_alert"

    const val ID_BRIDGE = 1
    const val ID_TYPE = 2
    const val ID_ALERT = 3

    fun ensureChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_BRIDGE, "Quick replies (lock screen)", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Always-on notification with buttons that speak your replies."
                setSound(null, null)
                enableVibration(false)
                setShowBadge(false)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_TYPE, "Type-to-me page", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Wakes the screen and shows the \"Please type here\" page."
                setSound(null, null)
                enableVibration(false)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ALERT, "Sound alerts (rings like a call)", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Shows what your glasses are flashing, like an incoming call, with buttons that speak your replies."
                // Silent but vibrating: the wearer feels it, the room does not hear it.
                setSound(null, null)
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 600, 300, 600, 300, 600)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
        )
    }

    fun bridge(context: Context, status: String): Notification {
        val prefs = Prefs(context)
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val icon = Icon.createWithResource(context, R.drawable.ic_stat_earshot)
        val builder = Notification.Builder(context, CHANNEL_BRIDGE)
            .setSmallIcon(R.drawable.ic_stat_earshot)
            .setContentTitle("Earshot: tap a button to speak")
            .setContentText(status)
            .setStyle(Notification.BigTextStyle().bigText(
                status + "\n" + Phrases.ALL.joinToString("\n") { "• ${it.label}: ${prefs.phraseText(it)}" }))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setCategory(Notification.CATEGORY_SERVICE)
            .setContentIntent(open)
            .setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
        Phrases.ALL.forEachIndexed { i, p ->
            val speak = PendingIntent.getForegroundService(
                context, 100 + i,
                Intent(context, BridgeService::class.java)
                    .setAction(BridgeService.ACTION_SPEAK)
                    .putExtra(BridgeService.EXTRA_REPLY, p.id),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            builder.addAction(Notification.Action.Builder(icon, p.label, speak).build())
        }
        return builder.build()
    }

    fun postTypeScreen(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        val show = PendingIntent.getActivity(
            context, 10,
            Intent(context, TypeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val n = Notification.Builder(context, CHANNEL_TYPE)
            .setSmallIcon(R.drawable.ic_stat_earshot)
            .setContentTitle("I'm Deaf. Please type here")
            .setContentText("Tap to type a message for me.")
            .setCategory(Notification.CATEGORY_CALL)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setFullScreenIntent(show, true)
            .setContentIntent(show)
            .setAutoCancel(true)
            .setTimeoutAfter(120_000)
            .build()
        // Cancel first so a repeat request fires the full-screen intent again.
        nm.cancel(ID_TYPE)
        nm.notify(ID_TYPE, n)
        if (!nm.canUseFullScreenIntent()) {
            BridgeState.log("ERR", "Full-screen intent not allowed: only a heads-up notification will show. Fix it in the permissions list.")
        }
    }

    fun cancelTypeScreen(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(ID_TYPE)
    }

    /**
     * Incoming-call notification for [alert]: the sound is the caller, Answer opens
     * the reply page, Decline dismisses. Locked or screen off, the full-screen intent
     * opens the reply page straight away. [ring] re-posts so a new sound alerts again;
     * otherwise the notification updates silently (the same sound changed direction).
     */
    fun postAlert(context: Context, alert: Alert, ring: Boolean) {
        val nm = context.getSystemService(NotificationManager::class.java)
        val show = PendingIntent.getActivity(
            context, 20,
            Intent(context, AlertActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        // Separate request code and extra: opened by a tap, so the page should not vibrate.
        val answer = PendingIntent.getActivity(
            context, 21,
            Intent(context, AlertActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                .putExtra(AlertActivity.EXTRA_ANSWERED, true),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val dismiss = PendingIntent.getForegroundService(
            context, 22,
            Intent(context, BridgeService::class.java)
                .setAction(BridgeService.ACTION_DISMISS_ALERT)
                .putExtra(BridgeService.EXTRA_ALERT_ID, alert.id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val icon = Icon.createWithResource(context, R.drawable.ic_stat_earshot)
        val builder = Notification.Builder(context, CHANNEL_ALERT)
            .setSmallIcon(R.drawable.ic_stat_earshot)
            .setContentTitle(alert.title)
            .setContentText(alert.where.ifEmpty { "Your glasses are showing this now" })
            .setCategory(Notification.CATEGORY_CALL)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setContentIntent(answer)
            .setFullScreenIntent(show, true)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        if (nm.canUseFullScreenIntent()) {
            val caller = Person.Builder().setName(alert.title).setIcon(icon).setImportant(true).build()
            builder.setStyle(Notification.CallStyle.forIncomingCall(caller, dismiss, answer))
        } else {
            // CallStyle needs the full-screen permission; a plain heads-up with the same two buttons still works.
            builder.addAction(Notification.Action.Builder(icon, "Dismiss", dismiss).build())
                .addAction(Notification.Action.Builder(icon, "Reply", answer).build())
            BridgeState.log("ERR", "Full-screen intent not allowed: sound alerts show as a heads-up only. Fix it in the permissions list.")
        }
        // Cancel first so a new sound alerts (and fires the full-screen intent) again.
        if (ring) nm.cancel(ID_ALERT)
        nm.notify(ID_ALERT, builder.build())
    }

    fun cancelAlert(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(ID_ALERT)
    }
}
