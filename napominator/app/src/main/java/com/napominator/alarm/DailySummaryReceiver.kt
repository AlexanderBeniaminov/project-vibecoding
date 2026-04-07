package com.napominator.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.napominator.notification.DailySummaryBuilder
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Получает будильник от DailySummaryScheduler → показывает утреннюю сводку
 * и перепланирует следующую сводку на завтра.
 */
@AndroidEntryPoint
class DailySummaryReceiver : BroadcastReceiver() {

    @Inject lateinit var dailySummaryBuilder: DailySummaryBuilder
    @Inject lateinit var dailySummaryScheduler: DailySummaryScheduler

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != DailySummaryScheduler.ACTION_DAILY_SUMMARY) return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                dailySummaryBuilder.showSummary()
                // Перепланируем на следующий день
                dailySummaryScheduler.scheduleNext()
            } finally {
                pendingResult.finish()
            }
        }
    }
}
