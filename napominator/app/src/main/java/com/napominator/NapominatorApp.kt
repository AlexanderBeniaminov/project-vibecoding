package com.napominator

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class NapominatorApp : Application() {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)

            // Обычные напоминания
            val reminderChannel = NotificationChannel(
                CHANNEL_REMINDER,
                "Напоминания",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Уведомления о задачах"
                enableVibration(true)
            }

            // Настойчивые повторяющиеся напоминания
            val persistentChannel = NotificationChannel(
                CHANNEL_PERSISTENT,
                "Настойчивые напоминания",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Повторяющиеся уведомления пока задача не выполнена"
                enableVibration(true)
            }

            // Фоновый сервис (можно скрыть)
            val serviceChannel = NotificationChannel(
                CHANNEL_SERVICE,
                "Фоновая работа",
                NotificationManager.IMPORTANCE_MIN
            ).apply {
                description = "Служебное уведомление для стабильной работы напоминаний"
                setShowBadge(false)
            }

            // Утренняя сводка
            val summaryChannel = NotificationChannel(
                CHANNEL_SUMMARY,
                "Сводка дня",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Утренний список задач на день"
            }

            manager.createNotificationChannels(
                listOf(reminderChannel, persistentChannel, serviceChannel, summaryChannel)
            )
        }
    }

    companion object {
        const val CHANNEL_REMINDER = "channel_reminder"
        const val CHANNEL_PERSISTENT = "channel_persistent"
        const val CHANNEL_SERVICE = "channel_service"
        const val CHANNEL_SUMMARY = "channel_summary"
    }
}
