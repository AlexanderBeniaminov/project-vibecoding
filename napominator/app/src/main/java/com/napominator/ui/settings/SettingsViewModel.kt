package com.napominator.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.napominator.alarm.DailySummaryScheduler
import com.napominator.data.prefs.AppPreferences
import com.napominator.data.repository.TaskRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val prefs: AppPreferences,
    private val taskRepository: TaskRepository,
    private val dailySummaryScheduler: DailySummaryScheduler
) : ViewModel() {

    val quietHoursEnabled = prefs.quietHoursEnabled.stateIn(viewModelScope, SharingStarted.Eagerly, false)
    val quietHoursStart = prefs.quietHoursStart.stateIn(viewModelScope, SharingStarted.Eagerly, 1380)
    val quietHoursEnd = prefs.quietHoursEnd.stateIn(viewModelScope, SharingStarted.Eagerly, 480)
    val snoozeInterval = prefs.defaultSnoozeInterval.stateIn(viewModelScope, SharingStarted.Eagerly, 0)
    val snoozeMax = prefs.defaultSnoozeMax.stateIn(viewModelScope, SharingStarted.Eagerly, 5)
    val morningTime = prefs.morningTime.stateIn(viewModelScope, SharingStarted.Eagerly, 540)
    val eveningTime = prefs.eveningTime.stateIn(viewModelScope, SharingStarted.Eagerly, 1080)
    val confirmTimer = prefs.confirmTimerSeconds.stateIn(viewModelScope, SharingStarted.Eagerly, 8)
    val recordModeToggle = prefs.recordModeToggle.stateIn(viewModelScope, SharingStarted.Eagerly, false)
    val asrEngine = prefs.asrEngine.stateIn(viewModelScope, SharingStarted.Eagerly, "auto")
    val dailySummaryEnabled = prefs.dailySummaryEnabled.stateIn(viewModelScope, SharingStarted.Eagerly, true)
    val dailySummaryTime = prefs.dailySummaryTime.stateIn(viewModelScope, SharingStarted.Eagerly, 480)

    fun setQuietHoursEnabled(enabled: Boolean) = viewModelScope.launch {
        prefs.setQuietHoursEnabled(enabled)
    }

    fun setQuietHours(startMinutes: Int, endMinutes: Int) = viewModelScope.launch {
        prefs.setQuietHours(startMinutes, endMinutes)
    }

    fun setSnooze(intervalMinutes: Int, maxCount: Int) = viewModelScope.launch {
        prefs.setDefaultSnooze(intervalMinutes, maxCount)
    }

    fun setMorningTime(minutes: Int) = viewModelScope.launch {
        prefs.setMorningTime(minutes)
    }

    fun setEveningTime(minutes: Int) = viewModelScope.launch {
        prefs.setEveningTime(minutes)
    }

    fun setConfirmTimer(seconds: Int) = viewModelScope.launch {
        prefs.setConfirmTimerSeconds(seconds)
    }

    fun setRecordMode(toggle: Boolean) = viewModelScope.launch {
        prefs.setRecordModeToggle(toggle)
    }

    fun setAsrEngine(engine: String) = viewModelScope.launch {
        prefs.setAsrEngine(engine)
    }

    fun setDailySummary(enabled: Boolean, timeMinutes: Int) = viewModelScope.launch {
        prefs.setDailySummary(enabled, timeMinutes)
        if (enabled) dailySummaryScheduler.scheduleNext()
        else dailySummaryScheduler.cancel()
    }

    fun deleteCompleted() = viewModelScope.launch {
        taskRepository.deleteCompleted()
    }
}
