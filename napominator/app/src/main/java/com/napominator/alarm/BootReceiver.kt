package com.napominator.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.napominator.data.repository.TaskRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Перепланирует все активные будильники после перезагрузки устройства.
 * Важно для Huawei — AlarmManager сбрасывается при каждой перезагрузке.
 */
@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {

    @Inject lateinit var taskRepository: TaskRepository
    @Inject lateinit var alarmScheduler: AlarmScheduler

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != "android.intent.action.QUICKBOOT_POWERON") return

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Перепланировать все будущие задачи с напоминанием
                val tasks = taskRepository.getFutureAlarmTasks()
                tasks.forEach { task -> alarmScheduler.schedule(task) }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
