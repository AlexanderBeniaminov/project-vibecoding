package com.napominator.alarm

import android.app.Service
import android.content.Intent
import android.os.IBinder

// TODO: Этап 6 — полная реализация Foreground Service
class ReminderForegroundService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int =
        START_STICKY
}
