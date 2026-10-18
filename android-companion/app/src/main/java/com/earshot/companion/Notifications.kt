package com.earshot.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon

object Notifications {
    /** Ongoing service notification. Also the fallback: its buttons speak the phrases from the lock screen. */
    const val CHANNEL_BRIDGE = "bridge"
    /** High-priority alert whose full-screen intent opens the type page over the lock screen. */
    const val CHANNEL_TYPE = "type_screen"

    const val ID_BRIDGE = 1
    const val ID_TYPE = 2

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
}
