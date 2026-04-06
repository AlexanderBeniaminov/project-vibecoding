package com.napominator.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

// TODO: Этап 6 — перепланировать будильники и геофенсы после перезагрузки
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == "android.intent.action.QUICKBOOT_POWERON") {
            // Будет реализовано в Этапе 6
        }
    }
}
