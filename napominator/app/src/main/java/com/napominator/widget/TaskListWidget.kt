package com.napominator.widget

import android.content.Context
import android.content.Intent
import androidx.glance.*
import androidx.glance.action.actionStartActivity
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.provideContent
import androidx.glance.layout.*
import androidx.glance.text.*
import androidx.glance.unit.ColorProvider
import android.graphics.Color
import com.napominator.MainActivity
import com.napominator.data.db.AppDatabase
import kotlinx.coroutines.flow.first
import java.text.SimpleDateFormat
import java.util.*

/**
 * Виджет 2×4 — список активных задач на сегодня.
 * Использует Glance (Compose для виджетов).
 */
class TaskListWidget : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = TaskListGlanceWidget()
}

class TaskListGlanceWidget : GlanceAppWidget() {

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // Берём задачи напрямую из DAO (вне DI — в виджете нет Hilt)
        val db = AppDatabase.getInstance(context)
        val now = System.currentTimeMillis()
        val todayEnd = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 23); set(Calendar.MINUTE, 59); set(Calendar.SECOND, 59)
        }.timeInMillis

        val allActive = db.taskDao().getActiveTasks().first()
        val overdue = allActive.filter { it.reminderAt != null && it.reminderAt < now }
        val today = allActive.filter { it.reminderAt != null && it.reminderAt in now..todayEnd }
        val noDate = allActive.filter { it.reminderAt == null }

        // Показываем: просроченные + сегодняшние, максимум 7 штук
        val displayTasks = (overdue + today).take(7)
        val remaining = allActive.size - displayTasks.size

        provideContent {
            GlanceTheme {
                Column(
                    modifier = GlanceModifier
                        .fillMaxSize()
                        .background(GlanceTheme.colors.background)
                        .padding(8.dp)
                        .clickable(actionStartActivity<MainActivity>())
                ) {
                    // Заголовок
                    Text(
                        text = "Задачи",
                        style = TextStyle(
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp,
                            color = GlanceTheme.colors.onBackground
                        )
                    )
                    Spacer(GlanceModifier.height(4.dp))

                    if (displayTasks.isEmpty() && noDate.isEmpty()) {
                        Text(
                            text = "Нет задач на сегодня",
                            style = TextStyle(
                                fontSize = 12.sp,
                                color = GlanceTheme.colors.onBackground
                            )
                        )
                    } else {
                        displayTasks.forEach { task ->
                            val isOverdue = task.reminderAt != null && task.reminderAt < now
                            val timeStr = task.reminderAt?.let {
                                SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(it))
                            } ?: ""

                            Row(
                                modifier = GlanceModifier.fillMaxWidth().padding(vertical = 2.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "• ",
                                    style = TextStyle(
                                        fontSize = 11.sp,
                                        color = if (isOverdue)
                                            ColorProvider(Color.RED)
                                        else
                                            GlanceTheme.colors.onBackground
                                    )
                                )
                                Text(
                                    text = if (timeStr.isNotEmpty()) "$timeStr ${task.title}" else task.title,
                                    style = TextStyle(
                                        fontSize = 11.sp,
                                        color = if (isOverdue)
                                            ColorProvider(Color.RED)
                                        else
                                            GlanceTheme.colors.onBackground
                                    ),
                                    maxLines = 1
                                )
                            }
                        }

                        if (remaining > 0) {
                            Text(
                                text = "  … ещё $remaining →",
                                style = TextStyle(
                                    fontSize = 10.sp,
                                    color = GlanceTheme.colors.primary
                                )
                            )
                        }
                    }
                }
            }
        }
    }
}
